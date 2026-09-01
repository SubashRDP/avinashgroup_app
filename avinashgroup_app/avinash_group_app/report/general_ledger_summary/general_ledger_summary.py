# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""General Ledger Summary.

One row per account: the opening balance before the report window, the debit and
credit movement inside the window, and the resulting closing balance -- each shown
in a Debit / Credit column pair (Tally "General Ledger - Summary" layout). A grand
total row closes the report.

The report window is driven by the Fiscal Year: the user picks a Fiscal Year and
the AD date window is resolved on the server from its year_start_date /
year_end_date. Optional From Date / To Date narrow the window but are always
clamped inside the chosen Fiscal Year.
"""

import json
import os

import frappe
import nepali_datetime as nd
from frappe import _
from frappe.utils import add_to_date, flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	window = _resolve_window(filters)

	columns = get_columns()
	if not filters.get("company"):
		return columns, []

	data, _meta = get_data(filters, window)
	return columns, data


# ── Fiscal-year window ──────────────────────────────────────────────────────────

def _resolve_window(filters):
	"""Resolve the AD (from_date, to_date) window from the Fiscal Year filter.

	Rules:
	  - No Fiscal Year given  -> the one containing today.
	  - From / To Date blank   -> the Fiscal Year's start / end.
	  - From / To Date given   -> used, but clamped inside the Fiscal Year.

	Writes the resolved dates back onto ``filters`` so the GL query and the
	print header both read the same values.
	"""
	from erpnext.accounts.utils import get_fiscal_year

	company = filters.get("company")
	fy_name = filters.get("fiscal_year")
	if not fy_name:
		fy_name = get_fiscal_year(nowdate(), company=company)[0]
		filters.fiscal_year = fy_name

	fy = frappe.db.get_value(
		"Fiscal Year", fy_name, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not fy:
		frappe.throw(_("Invalid Fiscal Year: {0}").format(fy_name))

	fy_start, fy_end = getdate(fy.year_start_date), getdate(fy.year_end_date)
	from_date = getdate(filters.from_date) if filters.get("from_date") else fy_start
	to_date = getdate(filters.to_date) if filters.get("to_date") else fy_end

	# the report window can never step outside its fiscal year
	from_date = max(from_date, fy_start)
	to_date = min(to_date, fy_end)
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date"))

	filters.from_date, filters.to_date = from_date, to_date
	return frappe._dict(
		fiscal_year=fy_name,
		fy_start=fy_start,
		fy_end=fy_end,
		from_date=from_date,
		to_date=to_date,
	)


# ── Columns ────────────────────────────────────────────────────────────────────

def get_columns():
	# Amounts are pre-formatted strings (blank for zero, lakh grouping) so a Dr in
	# one pair and a Cr in the other never both show "0.00".
	amt = {"fieldtype": "Data", "align": "right", "width": 130}
	return [
		{"label": _("Account"), "fieldname": "account", "fieldtype": "Data", "width": 320, "align": "left"},
		{"label": _("Opening Debit"), "fieldname": "opening_debit", **amt},
		{"label": _("Opening Credit"), "fieldname": "opening_credit", **amt},
		{"label": _("Period Debit"), "fieldname": "period_debit", **amt},
		{"label": _("Period Credit"), "fieldname": "period_credit", **amt},
		{"label": _("Closing Debit"), "fieldname": "closing_debit", **amt},
		{"label": _("Closing Credit"), "fieldname": "closing_credit", **amt},
	]


# ── Data ───────────────────────────────────────────────────────────────────────

def get_data(filters, window):
	company = filters.get("company")
	selected = _normalize_multiselect(filters.get("account"))

	# Every posting (non-group) account of the company -- cash / bank included.
	all_accounts = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0},
		fields=["name", "account_name", "account_number"],
	)
	total_ledgers = len(all_accounts)
	label_map = {a.name: _account_label(a) for a in all_accounts}

	# Restrict to the explicitly picked accounts, if any.
	if selected:
		pick = [a for a in selected if a in label_map]
	else:
		pick = list(label_map.keys())
	if not pick:
		return [], frappe._dict(shown=0, total_ledgers=total_ledgers)

	balances = _gl_balances(company, pick, window.from_date, window.to_date)

	records = []
	for account in pick:
		b = balances.get(account) or {}
		opening = flt(b.get("opening"))
		period_debit = flt(b.get("period_debit"))
		period_credit = flt(b.get("period_credit"))
		closing = round(opening + period_debit - period_credit, 2)

		# an account with no opening, no movement and no closing is dead weight
		if _is_all_zero(opening, period_debit, period_credit, closing):
			continue

		records.append(
			{
				"account": label_map.get(account, account),
				"opening_debit": _fmt(opening if opening > 0 else 0),
				"opening_credit": _fmt(-opening if opening < 0 else 0),
				"period_debit": _fmt(period_debit),
				"period_credit": _fmt(period_credit),
				"closing_debit": _fmt(closing if closing > 0 else 0),
				"closing_credit": _fmt(-closing if closing < 0 else 0),
				# raw values kept for the grand-total maths
				"_opening": opening,
				"_pd": period_debit,
				"_pc": period_credit,
				"_closing": closing,
			}
		)

	records.sort(key=lambda r: (r["account"] or "").lower())

	data = [{k: v for k, v in r.items() if not k.startswith("_")} for r in records]
	if records:
		data.append(_grand_total_row(records))

	return data, frappe._dict(shown=len(records), total_ledgers=total_ledgers)


def _grand_total_row(records):
	# Each column is the sum of that displayed column down the page (Tally style):
	# the Debit side and the Credit side are added independently, so a balanced
	# selection shows equal Debit / Credit totals rather than a netted-to-zero cell.
	def side(key, positive):
		total = 0.0
		for r in records:
			value = flt(r[key])
			if positive and value > 0:
				total += value
			elif not positive and value < 0:
				total += -value
		return total

	return {
		"account": _("Grand Total"),
		"opening_debit": _fmt(side("_opening", True)),
		"opening_credit": _fmt(side("_opening", False)),
		"period_debit": _fmt(sum(r["_pd"] for r in records)),
		"period_credit": _fmt(sum(r["_pc"] for r in records)),
		"closing_debit": _fmt(side("_closing", True)),
		"closing_credit": _fmt(side("_closing", False)),
		"is_grand_total": 1,
		"bold": 1,
	}


def _gl_balances(company, accounts, from_date, to_date):
	"""Opening (signed) + period debit / credit per account.

	Opening follows ERPNext General Ledger: everything strictly before From Date
	PLUS any is_opening='Yes' entry regardless of its date. Those opening entries
	are then excluded from the period debit / credit so nothing is double counted.

	Split into three plain range queries instead of one CASE aggregation: the
	original single query had no posting_date bound in its WHERE clause (all the
	date logic sat inside CASE), so it read every GL Entry of the company for all
	time. Each query below carries a real posting_date predicate, so it runs as an
	index range scan on GL Entry's fin_stmt_agg_index (company, account,
	posting_date, ...). Same numbers, far less work.
	"""
	params = {
		"company": company,
		"accounts": tuple(accounts),
		"from_date": from_date,
		"to_date": to_date,
	}

	# Opening, part 1: every entry strictly before From Date.
	opening = frappe.db.sql(
		"""
		SELECT gle.account AS account, SUM(gle.debit - gle.credit) AS amount
		FROM `tabGL Entry` gle
		WHERE gle.is_cancelled = 0
			AND gle.company = %(company)s
			AND gle.account IN %(accounts)s
			AND gle.posting_date < %(from_date)s
		GROUP BY gle.account
		""",
		params,
		as_dict=True,
	)

	# Opening, part 2: is_opening entries dated on/after From Date (a small set;
	# the pre-From-Date opening entries are already covered by part 1).
	opening_on_after = frappe.db.sql(
		"""
		SELECT gle.account AS account, SUM(gle.debit - gle.credit) AS amount
		FROM `tabGL Entry` gle
		WHERE gle.is_cancelled = 0
			AND gle.company = %(company)s
			AND gle.account IN %(accounts)s
			AND gle.is_opening = 'Yes'
			AND gle.posting_date >= %(from_date)s
		GROUP BY gle.account
		""",
		params,
		as_dict=True,
	)

	# Period movement inside the window, excluding is_opening entries.
	period = frappe.db.sql(
		"""
		SELECT gle.account AS account,
			SUM(gle.debit) AS period_debit,
			SUM(gle.credit) AS period_credit
		FROM `tabGL Entry` gle
		WHERE gle.is_cancelled = 0
			AND gle.company = %(company)s
			AND gle.account IN %(accounts)s
			AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND COALESCE(gle.is_opening, 'No') != 'Yes'
		GROUP BY gle.account
		""",
		params,
		as_dict=True,
	)

	out = {}
	for r in opening:
		out.setdefault(r.account, {})["opening"] = flt(r.amount)
	for r in opening_on_after:
		d = out.setdefault(r.account, {})
		d["opening"] = flt(d.get("opening")) + flt(r.amount)
	for r in period:
		d = out.setdefault(r.account, {})
		d["period_debit"] = flt(r.period_debit)
		d["period_credit"] = flt(r.period_credit)
	return out


# ── Small helpers ──────────────────────────────────────────────────────────────

def _account_label(a):
	"""'(B08) HP Loan A/c - ...' — account number prefix when the account has one."""
	name = a.get("account_name") or a.get("name")
	number = (a.get("account_number") or "").strip()
	return f"({number}) {name}" if number else name


def _is_all_zero(*values):
	return all(round(flt(v), 2) == 0 for v in values)


def _fmt(value):
	"""Lakh-grouped amount to 2 dp; blank for an exact zero."""
	n = flt(value)
	if round(n, 2) == 0:
		return ""
	neg = n < 0
	s = f"{abs(n):.2f}"
	int_part, dec = s.split(".")
	if len(int_part) > 3:
		out = int_part[-3:]
		int_part = int_part[:-3]
		while int_part:
			out = int_part[-2:] + "," + out
			int_part = int_part[:-2]
	else:
		out = int_part
	return ("-" if neg else "") + out + "." + dec


def _normalize_multiselect(value):
	if not value:
		return []
	if isinstance(value, str):
		value = value.strip()
		if not value:
			return []
		if value.startswith("[") and value.endswith("]"):
			try:
				parsed = json.loads(value)
				return [v for v in parsed if v] if isinstance(parsed, list) else []
			except Exception:
				pass
		return [value]
	if isinstance(value, (list, tuple, set)):
		return [v for v in value if v]
	return [value]


def _bs(ad_date):
	"""AD date -> 'YYYY/MM/DD' Bikram Sambat string for the print header."""
	if not ad_date:
		return ""
	return nd.date.from_datetime_date(getdate(ad_date)).strftime("%Y/%m/%d")


# ── Filter option source ───────────────────────────────────────────────────────

@frappe.whitelist()
def get_company_accounts(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None):
	"""Account MultiSelectList options — posting accounts of the selected company only.

	Registered as the filter's ``get_data`` source so the picker is always
	company-scoped (never the global Account link query).
	"""
	# frappe.call() serialises nested args to JSON, so `filters` arrives as a string
	# over HTTP even though it is a dict when called in-process.
	if isinstance(filters, str):
		filters = frappe.parse_json(filters or "{}")
	company = (filters or {}).get("company")
	if not company:
		return []
	txt = (txt or "").strip()
	rows = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0},
		or_filters=(
			{"name": ["like", f"%{txt}%"], "account_number": ["like", f"%{txt}%"]}
			if txt
			else None
		),
		fields=["name", "account_number"],
		order_by="account_number asc, name asc",
		limit=200,
	)
	return [{"value": r.name, "description": r.account_number or ""} for r in rows]


# ── Print / PDF ────────────────────────────────────────────────────────────────
# Standalone HTML render so browser Print (Ctrl+P) and Download PDF both give the
# full-content output the on-screen datatable can't produce, with in-body
# "Page X of Y" that works on plain (unpatched) wkhtmltopdf.

_PAGE_CAP = {"Portrait": 69.0, "Landscape": 44.0}
_ACCT_CHARS_PER_LINE = 46


def _row_units(row):
	import math

	label = row.get("account") or ""
	return float(max(1, math.ceil(len(label) / _ACCT_CHARS_PER_LINE)))


def _paginate(rows, orientation):
	cap = _PAGE_CAP.get(orientation, 30.0)
	pages, cur, used = [], [], 0.0
	for row in rows:
		h = _row_units(row)
		if cur and used + h > cap:
			pages.append(cur)
			cur, used = [], 0.0
		cur.append(row)
		used += h
	if cur:
		pages.append(cur)
	return pages or [[]]


def _render(filters, orientation):
	filters = frappe._dict(filters)
	window = _resolve_window(filters)
	columns = get_columns()
	data, _meta = get_data(filters, window)

	pages = _paginate(data, orientation)

	template_path = os.path.join(os.path.dirname(__file__), "general_ledger_summary_pdf.html")
	with open(template_path) as f:
		template = f.read()

	return frappe.render_template(
		template,
		{
			"columns": columns,
			"pages": pages,
			"total_pages": len(pages) or 1,
			"company": filters.get("company") or "",
			"fiscal_year": window.fiscal_year,
			"period_from_bs": _bs(window.fy_start),
			# Tally keeps the next year's books open too, so its "Accounting Period"
			# runs to the end of the year AFTER the selected fiscal year.
			"period_to_bs": _bs(add_to_date(window.fy_end, years=1)),
			"from_bs": _bs(window.from_date),
			"to_bs": _bs(window.to_date),
		},
	)


@frappe.whitelist()
def download_pdf(filters, orientation=None, view=None):
	from frappe.utils.pdf import get_pdf

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	orientation = orientation if orientation in ("Portrait", "Landscape") else "Landscape"

	html = _render(filters, orientation)
	options = {
		"page-size": "A4",
		"orientation": orientation,
		"margin-top": "10mm",
		"margin-right": "8mm",
		"margin-bottom": "12mm",
		"margin-left": "8mm",
		"encoding": "UTF-8",
		"enable-local-file-access": None,
	}
	pdf_data = get_pdf(html, options)

	frappe.response.filename = "general_ledger_summary.pdf"
	frappe.response.filecontent = pdf_data
	# view=1 (Print) -> open inline in a new tab; otherwise download.
	frappe.response.type = "pdf" if frappe.utils.cint(view) else "download"
