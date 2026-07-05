# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt
#
# A single Receipt Register report with a "View" dropdown that switches between:
#   - Customer - Date Wise        (grouped by voucher date)
#   - Customer - Customer Wise    (grouped by customer, code/name as left header)
#   - Customer Wise Summary       (one line per customer)
# All three read the same customer receipts (submitted Payment Entries, type Receive).

import json
import os
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
			SUBSTRING_INDEX(pe.custom_posting_miti, ' ', 1) AS miti,
			COALESCE(NULLIF(pe.custom_name, ''), pe.name) AS voucher_no,
			pe.name                 AS voucher_link,
			pe.party                AS customer_code,
			pe.party_name           AS customer_name,
			pe.paid_to              AS bank_account,
			pe.reference_no         AS cheque_no,
			pe.received_amount      AS net_amount,
			pe.custom_remark        AS remarks
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
	date_no = 0          # S.N. numbers the DATE groups (date 1 → 1, date 2 → 2, …)
	i, n = 0, len(rows)

	while i < n:
		current_date = rows[i]["date"]
		date_no += 1
		group_total = 0.0
		first = True
		while i < n and rows[i]["date"] == current_date:
			r = rows[i]
			net = flt(r.get("net_amount"))
			group_total += net
			grand_total += net

			data.append({
				"sn":            date_no if first else None,
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
			# A cheque no of "1" is a placeholder (e.g. cash receipts) — don't show it.
			if cheque == "1":
				cheque = ""
			data.append({
				"voucher_no":    cheque,
				"customer_name": r.get("remarks") or "",
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
	grand_total = 0.0
	for (code, name), recs in ordered:
		# Customer header: S.N. numbers the customer; Code + Name merged into one cell.
		cust_no += 1
		combined = f"{code} — {name}" if code else (name or "")
		data.append({"sn": cust_no, "cust_combined": combined, "is_customer_header": 1, "bold": 1})

		total = 0.0
		for r in recs:
			net = flt(r.get("net_amount"))
			total += net
			grand_total += net
			data.append({
				"date":         r.get("date"),
				"miti":         r.get("miti"),
				"voucher_no":   r.get("voucher_no"),
				"voucher_link": r.get("voucher_link"),
				"bank_account": r.get("bank_account"),
				"net_amount":   round(net, 2),
			})
			data.append({"bank_account": r.get("remarks") or "", "is_sub": 1})

		data.append({"voucher_no": _("Total"), "net_amount": round(total, 2), "is_total": 1, "bold": 1})

	# Grand total across all customers.
	data.append({"voucher_no": _("Grand Total"), "net_amount": round(grand_total, 2), "is_total": 1, "is_grand": 1, "bold": 1})

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
	"""Customer options scoped to the selected company via the customer's custom_company."""
	company = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = ["(cust.name LIKE %(txt)s OR cust.customer_name LIKE %(txt)s)"]
	values = {"txt": like}
	if company:
		conditions.append("(cust.custom_company IN %(company)s OR COALESCE(cust.custom_company, '') = '')")
		values["company"] = tuple(company)
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT cust.name AS value, cust.customer_name AS label, cust.name AS description
		FROM `tabCustomer` cust
		WHERE {where}
		ORDER BY cust.customer_name
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


# ── PDF / Print ─────────────────────────────────────────────────────────────────

def _fmt_inr(v):
	"""Indian-style grouping (e.g. 1,07,056.00). Empty for zero/None."""
	if v is None or v == "":
		return ""
	try:
		n = float(v)
	except (TypeError, ValueError):
		return ""
	if n == 0:
		return ""
	neg = n < 0
	n = abs(n)
	int_part, dec = f"{n:.2f}".split(".")
	if len(int_part) > 3:
		result = int_part[-3:]
		int_part = int_part[:-3]
		while int_part:
			result = int_part[-2:] + "," + result
			int_part = int_part[:-2]
	else:
		result = int_part
	return ("-" if neg else "") + result + "." + dec


# Per-page capacity in "line units" (after the repeated header band) and the chars that
# fit on one wrapped line of a remark / wide cell. Conservative — better an under-filled
# page than content spilling onto the next physical page.
_PAGE_CAP = {"Portrait": 117.0, "Landscape": 72.0}
# Summary view packs one row per customer (no sub-lines), so it needs a lower budget.
_PAGE_CAP_SUMMARY = {"Portrait": 69.0, "Landscape": 44.0}
# Date Wise has its own budget so it can be tuned independently of Customer Wise.
_PAGE_CAP_DATE_WISE = {"Portrait": 136.0, "Landscape": 73.0}
_CHARS_PER_LINE = 45


def _row_line_units(row):
	"""Estimate how many text lines a data row occupies (remarks/long cells wrap)."""
	import math
	if row.get("is_sub"):
		# Remarks now render on a FULL-WIDTH line, so far more chars fit before wrapping.
		text = " ".join(p for p in (row.get("voucher_no"), row.get("bank_account"), row.get("customer_name")) if p)
		return max(1, math.ceil(len(text) / 130)) * 0.9
	# primary / header / total row — long name/bank/combined cells can wrap to 2+ lines
	height = 1.0
	for f in ("customer_name", "bank_account", "cust_combined"):
		v = row.get(f) or ""
		if len(v) > _CHARS_PER_LINE:
			height += math.ceil(len(v) / _CHARS_PER_LINE) - 1
	return height


def _paginate(data, orientation, view=None):
	"""Split rows into pages by estimated height (not a flat row count), keeping each
	receipt's main row + its Remarks sub-line together on one page."""
	if not data:
		return []
	if view == VIEW_SUMMARY:
		cap_table = _PAGE_CAP_SUMMARY
	elif view == VIEW_DATE_WISE:
		cap_table = _PAGE_CAP_DATE_WISE
	else:
		cap_table = _PAGE_CAP
	cap = cap_table.get(orientation, 40.0)

	# Atomic blocks: a primary row plus the is_sub row(s) that immediately follow it.
	blocks = []
	i, n = 0, len(data)
	while i < n:
		block = [data[i]]
		i += 1
		while i < n and data[i].get("is_sub"):
			block.append(data[i])
			i += 1
		blocks.append(block)

	pages, cur, used = [], [], 0.0
	for block in blocks:
		bh = sum(_row_line_units(r) for r in block)
		if cur and used + bh > cap:
			pages.append(cur)
			cur, used = [], 0.0
		cur.extend(block)
		used += bh
	if cur:
		pages.append(cur)
	return pages


def _render(filters, orientation):
	columns, data = execute(filters)
	pages = _paginate(data, orientation, filters.get("view") or VIEW_DATE_WISE)
	template_path = os.path.join(os.path.dirname(__file__), "receipt_register_pdf.html")
	with open(template_path) as f:
		template = f.read()
	return frappe.render_template(template, {
		"filters": filters,
		"columns": columns,
		"pages": pages,
		"total_pages": len(pages) or 1,
		"view": filters.get("view") or VIEW_DATE_WISE,
		"company": filters.get("company") or "",
		"orientation": orientation,
		"fmt": _fmt_inr,
		"fmtdate": frappe.utils.formatdate,
	})


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

	frappe.response.filename = "receipt_register.pdf"
	frappe.response.filecontent = pdf_data
	# view=1 (Print) → open inline in a new tab; otherwise download.
	frappe.response.type = "pdf" if frappe.utils.cint(view) else "download"
