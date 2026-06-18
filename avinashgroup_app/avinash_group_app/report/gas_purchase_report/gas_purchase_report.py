# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import json
import re

import frappe
from frappe import _

# Values stored in the "Purchase Type" / "Receipt type" masters that identify gas documents.
# Adjust these if the master values differ from the spec.
GAS_INVOICE_TYPE = "Gas Purchase Invoice"
GAS_RECEIPT_TYPE = "Gas Purchase Receipt"
# A "Service Charge ICP" invoice supplies BOTH the Icp column (its total incl. excise)
# and the ICT Vat column (its total VAT). "Service Charge NA" supplies the N.A column
# (its grand total). There is no separate "ICT VAT" purchase type.
SC_ICP = "Service Charge ICP"
SC_NA = "Service Charge NA"


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
def get_refineries(txt=None):
	"""Refinery filter options taken from the custom_refinery Select field's own option list
	(Customize Form / Property Setter), not from existing data — so the full list always shows.
	Falls back to Purchase Receipt if the field is missing on Purchase Invoice."""
	options = ""
	for doctype in ("Purchase Invoice", "Purchase Receipt"):
		field = frappe.get_meta(doctype).get_field("custom_refinery")
		if field and field.options:
			options = field.options
			break

	txt = (txt or "").strip().lower()
	values = [o.strip() for o in options.splitlines() if o.strip()]
	# MultiSelectList expects [{value, description}], not bare values.
	return [{"value": v, "description": ""} for v in values if txt in v.lower()]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)

	if data:
		total = {"refinery": _("Total"), "bold": 1}
		for col in columns:
			if col.get("fieldtype") in ("Currency", "Float"):
				total[col["fieldname"]] = sum(row.get(col["fieldname"]) or 0 for row in data)
		data.append(total)

	return columns, data


def get_columns():
	return [
		{"fieldname": "refinery",       "label": _("Refinery"),       "fieldtype": "Data",     "width": 90},
		{"fieldname": "voucher_no",     "label": _("Vch. No."),       "fieldtype": "Data",     "width": 110},
		{"fieldname": "do_no",          "label": _("DO No."),         "fieldtype": "Data",     "width": 90},
		{"fieldname": "tanker_no",      "label": _("Tanker No"),      "fieldtype": "Data",     "width": 120},
		{"fieldname": "ioc_challan_no", "label": _("IOC Challan No"), "fieldtype": "Data",     "width": 120},
		{"fieldname": "challan_date",   "label": _("Challan Date"),   "fieldtype": "Date",     "width": 100},
		{"fieldname": "sr_no",          "label": _("SR No"),          "fieldtype": "Data",     "width": 70},
		{"fieldname": "sr_miti",        "label": _("SR. Miti"),       "fieldtype": "Data",     "width": 100},
		{"fieldname": "qty",            "label": _("QTY"),            "fieldtype": "Float",    "width": 90, "precision": 3},
		{"fieldname": "bill_no",        "label": _("Bill NO"),        "fieldtype": "Data",     "width": 90},
		{"fieldname": "rate",           "label": _("Rate"),           "fieldtype": "Currency", "width": 110},
		{"fieldname": "price",          "label": _("Price"),          "fieldtype": "Currency", "width": 130},
		{"fieldname": "vat",            "label": _("Vat"),            "fieldtype": "Currency", "width": 120},
		{"fieldname": "other_expense",  "label": _("Other Expense"),  "fieldtype": "Currency", "width": 110},
		{"fieldname": "icp",            "label": _("ICP"),            "fieldtype": "Currency", "width": 100},
		{"fieldname": "ict_vat",        "label": _("ICT Vat"),        "fieldtype": "Currency", "width": 100},
		{"fieldname": "na",             "label": _("N.A"),            "fieldtype": "Currency", "width": 100},
		{"fieldname": "total_amount",   "label": _("Total Amount"),   "fieldtype": "Currency", "width": 140},
		{"fieldname": "transporters",   "label": _("Transporters"),   "fieldtype": "Data",     "width": 160},
		{"fieldname": "remarks",        "label": _("Remarks"),        "fieldtype": "Data",     "width": 160},
	]


def _doc_conditions(filters, alias, with_date=True):
	"""Shared WHERE clauses (company / date / refinery) for the gas invoice & receipt queries.
	The period is taken from the Store Receipt date, which is the basis the sample groups on.
	with_date=False is used for the invoice scan, where linkage is resolved globally and the
	period is decided afterwards in Python (a receipt's invoice may fall in a later month)."""
	conditions = [f"{alias}.docstatus = 1"]
	values = {}

	company = _as_list(filters.get("company"))
	if company:
		conditions.append(f"{alias}.company IN %(company)s")
		values["company"] = tuple(company)
	if with_date and filters.get("from_date"):
		conditions.append(f"{alias}.custom_store_receipt_date >= %(from_date)s")
		values["from_date"] = filters.get("from_date")
	if with_date and filters.get("to_date"):
		conditions.append(f"{alias}.custom_store_receipt_date <= %(to_date)s")
		values["to_date"] = filters.get("to_date")
	refinery = _as_list(filters.get("refinery"))
	if refinery:
		conditions.append(f"{alias}.custom_refinery IN %(refinery)s")
		values["refinery"] = tuple(refinery)

	return conditions, values


def _doc_no(value):
	"""Extract the document number that links a row to its Service Charge invoice.
	A plain number ('218') returns '218'. A coded voucher name like
	'NGK-ICP-00218-82/83' returns '218' (longest all-digit segment, zeros stripped).
	Returns '' when no number is present."""
	if value is None:
		return ""
	s = str(value).strip()
	if s.isdigit():
		return str(int(s))
	segments = [seg for seg in re.split(r"[-/ ]", s) if seg.isdigit()]
	if not segments:
		return ""
	return str(int(max(segments, key=len)))


def _service_charges(filters):
	"""Map document no -> {icp, ict_vat, na} from the Service Charge purchase invoices.
	The link number is taken from Store Receipt No when filled, otherwise parsed from the
	coded voucher name (custom_name, e.g. NGK-ICP-00218-82/83 -> 218). A Service Charge ICP
	invoice supplies both Icp (total incl. excise) and ICT Vat (total VAT); Service Charge NA
	supplies N.A (grand total)."""
	conditions = ["pi.docstatus = 1", "pi.custom_purchase_type IN %(sc_types)s"]
	values = {"sc_types": (SC_ICP, SC_NA)}

	company = _as_list(filters.get("company"))
	if company:
		conditions.append("pi.company IN %(company)s")
		values["company"] = tuple(company)

	where = " AND ".join(conditions)
	rows = frappe.db.sql(
		f"""
		SELECT
			pi.custom_store_receipt_no                AS sr_no,
			pi.custom_name                            AS coded_name,
			pi.custom_purchase_type                   AS ptype,
			pi.custom_total_amount_including_excise   AS incl_excise,
			pi.custom_total_vat_amount                AS total_vat,
			pi.grand_total                            AS grand_total
		FROM `tabPurchase Invoice` pi
		WHERE {where}
		""",
		values,
		as_dict=True,
	)

	sc = {}
	for r in rows:
		key = _doc_no(r.sr_no) or _doc_no(r.coded_name)
		if not key:
			continue
		entry = sc.setdefault(key, {"icp": 0, "ict_vat": 0, "na": 0})
		if r.ptype == SC_ICP:
			# One Service Charge ICP invoice feeds both Icp and ICT Vat.
			entry["icp"] += r.incl_excise or 0
			entry["ict_vat"] += r.total_vat or 0
		elif r.ptype == SC_NA:
			entry["na"] += r.grand_total or 0
	return sc


def _blank_if_zero(value):
	"""Return None for empty zero-like amounts so the report shows a blank cell."""
	return None if not value else value


def _gas_invoices(filters):
	"""Gas Purchase Invoices, company/refinery scoped but NOT date scoped, each tagged with
	the Purchase Receipt it was billed from (pii.purchase_receipt) so linkage can be resolved."""
	conditions, values = _doc_conditions(filters, "pi", with_date=False)
	conditions.append("pi.custom_purchase_type = %(gas_inv_type)s")
	values["gas_inv_type"] = GAS_INVOICE_TYPE

	return frappe.db.sql(
		f"""
		SELECT
			pi.name                            AS docname,
			MAX(pii.purchase_receipt)          AS linked_pr,
			pi.custom_store_receipt_date       AS sr_date,
			pi.custom_store_receipt_no         AS sr_no,
			pi.custom_refinery                 AS refinery,
			pi.custom_pdo_no                   AS do_no,
			pi.custom_vehicle_no               AS tanker_no,
			pi.custom_ioc_challan_no           AS ioc_challan_no,
			pi.custom_ioc_challan_date         AS challan_date,
			pi.custom_store_receipt_miti       AS sr_miti,
			pi.bill_no                         AS bill_no,
			pi.custom_name_of_transportor      AS transporters,
			pi.remarks                         AS remarks,
			pi.custom_total_vat_amount         AS vat,
			SUM(pii.qty)                       AS qty,
			SUM(pii.amount)                    AS price
		FROM `tabPurchase Invoice` pi
		JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		WHERE {" AND ".join(conditions)}
		GROUP BY pi.name
		""",
		values,
		as_dict=True,
	)


def _gas_receipts(filters):
	"""Gas Purchase Receipts, company/refinery scoped. The reporting period is applied
	afterwards on the BS Store Receipt Miti (see _in_period)."""
	conditions, values = _doc_conditions(filters, "pr", with_date=False)
	conditions.append("pr.custom_receipt_type = %(gas_rec_type)s")
	values["gas_rec_type"] = GAS_RECEIPT_TYPE

	return frappe.db.sql(
		f"""
		SELECT
			pr.name                       AS docname,
			pr.custom_store_receipt_date  AS sr_date,
			pr.custom_store_receipt_no    AS sr_no,
			pr.custom_refinery            AS refinery,
			pr.custom_pdo_no              AS do_no,
			pr.custom_vehicle_no          AS tanker_no,
			pr.custom_ioc_challan_no      AS ioc_challan_no,
			pr.custom_ioc_challan_date    AS challan_date,
			pr.custom_store_receipt_miti  AS sr_miti,
			NULL                          AS bill_no,
			pr.custom_name_of_transportor AS transporters,
			pr.remarks                    AS remarks,
			0                             AS vat,
			SUM(pri.qty)                  AS qty,
			SUM(pri.amount)               AS price
		FROM `tabPurchase Receipt` pr
		JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
		WHERE {" AND ".join(conditions)}
		GROUP BY pr.name
		""",
		values,
		as_dict=True,
	)


def _normalize_miti(value):
	"""BS dates may be stored/typed as 2082-04-04 or 2082.04.04 — normalize to dashes.
	Stored miti is zero-padded YYYY-MM-DD, so normalized strings sort chronologically."""
	if not value:
		return ""
	return str(value).strip().replace(".", "-").replace("/", "-")


def _bs_bounds(filters):
	"""Inclusive (low, high) BS-miti strings for the period, or (None, None) if no BS filter.
	From/To Miti win; otherwise BS Year + BS Month select a whole Nepali month."""
	frm = _normalize_miti(filters.get("from_miti"))
	to = _normalize_miti(filters.get("to_miti"))
	if frm or to:
		return (frm or "0000-00-00", to or "9999-99-99")

	year, month = filters.get("bs_year"), filters.get("bs_month")
	if year and month:
		mm = str(month).strip()[:2].zfill(2)   # "04 - Shrawan" -> "04"
		y = str(year).strip()[:4]
		return (f"{y}-{mm}-00", f"{y}-{mm}-99")
	return (None, None)


def _in_period(row, filters):
	"""A row is in the period if its BS miti is within the BS bounds (when a BS filter is set)
	AND its AD store-receipt date is within the AD range (when that is set). Both optional."""
	lo, hi = _bs_bounds(filters)
	if lo is not None:
		miti = _normalize_miti(row.get("sr_miti"))
		if not miti or miti < lo or miti > hi:
			return False

	frm, to = filters.get("from_date"), filters.get("to_date")
	if frm or to:
		d = row.get("sr_date")
		if frm and (not d or str(d) < str(frm)):
			return False
		if to and (not d or str(d) > str(to)):
			return False
	return True


def get_data(filters):
	invoices = _gas_invoices(filters)
	receipts = _gas_receipts(filters)

	# Resolve source by document linkage:
	#  - a receipt that was invoiced (its invoice references it via purchase_receipt)
	#    is represented by the INVOICE;
	#  - a receipt never invoiced is represented by the RECEIPT itself.
	linked_pr_to_inv = {}   # purchase_receipt name -> invoice row
	direct_invoices = []    # gas invoices made without a receipt
	for inv in invoices:
		if inv.get("linked_pr"):
			linked_pr_to_inv[inv["linked_pr"]] = inv
		else:
			direct_invoices.append(inv)

	by_sr = {}
	# Each receipt: take its linked invoice if any, else the receipt itself.
	for rec in receipts:
		src = linked_pr_to_inv.get(rec["docname"], rec)
		if src.get("sr_no"):
			by_sr[src["sr_no"]] = src
	# Invoices entered without a receipt appear on their own right.
	for inv in direct_invoices:
		if inv.get("sr_no"):
			by_sr.setdefault(inv["sr_no"], inv)

	# Apply the reporting period (BS month / BS miti range, or AD date range).
	rows = [r for r in by_sr.values() if _in_period(r, filters)]

	service = _service_charges(filters)

	data = []
	for r in rows:
		sr_no = r.get("sr_no")
		# Match service charges on the normalized document no (handles coded names).
		sc = service.get(_doc_no(sr_no), {})
		icp = sc.get("icp", 0)
		ict_vat = sc.get("ict_vat", 0)
		na = sc.get("na", 0)
		other_expense = icp + ict_vat + na

		qty = r.get("qty") or 0
		price = r.get("price") or 0
		# Rate is the per-unit price (sample: Price / Qty), guarding against zero qty.
		rate = (price / qty) if qty else 0
		# Total Amount = Price + other expense - ICT Vat (verified against the sample).
		total_amount = price + other_expense - ict_vat

		data.append({
			"refinery": r.get("refinery"),
			# Vch. No. = Refinery + SR no, per the spec.
			"voucher_no": f"{r.get('refinery') or ''}{sr_no or ''}",
			"do_no": r.get("do_no"),
			"tanker_no": r.get("tanker_no"),
			"ioc_challan_no": r.get("ioc_challan_no"),
			"challan_date": r.get("challan_date"),
			"sr_no": sr_no,
			"sr_miti": (r.get("sr_miti") or "").split(" ")[0] if r.get("sr_miti") else None,
			"qty": qty,
			"bill_no": r.get("bill_no"),
			"rate": rate,
			"price": price,
				"vat": _blank_if_zero(r.get("vat")),
			"other_expense": _blank_if_zero(other_expense),
			"icp": _blank_if_zero(icp),
			"ict_vat": _blank_if_zero(ict_vat),
			"na": _blank_if_zero(na),
			"total_amount": total_amount,
			"transporters": r.get("transporters"),
			"remarks": r.get("remarks"),
		})

	# Order by SR no numerically when possible (the sample is sequential by SR no).
	def _sort_key(row):
		try:
			return (0, int(row["sr_no"]))
		except (TypeError, ValueError):
			return (1, row.get("sr_no") or "")

	data.sort(key=_sort_key)
	return data
