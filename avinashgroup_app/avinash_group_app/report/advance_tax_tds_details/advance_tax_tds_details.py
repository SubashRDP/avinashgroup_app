# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.utils import flt, getdate

# Tax Withholding Category names encode everything, e.g.
#   "2.5% -11124 TDS-Other Entities"  ->  rate 2.5, khata 11124, title "TDS-Other Entities"
CATEGORY_RE = re.compile(r"^\s*([\d.]+)\s*%\s*-?\s*(\d+)\s+(.+?)\s*$")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		frappe.throw(_("Please select a Company."))

	from_date, to_date = _resolve_period(filters)

	rows = _get_tds_rows(filters.company, from_date, to_date)
	columns = _get_columns()
	data = _build_rows(rows)
	return columns, data


def _resolve_period(filters):
	"""Return (from_date, to_date) from the From/To Date filters.

	The dates may be picked in AD or BS (the rdp Nepali-date widget writes the AD
	value back to from_date/to_date).
	"""
	if not (filters.get("from_date") and filters.get("to_date")):
		frappe.throw(_("Select From Date and To Date."))

	return getdate(filters.from_date), getdate(filters.to_date)


def _get_tds_rows(company, from_date, to_date):
	"""One aggregated row per (supplier, withholding category) for the period.

	karobar = sum of item amounts that have Apply TDS ticked (un-ticked items
	          are excluded, i.e. invoice total minus the un-ticked lines).
	tds     = sum of item TDS amounts.
	"""
	return frappe.db.sql(
		"""
		SELECT
			pi.supplier_name AS supplier_name,
			sup.tax_id AS pan,
			pi.custom_tax_withholding_category_custom AS category,
			SUM(CASE WHEN it.apply_tds = 1 THEN it.amount ELSE 0 END) AS turnover,
			SUM(it.custom_tds_amount) AS tds_amount,
			MAX(CASE WHEN it.custom_tds_apply_on = 'Amount' THEN 1 ELSE 0 END) AS amount_based
		FROM `tabPurchase Invoice` pi
		INNER JOIN `tabPurchase Invoice Item` it ON it.parent = pi.name
		LEFT JOIN `tabSupplier` sup ON sup.name = pi.supplier
		WHERE pi.company = %(company)s
			AND pi.docstatus = 1
			AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND pi.custom_tax_withholding_category_custom IS NOT NULL
			AND pi.custom_tax_withholding_category_custom != ''
		GROUP BY pi.supplier_name, pi.custom_tax_withholding_category_custom, sup.tax_id
		HAVING tds_amount != 0 OR turnover != 0
		ORDER BY pi.supplier_name
		""",
		{"company": company, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)


def _parse_category(name):
	"""Return (rate_str, khata, title) parsed from a withholding category name."""
	name = (name or "").strip()
	# with account no: "2.5% -11124 TDS-Other Entities"
	match = CATEGORY_RE.match(name)
	if match:
		return match.group(1), match.group(2), match.group(3).strip()
	# without account no: "1.5% - TDS Payable" -> rate 1.5, no khata, title "TDS Payable"
	match = re.match(r"^([\d.]+)\s*%\s*-?\s*(.+?)$", name)
	if match:
		return match.group(1), "", match.group(2).strip()
	return "", "", name


def _get_columns():
	return [
		{"label": _("क्र.सं."), "fieldname": "sn", "fieldtype": "Data", "width": 55, "align": "center"},
		{"label": _("नाम"), "fieldname": "party", "fieldtype": "Data", "width": 260},
		{"label": _("कारोबार रकम"), "fieldname": "turnover", "fieldtype": "Float", "precision": 2, "width": 140},
		{"label": _("खाता नं"), "fieldname": "account_no", "fieldtype": "Data", "width": 90, "align": "center"},
		{"label": _("अग्रिम कर रकम"), "fieldname": "tds_amount", "fieldtype": "Float", "precision": 2, "width": 140},
		{"label": _("पान नम्बर"), "fieldname": "pan", "fieldtype": "Data", "width": 120},
		{"label": _("रेट"), "fieldname": "rate", "fieldtype": "Data", "width": 80, "align": "right"},
	]


def _build_rows(rows):
	# group (supplier, category) rows into sections keyed by khata (account no)
	sections = {}
	for r in rows:
		rate, khata, title = _parse_category(r.category)
		section = sections.setdefault(khata, {"title": title, "khata": khata, "rows": []})
		# keep the first non-empty title seen for the account
		if not section["title"] and title:
			section["title"] = title
		section["rows"].append(
			frappe._dict(
				supplier_name=r.supplier_name,
				pan=r.pan or "",
				turnover=flt(r.turnover),
				tds_amount=flt(r.tds_amount),
				rate="amount" if r.amount_based else ("{0}%".format(rate) if rate else ""),
			)
		)

	data = []
	serial = 0
	grand_turnover = grand_tds = 0.0

	# order sections by khata (numeric where possible)
	for khata in sorted(sections, key=lambda k: (int(k) if k.isdigit() else 9999999, k)):
		section = sections[khata]

		# section header: category title goes in the कारोबार रकम (turnover) column,
		# account no in खाता नं; the JS formatter blanks the other cells (no 0.00)
		data.append(
			{"_section": 1, "section_title": section["title"], "account_no": section["khata"]}
		)

		sec_turnover = sec_tds = 0.0
		for row in sorted(section["rows"], key=lambda x: (x.supplier_name or "")):
			serial += 1
			sec_turnover += row.turnover
			sec_tds += row.tds_amount
			data.append(
				{
					"sn": serial,
					"party": row.supplier_name,
					"turnover": row.turnover,
					"tds_amount": row.tds_amount,
					"pan": row.pan,
					"rate": row.rate,
				}
			)

		# section total (English label; Nepali stays in the column headers only)
		data.append(
			{
				"party": "TOTAL ({0})".format(section["khata"] or section["title"]),
				"turnover": sec_turnover,
				"tds_amount": sec_tds,
				"_bold": 1,
			}
		)
		data.append({})  # spacer between sections
		grand_turnover += sec_turnover
		grand_tds += sec_tds

	if data:
		data.append(
			{
				"party": "GRAND TOTAL",
				"turnover": grand_turnover,
				"tds_amount": grand_tds,
				"_bold": 1,
			}
		)
	return data


