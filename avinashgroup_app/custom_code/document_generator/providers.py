# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Data for the Document Generator.

A template's data comes entirely from its **Custom Data Sources** — admin-authored
SQL / Python that run with the user's inputs and expose each result to the document
as ``data.<source_name>.rows`` and ``data.<source_name>.row.<column>``.
"""

import re

import frappe
from frappe import _
from frappe.utils import nowdate
from frappe.utils.safe_exec import safe_exec

from avinashgroup_app.avinash_group_app.report.party_ledger.party_ledger import _fmt_inr


class _Any:
	"""Permissive placeholder: any attribute/item access, iteration, call or
	string/number coercion is safe. Used to validate/preview admin templates
	without the real data (which only exists at generation time)."""

	def __getattr__(self, _k):
		return _ANY

	def __getitem__(self, _k):
		return _ANY

	def __iter__(self):
		return iter([])

	def __call__(self, *a, **k):
		return _ANY

	def __str__(self):
		return ""

	def __html__(self):
		return ""

	def __float__(self):
		return 0.0

	def __int__(self):
		return 0


_ANY = _Any()


class _EmptySource:
	"""Stub for ``data.<name>``: ``.rows`` is an empty list (loops run zero times),
	``.row`` and anything else coerces to blank."""

	def __getattr__(self, k):
		if k == "rows":
			return []
		return _ANY


class _EmptyData:
	"""Stub for ``data`` — any source name resolves to an _EmptySource."""

	def __getattr__(self, _k):
		return _EMPTY_SOURCE

	def __getitem__(self, _k):
		return _EMPTY_SOURCE


_EMPTY_SOURCE = _EmptySource()
_EMPTY_DATA = _EmptyData()


def stub_context():
	"""A permissive Jinja context for validating/previewing a template (no real data)."""
	return {
		"doc": _ANY,
		"company": "",
		"data": _EMPTY_DATA,
		"inputs": _ANY,
		"org": _ANY,
		"today": nowdate(),
		"today_bs": bs(),
		"bs": bs,
		"user": current_user_info(),
		"fmt": _fmt_inr,
		"money": money,
		"letter_head_html": "",
	}


def image_data_uri(file_url):
	"""Embed an attached image as a base64 data URI (reliable in the PDF). Falls back
	to the URL if it can't be read."""
	if not file_url:
		return ""
	if file_url.startswith("data:"):
		return file_url
	# Embed as data URI; return "" (not the URL) on failure so we never show a broken image.
	try:
		import base64
		import mimetypes

		f = frappe.get_all("File", filters={"file_url": file_url}, limit=1, pluck="name")
		if not f:
			return ""
		content = frappe.get_doc("File", f[0]).get_content()
		if isinstance(content, str):
			content = content.encode()
		mime = mimetypes.guess_type(file_url)[0] or "image/png"
		return "data:%s;base64,%s" % (mime, base64.b64encode(content).decode())
	except Exception:
		return ""


def current_user_info():
	"""Name, designation and signature image of the logged-in user (for signatures)."""
	user = frappe.session.user
	full_name = frappe.db.get_value("User", user, "full_name") or user
	designation = signature = ""
	fields = ["designation", "employee_name"]
	if frappe.db.has_column("Employee", "custom_signature_image"):
		fields.append("custom_signature_image")
	emp = frappe.db.get_value("Employee", {"user_id": user}, fields, as_dict=True)
	if emp:
		designation = emp.get("designation") or ""
		full_name = emp.get("employee_name") or full_name
		signature = image_data_uri(emp.get("custom_signature_image"))
	return frappe._dict(
		{"name": user, "full_name": full_name, "designation": designation, "signature": signature}
	)


def company_info(company):
	"""Company name, VAT (tax_id), logo and stamp (images as data URIs)."""
	if not company:
		return frappe._dict()
	std = frappe.db.get_value(
		"Company", company, ["company_name", "tax_id", "company_logo"], as_dict=True
	) or frappe._dict()
	stamp = ""
	if frappe.db.has_column("Company", "custom_document_stamp"):
		stamp = frappe.db.get_value("Company", company, "custom_document_stamp")
	return frappe._dict(
		{
			"name": company,
			"company_name": std.get("company_name") or company,
			"vat": std.get("tax_id") or "",
			"logo": image_data_uri(std.get("company_logo")),
			"stamp": image_data_uri(stamp),
		}
	)


def money(v):
	"""Format an amount with 2 decimals, showing 0.00 for zero/empty (unlike ``fmt``
	which blanks zeros for ledgers)."""
	return _fmt_inr(v) or "0.00"


def bs(d=None):
	"""Convert a Gregorian date to a Nepali (BS) date string ``YYYY/MM/DD``."""
	try:
		import nepali_datetime
		from frappe.utils import getdate

		nd = nepali_datetime.date.today() if not d else nepali_datetime.date.from_datetime_date(getdate(d))
		return nd.strftime("%Y/%m/%d")
	except Exception:
		return frappe.utils.cstr(d or nowdate())


def _base_context(extra=None):
	"""Common, safe context. Never expose raw ``frappe``."""
	ctx = {
		"doc": None,
		"company": None,
		"org": frappe._dict(),
		"data": frappe._dict(),
		"today": nowdate(),
		"today_bs": bs(),
		"bs": bs,
		"user": current_user_info(),
		"fmt": _fmt_inr,
		"money": money,
	}
	if extra:
		ctx.update(extra)
	return ctx


# ── Custom Data Sources (admin-authored SQL / Python) ───────────────────────────

_FORBIDDEN_SQL = re.compile(
	r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|replace|"
	r"rename|lock|call|use|into\s+outfile|load_data|load\s+data)\b",
	re.IGNORECASE,
)


def _assert_safe_select(sql):
	"""Allow a single read-only SELECT (or CTE) only."""
	q = (sql or "").strip().rstrip(";").strip()
	if not q:
		frappe.throw(_("A data source has an empty SQL query."))
	if ";" in q:
		frappe.throw(_("Only a single SELECT statement is allowed (no ';')."))
	if not re.match(r"^\s*(select|with)\b", q, re.IGNORECASE):
		frappe.throw(_("Only SELECT queries are allowed in a data source."))
	if _FORBIDDEN_SQL.search(q):
		frappe.throw(_("The SQL contains a disallowed keyword. Only read-only SELECT is permitted."))
	return q


def _run_sql_source(query, params):
	return frappe.db.sql(_assert_safe_select(query), params, as_dict=True)


def _run_python_source(script, params):
	"""Run admin Python in Frappe's safe sandbox; the script assigns ``result``."""
	loc = {"params": frappe._dict(params), "result": None}
	safe_exec(script or "", None, loc)
	res = loc.get("result")
	if isinstance(res, dict):
		return [res]
	if isinstance(res, (list, tuple)):
		return list(res)
	if res is None:
		return []
	return [{"value": res}]


def _resolve_fiscal_year(params):
	"""If a ``fiscal_year`` input is given, fill from_date/to_date from its range
	(unless the user already entered explicit dates)."""
	fy = params.get("fiscal_year")
	if not fy:
		return
	dates = frappe.db.get_value("Fiscal Year", fy, ["year_start_date", "year_end_date"], as_dict=True)
	if dates:
		if not params.get("from_date"):
			params["from_date"] = str(dates.year_start_date)
		if not params.get("to_date"):
			params["to_date"] = str(dates.year_end_date)


def build_custom_context(template_doc, payload):
	"""Run every data source on the template, exposing each result as
	``data.<source_name>.rows`` and ``data.<source_name>.row.<column>``."""
	# Normalise blanks to None, then make sure EVERY declared input is a bound param.
	# The client drops empty inputs from the JSON payload (JSON has no `undefined`), so
	# without this a query referencing e.g. %(from_date)s would raise KeyError.
	params = {k: (None if v == "" else v) for k, v in (payload or {}).items()}
	for inp in template_doc.inputs or []:
		params.setdefault(inp.fieldname, None)
	_resolve_fiscal_year(params)
	data = frappe._dict()
	for src in template_doc.data_sources or []:
		if src.source_type == "Python":
			rows = _run_python_source(src.query, params)
		else:
			rows = _run_sql_source(src.query, params)
		data[src.source_name] = frappe._dict(
			{
				"rows": rows,
				"row": frappe._dict(rows[0]) if rows else frappe._dict(),
			}
		)
	return _base_context(
		{
			"doc": None,
			"company": payload.get("company"),
			"org": company_info(payload.get("company")),
			"data": data,
			"inputs": frappe._dict(params),
		}
	)
