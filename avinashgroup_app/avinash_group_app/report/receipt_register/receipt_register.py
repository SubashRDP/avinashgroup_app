# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt
#
# A single Receipt Register report with a "View" dropdown that switches between:
#   - Customer - Date Wise        (grouped by voucher date)
#   - Customer - Customer Wise    (grouped by customer, code/name as left header)
#   - Customer Wise Summary       (one line per customer)
# All three read the same customer receipts (submitted Payment Entries, type Receive).

import json
from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import flt

VIEW_DATE_WISE = "Customer - Date Wise"
VIEW_CUSTOMER_WISE = "Customer - Customer Wise"
VIEW_SUMMARY = "Customer Wise Summary"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	view = filters.get("view") or VIEW_DATE_WISE
	rows = get_receipts(filters)

	if view == VIEW_SUMMARY:
		return get_columns_summary(), build_summary(rows)
	if view == VIEW_CUSTOMER_WISE:
		return get_columns_customer_wise(), build_customer_wise(rows)
	return get_columns_date_wise(), build_date_wise(rows)


# ── Data ────────────────────────────────────────────────────────────────────────

def get_receipts(filters):
	"""Raw customer-receipt rows: submitted Payment Entries (type Receive, party Customer)
	for the Company / date range / Customer / Bank filters, ordered by date then voucher."""
	company   = filters.get("company")
	from_date = filters.get("from_date")
	to_date   = filters.get("to_date")
	customers = _as_list(filters.get("customer"))
	banks     = _as_list(filters.get("bank"))

	if not (company and from_date and to_date):
		return []

	conditions = [
		"pe.docstatus = 1",
		"pe.payment_type = 'Receive'",
		"pe.party_type = 'Customer'",
		"pe.company = %(company)s",
		"pe.posting_date BETWEEN %(from_date)s AND %(to_date)s",
	]
	params = {"company": company, "from_date": from_date, "to_date": to_date}

	if customers:
		conditions.append("pe.party IN %(customers)s")
		params["customers"] = tuple(customers)
	if banks:
		conditions.append("pe.paid_to IN %(banks)s")
		params["banks"] = tuple(banks)

	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			pe.posting_date         AS date,
			pe.custom_posting_miti  AS miti,
			COALESCE(NULLIF(pe.custom_name, ''), pe.name) AS voucher_no,
			pe.name                 AS voucher_link,
			pe.party                AS customer_code,
			pe.party_name           AS customer_name,
			pe.paid_to              AS bank_account,
			pe.reference_no         AS cheque_no,
			pe.received_amount      AS net_amount,
			pe.remarks              AS remarks
		FROM `tabPayment Entry` pe
		WHERE {where}
		ORDER BY pe.posting_date ASC, pe.name ASC
		""",
		params,
		as_dict=True,
	)


# ── View 1: Date Wise ─────────────────────────────────────────────────────────────

def get_columns_date_wise():
	# Cheque Number and Remarks are a sub-line under each receipt.
	# GL Code is kept as a column title only (left empty) — its source isn't finalized yet.
	return [
		{"label": _("S.N."),                  "fieldname": "sn",            "fieldtype": "Data", "width": 50},
		{"label": _("Voucher Date"),          "fieldname": "date",          "fieldtype": "Date", "width": 100},
		{"label": _("Voucher Miti"),          "fieldname": "miti",          "fieldtype": "Data", "width": 110},
		{"label": _("Voucher Number"),        "fieldname": "voucher_no",    "fieldtype": "Data", "width": 200},
		{"label": _("Customer Code / GL Code"), "fieldname": "customer_code", "fieldtype": "Data", "width": 160},
		{"label": _("Customer Name"),         "fieldname": "customer_name", "fieldtype": "Data", "width": 230},
		{"label": _("Bank Account"),          "fieldname": "bank_account",  "fieldtype": "Data", "width": 240},
		{"label": _("Net Amount"),            "fieldname": "net_amount",    "fieldtype": "Currency", "width": 130},
	]


def build_date_wise(rows):
	if not rows:
		return []

	data = []
	grand_total = 0.0
	sn = 0
	i, n = 0, len(rows)

	while i < n:
		current_date = rows[i]["date"]
		group_total = 0.0
		first = True
		while i < n and rows[i]["date"] == current_date:
			r = rows[i]
			net = flt(r.get("net_amount"))
			group_total += net
			grand_total += net
			sn += 1

			data.append({
				"sn":            sn,
				"date":          r["date"] if first else None,
				"miti":          r.get("miti") if first else None,
				"voucher_no":    r.get("voucher_no"),
				"voucher_link":  r.get("voucher_link"),
				"customer_code": r.get("customer_code"),
				"customer_name": r.get("customer_name"),
				"bank_account":  r.get("bank_account"),
				"net_amount":    round(net, 2),
			})
			# Sub-line: Cheque No (under Voucher No), Remarks (under Customer Name).
			cheque = (r.get("cheque_no") or "").strip()
			data.append({
				"voucher_no":    ("Chq No: " + cheque) if cheque else "",
				"customer_name": "Remarks: " + (r.get("remarks") or ""),
				"is_sub":        1,
			})
			first = False
			i += 1

		data.append({"voucher_no": _("Total"), "net_amount": round(group_total, 2), "is_total": 1, "bold": 1})

	data.append({"voucher_no": _("Grand Total"), "net_amount": round(grand_total, 2), "is_total": 1, "is_grand": 1, "bold": 1})
	return data


# ── View 2: Customer Wise ─────────────────────────────────────────────────────────

def get_columns_customer_wise():
	# Customer Code + Name head each group on the left (see build); not columns.
	# The Bank Account cell also carries the Remarks sub-line.
	return [
		{"label": _("S.N."),           "fieldname": "sn",           "fieldtype": "Data", "width": 50},
		{"label": _("Voucher Date"),   "fieldname": "date",         "fieldtype": "Date", "width": 110},
		{"label": _("Voucher Miti"),   "fieldname": "miti",         "fieldtype": "Data", "width": 120},
		{"label": _("Voucher Number"), "fieldname": "voucher_no",   "fieldtype": "Data", "width": 200},
		{"label": _("Bank Account"),   "fieldname": "bank_account", "fieldtype": "Data", "width": 260},
		{"label": _("Net Amount"),     "fieldname": "net_amount",   "fieldtype": "Currency", "width": 140},
	]


def build_customer_wise(rows):
	if not rows:
		return []

	groups = OrderedDict()
	for r in rows:
		key = (r.get("customer_code"), r.get("customer_name") or r.get("customer_code"))
		groups.setdefault(key, []).append(r)

	ordered = sorted(groups.items(), key=lambda kv: (kv[0][1] or "").lower())

	data = []
	cust_no = 0
	for (code, name), recs in ordered:
		# Customer header: S.N. numbers the customer; Code + Name merged into one cell.
		cust_no += 1
		combined = f"{code} — {name}" if code else (name or "")
		data.append({"sn": cust_no, "cust_combined": combined, "is_customer_header": 1, "bold": 1})

		total = 0.0
		for r in recs:
			net = flt(r.get("net_amount"))
			total += net
			data.append({
				"date":         r.get("date"),
				"miti":         r.get("miti"),
				"voucher_no":   r.get("voucher_no"),
				"voucher_link": r.get("voucher_link"),
				"bank_account": r.get("bank_account"),
				"net_amount":   round(net, 2),
			})
			data.append({"bank_account": "Remarks: " + (r.get("remarks") or ""), "is_sub": 1})

		data.append({"voucher_no": _("Total"), "net_amount": round(total, 2), "is_total": 1, "bold": 1})

	return data


# ── View 3: Customer Wise Summary ─────────────────────────────────────────────────

def get_columns_summary():
	return [
		{"label": _("S.N."),          "fieldname": "sn",            "fieldtype": "Data", "width": 50},
		{"label": _("Customer Code"), "fieldname": "customer_code", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 280},
		{"label": _("Net Amount"),    "fieldname": "net_amount",    "fieldtype": "Currency", "width": 160},
	]


def build_summary(rows):
	if not rows:
		return []

	agg = OrderedDict()
	for r in rows:
		code = r.get("customer_code")
		if code not in agg:
			agg[code] = {"customer_code": code, "customer_name": r.get("customer_name") or code, "net_amount": 0.0}
		agg[code]["net_amount"] += flt(r.get("net_amount"))

	data = sorted(agg.values(), key=lambda d: (d["customer_name"] or "").lower())
	for idx, d in enumerate(data, start=1):
		d["sn"] = idx
		d["net_amount"] = round(d["net_amount"], 2)

	grand_total = round(sum(d["net_amount"] for d in data), 2)
	data.append({"customer_name": _("Total"), "net_amount": grand_total, "is_total": 1, "bold": 1})
	return data


# ── Filter option helpers (company-scoped) ──────────────────────────────────────

def _as_list(value):
	"""Normalize a MultiSelectList/Link filter value (list, JSON string, or single) to a list."""
	if not value:
		return []
	if isinstance(value, str):
		value = value.strip()
		if value.startswith("["):
			try:
				value = json.loads(value)
			except Exception:
				return [value]
		else:
			return [value]
	if isinstance(value, (list, tuple, set)):
		return [v for v in value if v]
	return [value]


@frappe.whitelist()
def get_company_customers(company=None, txt=None):
	"""Customers with a submitted customer receipt (Payment Entry) in the company."""
	company = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = [
		"pe.docstatus = 1", "pe.payment_type = 'Receive'", "pe.party_type = 'Customer'",
		"(pe.party LIKE %(txt)s OR pe.party_name LIKE %(txt)s)",
	]
	values = {"txt": like}
	if company:
		conditions.append("pe.company IN %(company)s")
		values["company"] = tuple(company)
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT DISTINCT pe.party AS value, pe.party_name AS description
		FROM `tabPayment Entry` pe
		WHERE {where}
		ORDER BY pe.party_name
		LIMIT 50
		""",
		values,
		as_dict=True,
	)


@frappe.whitelist()
def get_company_bank_accounts(company=None, txt=None):
	"""Bank / Cash accounts of the selected company (the receipt's paid_to account)."""
	company = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = ["a.is_group = 0", "a.account_type IN ('Bank', 'Cash')", "a.name LIKE %(txt)s"]
	values = {"txt": like}
	if company:
		conditions.append("a.company IN %(company)s")
		values["company"] = tuple(company)
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT a.name AS value, a.name AS description
		FROM `tabAccount` a
		WHERE {where}
		ORDER BY a.name
		LIMIT 50
		""",
		values,
		as_dict=True,
	)
