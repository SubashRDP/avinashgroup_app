# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import os
import math
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


_PL_CAPACITY = {
	'Portrait':  {False: 64, True: 48},
	'Landscape': {False: 23, True: 26},
}
_PL_CHARS_PER_LINE = {'Portrait': 55, 'Landscape': 90}  # remark chars before it wraps to another line


def _pl_block_height(block, show_remarks, chars_per_line):
	h = 0.0
	for r in block:
		if r.get('is_detail'):
			h += 0.85   # detail rows use a smaller font (10px) so they're shorter
		elif r.get('is_separator'):
			h += 0.4
		else:
			h += 1.0  # main row or summary row
		rem = r.get('remarks') or ''
		if show_remarks and rem:
			h += max(1, math.ceil(len(rem) / chars_per_line)) * 0.85
	return h


def _pl_paginate(data, orientation, show_remarks, detailed, party_names=None, capacity_override=None, extra_header_lines=0):

	if not data:
		return []

	# capacity_override lets a specific caller (e.g. the Customer Statement) pack more
	# rows per page without changing the shared _PL_CAPACITY used by the report itself.
	if capacity_override:
		capacity = capacity_override
	else:
		capacity = _PL_CAPACITY.get(orientation, {}).get(bool(detailed), 18)
	# The header (repeated on every page) grows by one line per party name shown,
	# plus any extra header lines (e.g. the single-party Tax ID line).
	capacity -= len(party_names or []) + (extra_header_lines or 0)
	if capacity < 5:
		capacity = 5
	chars_per_line = _PL_CHARS_PER_LINE.get(orientation, 90)

	# Group into atomic blocks: a main/summary row plus the detail/separator rows that
	# follow it (a voucher's remark is a field on its main row, so it travels with it).
	blocks = []
	i, n = 0, len(data)
	while i < n:
		r = data[i]
		if r.get('is_detail') or r.get('is_separator') or r.get('is_remark'):
			# Continuation row with no preceding main row (shouldn't normally happen) —
			# attach it to the current block, starting one if needed.
			if not blocks:
				blocks.append([])
			blocks[-1].append(r)
			i += 1
			continue
		block = [r]
		i += 1
		while i < n and (data[i].get('is_detail') or data[i].get('is_separator')):
			block.append(data[i])
			i += 1
		blocks.append(block)

	# Pack blocks into pages, never splitting a block.
	pages, cur, used = [], [], 0.0
	for block in blocks:
		bh = _pl_block_height(block, show_remarks, chars_per_line)
		if cur and used + bh > capacity:
			pages.append(cur)
			cur, used = [], 0.0
		cur.extend(block)
		used += bh
	if cur:
		pages.append(cur)
	return pages


@frappe.whitelist()
def download_pdf(filters, orientation=None, report_title=None, filename=None, selected_columns=None, view=None, capacity_override=None):
	from frappe.utils.pdf import get_pdf

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	if isinstance(selected_columns, str):
		selected_columns = json.loads(selected_columns)

	orientation = orientation if orientation in ('Portrait', 'Landscape') else 'Landscape'
	# Default keeps the existing "Party Ledger - Customer/Supplier" heading; callers
	# (e.g. the Customer Statement portal) can override with their own title.
	report_title = report_title or 'Party Ledger - {0}'.format(filters.get('party_type') or 'Customer')

	_, data = execute(filters)

	# Only show party names in header when a specific party filter was applied.
	# In customer-wise grouped mode (2+ parties) each section already names its customer,
	# so we keep the page header clean instead of listing every party there.
	selected_parties = _normalize_multiselect(filters.get("party"))
	grouped_mode = len(selected_parties) != 1 and not filters.get("disable_party_grouping")
	seen = set()
	party_names = []
	if selected_parties and not grouped_mode:
		for row in data:
			pn = row.get('party_name') or ''
			for part in pn.split(','):
				part = part.strip()
				if part and part not in seen:
					seen.add(part)
					party_names.append(part)

	# When exactly one party is selected, show its Tax ID (VAT/PAN) under the name.
	party_tax_id = None
	if len(selected_parties) == 1:
		party_tax_id = frappe.db.get_value(
			filters.get("party_type") or "Customer", selected_parties[0], "tax_id"
		)

	pages = _pl_paginate(
		data, orientation, bool(filters.get('show_remarks')), bool(filters.get('detailed_mapping')),
		party_names, capacity_override=capacity_override,
		extra_header_lines=1 if party_tax_id else 0,
	)

	template_path = os.path.join(os.path.dirname(__file__), 'party_ledger_pdf.html')
	with open(template_path) as f:
		template_content = f.read()

	# Page numbers are rendered in the template body (manual pagination) so they work on
	html = frappe.render_template(
		template_content,
		{
			'filters': filters,
			'pages': pages,
			'total_pages': len(pages) or 1,
			'party_names': party_names,
			'party_tax_id': party_tax_id,
			# No Party column: in grouped mode each customer is named in a header row instead.
			'show_party': False,
			'fmt': _fmt_inr,
			'bal': _bal_str,
			'sc': selected_columns or [],
			'orientation': orientation,
			'report_title': report_title,
		}
	)

	if orientation == 'Portrait':
		margin_top, margin_right, margin_bottom, margin_left = '10mm', '5mm', '15mm', '5mm'
	else:
		margin_top, margin_right, margin_bottom, margin_left = '10mm', '15mm', '15mm', '15mm'

	options = {
		'page-size': 'A4',
		'orientation': orientation,
		'margin-top': margin_top,
		'margin-right': margin_right,
		'margin-bottom': margin_bottom,
		'margin-left': margin_left,
		'encoding': 'UTF-8',
		'enable-local-file-access': None,
	}
	pdf_data = get_pdf(html, options)

	frappe.response.filename = filename or 'party_ledger.pdf'
	frappe.response.filecontent = pdf_data
	# view=1 (Print) → open inline in the browser tab; otherwise download the file.
	frappe.response.type = 'pdf' if frappe.utils.cint(view) else 'download'


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


@frappe.whitelist()
def get_company_parties(party_type, company, txt=None):
	"""Party options limited to those that actually transact in the selected company.

	Customer/Supplier are global in ERPNext, so we scope the list by checking for any
	GL Entry of that party in the company. Keeps the dropdown relevant per company.
	"""
	party_type = party_type if party_type in ("Customer", "Supplier") else "Customer"
	if not company:
		return []

	name_field = "customer_name" if party_type == "Customer" else "supplier_name"
	like = f"%{(txt or '').strip()}%"

	return frappe.db.sql(
		f"""
		SELECT p.name AS value, p.`{name_field}` AS description
		FROM `tab{party_type}` p
		WHERE (p.name LIKE %(txt)s OR p.`{name_field}` LIKE %(txt)s)
		  AND EXISTS (
			SELECT 1 FROM `tabGL Entry` gle
			WHERE gle.party = p.name
			  AND gle.party_type = %(party_type)s
			  AND gle.company = %(company)s
			  AND gle.is_cancelled = 0
		  )
		ORDER BY p.`{name_field}`
		LIMIT 50
		""",
		{"txt": like, "party_type": party_type, "company": company},
		as_dict=True,
	)


def execute(filters=None):
	filters = filters or {}
	columns = get_columns(filters)

	if not filters.get("company") or not filters.get("from_date") or not filters.get("to_date"):
		return columns, []

	data = get_data(filters)
	return columns, data



def get_columns(filters=None):
	filters = filters or {}
	# Customer-wise grouping identifies each customer with a header row (code + name/VAT),
	# so there is no separate Party column.
	columns = [
		{"label": _("S.No"),        "fieldname": "sr_no",        "fieldtype": "Data",     "width": 40},
		{"label": _("Date"),        "fieldname": "date",         "fieldtype": "Date",     "width": 90},
		{"label": _("Miti (BS)"),   "fieldname": "miti",         "fieldtype": "Data",     "width": 200},
		{"label": _("Voucher No"),  "fieldname": "voucher_no",   "fieldtype": "Data",     "width": 200},
	]

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
	# Customer-wise grouping: one section per party (each with its own opening/running/
	# closing balance) plus a combined grand total. Group unless exactly one party is selected
	# (none selected → every party in the company; a single party → the plain flat ledger).
	grouped_mode = len(parties) != 1 and not filters.get("disable_party_grouping")

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

	# Exclude Journal Entries whose JV Type (custom_p_type) is "Contract Form" UNLESS the
	# "Show Contract Form" checkbox is ticked. Applied to the shared conditions so both the
	# opening balance and the period rows drop them (keeps the running balance consistent).
	# The customer_statement portal never sets this flag, so it always excludes them.
	if not filters.get("show_contract_form"):
		conditions += """ AND NOT EXISTS (
			SELECT 1 FROM `tabJournal Entry` je
			WHERE je.name = gle.voucher_no
			  AND gle.voucher_type = 'Journal Entry'
			  AND je.custom_p_type = %(exclude_jv_type)s
		)"""
		params["exclude_jv_type"] = "Contract Form"

	# ── Opening balance ────────────────────────────────────────────────────────
	# Match ERPNext General Ledger: opening = everything before the From Date PLUS any
	# opening-balance entries (is_opening = 'Yes') regardless of their posting date.
	# Those opening entries are excluded from the period rows below so they are not
	# counted/shown twice.
	# Grouped mode needs each party's own opening (GROUP BY party); otherwise one combined opening.
	if grouped_mode:
		opening_rows = frappe.db.sql(f"""
			SELECT
				gle.party                    AS party,
				COALESCE(SUM(gle.debit),  0) AS opening_debit,
				COALESCE(SUM(gle.credit), 0) AS opening_credit
			FROM `tabGL Entry` gle
			WHERE {conditions}
			  AND (gle.posting_date < %(from_date)s OR gle.is_opening = 'Yes')
			GROUP BY gle.party
		""", params, as_dict=True)
		opening_by_party = {
			r.party: (flt(r.opening_debit), flt(r.opening_credit)) for r in opening_rows
		}
		opening_debit = opening_credit = opening_balance = 0.0
	else:
		opening_row = frappe.db.sql(f"""
			SELECT
				COALESCE(SUM(gle.debit),  0) AS opening_debit,
				COALESCE(SUM(gle.credit), 0) AS opening_credit
			FROM `tabGL Entry` gle
			WHERE {conditions}
			  AND (gle.posting_date < %(from_date)s OR gle.is_opening = 'Yes')
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
			gle.account       AS account,
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
		  AND COALESCE(gle.is_opening, 'No') != 'Yes'
		ORDER BY gle.posting_date ASC, gle.creation ASC
	""", params, as_dict=True)

	if detailed_mapping:
		entries = _merge_entries_detailed(entries)
	else:
		entries = _merge_entries(entries)

	# Batch-fetch all detail data upfront when detailed_mapping is on (avoids N+1 queries)
	detail_data = _fetch_all_details(entries) if detailed_mapping else {}

	if grouped_mode:
		data = _build_grouped_data(
			entries, opening_by_party, party_type,
			detail_data, detailed_mapping, show_remarks,
		)
	else:
		data, _pd, _pc, _run = _build_section_rows(
			entries, opening_debit, opening_credit,
			detail_data, detailed_mapping, show_remarks,
			closing_voucher_no="NPR",
		)

	_apply_bs_miti(data)
	_apply_custom_voucher_names(data)
	# Grouped mode sets party_name only on each section's first row (the name shows once);
	# the flat layout fills it on every row via _apply_party_names.
	if not grouped_mode:
		_apply_party_names(data, party_type)
	if show_remarks:
		_apply_voucher_remarks(data)
	return data


# ── Section builders ───────────────────────────────────────────────────────────

def _build_section_rows(entries, opening_debit, opening_credit, detail_data,
						detailed_mapping, show_remarks, closing_voucher_no="NPR",
						section_mode=False):
	"""Build one ledger section: Opening row → entry rows → For the Periods → Closing.

	Returns (rows, period_debit, period_credit, closing_balance). Used both for the
	whole ledger (non-grouped) and for each customer's section (grouped mode).
	section_mode tags the subtotal rows so the PDF can keep them light (one thin line
	per customer) instead of the heavy boxed rules used for the flat/grand-total totals.
	"""
	# is_section: 1 on a per-customer subtotal row → light styling in the PDF.
	sec = 1 if section_mode else 0
	rows = []
	opening_balance = opening_debit - opening_credit

	rows.append({
		"date":        "",
		"miti":        "",
		"voucher_no":  "",
		"description": "Opening Balance",
		"debit":       opening_debit,
		"credit":      opening_credit,
		"balance":     opening_balance,
		"bold":        1,
		"is_summary":  1,
		"is_section":  sec,
		"kind":        "opening",
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
		rows.append({
			"sr_no":        sr_no,
			"date":         entry.get("date"),
			"miti":         "",
			"voucher_no":   entry.get("voucher_no"),
			# Real document id for the navigation link — kept separate so a custom
			# display name (applied later) doesn't break the href.
			"voucher_link": entry.get("voucher_no"),
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
			rows.extend(sub_rows)
			rows.append({"is_separator": 1, "balance": None})

	# ── For the Periods row ────────────────────────────────────────────────────
	period_net = round(period_debit - period_credit, 2)
	rows.append({
		"date":        "",
		"miti":        "",
		"voucher_no":  "",
		"description": "For the Periods",
		"debit":       round(period_debit,  2) if period_debit  else None,
		"credit":      round(period_credit, 2) if period_credit else None,
		"balance":     period_net or None,
		"bold":        1,
		"is_summary":  1,
		"is_section":  sec,
		"kind":        "period",
	})

	# ── Closing Balance row ────────────────────────────────────────────────────
	cumulative_debit  = round(opening_debit  + period_debit,  2)
	cumulative_credit = round(opening_credit + period_credit, 2)
	rows.append({
		"date":        "",
		"miti":        "",
		"voucher_no":  closing_voucher_no,
		"description": "Closing Balance",
		"debit":       cumulative_debit  if cumulative_debit  else None,
		"credit":      cumulative_credit if cumulative_credit else None,
		"balance":     running_balance   if running_balance   else None,
		"bold":        1,
		"is_summary":  1,
		"is_section":  sec,
		"kind":        "closing",
	})

	return rows, period_debit, period_credit, running_balance


def _party_info_map(party_type, party_ids):
	"""Map party id → {"name": display name, "tax_id": VAT/PAN}. Name falls back to the id."""
	party_ids = [p for p in party_ids if p]
	if not party_ids:
		return {}
	name_field = "customer_name" if party_type == "Customer" else "supplier_name"
	fields = ["name"]
	has_name = frappe.db.has_column(party_type, name_field)
	has_tax = frappe.db.has_column(party_type, "tax_id")
	if has_name:
		fields.append(name_field)
	if has_tax:
		fields.append("tax_id")
	rows = frappe.db.get_all(party_type, filters={"name": ("in", party_ids)}, fields=fields)
	return {
		r.name: {"name": (r.get(name_field) if has_name else None) or r.name,
				 "tax_id": (r.get("tax_id") if has_tax else None)}
		for r in rows
	}


def _customer_header_label(info, party):
	"""'<Customer Name> (VAT/PAN No.: <tax_id>)' — tax id omitted when missing."""
	name = (info or {}).get("name") or party
	tax_id = (info or {}).get("tax_id")
	return f"{name} (VAT/PAN No.: {tax_id})" if tax_id else name


def _build_grouped_data(entries, opening_by_party, party_type, detail_data,
						detailed_mapping, show_remarks):
	"""Customer-wise layout:
	    Total Opening Balance (all customers)
	    ── per customer ──
	      header: <Customer Code> | <Customer Name (VAT/PAN No.)>
	      Opening Balance → transactions → For the Periods → Closing Balance
	    Total Period Closing  (all customers)
	    Total Closing Balance (all customers)
	"""
	from collections import OrderedDict

	entries_by_party = OrderedDict()
	for e in entries:
		entries_by_party.setdefault(e.get("party") or "", []).append(e)

	all_parties = set(opening_by_party) | set(entries_by_party)
	info_map = _party_info_map(party_type, all_parties)
	# Display A → B → C: order sections by the party's display name.
	ordered = sorted(all_parties, key=lambda p: ((info_map.get(p) or {}).get("name") or p or "").lower())

	sections = []
	g_open_debit = g_open_credit = 0.0
	g_period_debit = g_period_credit = 0.0
	g_closing = 0.0

	for party in ordered:
		open_debit, open_credit = opening_by_party.get(party, (0.0, 0.0))
		party_entries = entries_by_party.get(party, [])
		# Skip a selected party with no opening and no activity in the period.
		if not party_entries and open_debit == 0 and open_credit == 0:
			continue

		section_rows, period_debit, period_credit, closing = _build_section_rows(
			party_entries, open_debit, open_credit,
			detail_data, detailed_mapping, show_remarks,
			closing_voucher_no="",  # NPR label only on the grand-total closing
			section_mode=True,      # light per-customer subtotals + one separator line
		)
		# Customer header: code in the Date column, "Name (VAT/PAN No.)" in the Miti column.
		sections.append({
			"cust_code":  party,
			"cust_label": _customer_header_label(info_map.get(party), party),
			"date": "", "miti": "", "voucher_no": "", "description": "",
			"balance": None, "is_customer_header": 1, "bold": 1,
		})
		sections.extend(section_rows)

		g_open_debit    += open_debit
		g_open_credit   += open_credit
		g_period_debit  += period_debit
		g_period_credit += period_credit
		g_closing       += closing

	data = []
	# ── Total Opening Balance (all customers) — shown up front ──
	data.append({
		"date": "", "miti": "", "voucher_no": "", "description": "Total Opening Balance",
		"debit":   round(g_open_debit,  2),
		"credit":  round(g_open_credit, 2),
		"balance": round(g_open_debit - g_open_credit, 2),
		"bold": 1, "is_summary": 1, "kind": "grand_opening",
	})
	data.extend(sections)
	# ── Totals across all customers — at the end ──
	data.append({
		"date": "", "miti": "", "voucher_no": "", "description": "Total Period Closing",
		"debit":   round(g_period_debit,  2) if g_period_debit  else None,
		"credit":  round(g_period_credit, 2) if g_period_credit else None,
		"balance": round(g_period_debit - g_period_credit, 2) or None,
		"bold": 1, "is_summary": 1, "kind": "grand_period",
	})
	cum_debit  = round(g_open_debit  + g_period_debit,  2)
	cum_credit = round(g_open_credit + g_period_credit, 2)
	data.append({
		"date": "", "miti": "", "voucher_no": "NPR", "description": "Total Closing Balance",
		"debit":   cum_debit  if cum_debit  else None,
		"credit":  cum_credit if cum_credit else None,
		"balance": round(g_closing, 2) or None,
		"bold": 1, "is_summary": 1, "kind": "grand_closing",
	})
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

	Exception — Journal Entries: a single JE can post both a debit and a credit to
	the SAME party across two different accounts (e.g. a contra between deposit
	accounts). We keep those as separate lines (group also by account) so each
	account posting shows on its own row, with the account as its description —
	instead of collapsing into one line showing both a debit and a credit.
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
		vt = e.get("voucher_type")
		# Journal Entries split by account; all other voucher types merge per voucher.
		if vt == "Journal Entry":
			key = (e.get("party"), e.get("date"), vt, e.get("voucher_no"), e.get("account"))
		else:
			key = (e.get("party"), e.get("date"), vt, e.get("voucher_no"))
		if key not in grouped:
			grouped[key] = {
				"party": e.get("party"),
				"date": e.get("date"),
				"voucher_type": vt,
				"voucher_no": e.get("voucher_no"),
				"account": e.get("account"),
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

		# For a JE line, the account is the meaningful label (not the generic "Journal Entry").
		if vt == "Journal Entry":
			description = g.get("account") or _pick_description(descriptions, vt)
		else:
			description = _pick_description(descriptions, vt)

		out.append({
			"party": g.get("party") or "",
			"date": g.get("date"),
			"voucher_type": vt,
			"voucher_no": g.get("voucher_no"),
			"description": description,
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
