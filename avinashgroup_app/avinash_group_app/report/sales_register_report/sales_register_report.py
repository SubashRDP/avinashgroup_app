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


def _get_customer_display(filters):
	if filters.get('customer'):
		rows = frappe.db.get_all('Customer',
			filters=[['name', 'in', filters.get('customer')]],
			fields=['customer_name'], order_by='customer_name asc')
		return ', '.join(r.customer_name for r in rows)
	return ''


@frappe.whitelist()
def get_print_html(filters, selected_columns=None):
	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	if isinstance(selected_columns, str):
		selected_columns = json.loads(selected_columns)

	_, data = execute(filters)
	customer_display = _get_customer_display(filters)

	template_path = os.path.join(os.path.dirname(__file__), 'sales_register_report_pdf.html')
	with open(template_path) as f:
		template_content = f.read()

	return frappe.render_template(template_content, {
		'filters': filters,
		'data': data,
		'fmt': _fmt_inr,
		'sc': selected_columns or [],
		'is_html_view': True,
		'customer_display': customer_display,
	})


@frappe.whitelist()
def download_pdf(filters):
	from frappe.utils.pdf import get_pdf
	import tempfile

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))

	_, data = execute(filters)
	customer_display = _get_customer_display(filters)

	template_path = os.path.join(os.path.dirname(__file__), 'sales_register_report_pdf.html')
	with open(template_path) as f:
		template_content = f.read()

	html = frappe.render_template(template_content, {
		'filters': filters,
		'data': data,
		'fmt': _fmt_inr,
		'customer_display': customer_display,
	})

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
			'margin-right': '10mm',
			'margin-bottom': '15mm',
			'margin-left': '10mm',
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

	frappe.response.filename = 'sales_register.pdf'
	frappe.response.filecontent = pdf_data
	frappe.response.type = 'download'


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	if data:
		total = {"date": None, "miti": None, "bill_no": _("Total"), "customer": None, "vat_number": None, "bold": 1}
		for col in columns:
			if col.get("fieldtype") == "Currency":
				total[col["fieldname"]] = sum(row.get(col["fieldname"]) or 0 for row in data)
		data.append(total)
	return columns, data


def get_columns():
	return [
		{"fieldname": "date",          "label": _("Date"),           "fieldtype": "Date",     "width": 100},
		{"fieldname": "miti",          "label": _("Miti"),           "fieldtype": "Data",     "width": 120},
		{"fieldname": "bill_no",       "label": _("Bill No"),        "fieldtype": "Link",     "options": "Sales Invoice", "width": 170},
		{"fieldname": "customer",      "label": _("Customer Name"),  "fieldtype": "Data",     "width": 180},
		{"fieldname": "vat_number",    "label": _("VAT Number"),     "fieldtype": "Data",     "width": 130},
		{"fieldname": "total_sales",   "label": _("Total Sales"),    "fieldtype": "Currency", "width": 130},
		{"fieldname": "tax_free_sale", "label": _("Tax Free Sale"),  "fieldtype": "Currency", "width": 140},
		{"fieldname": "export_npr",    "label": _("Export NPR"),     "fieldtype": "Currency", "width": 130},
		{"fieldname": "taxable_sales", "label": _("Taxable Sales"),  "fieldtype": "Currency", "width": 140},
		{"fieldname": "vat",           "label": _("VAT"),            "fieldtype": "Currency", "width": 110},
	]


def get_data(filters):
	is_return = 1 if filters.get("is_return") else 0
	conditions = f"si.docstatus = 1 AND si.is_return = {is_return}"

	if filters.get("company"):
		placeholders = ", ".join(["'{}'".format(c) for c in filters.get("company")])
		conditions += " AND si.company IN ({})".format(placeholders)
	if filters.get("from_date"):
		conditions += " AND si.posting_date >= %(from_date)s"
	if filters.get("to_date"):
		conditions += " AND si.posting_date <= %(to_date)s"
	if filters.get("customer"):
		placeholders = ", ".join(["'{}'".format(c) for c in filters.get("customer")])
		conditions += " AND si.customer IN ({})".format(placeholders)

	return frappe.db.sql(
		f"""
		SELECT
			si.posting_date                                                                                                               AS date,
			SUBSTRING_INDEX(si.custom_invoice_miti, ' ', 1)                                                                               AS miti,
			si.name                                                                                                                        AS bill_no,
			si.customer_name                                                                                                               AS customer,
			c.tax_id                                                                                                                       AS vat_number,
			si.custom_total_amount_including_excise                                                                                        AS total_sales,
			SUM(CASE WHEN sii.custom_vat_apply_on = 'VAT 0%%'                                             AND c.territory = 'Nepal'    THEN sii.amount ELSE 0 END) AS tax_free_sale,
			SUM(CASE WHEN sii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND c.territory != 'Nepal' THEN sii.base_amount ELSE 0 END)      AS export_npr,
			SUM(CASE WHEN sii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND c.territory = 'Nepal'  THEN sii.amount ELSE 0 END)           AS taxable_sales,
			SUM(CASE WHEN sii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND c.territory = 'Nepal'  THEN sii.custom_vat_amount ELSE 0 END) AS vat
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		JOIN `tabCustomer` c ON c.name = si.customer
		WHERE {conditions}
		GROUP BY si.name
		ORDER BY si.posting_date ASC
		""",
		filters,
		as_dict=True,
	)
