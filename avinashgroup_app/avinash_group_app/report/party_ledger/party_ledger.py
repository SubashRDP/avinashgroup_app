# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from datetime import date, datetime


def execute(filters=None):
	filters = filters or {}
	columns = get_columns(filters)

	if not filters.get("company") or not filters.get("from_date") or not filters.get("to_date"):
		return columns, []

	data = get_data(filters)
	return columns, data


def get_columns(filters=None):
	columns = [
		{"label": _("Date"),        "fieldname": "date",         "fieldtype": "Date",     "width": 100},
		{"label": _("Miti (BS)"),   "fieldname": "miti",         "fieldtype": "Data",     "width": 110},
		{"label": _("Voucher No"),  "fieldname": "voucher_no",   "fieldtype": "Data",     "width": 200},
		{"label": _("Description"), "fieldname": "description",  "fieldtype": "Data",     "width": 280},
	]

	if filters and filters.get("show_remarks"):
		columns.append(
			{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 250}
		)

	if filters and filters.get("detailed_mapping"):
		columns.append(
			{"label": _("Against"), "fieldname": "against", "fieldtype": "Data", "width": 220}
		)

	columns += [
		{"label": _("Debit"),   "fieldname": "debit",   "fieldtype": "Currency", "width": 140},
		{"label": _("Credit"),  "fieldname": "credit",  "fieldtype": "Currency", "width": 140},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 160},
	]
	return columns


def get_data(filters):
	company    = filters.get("company")
	from_date  = filters.get("from_date")
	to_date    = filters.get("to_date")
	party_type = filters.get("party_type") or "Customer"
	party      = filters.get("party")
	account    = filters.get("account")
	detailed_mapping = bool(filters.get("detailed_mapping"))
	show_remarks = bool(filters.get("show_remarks"))

	# GL Entry conditions — party_type + party narrows to the receivable/payable account rows only
	conditions = "gle.is_cancelled = 0 AND gle.company = %(company)s AND gle.party_type = %(party_type)s"
	params = {
		"company":    company,
		"from_date":  from_date,
		"to_date":    to_date,
		"party_type": party_type,
	}

	if party:
		conditions += " AND gle.party = %(party)s"
		params["party"] = party

	if account:
		conditions += " AND gle.account = %(account)s"
		params["account"] = account

	# ── Opening balance ────────────────────────────────────────────────────────
	opening_row = frappe.db.sql(f"""
		SELECT
			COALESCE(SUM(gle.debit),  0) AS opening_debit,
			COALESCE(SUM(gle.credit), 0) AS opening_credit
		FROM `tabGL Entry` gle
		WHERE {conditions}
		  AND gle.posting_date < %(from_date)s
	""", params, as_dict=True)

	opening = opening_row[0] if opening_row else {}
	opening_debit   = flt(opening.get("opening_debit"))
	opening_credit  = flt(opening.get("opening_credit"))
	opening_balance = opening_debit - opening_credit   # positive = DB, negative = CR

	# ── Period entries ─────────────────────────────────────────────────────────
	entries = frappe.db.sql(f"""
		SELECT
			gle.posting_date  AS date,
			gle.voucher_type,
			gle.voucher_no,
			gle.against,
			gle.debit,
			gle.credit,
			CASE
				WHEN gle.voucher_type = 'Sales Invoice'    AND si.is_return = 1 THEN 'Sales Return'
				WHEN gle.voucher_type = 'Sales Invoice'                         THEN 'Sales Invoice'
				WHEN gle.voucher_type = 'Purchase Invoice' AND pi.is_return = 1 THEN 'Purchase Return'
				WHEN gle.voucher_type = 'Purchase Invoice'                      THEN 'Purchase Invoice'
				WHEN gle.voucher_type = 'Payment Entry'
					THEN COALESCE(NULLIF(gle.against, ''), 'Payment')
				ELSE gle.voucher_type
			END AS description
		FROM `tabGL Entry` gle
		LEFT JOIN `tabSales Invoice`    si ON si.name = gle.voucher_no AND gle.voucher_type = 'Sales Invoice'
		LEFT JOIN `tabPurchase Invoice` pi ON pi.name = gle.voucher_no AND gle.voucher_type = 'Purchase Invoice'
		WHERE {conditions}
		  AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		ORDER BY gle.posting_date ASC, gle.creation ASC
	""", params, as_dict=True)

	if detailed_mapping:
		entries = _merge_entries_detailed(entries)
	else:
		entries = _merge_entries(entries)

	data = []

	# Opening Balance row
	data.append({
		"date":        "",
		"miti":        "",
		"voucher_no":  "",
		"description": "Opening Balance",
		"debit":       opening_debit,
		"credit":      opening_credit,
		"balance":     opening_balance,
		"bold":        1,
		"is_summary":  1,
	})

	running_balance = opening_balance
	period_debit    = 0.0
	period_credit   = 0.0

	for entry in entries:
		debit  = flt(entry.get("debit"))
		credit = flt(entry.get("credit"))
		running_balance = round(running_balance + debit - credit, 2)
		period_debit   += debit
		period_credit  += credit

		data.append({
			"date":         entry.get("date"),
			"miti":         "",
			"voucher_no":   entry.get("voucher_no"),
			"voucher_type": entry.get("voucher_type"),
			"description":  entry.get("description") or "",
			"remarks":      "",
			"against":      entry.get("against") or "",
			# Show blank cell instead of 0 for one side of a transaction
			"debit":        round(debit,  2) if debit  else None,
			"credit":       round(credit, 2) if credit else None,
			"balance":      running_balance,
			"bold":         0,
			"is_summary":   0,
		})

	_apply_bs_miti(data)
	if show_remarks:
		_apply_voucher_remarks(data)
	return data


def _merge_entries(entries):
	"""Return one row per voucher (unique) with summed debit/credit.

	GL Entries can have multiple rows for the same voucher_no for the same party;
	we merge them so each voucher appears only once in the report.
	"""
	if not entries:
		return []

	def _pick_description(descriptions, voucher_type):
		descriptions = [d for d in descriptions if d]
		if not descriptions:
			return voucher_type or ""
		if len(descriptions) == 1:
			return descriptions[0]

		# Prefer something more informative than generic fallbacks.
		avoid = {voucher_type or "", "Payment"}
		candidates = [d for d in descriptions if d not in avoid] or descriptions
		return max(candidates, key=lambda s: len(s))

	grouped = {}
	order = []
	for e in entries:
		key = (e.get("date"), e.get("voucher_type"), e.get("voucher_no"))
		if key not in grouped:
			grouped[key] = {
				"date": e.get("date"),
				"voucher_type": e.get("voucher_type"),
				"voucher_no": e.get("voucher_no"),
				"debit": 0.0,
				"credit": 0.0,
				"_descriptions": [],
			}
			order.append(key)

		g = grouped[key]
		g["debit"] += flt(e.get("debit"))
		g["credit"] += flt(e.get("credit"))
		g["_descriptions"].append((e.get("description") or "").strip())

	out = []
	for key in order:
		g = grouped[key]
		vt = g.get("voucher_type")
		descriptions = list(dict.fromkeys(g["_descriptions"]))

		out.append({
			"date": g.get("date"),
			"voucher_type": vt,
			"voucher_no": g.get("voucher_no"),
			"description": _pick_description(descriptions, vt),
			"remarks": "",
			"debit": round(g.get("debit") or 0, 2),
			"credit": round(g.get("credit") or 0, 2),
		})
	return out


def _merge_entries_detailed(entries):
	"""Return unique rows for mapping: group by voucher + against and sum debit/credit."""
	if not entries:
		return []

	grouped = {}
	order = []
	for e in entries:
		key = (e.get("date"), e.get("voucher_type"), e.get("voucher_no"), (e.get("against") or "").strip())
		if key not in grouped:
			grouped[key] = {
				"date": e.get("date"),
				"voucher_type": e.get("voucher_type"),
				"voucher_no": e.get("voucher_no"),
				"against": (e.get("against") or "").strip(),
				"debit": 0.0,
				"credit": 0.0,
				"description": (e.get("description") or "").strip(),
			}
			order.append(key)

		g = grouped[key]
		g["debit"] += flt(e.get("debit"))
		g["credit"] += flt(e.get("credit"))

	out = []
	for key in order:
		g = grouped[key]
		out.append({
			"date": g.get("date"),
			"voucher_type": g.get("voucher_type"),
			"voucher_no": g.get("voucher_no"),
			"against": g.get("against"),
			"description": g.get("description"),
			"remarks": "",
			"debit": round(g.get("debit") or 0, 2),
			"credit": round(g.get("credit") or 0, 2),
		})
	return out


def _apply_bs_miti(rows):
	"""Populate BS (miti) date based on source voucher doctype/custom fields."""
	if not rows:
		return

	def _normalize_miti(value):
		if not value:
			return ""
		if isinstance(value, datetime):
			return value.date().isoformat()
		if isinstance(value, date):
			return value.isoformat()
		value = str(value)
		return value.split(" ", 1)[0] if " " in value else value

	vouchers_by_type = {}
	for r in rows:
		vt = r.get("voucher_type")
		vn = r.get("voucher_no")
		if not vt or not vn:
			continue
		vouchers_by_type.setdefault(vt, set()).add(vn)

	def _get_field_map(doctype, fieldname, names):
		if not names:
			return {}
		if not frappe.db.has_column(doctype, fieldname):
			return {}
		out = {}
		names = list(names)
		for i in range(0, len(names), 500):
			res = frappe.get_all(
				doctype,
				filters={"name": ("in", names[i:i + 500])},
				fields=["name", fieldname],
			)
			out.update({d["name"]: d.get(fieldname) for d in res})
		return out

	si_map = _get_field_map("Sales Invoice", "custom_invoice_miti", vouchers_by_type.get("Sales Invoice"))
	je_map = _get_field_map("Journal Entry", "custom_posting_miti", vouchers_by_type.get("Journal Entry"))
	pi_map = _get_field_map("Purchase Invoice", "custom_nepali_miti", vouchers_by_type.get("Purchase Invoice"))
	pe_map = _get_field_map("Payment Entry", "custom_posting_miti", vouchers_by_type.get("Payment Entry"))

	for r in rows:
		vt = r.get("voucher_type")
		vn = r.get("voucher_no")
		if not vt or not vn:
			continue

		if vt == "Sales Invoice":
			r["miti"] = _normalize_miti(si_map.get(vn))
		elif vt == "Journal Entry":
			r["miti"] = _normalize_miti(je_map.get(vn))
		elif vt == "Purchase Invoice":
			r["miti"] = _normalize_miti(pi_map.get(vn))
		elif vt == "Payment Entry":
			r["miti"] = _normalize_miti(pe_map.get(vn))


def _apply_voucher_remarks(rows):
	"""Populate remarks based on voucher doctype/custom fields (when Show Remarks is enabled)."""
	if not rows:
		return

	def _normalize(value):
		if value is None:
			return ""
		# Keep as string; strip newline noise from editors.
		return str(value).strip()

	vouchers_by_type = {}
	for r in rows:
		vt = r.get("voucher_type")
		vn = r.get("voucher_no")
		if not vt or not vn:
			continue
		vouchers_by_type.setdefault(vt, set()).add(vn)

	def _get_field_map(doctype, fieldname, names):
		if not names:
			return {}
		if not frappe.db.has_column(doctype, fieldname):
			return {}
		out = {}
		names = list(names)
		for i in range(0, len(names), 500):
			res = frappe.get_all(
				doctype,
				filters={"name": ("in", names[i:i + 500])},
				fields=["name", fieldname],
			)
			out.update({d["name"]: d.get(fieldname) for d in res})
		return out

	si_map = _get_field_map("Sales Invoice", "custom_narration", vouchers_by_type.get("Sales Invoice"))
	pi_map = _get_field_map("Purchase Invoice", "memo", vouchers_by_type.get("Purchase Invoice"))
	pe_map = _get_field_map("Payment Entry", "remarks", vouchers_by_type.get("Payment Entry"))
	je_map = _get_field_map("Journal Entry", "user_remark", vouchers_by_type.get("Journal Entry"))

	for r in rows:
		vt = r.get("voucher_type")
		vn = r.get("voucher_no")
		if not vt or not vn:
			continue

		if vt == "Sales Invoice":
			r["remarks"] = _normalize(si_map.get(vn))
		elif vt == "Purchase Invoice":
			r["remarks"] = _normalize(pi_map.get(vn))
		elif vt == "Payment Entry":
			r["remarks"] = _normalize(pe_map.get(vn))
		elif vt == "Journal Entry":
			r["remarks"] = _normalize(je_map.get(vn))
