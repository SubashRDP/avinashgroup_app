"""Net Position of Cash and Bank.

Lists every leaf account whose `account_type` is Cash or Bank for the
selected company and reports four numbers per account over the chosen
period:

    Opening   = closing balance one day before `from_date`
    Receipts  = sum of debits between `from_date` and `to_date`
    Payments  = sum of credits between `from_date` and `to_date`
    Closing   = Opening + Receipts − Payments

A consolidated totals row is appended at the bottom.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate(filters)
	columns = _columns()
	data = _build_data(filters)
	return columns, data


# ---------- filters / columns ----------


def _validate(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is required"))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are required"))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))


def _columns():
	return [
		{
			"label": _("Cash / Bank Code"),
			"fieldname": "code",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": _("Cash / Bank Description"),
			"fieldname": "description",
			"fieldtype": "Link",
			"options": "Account",
			"width": 280,
		},
		{
			"label": _("Cash Book"),
			"fieldname": "cash_book",
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"label": _("Currency Code"),
			"fieldname": "currency",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Opening"),
			"fieldname": "opening",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"label": _("Receipts"),
			"fieldname": "receipts",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"label": _("Payments"),
			"fieldname": "payments",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"label": _("Closing"),
			"fieldname": "closing",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
	]


# ---------- data ----------


def _build_data(filters):
	company = filters.company
	from_date = getdate(filters.from_date)
	to_date = getdate(filters.to_date)
	day_before_from = add_days(from_date, -1)
	suppress_lc = cint_bool(filters.get("suppress_local_currency_equivalents"))
	consider_pdc = cint_bool(filters.get("consider_post_dated_cheques"))

	accounts = _cash_and_bank_accounts(company, filters.get("cash_bank_codes"))
	if not accounts:
		return []

	# Aggregate opening + period movements in two SQL queries (one per phase),
	# keyed by account, for efficiency on companies with many accounts.
	account_names = [a.name for a in accounts]
	opening_map = _opening_balances(account_names, day_before_from, consider_pdc)
	movement_map = _period_movements(account_names, from_date, to_date, consider_pdc)

	company_currency = frappe.get_cached_value("Company", company, "default_currency")

	data = []
	totals = {"opening": 0.0, "receipts": 0.0, "payments": 0.0, "closing": 0.0}

	for acc in accounts:
		opening = flt(opening_map.get(acc.name, 0.0))
		mv = movement_map.get(acc.name, {"receipts": 0.0, "payments": 0.0})
		receipts = flt(mv["receipts"])
		payments = flt(mv["payments"])
		closing = opening + receipts - payments

		currency = acc.account_currency or company_currency
		if suppress_lc and currency != company_currency:
			# Suppress account-currency display, force to company currency.
			currency = company_currency

		data.append({
			"code": acc.code,
			"description": acc.name,
			"cash_book": "Yes" if acc.account_type == "Cash" else "No",
			"currency": currency,
			"opening": opening,
			"receipts": receipts,
			"payments": payments,
			"closing": closing,
		})

		totals["opening"] += opening
		totals["receipts"] += receipts
		totals["payments"] += payments
		totals["closing"] += closing

	# Consolidated totals row in company currency.
	data.append({
		"code": "",
		"description": _("Totals in {0}").format(company_currency),
		"cash_book": "",
		"currency": company_currency,
		"opening": totals["opening"],
		"receipts": totals["receipts"],
		"payments": totals["payments"],
		"closing": totals["closing"],
	})

	return data


# ---------- queries ----------


def _cash_and_bank_accounts(company, code_filter):
	"""All leaf accounts of type Cash or Bank for the company."""
	where = [
		"company = %(company)s",
		"account_type IN ('Cash', 'Bank')",
		"is_group = 0",
		"disabled = 0",
	]
	params = {"company": company}
	if code_filter:
		if isinstance(code_filter, str):
			code_filter = [c.strip() for c in code_filter.split(",") if c.strip()]
		where.append("name IN %(codes)s")
		params["codes"] = tuple(code_filter)

	rows = frappe.db.sql(
		f"""SELECT name, account_name, account_number, account_currency, account_type
		    FROM `tabAccount`
		    WHERE {' AND '.join(where)}
		    ORDER BY COALESCE(account_number, ''), name""",
		params,
		as_dict=True,
	)
	# Use account_number when present, otherwise fall back to a numeric index.
	for i, r in enumerate(rows, start=1):
		r["code"] = r.account_number or str(i)
	return rows


def _opening_balances(account_names, before_date, consider_pdc):
	"""Returns {account: opening_balance} as (sum debit − sum credit) before from_date."""
	if not account_names:
		return {}
	pdc_clause = "" if consider_pdc else "AND (is_pdc = 0 OR is_pdc IS NULL)"
	rows = frappe.db.sql(
		f"""SELECT account, COALESCE(SUM(debit), 0) - COALESCE(SUM(credit), 0) AS bal
		    FROM `tabGL Entry`
		    WHERE account IN %(accounts)s
		      AND posting_date <= %(date)s
		      AND is_cancelled = 0
		      {pdc_clause if _gl_has_pdc_column() else ''}
		    GROUP BY account""",
		{"accounts": tuple(account_names), "date": before_date},
		as_dict=True,
	)
	return {r.account: r.bal for r in rows}


def _period_movements(account_names, from_date, to_date, consider_pdc):
	"""Returns {account: {'receipts': debit_sum, 'payments': credit_sum}}."""
	if not account_names:
		return {}
	pdc_clause = "" if consider_pdc else "AND (is_pdc = 0 OR is_pdc IS NULL)"
	rows = frappe.db.sql(
		f"""SELECT account,
		           COALESCE(SUM(debit), 0)  AS receipts,
		           COALESCE(SUM(credit), 0) AS payments
		    FROM `tabGL Entry`
		    WHERE account IN %(accounts)s
		      AND posting_date BETWEEN %(from)s AND %(to)s
		      AND is_cancelled = 0
		      {pdc_clause if _gl_has_pdc_column() else ''}
		    GROUP BY account""",
		{"accounts": tuple(account_names), "from": from_date, "to": to_date},
		as_dict=True,
	)
	return {r.account: {"receipts": r.receipts, "payments": r.payments} for r in rows}


# ---------- helpers ----------


def cint_bool(v):
	"""Tolerant truthy check for filter values that may come as bool/int/str."""
	if v in (None, "", 0, "0", False, "false", "False"):
		return False
	return True


_has_pdc_column = None


def _gl_has_pdc_column():
	"""Detect whether the GL Entry table has an `is_pdc` column.
	Some ERPNext installs ship it via custom fields; others don't.
	Cached for the request."""
	global _has_pdc_column
	if _has_pdc_column is None:
		cols = [r[0] for r in frappe.db.sql("DESC `tabGL Entry`")]
		_has_pdc_column = "is_pdc" in cols
	return _has_pdc_column
