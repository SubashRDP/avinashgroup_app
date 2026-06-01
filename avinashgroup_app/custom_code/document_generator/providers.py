# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Data providers for the Document Generator.

A provider turns a generation *payload* (the user's selection — a record name, or a
party + period) into the Jinja *context* used to render a template's sections.

Add a new provider by writing a ``build_context(payload) -> dict`` function and
registering it in ``PROVIDERS``. The ``data_provider`` Select on Document Template
chooses which one runs.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate
from frappe.utils.safe_exec import safe_exec

from avinashgroup_app.avinash_group_app.report.party_ledger.party_ledger import (
	_fmt_inr,
	execute as party_ledger_execute,
)


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


def stub_context():
	"""A permissive Jinja context for validating/previewing a template."""
	return {
		"doc": _ANY,
		"company": "",
		"data": _ANY,
		"inputs": _ANY,
		"today": nowdate(),
		"fmt": _fmt_inr,
		"letter_head_html": "",
	}


def _base_context(extra=None):
	"""Common, safe context shared by every provider. Never expose raw ``frappe``."""
	ctx = {
		"doc": None,
		"company": None,
		"data": frappe._dict(),
		"today": nowdate(),
		"fmt": _fmt_inr,
	}
	if extra:
		ctx.update(extra)
	return ctx


def build_single_record_context(payload):
	"""Bind to a single record of the target doctype.

	payload: {"target_doctype": str, "record_name": str, "company": str (optional)}
	"""
	target_doctype = payload.get("target_doctype")
	record_name = payload.get("record_name")
	if not target_doctype or not record_name:
		frappe.throw(_("Target DocType and record are required."))

	doc = frappe.get_doc(target_doctype, record_name)
	doc.check_permission("read")

	company = payload.get("company") or doc.get("company")
	return _base_context(
		{
			"doc": doc,
			"company": company,
			"data": frappe._dict(),
		}
	)


def build_party_balance_confirmation_context(payload):
	"""Aggregate a Customer/Supplier ledger over a period into balance figures.

	payload: {"party_type": str, "party": str, "company": str,
	          "from_date": str, "to_date": str}

	Reuses the Party Ledger report's ``execute`` so the figures match the ledger
	exactly (opening / period / closing), and adds the period VAT total.
	"""
	party_type = payload.get("party_type")
	party = payload.get("party")
	company = payload.get("company")
	from_date = payload.get("from_date")
	to_date = payload.get("to_date")

	for label, value in (
		("Party Type", party_type),
		("Party", party),
		("Company", company),
		("From Date", from_date),
		("To Date", to_date),
	):
		if not value:
			frappe.throw(_("{0} is required for a Party Balance Confirmation.").format(_(label)))

	if not frappe.has_permission(party_type, "read", doc=party):
		frappe.throw(_("Not permitted to read {0} {1}.").format(party_type, party))

	filters = frappe._dict(
		{
			"company": company,
			"party_type": party_type,
			"party": party,
			"from_date": from_date,
			"to_date": to_date,
		}
	)
	_columns, rows = party_ledger_execute(filters)

	summary = {r.get("description"): r for r in rows if r.get("is_summary")}
	opening = summary.get("Opening Balance", {})
	period = summary.get("For the Periods", {})
	closing = summary.get("Closing Balance", {})

	vat_amount = _period_vat(party_type, party, company, from_date, to_date)

	party_doc = frappe.get_doc(party_type, party)

	data = frappe._dict(
		{
			"party": party,
			"party_type": party_type,
			"party_name": party_doc.get("customer_name") or party_doc.get("supplier_name") or party,
			"from_date": getdate(from_date),
			"to_date": getdate(to_date),
			"opening_balance": flt(opening.get("balance")),
			"period_debit": flt(period.get("debit")),
			"period_credit": flt(period.get("credit")),
			"vat_amount": vat_amount,
			"closing_balance": flt(closing.get("balance")),
			"rows": rows,
		}
	)

	return _base_context(
		{
			"doc": party_doc,
			"company": company,
			"data": data,
		}
	)


def _period_vat(party_type, party, company, from_date, to_date):
	"""Sum VAT on submitted invoices for the party within the period.

	Sales Invoice uses ``custom_total_vat_amount``; Purchase Invoice uses
	``custom_vat_amount`` (mirrors the Party Ledger report).
	"""
	if party_type == "Customer":
		field, doctype, party_field = "custom_total_vat_amount", "Sales Invoice", "customer"
	else:
		field, doctype, party_field = "custom_vat_amount", "Purchase Invoice", "supplier"

	if not frappe.db.has_column(doctype, field):
		return 0.0

	total = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(`{field}`), 0)
		FROM `tab{doctype}`
		WHERE docstatus = 1
		  AND company = %(company)s
		  AND `{party_field}` = %(party)s
		  AND posting_date BETWEEN %(from_date)s AND %(to_date)s
		""",
		{"company": company, "party": party, "from_date": from_date, "to_date": to_date},
	)
	return flt(total[0][0]) if total else 0.0


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


def build_custom_context(template_doc, payload):
	"""Run every data source on the template, exposing each result as
	``data.<source_name>.rows`` and ``data.<source_name>.row.<column>``."""
	params = dict(payload or {})
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
			"data": data,
			"inputs": frappe._dict(params),
		}
	)


PROVIDERS = {
	"Single Record": build_single_record_context,
	"Party Balance Confirmation": build_party_balance_confirmation_context,
}


def build_context(data_provider, payload):
	"""Dispatch to the named provider and return its render context."""
	builder = PROVIDERS.get(data_provider)
	if not builder:
		frappe.throw(_("Unknown data provider: {0}").format(data_provider))
	return builder(payload)
