# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import json
import os

import frappe
from frappe import _


def _fmt_inr(v):
	if not v:
		return ''
	import locale
	try:
		locale.setlocale(locale.LC_ALL, 'en_IN.UTF-8')
		return locale.format_string('%.2f', v, grouping=True)
	except Exception:
		return '{:,.2f}'.format(v)


def _get_display_names(filters):
	supplier_display = ''
	ptype_display = ''
	if filters.get('supplier'):
		rows = frappe.db.get_all('Supplier',
			filters=[['name', 'in', filters.get('supplier')]],
			fields=['supplier_name'], order_by='supplier_name asc')
		supplier_display = ', '.join(r.supplier_name for r in rows)
	if filters.get('purchase_type'):
		ptype_display = ', '.join(filters.get('purchase_type'))
	return supplier_display, ptype_display


@frappe.whitelist()
def get_print_html(filters, selected_columns=None, orientation=None):
	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	if isinstance(selected_columns, str):
		selected_columns = json.loads(selected_columns)

	_, data = execute(filters)
	supplier_display, ptype_display = _get_display_names(filters)

	template_path = os.path.join(os.path.dirname(__file__), 'purchase_register_report_pdf.html')
	with open(template_path) as f:
		template_content = f.read()

	return frappe.render_template(template_content, {
		'filters': filters,
		'data': data,
		'fmt': _fmt_inr,
		'sc': selected_columns or [],
		'is_html_view': True,
		'orientation': orientation or 'Landscape',
		'supplier_display': supplier_display,
		'ptype_display': ptype_display,
	})


@frappe.whitelist()
def download_pdf(filters, orientation=None, selected_columns=None):
	from frappe.utils.pdf import get_pdf

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	if isinstance(selected_columns, str):
		selected_columns = json.loads(selected_columns)

	orientation = orientation if orientation in ('Portrait', 'Landscape') else 'Landscape'

	_, data = execute(filters)
	supplier_display, ptype_display = _get_display_names(filters)

	template_path = os.path.join(os.path.dirname(__file__), 'purchase_register_report_pdf.html')
	with open(template_path) as f:
		template_content = f.read()

	# sc = columns currently shown in the report (picked in the print dialog, or whatever
	# is left after removing columns in the datatable). Empty => show all.
	# Page numbers are rendered in the template body (manual pagination) so they work on
	# plain/unpatched wkhtmltopdf — no --footer-html (needs patched-Qt, silently ignored).
	html = frappe.render_template(template_content, {
		'filters': filters,
		'supplier_display': supplier_display,
		'ptype_display': ptype_display,
		'data': data,
		'fmt': _fmt_inr,
		'sc': selected_columns or [],
		'orientation': orientation,
	})

	options = {
		'page-size': 'A4',
		'orientation': orientation,
		'margin-top': '10mm',
		'margin-right': '8mm',
		'margin-bottom': '15mm',
		'margin-left': '8mm',
		'encoding': 'UTF-8',
		'enable-local-file-access': None,
	}
	pdf_data = get_pdf(html, options)

	frappe.response.filename = 'purchase_register.pdf'
	frappe.response.filecontent = pdf_data
	frappe.response.type = 'download'


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)

	# Purchase Returns store amounts as negatives in the DB. Show them as positives in the register.
	if filters.get("is_return") and data:
		numeric_fields = [c["fieldname"] for c in columns if c.get("fieldtype") in ("Currency", "Float")]
		for row in data:
			for f in numeric_fields:
				if row.get(f) is not None:
					row[f] = abs(row[f])

	if data:
		total = {"date": None, "miti": None, "purchase_type": None, "voucher_no": _("Total"), "supplier_invoice_no": None, "supplier_invoice_date": None, "supplier_invoice_miti": None, "supplier_name": None, "vat_number": None, "bold": 1}
		for col in columns:
			if col.get("fieldtype") in ("Currency", "Float"):
				total[col["fieldname"]] = sum(row.get(col["fieldname"]) or 0 for row in data)
		data.append(total)
	return columns, data


def get_columns():
	return [
		{"fieldname": "date",                  "label": _("Date"),                    "fieldtype": "Date",            "width": 100},
		{"fieldname": "miti",                  "label": _("Miti"),                    "fieldtype": "Data",            "width": 120},
		{"fieldname": "purchase_type",         "label": _("Purchase Type"),           "fieldtype": "Data",            "width": 120},
		{"fieldname": "voucher_no",            "label": _("Voucher No"),              "fieldtype": "Data",            "width": 170},
		{"fieldname": "supplier_invoice_no",   "label": _("Supplier Invoice No"),     "fieldtype": "Data",            "width": 150},
		{"fieldname": "supplier_invoice_date", "label": _("Supplier Invoice Date"),   "fieldtype": "Date",            "width": 130},
		{"fieldname": "supplier_invoice_miti", "label": _("Supplier Invoice Miti"),   "fieldtype": "Data",            "width": 130},
		{"fieldname": "supplier_name",         "label": _("Supplier Name"),           "fieldtype": "Data",            "width": 180},
		{"fieldname": "vat_number",            "label": _("VAT Number"),              "fieldtype": "Data",            "width": 130},
		{"fieldname": "purchase",              "label": _("Purchase"),                "fieldtype": "Currency",        "width": 130},
		{"fieldname": "tax_free_purchase",     "label": _("Tax Free Purchase"),       "fieldtype": "Currency",        "width": 140},
		{"fieldname": "taxable_purchase",      "label": _("Taxable Purchase"),        "fieldtype": "Currency",        "width": 140},
		{"fieldname": "vat",                   "label": _("VAT"),                     "fieldtype": "Currency",        "width": 110},
		{"fieldname": "taxable_import",        "label": _("Taxable Import"),          "fieldtype": "Currency",        "width": 140},
		{"fieldname": "import_vat",            "label": _("Import VAT"),              "fieldtype": "Currency",        "width": 110},
		{"fieldname": "capitalized_purchase",  "label": _("Capitalized Purchase"),    "fieldtype": "Currency",        "width": 170},
		{"fieldname": "capitalized_vat",       "label": _("Capitalized VAT"),         "fieldtype": "Currency",        "width": 120},
		{"fieldname": "total_vat",             "label": _("Total VAT"),               "fieldtype": "Currency",        "width": 110},
		{"fieldname": "qty",                   "label": _("QTY"),                     "fieldtype": "Float",           "width": 80},
	]


def get_data(filters):
	is_return = 1 if filters.get("is_return") else 0
	conditions = f"pi.docstatus = 1 AND pi.is_return = {is_return}"

	if filters.get("company"):
		placeholders = ", ".join(["'{}'".format(c) for c in filters.get("company")])
		conditions += " AND pi.company IN ({})".format(placeholders)
	if filters.get("from_date"):
		conditions += " AND pi.posting_date >= %(from_date)s"
	if filters.get("to_date"):
		conditions += " AND pi.posting_date <= %(to_date)s"
	if filters.get("supplier"):
		placeholders = ", ".join(["'{}'".format(c) for c in filters.get("supplier")])
		conditions += " AND pi.supplier IN ({})".format(placeholders)
	if filters.get("purchase_type"):
		placeholders = ", ".join(["'{}'".format(c) for c in filters.get("purchase_type")])
		conditions += " AND pi.custom_purchase_type IN ({})".format(placeholders)

	rows = frappe.db.sql(
		f"""
		SELECT
			pi.posting_date                                                                          AS date,
			SUBSTRING_INDEX(pi.custom_nepali_miti, ' ', 1)                                           AS miti,
			pi.custom_purchase_type                                                                  AS purchase_type,
			CONCAT(IFNULL(pi.custom_name, pi.name), '::', pi.name)                                  AS voucher_no,
			pi.bill_no                                                                               AS supplier_invoice_no,
			pi.bill_date                                                                             AS supplier_invoice_date,
			SUBSTRING_INDEX(pi.custom_supplier_invoice_miti, ' ', 1)                                 AS supplier_invoice_miti,
			pi.supplier_name                                                                         AS supplier_name,
			s.tax_id                                                                                 AS vat_number,
			pi.custom_total_amount_including_excise                                                  AS purchase,
			SUM(CASE WHEN pii.custom_vat_apply_on = 'VAT 0%%'                                                                          THEN pii.amount ELSE 0 END) AS tax_free_purchase,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 0 AND s.custom_territory = 'Nepal'    THEN pii.amount ELSE 0 END) AS taxable_purchase,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 0 AND s.custom_territory = 'Nepal'    THEN pii.custom_vat_amount ELSE 0 END) AS vat,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 0 AND s.custom_territory != 'Nepal'   THEN pii.amount ELSE 0 END) AS taxable_import,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 0 AND s.custom_territory != 'Nepal'   THEN pii.custom_vat_amount ELSE 0 END) AS import_vat,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 1 AND s.custom_territory = 'Nepal'    THEN pii.amount ELSE 0 END) AS capitalized_purchase,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 1 AND s.custom_territory = 'Nepal'    THEN pii.custom_vat_amount ELSE 0 END) AS capitalized_vat,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 0 AND s.custom_territory = 'Nepal'    THEN pii.custom_vat_amount
			         WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 0 AND s.custom_territory != 'Nepal'   THEN pii.custom_vat_amount
			         WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 1 AND s.custom_territory = 'Nepal'    THEN pii.custom_vat_amount
			         ELSE 0 END)                                                                      AS total_vat,
			SUM(pii.qty)                                                                             AS qty
		FROM `tabPurchase Invoice` pi
		JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		JOIN `tabSupplier` s ON s.name = pi.supplier
		JOIN `tabItem` i ON i.name = pii.item_code
		WHERE {conditions}
		GROUP BY pi.name
		ORDER BY pi.posting_date ASC
		""",
		filters,
		as_dict=True,
	)
	return rows
