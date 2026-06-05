# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

# Customer / Vendor Ledger Summary (Trial) Report
# ------------------------------------------------
# One row per party showing Opening Balance, period Debit, period Credit and
# Closing Balance. This is the *summary / trial-balance* counterpart to the
# detailed `Party Ledger` report — it reuses the same GL Entry conventions
# (is_cancelled = 0, party_type + party scoping, posting_date windows) so the
# two reports always reconcile.

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	columns = get_columns(filters)

	if not filters.get("company") or not filters.get("from_date") or not filters.get("to_date"):
		return columns, []

	data = get_data(filters)
	return columns, data


def get_columns(filters=None):
	filters = filters or {}
	party_type = filters.get("party_type") or "Customer"

	return [
		{"label": _("Party"),           "fieldname": "party",          "fieldtype": "Link",     "options": party_type, "width": 200},
		{"label": _("Party Name"),      "fieldname": "party_name",     "fieldtype": "Data",     "width": 260},
		{"label": _("Opening Balance"), "fieldname": "opening",        "fieldtype": "Currency", "width": 150},
		{"label": _("Dr/Cr"),           "fieldname": "opening_side",   "fieldtype": "Data",     "width": 60},
		{"label": _("Debit"),           "fieldname": "debit",          "fieldtype": "Currency", "width": 150},
		{"label": _("Credit"),          "fieldname": "credit",         "fieldtype": "Currency", "width": 150},
		{"label": _("Closing Balance"), "fieldname": "closing",        "fieldtype": "Currency", "width": 150},
		{"label": _("Dr/Cr"),           "fieldname": "closing_side",   "fieldtype": "Data",     "width": 60},
	]


def _normalize_multiselect(value):
	"""Return a cleaned list for MultiSelectList / Link-like inputs."""
	import json

	if not value:
		return []

	if isinstance(value, str):
		value = value.strip()
		if not value:
			return []
		if value.startswith("[") and value.endswith("]"):
			try:
				parsed = json.loads(value)
				if isinstance(parsed, list):
					return [v for v in parsed if v]
			except Exception:
				pass
		return [value]

	if isinstance(value, (list, tuple, set)):
		return [v for v in value if v]

	return [value]


def _side(amount):
	"""Return 'Dr' for a positive (debit) balance, 'Cr' for negative, '' for zero."""
	amount = flt(amount, 2)
	if amount > 0:
		return "Dr"
	if amount < 0:
		return "Cr"
	return ""


def get_data(filters):
	company    = filters.get("company")
	from_date  = filters.get("from_date")
	to_date    = filters.get("to_date")
	party_type = filters.get("party_type") or "Customer"
	parties    = _normalize_multiselect(filters.get("party"))
	accounts   = _normalize_multiselect(filters.get("account"))
	hide_zero  = bool(filters.get("hide_zero_balance"))

	# Same scoping as Party Ledger: only the receivable / payable party rows.
	conditions = (
		"gle.is_cancelled = 0 "
		"AND gle.company = %(company)s "
		"AND gle.party_type = %(party_type)s "
		"AND gle.party IS NOT NULL AND gle.party != ''"
	)
	params = {
		"company":    company,
		"from_date":  from_date,
		"to_date":    to_date,
		"party_type": party_type,
	}

	if parties:
		if len(parties) == 1:
			conditions += " AND gle.party = %(party)s"
			params["party"] = parties[0]
		else:
			conditions += " AND gle.party IN %(party)s"
			params["party"] = tuple(parties)

	if accounts:
		if len(accounts) == 1:
			conditions += " AND gle.account = %(account)s"
			params["account"] = accounts[0]
		else:
			conditions += " AND gle.account IN %(account)s"
			params["account"] = tuple(accounts)

	# Single pass: opening (before from_date) and period (from_date..to_date)
	# computed per party with conditional aggregation. Rows after to_date are
	# excluded entirely so the closing balance is as-of to_date.
	rows = frappe.db.sql(
		f"""
		SELECT
			gle.party AS party,
			COALESCE(SUM(CASE WHEN gle.posting_date < %(from_date)s
				THEN gle.debit - gle.credit ELSE 0 END), 0) AS opening,
			COALESCE(SUM(CASE WHEN gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
				THEN gle.debit ELSE 0 END), 0) AS debit,
			COALESCE(SUM(CASE WHEN gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
				THEN gle.credit ELSE 0 END), 0) AS credit
		FROM `tabGL Entry` gle
		WHERE {conditions}
		  AND gle.posting_date <= %(to_date)s
		GROUP BY gle.party
		ORDER BY gle.party ASC
		""",
		params,
		as_dict=True,
	)

	name_map = _party_name_map(party_type, [r["party"] for r in rows])

	data = []
	tot_opening = tot_debit = tot_credit = tot_closing = 0.0

	for r in rows:
		opening = flt(r.get("opening"), 2)
		debit   = flt(r.get("debit"), 2)
		credit  = flt(r.get("credit"), 2)
		closing = round(opening + debit - credit, 2)

		# Skip parties with no opening, no movement and no closing balance.
		if hide_zero and not opening and not debit and not credit and not closing:
			continue
		if not opening and not debit and not credit and not closing:
			continue

		tot_opening += opening
		tot_debit   += debit
		tot_credit  += credit
		tot_closing += closing

		data.append({
			"party":        r.get("party"),
			"party_name":   name_map.get(r.get("party")) or r.get("party"),
			"opening":      opening or None,
			"opening_side": _side(opening),
			"debit":        debit or None,
			"credit":       credit or None,
			"closing":      closing or None,
			"closing_side": _side(closing),
		})

	if data:
		data.append({
			"party":        "",
			"party_name":   _("Total"),
			"opening":      round(tot_opening, 2) or None,
			"opening_side": _side(tot_opening),
			"debit":        round(tot_debit, 2) or None,
			"credit":       round(tot_credit, 2) or None,
			"closing":      round(tot_closing, 2) or None,
			"closing_side": _side(tot_closing),
			"is_total":     1,
			"bold":         1,
		})

	return data


def _party_name_map(party_type, party_ids):
	"""Map party id -> display name (customer_name / supplier_name)."""
	party_ids = [p for p in set(party_ids) if p]
	if not party_ids:
		return {}

	name_field = "customer_name" if party_type == "Customer" else "supplier_name"
	if not frappe.db.has_column(party_type, name_field):
		return {}

	rows = frappe.db.get_all(
		party_type,
		filters={"name": ("in", party_ids)},
		fields=["name", name_field],
	)
	return {r["name"]: r.get(name_field) for r in rows}
