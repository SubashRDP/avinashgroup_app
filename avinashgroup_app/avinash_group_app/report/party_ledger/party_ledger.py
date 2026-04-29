# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import os
import frappe
from frappe import _
from frappe.utils import flt
from datetime import date, datetime
from markupsafe import Markup
import json


def _fmt_inr(v):
	"""Format number in Indian style (e.g. 1,50,000.00). Returns empty string for zero/None."""
	if v is None or v == '':
		return ''
	try:
		n = float(v)
	except (TypeError, ValueError):
		return ''
	if n == 0:
		return ''
	neg = n < 0
	n = abs(n)
	s = f"{n:.2f}"
	int_part, dec = s.split('.')
	if len(int_part) > 3:
		result = int_part[-3:]
		int_part = int_part[:-3]
		while int_part:
			result = int_part[-2:] + ',' + result
			int_part = int_part[:-2]
	else:
		result = int_part
	return ('-' if neg else '') + result + '.' + dec


def _bal_str(v):
	"""Return bold balance string with DB/CR suffix as safe HTML Markup."""
	if v is None or v == '':
		return Markup('')
	try:
		n = float(v)
	except (TypeError, ValueError):
		return Markup('')
	suffix = 'DB' if n >= 0 else 'CR'
	formatted = _fmt_inr(abs(n)) or '0.00'
	return Markup(f'<b>{formatted}</b>&thinsp;<small>{suffix}</small>')


@frappe.whitelist()
def download_pdf(filters):
	import tempfile
	from frappe.utils.pdf import get_pdf

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))

	_, data = execute(filters)

	# Collect unique party display names for the header
	seen = set()
	party_names = []
	for row in data:
		pn = row.get('party_name') or ''
		for part in pn.split(','):
			part = part.strip()
			if part and part not in seen:
				seen.add(part)
				party_names.append(part)

	template_path = os.path.join(os.path.dirname(__file__), 'party_ledger_pdf.html')
	with open(template_path) as f:
		template_content = f.read()

	html = frappe.render_template(
		template_content,
		{
			'filters': filters,
			'data': data,
			'party_names': party_names,
			'fmt': _fmt_inr,
			'bal': _bal_str,
		}
	)

	# Build footer HTML (page numbers via JS — wkhtmltopdf injects page/topage in query string)
	footer_html = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script>
function subst() {
	var v = {}, x = window.location.search.substring(1).split('&');
	for (var i in x) { var z = x[i].split('=', 2); v[z[0]] = unescape(z[1]); }
	document.getElementById('pn').textContent = v['page'];
	document.getElementById('tp').textContent = v['topage'];
}
</script>
</head>
<body onload="subst()" style="margin:0;padding:2mm 0;font-family:Arial,sans-serif;font-size:9pt;color:#000;text-align:center;">
Page <span id="pn"></span>/<span id="tp"></span>
</body></html>"""

	footer_file = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8')
	footer_file.write(footer_html)
	footer_file.close()

	try:
		options = {
			'page-size': 'A4',
			'orientation': 'Landscape',
			'margin-top': '10mm',
			'margin-right': '15mm',
			'margin-bottom': '15mm',
			'margin-left': '15mm',
			'footer-html': footer_file.name,
			'footer-spacing': '2',
			'encoding': 'UTF-8',
			'enable-local-file-access': None,
		}
		pdf_data = get_pdf(html, options)
	finally:
		try:
			os.unlink(footer_file.name)
		except FileNotFoundError:
			pass

	frappe.response.filename = 'party_ledger.pdf'
	frappe.response.filecontent = pdf_data
	frappe.response.type = 'download'


def _normalize_multiselect(value):
	"""Return a cleaned list for MultiSelectList / Link-like inputs."""
	if not value:
		return []

	if isinstance(value, str):
		value = value.strip()
		if not value:
			return []
		# Route/options sometimes come as a JSON string.
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
	parties = _normalize_multiselect(filters.get("party"))
	show_party_column = len(parties) != 1

	columns = [
		{"label": _("S.No"),           "fieldname": "sr_no",        "fieldtype": "Data",     "width": 40},
		{"label": _("Date"),        "fieldname": "date",         "fieldtype": "Date",     "width": 80},
		{"label": _("Miti (BS)"),   "fieldname": "miti",         "fieldtype": "Data",     "width": 85},
		{"label": _("Voucher No"),  "fieldname": "voucher_no",   "fieldtype": "Data",     "width": 200},
	]

	if show_party_column:
		columns.append({
			"label": _("Party"),
			"fieldname": "party",
			"fieldtype": "Link",
			"options": party_type,
			"width": 220,
		})

	columns.append({"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 320})

	if filters.get("detailed_mapping"):
		columns += [
			{"label": "", "fieldname": "detail_qty",    "fieldtype": "Data",     "width": 100},
			{"label": "", "fieldname": "detail_uom",    "fieldtype": "Data",     "width": 70},
			{"label": "", "fieldname": "detail_rate",   "fieldtype": "Currency", "width": 120},
			{"label": "", "fieldname": "detail_amount", "fieldtype": "Currency", "width": 120},
		]

	columns += [
		{"label": _("Debit"),   "fieldname": "debit",   "fieldtype": "Currency", "width": 140},
		{"label": _("Credit"),  "fieldname": "credit",  "fieldtype": "Currency", "width": 140},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 160},
	]

	if filters.get("show_remarks"):
		columns.append(
			{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 250}
		)

	return columns


def get_data(filters):
	company    = filters.get("company")
	from_date  = filters.get("from_date")
	to_date    = filters.get("to_date")
	party_type = filters.get("party_type") or "Customer"
	parties    = _normalize_multiselect(filters.get("party"))
	accounts   = _normalize_multiselect(filters.get("account"))
	voucher_no_filter = (filters.get("voucher_no") or "").strip()
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

	if parties:
		if len(parties) == 1:
			conditions += " AND gle.party = %(party)s"
			params["party"] = parties[0]
		else:
			conditions += " AND gle.party in %(party)s"
			params["party"] = tuple(parties)

	if accounts:
		if len(accounts) == 1:
			conditions += " AND gle.account = %(account)s"
			params["account"] = accounts[0]
		else:
			conditions += " AND gle.account in %(account)s"
			params["account"] = tuple(accounts)

	if voucher_no_filter:
		conditions += " AND gle.voucher_no LIKE %(voucher_no_filter)s"
		params["voucher_no_filter"] = f"%{voucher_no_filter}%"

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
			gle.party         AS party,
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

	# Batch-fetch all detail data upfront when detailed_mapping is on (avoids N+1 queries)
	detail_data = _fetch_all_details(entries) if detailed_mapping else {}

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
	sr_no           = 0

	for entry in entries:
		debit  = flt(entry.get("debit"))
		credit = flt(entry.get("credit"))
		running_balance = round(running_balance + debit - credit, 2)
		period_debit   += debit
		period_credit  += credit

		sr_no += 1
		data.append({
			"sr_no":        sr_no,
			"date":         entry.get("date"),
			"miti":         "",
			"voucher_no":   entry.get("voucher_no"),
			"voucher_type": entry.get("voucher_type"),
			"party":        entry.get("party") or "",
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

		# Inject indented sub-rows + separator for detailed_mapping mode
		if detailed_mapping:
			sub_rows = _build_detail_rows(
				entry.get("voucher_type"),
				entry.get("voucher_no"),
				debit, credit,
				detail_data,
				show_remarks,
			)
			if sub_rows:
				sub_rows[0]["is_first_detail"] = 1
				sub_rows[-1]["is_last_detail"]  = 1
			data.extend(sub_rows)
			data.append({"is_separator": 1, "balance": None})

	# ── For the Periods row ────────────────────────────────────────────────────
	period_net = round(period_debit - period_credit, 2)
	data.append({
		"date":        "",
		"miti":        "",
		"voucher_no":  "",
		"description": "For the Periods",
		"debit":       round(period_debit,  2) if period_debit  else None,
		"credit":      round(period_credit, 2) if period_credit else None,
		"balance":     period_net or None,
		"bold":        1,
		"is_summary":  1,
	})

	# ── Closing Balance row ────────────────────────────────────────────────────
	cumulative_debit  = round(opening_debit  + period_debit,  2)
	cumulative_credit = round(opening_credit + period_credit, 2)
	closing_label = "Closing Balance"
	data.append({
		"date":        "",
		"miti":        "",
		"voucher_no":  "NPR",
		"description": closing_label,
		"debit":       cumulative_debit  if cumulative_debit  else None,
		"credit":      cumulative_credit if cumulative_credit else None,
		"balance":     running_balance   if running_balance   else None,
		"bold":        1,
		"is_summary":  1,
	})

	_apply_bs_miti(data)
	_apply_custom_voucher_names(data)
	_apply_party_names(data, party_type)
	if show_remarks:
		_apply_voucher_remarks(data)
	return data


# ── Detail helpers ─────────────────────────────────────────────────────────────

def _fetch_all_details(entries):
	"""Batch-fetch all sub-row data for detailed_mapping mode in one pass per doctype."""
	si_names = [e["voucher_no"] for e in entries if e.get("voucher_type") == "Sales Invoice"]
	pe_names = [e["voucher_no"] for e in entries if e.get("voucher_type") == "Payment Entry"]
	je_names = [e["voucher_no"] for e in entries if e.get("voucher_type") == "Journal Entry"]
	pi_names = [e["voucher_no"] for e in entries if e.get("voucher_type") == "Purchase Invoice"]

	# ── Sales Invoice items + total VAT ──────────────────────────────────────
	si_items = {}
	si_info  = {}
	if si_names:
		rows = frappe.db.get_all(
			"Sales Invoice Item",
			filters={"parent": ("in", si_names)},
			fields=["parent", "item_code", "item_name", "qty", "uom", "rate", "amount"],
			order_by="parent, idx",
		)
		for r in rows:
			si_items.setdefault(r.parent, []).append(r)

		si_fields = ["name"]
		if frappe.db.has_column("Sales Invoice", "custom_total_vat_amount"):
			si_fields.append("custom_total_vat_amount")
		rows = frappe.db.get_all("Sales Invoice",
			filters={"name": ("in", si_names)}, fields=si_fields)
		si_info = {r.name: r for r in rows}

	# ── Payment Entry references + unallocated amount ─────────────────────────
	pe_refs = {}
	pe_info = {}
	if pe_names:
		rows = frappe.db.get_all(
			"Payment Entry Reference",
			filters={"parent": ("in", pe_names)},
			fields=["parent", "reference_doctype", "reference_name", "allocated_amount"],
			order_by="parent, idx",
		)
		for r in rows:
			pe_refs.setdefault(r.parent, []).append(r)

		rows = frappe.db.get_all("Payment Entry",
			filters={"name": ("in", pe_names)},
			fields=["name", "unallocated_amount", "payment_type"])
		pe_info = {r.name: r for r in rows}

	# ── Journal Entry remarks ─────────────────────────────────────────────────
	je_remarks = {}
	if je_names:
		rows = frappe.db.get_all("Journal Entry",
			filters={"name": ("in", je_names)},
			fields=["name", "user_remark"])
		je_remarks = {r.name: r.user_remark for r in rows}

	# ── Purchase Invoice items + VAT ──────────────────────────────────────────
	pi_items = {}
	pi_info  = {}
	if pi_names:
		rows = frappe.db.get_all(
			"Purchase Invoice Item",
			filters={"parent": ("in", pi_names)},
			fields=["parent", "item_code", "item_name", "qty", "uom", "rate", "amount"],
			order_by="parent, idx",
		)
		for r in rows:
			pi_items.setdefault(r.parent, []).append(r)

		pi_fields = ["name", "is_return"]
		if frappe.db.has_column("Purchase Invoice", "custom_vat_amount"):
			pi_fields.append("custom_vat_amount")
		if frappe.db.has_column("Purchase Invoice", "custom_vat_apply_on"):
			pi_fields.append("custom_vat_apply_on")
		rows = frappe.db.get_all("Purchase Invoice",
			filters={"name": ("in", pi_names)}, fields=pi_fields)
		pi_info = {r.name: r for r in rows}

	return {
		"si_items": si_items,
		"si_info":  si_info,
		"pe_refs":  pe_refs,
		"pe_info":  pe_info,
		"je_remarks": je_remarks,
		"pi_items": pi_items,
		"pi_info":  pi_info,
	}


def _build_detail_rows(voucher_type, voucher_no, main_debit, main_credit, detail_data, show_remarks=False):
	"""Return indented sub-rows for one voucher in detailed_mapping mode."""
	rows = []
	is_debit_side = main_debit > 0

	def _sub(code_col, desc, qty_str="", uom="", rate=None, amount=None):
		return {
			"date":          "",
			"miti":          "",
			"voucher_no":    code_col,
			"description":   desc,
			"remarks":       "",
			"detail_qty":    qty_str,
			"detail_uom":    uom,
			"detail_rate":   round(flt(rate), 2) if rate is not None else None,
			"detail_amount": round(flt(amount), 2) if amount is not None else None,
			"debit":         None,
			"credit":        None,
			"balance":       None,
			"indent":        1,
			"is_detail":     1,
			"bold":          0,
			"is_summary":    0,
		}

	# ── Sales Invoice / Sales Return ──────────────────────────────────────────
	if voucher_type == "Sales Invoice":
		items   = detail_data["si_items"].get(voucher_no, [])
		si_info = detail_data["si_info"].get(voucher_no, {})

		for item in items:
			qty_str = f"{flt(item.qty):.3f}"
			rows.append(_sub(
				item.item_code or "",
				item.item_name or item.item_code or "",
				qty_str, item.uom or "", flt(item.rate), flt(item.amount),
			))

		total_vat = flt(si_info.get("custom_total_vat_amount")) if si_info else 0
		rows.append(_sub("ADD :", "VAT", "", "", None, total_vat))

	# ── Purchase Invoice / Purchase Return ────────────────────────────────────
	elif voucher_type == "Purchase Invoice":
		items   = detail_data["pi_items"].get(voucher_no, [])
		pi_info = detail_data["pi_info"].get(voucher_no, {})

		for item in items:
			qty_str = f"{flt(item.qty):.3f}"
			rows.append(_sub(
				item.item_code or "",
				item.item_name or item.item_code or "",
				qty_str, item.uom or "", flt(item.rate), flt(item.amount),
			))

		vat_amt   = flt(pi_info.get("custom_vat_amount")) if pi_info else 0
		vat_apply = flt(pi_info.get("custom_vat_apply_on")) if pi_info else 0
		rate_str = f"{vat_apply:.2f}" if vat_apply else ""
		rows.append(_sub("ADD :", "VAT", rate_str, "", None, vat_amt))

	# ── Payment Entry ─────────────────────────────────────────────────────────
	elif voucher_type == "Payment Entry":
		refs    = detail_data["pe_refs"].get(voucher_no, [])
		pe_info = detail_data["pe_info"].get(voucher_no, {})

		for ref in refs:
			ref_name = ref.reference_name or ""
			ref_url  = f'/app/{(ref.reference_doctype or "").lower().replace(" ", "-")}/{ref_name}'
			ref_link = (
				f'<a href="{ref_url}" style="text-decoration:underline;cursor:pointer">{ref_name}</a>'
			) if ref_name else ""
			rows.append(_sub(
				"Invoice Adjustment",
				ref_link,
				f"{flt(ref.allocated_amount):,.2f}",
			))

		unalloc = flt(pe_info.get("unallocated_amount")) if pe_info else 0
		if unalloc:
			rows.append(_sub("Advance", "", f"{unalloc:,.2f}"))

	# ── Journal Entry ─────────────────────────────────────────────────────────
	elif voucher_type == "Journal Entry":
		if show_remarks:
			remark = (detail_data["je_remarks"].get(voucher_no) or "").strip()
			if remark:
				rows.append(_sub("", remark))

	return rows


# ── Merge helpers ──────────────────────────────────────────────────────────────

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
		key = (e.get("party"), e.get("date"), e.get("voucher_type"), e.get("voucher_no"))
		if key not in grouped:
			grouped[key] = {
				"party": e.get("party"),
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
			"party": g.get("party") or "",
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
		key = (e.get("party"), e.get("date"), e.get("voucher_type"), e.get("voucher_no"), (e.get("against") or "").strip())
		if key not in grouped:
			grouped[key] = {
				"party": e.get("party"),
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
			"party": g.get("party") or "",
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


# ── Enrichment helpers ─────────────────────────────────────────────────────────

def _apply_custom_voucher_names(rows):
	"""Replace voucher_no on main rows with custom display name if available."""
	if not rows:
		return

	vouchers_by_type = {}
	for r in rows:
		if r.get("is_detail"):
			continue
		vt = r.get("voucher_type")
		vn = r.get("voucher_no")
		if not vt or not vn:
			continue
		vouchers_by_type.setdefault(vt, set()).add(vn)

	def _get_name_map(doctype, fieldname, names):
		if not names or not frappe.db.has_column(doctype, fieldname):
			return {}
		result = frappe.db.get_all(doctype,
			filters={"name": ("in", list(names))},
			fields=["name", fieldname])
		return {r.name: r.get(fieldname) for r in result}

	# Sales Invoice uses custom_branch_name; all others use custom_name
	si_map = _get_name_map("Sales Invoice",    "custom_branch_name", vouchers_by_type.get("Sales Invoice"))
	pe_map = _get_name_map("Payment Entry",    "custom_name",        vouchers_by_type.get("Payment Entry"))
	pi_map = _get_name_map("Purchase Invoice", "custom_name",        vouchers_by_type.get("Purchase Invoice"))
	je_map = _get_name_map("Journal Entry",    "custom_name",        vouchers_by_type.get("Journal Entry"))

	type_map = {
		"Sales Invoice":    si_map,
		"Payment Entry":    pe_map,
		"Purchase Invoice": pi_map,
		"Journal Entry":    je_map,
	}

	for r in rows:
		if r.get("is_detail"):
			continue
		vt = r.get("voucher_type")
		vn = r.get("voucher_no")
		if not vt or not vn:
			continue
		custom = (type_map.get(vt) or {}).get(vn)
		if custom:
			r["voucher_no"] = custom


def _apply_party_names(data, party_type):
	"""Add party_name (display name) to each main row. Extra field — not in columns, invisible on screen."""
	party_ids = {
		r.get("party") for r in data
		if r.get("party") and not r.get("is_summary") and not r.get("is_detail") and not r.get("is_separator")
	}
	if not party_ids:
		return

	name_field = "customer_name" if party_type == "Customer" else "supplier_name"
	if not frappe.db.has_column(party_type, name_field):
		return

	rows = frappe.db.get_all(party_type,
		filters={"name": ("in", list(party_ids))},
		fields=["name", name_field])
	name_map = {r.name: r.get(name_field) for r in rows}

	for row in data:
		pid = row.get("party")
		if pid:
			row["party_name"] = name_map.get(pid) or pid


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
