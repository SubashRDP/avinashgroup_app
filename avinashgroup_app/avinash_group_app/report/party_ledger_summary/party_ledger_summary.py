# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import os
import json
import frappe
from frappe import _
from frappe.utils import flt
from markupsafe import Markup


# ── Formatting helpers (kept local so this report is self-contained) ─────────────

def _fmt_inr(v):
	"""Format a number in Indian style (e.g. 1,50,000.00). Blank for zero/None."""
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
	"""Bold balance string with DB/CR suffix as safe HTML Markup (positive = DB)."""
	if v is None or v == '':
		return Markup('')
	try:
		n = float(v)
	except (TypeError, ValueError):
		return Markup('')
	suffix = 'DB' if n >= 0 else 'CR'
	formatted = _fmt_inr(abs(n)) or '0.00'
	return Markup(f'<b>{formatted}</b>&thinsp;<small>{suffix}</small>')


def _drcr(v):
	"""Dr / Cr indicator from a signed balance (positive = Dr). Blank for zero/empty."""
	if v is None or v == '' or round(flt(v), 2) == 0:
		return ""
	return "Dr" if flt(v) > 0 else "Cr"


def _normalize_multiselect(value):
	"""Return a cleaned list for MultiSelectList / Link-like inputs."""
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


# ── Report entry point ───────────────────────────────────────────────────────

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
	code_label = _("Customer Code") if party_type == "Customer" else _("Vendor Code")
	name_label = _("Customer Name") if party_type == "Customer" else _("Vendor Name")

	return [
		# Kept as Data (not Link) so the inline column filter can search it; the JS
		# formatter renders it as a clickable link to the Customer/Supplier master.
		{"label": code_label,      "fieldname": "party",      "fieldtype": "Data",     "width": 120},
		{"label": name_label,      "fieldname": "party_name", "fieldtype": "Data",     "width": 280, "align": "left"},
		{"label": _("Vat/Pan No"), "fieldname": "tax_id",     "fieldtype": "Data",     "width": 130},
		{"label": _("Opening"),  "fieldname": "opening",    "fieldtype": "Currency", "width": 150},
		{"label": _("Debit"),    "fieldname": "debit",      "fieldtype": "Currency", "width": 140},
		{"label": _("Credit"),   "fieldname": "credit",     "fieldtype": "Currency", "width": 140},
		{"label": _("Closing"),  "fieldname": "closing",    "fieldtype": "Currency", "width": 160},
	]


def get_data(filters):
	company     = filters.get("company")
	from_date   = filters.get("from_date")
	to_date     = filters.get("to_date")
	party_type  = filters.get("party_type") or "Customer"
	report_type = filters.get("report_type") or "Super Summary"
	parties      = _normalize_multiselect(filters.get("party"))
	party_groups = _normalize_multiselect(filters.get("party_group"))
	show_zero    = bool(filters.get("show_zero_balance"))

	group_field = "customer_group" if party_type == "Customer" else "supplier_group"
	name_field  = "customer_name"  if party_type == "Customer" else "supplier_name"

	# Master-level filter (explicit party + group). When present it constrains the GL
	# query and — with Show Zero Balance — seeds the displayed party set.
	master_filter = {}
	if parties:
		master_filter["name"] = ("in", parties)
	if party_groups:
		master_filter[group_field] = ("in", party_groups)

	allowed = None
	if master_filter:
		allowed = set(frappe.get_all(party_type, filters=master_filter, pluck="name"))
		if not allowed:
			return []

	# ── One aggregate row per party (opening before the period, debit/credit in it) ──
	conditions = (
		"gle.is_cancelled = 0 AND gle.company = %(company)s AND gle.party_type = %(party_type)s"
		" AND gle.party IS NOT NULL AND gle.party != ''"
	)
	params = {
		"company":    company,
		"from_date":  from_date,
		"to_date":    to_date,
		"party_type": party_type,
	}
	if allowed is not None:
		conditions += " AND gle.party IN %(allowed)s"
		params["allowed"] = tuple(allowed)

	# Opening matches ERPNext General Ledger: everything before the From Date PLUS any
	# opening-balance entries (is_opening = 'Yes') regardless of posting date. Those
	# opening entries are excluded from the period debit/credit so they aren't counted twice.
	agg_rows = frappe.db.sql(f"""
		SELECT
			gle.party AS party,
			COALESCE(SUM(CASE WHEN gle.posting_date < %(from_date)s OR gle.is_opening = 'Yes'
			                  THEN gle.debit - gle.credit END), 0) AS opening,
			COALESCE(SUM(CASE WHEN gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
			                   AND COALESCE(gle.is_opening, 'No') != 'Yes'
			                  THEN gle.debit  END), 0)             AS debit,
			COALESCE(SUM(CASE WHEN gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
			                   AND COALESCE(gle.is_opening, 'No') != 'Yes'
			                  THEN gle.credit END), 0)             AS credit
		FROM `tabGL Entry` gle
		WHERE {conditions}
		GROUP BY gle.party
	""", params, as_dict=True)
	agg = {r["party"]: r for r in agg_rows}

	# ── Which parties to display ─────────────────────────────────────────────
	# agg already holds every party with GL activity in the SELECTED COMPANY. Show Zero
	# Balance must stay company-scoped — it only stops hiding the zero-closing company
	# parties (handled by the skip below); it must NOT pull in parties from other companies.
	display_ids = set(agg.keys())

	if not display_ids:
		return []

	# ── Names + groups for the displayed parties ─────────────────────────────
	# tax_id (Tax tab) feeds the "Vat/Pan No" column; guard in case a site lacks it.
	has_tax = frappe.db.has_column(party_type, "tax_id")
	info_fields = ["name", f"{name_field} as party_name", f"{group_field} as party_group"]
	if has_tax:
		info_fields.append("tax_id")
	info_rows = frappe.get_all(
		party_type,
		filters={"name": ("in", list(display_ids))},
		fields=info_fields,
	)
	info = {r["name"]: r for r in info_rows}

	# The party stores the group's id (docname, e.g. "NGK-CGR-0002"); resolve it to the
	# readable group name (e.g. "Bulk/Retail") for the group header / subtotal labels.
	group_doctype  = "Customer Group" if party_type == "Customer" else "Supplier Group"
	group_namefield = "customer_group_name" if party_type == "Customer" else "supplier_group_name"
	group_ids = {r.get("party_group") for r in info_rows if r.get("party_group")}
	group_name_map = {}
	if group_ids:
		group_name_map = {
			g["name"]: g.get(group_namefield)
			for g in frappe.get_all(
				group_doctype,
				filters={"name": ("in", list(group_ids))},
				fields=["name", group_namefield],
			)
		}

	# ── Build per-party records ──────────────────────────────────────────────
	records = []
	for pid in display_ids:
		if not pid:
			continue
		a = agg.get(pid) or {}
		opening = flt(a.get("opening"))
		debit   = flt(a.get("debit"))
		credit  = flt(a.get("credit"))
		closing = round(opening + debit - credit, 2)

		# Hide net-zero parties unless Show Zero Balance is on
		if not show_zero and round(closing, 2) == 0:
			continue

		m = info.get(pid) or {}
		group_id = m.get("party_group")
		records.append({
			"party":       pid,
			"party_name":  m.get("party_name") or pid,
			"tax_id":      m.get("tax_id") or "",
			"party_group": group_name_map.get(group_id) or group_id or _("Ungrouped"),
			"opening":     round(opening, 2),
			"debit":       round(debit, 2),
			"credit":      round(credit, 2),
			"closing":     closing,
		})

	if not records:
		return []

	if report_type == "Group Wise":
		return _build_group_wise(records, party_type)
	return _build_super_summary(records, party_type)


def _build_super_summary(records, party_type):
	"""Flat list of parties + a single grand-total row at the end."""
	records.sort(key=lambda r: (r["party"] or ""))
	data = list(records)

	n        = len(records)
	t_open   = round(sum(r["opening"] for r in records), 2)
	t_debit  = round(sum(r["debit"]   for r in records), 2)
	t_credit = round(sum(r["credit"]  for r in records), 2)
	t_close  = round(sum(r["closing"] for r in records), 2)

	noun = "Customers" if party_type == "Customer" else "Vendors"
	data.append({
		"party":        "",
		"party_name":   "Closing Totals ({0} {1})".format(n, noun),
		"opening":      t_open,
		"debit":        t_debit,
		"credit":       t_credit,
		"closing":      t_close,
		"is_grand_total": 1,
		"bold":         1,
	})
	return data


def _build_group_wise(records, party_type):
	"""Parties bucketed by group: group header → party rows → 'Group Total for : X'."""
	records.sort(key=lambda r: ((r["party_group"] or "").lower(), r["party"] or ""))

	data = []
	cur_group = None
	acc = None

	def _flush(acc):
		data.append({
			"party":        "",
			"party_name":   "Group Total for : {0}".format(acc["group"]),
			"opening":      round(acc["opening"], 2),
			"debit":        round(acc["debit"],   2),
			"credit":       round(acc["credit"],  2),
			"closing":      round(acc["closing"], 2),
			"is_group_total": 1,
			"bold":         1,
		})

	for r in records:
		g = r["party_group"]
		if g != cur_group:
			if acc:
				_flush(acc)
			cur_group = g
			acc = {"group": g, "opening": 0.0, "debit": 0.0, "credit": 0.0, "closing": 0.0}
			data.append({
				"party":      g,
				"party_name": "",
				"is_group_header": 1,
				"bold":       1,
			})
		data.append(r)
		acc["opening"] += r["opening"]
		acc["debit"]   += r["debit"]
		acc["credit"]  += r["credit"]
		acc["closing"] += r["closing"]

	if acc:
		_flush(acc)

	# Group Wise intentionally has no grand total — only per-group subtotals.
	return data


# ── Filter helper: parties that actually transact in the selected company ────────

@frappe.whitelist()
@frappe.whitelist()
def get_company_party_groups(party_type, company, txt=None):
	"""Party groups that actually have parties transacting in the selected company."""
	party_type = party_type if party_type in ("Customer", "Supplier") else "Customer"
	if not company:
		return []

	group_field = "customer_group" if party_type == "Customer" else "supplier_group"
	group_doctype = "Customer Group" if party_type == "Customer" else "Supplier Group"
	group_name_field = "customer_group_name" if party_type == "Customer" else "supplier_group_name"
	like = f"%{(txt or '').strip()}%"

	# value = group id (used by the report filter); description = readable group name.
	return frappe.db.sql(
		f"""
		SELECT DISTINCT p.`{group_field}` AS value, g.`{group_name_field}` AS description
		FROM `tab{party_type}` p
		JOIN `tab{group_doctype}` g ON g.name = p.`{group_field}`
		WHERE p.`{group_field}` IS NOT NULL
		  AND (p.`{group_field}` LIKE %(txt)s OR g.`{group_name_field}` LIKE %(txt)s)
		  AND EXISTS (
			SELECT 1 FROM `tabGL Entry` gle
			WHERE gle.party = p.name
			  AND gle.party_type = %(party_type)s
			  AND gle.company = %(company)s
			  AND gle.is_cancelled = 0
		  )
		ORDER BY g.`{group_name_field}`
		LIMIT 50
		""",
		{"txt": like, "party_type": party_type, "company": company},
		as_dict=True,
	)


@frappe.whitelist()
def get_company_parties(party_type, company, txt=None):
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


# ── PDF / Print pipeline ─────────────────────────────────────────────────────

# Body rows per page (header band is repeated per page via thead). Summary rows are
# single-line, so a simple count-based pack is enough — conservative on purpose.
_SUM_CAPACITY = {'Portrait': 58, 'Landscape': 24}


def _paginate(rows, orientation):
	"""Pack rows into pages by count; never leave a group header as the last row."""
	cap = _SUM_CAPACITY.get(orientation, 20)
	pages, cur = [], []
	for r in rows:
		cur.append(r)
		if len(cur) >= cap:
			if cur[-1].get("is_group_header") and len(cur) > 1:
				last = cur.pop()
				pages.append(cur)
				cur = [last]
			else:
				pages.append(cur)
				cur = []
	if cur:
		pages.append(cur)
	return pages


@frappe.whitelist()
def export_xlsx(filters):
	"""Excel-only layout: Opening/Closing as magnitude, each followed by a Dr/Cr column.
	The on-screen report and PDF are unchanged — this layout lives only in the export."""
	from frappe.utils.xlsxutils import make_xlsx

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))

	columns, data = execute(filters)
	# First three labels (Customer/Supplier Code, Name, Vat/Pan) come from the report itself.
	base_labels = [c["label"] for c in columns[:3]]
	headers = base_labels + ["Opening", "Opening Dr/Cr", "Debit", "Credit", "Closing", "Closing Dr/Cr"]

	rows = [headers]
	for d in data:
		if not isinstance(d, dict):
			continue
		# Group-header rows carry only the group name, no balances.
		if d.get("is_group_header"):
			rows.append([d.get("party") or "", "", "", "", "", "", "", "", ""])
			continue

		opening = flt(d.get("opening"))
		closing = flt(d.get("closing"))
		rows.append([
			d.get("party") or "",
			d.get("party_name") or "",
			d.get("tax_id") or "",
			round(abs(opening), 2), _drcr(opening),     # Opening magnitude + Dr/Cr
			flt(d.get("debit")),
			flt(d.get("credit")),
			round(abs(closing), 2), _drcr(closing),     # Closing magnitude + Dr/Cr
		])

	xlsx = make_xlsx(rows, "Party Ledger Summary")
	frappe.response.filename = "party_ledger_summary.xlsx"
	frappe.response.filecontent = xlsx.getvalue()
	frappe.response.type = "binary"


@frappe.whitelist()
def download_pdf(filters, orientation=None, report_title=None, filename=None, view=None, selected_columns=None):
	from frappe.utils.pdf import get_pdf

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	if isinstance(selected_columns, str):
		selected_columns = json.loads(selected_columns)

	orientation = orientation if orientation in ('Portrait', 'Landscape') else 'Portrait'
	party_type  = filters.get('party_type') or 'Customer'
	report_type = filters.get('report_type') or 'Super Summary'
	report_title = report_title or 'Party Ledger - {0} - {1}'.format(party_type, report_type)

	_, data = execute(filters)
	pages = _paginate(data, orientation)

	template_path = os.path.join(os.path.dirname(__file__), 'party_ledger_summary_pdf.html')
	with open(template_path) as f:
		template_content = f.read()

	html = frappe.render_template(
		template_content,
		{
			'filters':      filters,
			'pages':        pages,
			'total_pages':  len(pages) or 1,
			'fmt':          _fmt_inr,
			'bal':          _bal_str,
			'sc':           selected_columns or [],
			'orientation':  orientation,
			'report_title': report_title,
		},
	)

	if orientation == 'Portrait':
		margins = ('10mm', '5mm', '15mm', '5mm')
	else:
		margins = ('10mm', '15mm', '15mm', '15mm')

	options = {
		'page-size':   'A4',
		'orientation': orientation,
		'margin-top':    margins[0],
		'margin-right':  margins[1],
		'margin-bottom': margins[2],
		'margin-left':   margins[3],
		'encoding':    'UTF-8',
		'enable-local-file-access': None,
	}
	pdf_data = get_pdf(html, options)

	frappe.response.filename = filename or 'party_ledger_summary.pdf'
	frappe.response.filecontent = pdf_data
	# view=1 (Print) → open inline in the browser tab; otherwise download the file.
	frappe.response.type = 'pdf' if frappe.utils.cint(view) else 'download'
