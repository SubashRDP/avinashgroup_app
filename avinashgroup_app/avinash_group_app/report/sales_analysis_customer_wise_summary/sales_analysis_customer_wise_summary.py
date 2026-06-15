# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import json
import os

import frappe
from frappe import _


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
		SELECT cust.name AS value, cust.customer_name AS description
		FROM `tabCustomer` cust
		WHERE {where}
		ORDER BY cust.customer_name
		LIMIT 50
		""",
		values,
		as_dict=True,
	)


def execute(filters=None):
	filters = frappe._dict(filters or {})

	include_return = int(filters.get("include_return") or 0)

	columns = get_columns(include_return)
	data = get_data(filters, include_return)

	return columns, data


def get_columns(include_return):
	columns = [
		{
			"label": _("Customer Code"),
			"fieldname": "customer_code",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 110,
		},
		{
			"label": _("Customer Name"),
			"fieldname": "customer_name",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("VAT/PAN No."),
			"fieldname": "tax_id",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Sales Quantity"),
			"fieldname": "sales_qty",
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"label": _("Gross Value"),
			"fieldname": "gross_value",
			"fieldtype": "Currency",
			"width": 140,
		},
	]

	# Return + Net columns are only generated when "Include Return" is ticked.
	if include_return:
		columns += [
			{
				"label": _("Return Quantity"),
				"fieldname": "return_qty",
				"fieldtype": "Float",
				"width": 110,
			},
			{
				"label": _("Return Value"),
				"fieldname": "return_value",
				"fieldtype": "Currency",
				"width": 140,
			},
			{
				"label": _("Net Sales Quantity"),
				"fieldname": "net_sales_qty",
				"fieldtype": "Float",
				"width": 120,
			},
			{
				"label": _("Net Sales Value"),
				"fieldname": "net_sales_value",
				"fieldtype": "Currency",
				"width": 150,
			},
		]

	return columns


def get_data(filters, include_return):
	conditions = ["si.docstatus = 1"]
	values = {
		"from_date": filters.get("from_date"),
		"to_date": filters.get("to_date"),
	}

	conditions.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")

	if filters.get("company"):
		conditions.append("si.company IN %(company)s")
		values["company"] = tuple(filters.get("company"))

	if filters.get("customer"):
		conditions.append("si.customer IN %(customer)s")
		values["customer"] = tuple(filters.get("customer"))

	where = " AND ".join(conditions)

	# Returns are stored with negative qty/value, so negate them to show positives.
	rows = frappe.db.sql(
		f"""
		SELECT
			si.customer AS customer_code,
			cust.customer_name AS customer_name,
			cust.tax_id AS tax_id,
			SUM(CASE WHEN si.is_return = 0 THEN si.total_qty ELSE 0 END) AS sales_qty,
			SUM(CASE WHEN si.is_return = 0 THEN si.custom_total_amount_including_excise ELSE 0 END) AS gross_value,
			-SUM(CASE WHEN si.is_return = 1 THEN si.total_qty ELSE 0 END) AS return_qty,
			-SUM(CASE WHEN si.is_return = 1 THEN si.custom_total_amount_including_excise ELSE 0 END) AS return_value
		FROM `tabSales Invoice` si
		LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
		WHERE {where}
		GROUP BY si.customer, cust.customer_name, cust.tax_id
		ORDER BY si.customer
		""",
		values,
		as_dict=True,
	)

	data = []
	# Total row: sum the quantity columns and the value columns.
	total = {
		"customer_name": _("Total of Reported Sales and Returns"),
		"sales_qty": 0,
		"gross_value": 0,
		"return_qty": 0,
		"return_value": 0,
		"net_sales_qty": 0,
		"net_sales_value": 0,
		"bold": 1,
	}

	for row in rows:
		row.sales_qty = row.sales_qty or 0
		row.gross_value = row.gross_value or 0
		row.return_qty = row.return_qty or 0
		row.return_value = row.return_value or 0
		row.net_sales_qty = row.sales_qty - row.return_qty
		row.net_sales_value = row.gross_value - row.return_value

		total["sales_qty"] += row.sales_qty
		total["gross_value"] += row.gross_value
		total["return_qty"] += row.return_qty
		total["return_value"] += row.return_value
		total["net_sales_qty"] += row.net_sales_qty
		total["net_sales_value"] += row.net_sales_value

		data.append(row)

	if data:
		data.append(total)

	return data


# ──────────────────────────────────────────────────────────────────────────────
# PDF / Print  (Download PDF button + Print → same wkhtmltopdf PDF, in-body pages)
# ──────────────────────────────────────────────────────────────────────────────

def _fmt_inr(v):
	# Lakh/crore grouping (e.g. 1,48,85,884.40) to match the Nepali sample. 0 shows as 0.00;
	# only a missing value (None — e.g. blank qty on the total row) renders empty.
	if v is None:
		return ''
	import locale
	try:
		locale.setlocale(locale.LC_ALL, 'en_IN.UTF-8')
		return locale.format_string('%.2f', v, grouping=True)
	except Exception:
		return '{:,.2f}'.format(v)


def _fmt_qty(v):
	if v is None:
		return ''
	import locale
	try:
		locale.setlocale(locale.LC_ALL, 'en_IN.UTF-8')
		return locale.format_string('%.3f', v, grouping=True)
	except Exception:
		return '{:,.3f}'.format(v)


def _get_customer_display(filters):
	if filters.get('customer'):
		rows = frappe.db.get_all('Customer',
			filters=[['name', 'in', filters.get('customer')]],
			fields=['customer_name'], order_by='customer_name asc')
		return ', '.join(r.customer_name for r in rows)
	return ''


def _render(filters, selected_columns, orientation, is_html_view):
	include_return = int(filters.get("include_return") or 0)
	_, data = execute(filters)
	customer_display = _get_customer_display(filters)

	template_path = os.path.join(os.path.dirname(__file__), 'sales_analysis_customer_wise_summary_pdf.html')
	with open(template_path) as f:
		template_content = f.read()

	return frappe.render_template(template_content, {
		'filters': filters,
		'data': data,
		'fmt': _fmt_inr,
		'fmtq': _fmt_qty,
		'sc': selected_columns or [],
		'include_return': include_return,
		'orientation': orientation,
		'is_html_view': is_html_view,
		'customer_display': customer_display,
	})


@frappe.whitelist()
def get_print_html(filters, selected_columns=None, orientation=None):
	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	if isinstance(selected_columns, str):
		selected_columns = json.loads(selected_columns)

	return _render(filters, selected_columns, orientation or 'Landscape', is_html_view=True)


@frappe.whitelist()
def download_pdf(filters, orientation=None, selected_columns=None, view=None):
	from frappe.utils.pdf import get_pdf

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	if isinstance(selected_columns, str):
		selected_columns = json.loads(selected_columns)

	orientation = orientation if orientation in ('Portrait', 'Landscape') else 'Landscape'

	# Page numbers are rendered inside the template body (manual pagination), so they
	# work on plain/unpatched wkhtmltopdf.
	html = _render(filters, selected_columns, orientation, is_html_view=False)

	options = {
		'page-size': 'A4',
		'orientation': orientation,
		'margin-top': '10mm',
		'margin-right': '10mm',
		'margin-bottom': '15mm',
		'margin-left': '10mm',
		'encoding': 'UTF-8',
		'enable-local-file-access': None,
	}
	pdf_data = get_pdf(html, options)

	frappe.response.filename = 'sales_analysis_customer_wise_summary.pdf'
	frappe.response.filecontent = pdf_data
	# view=1 (Print) → open inline in the browser tab; otherwise download the file.
	frappe.response.type = 'pdf' if frappe.utils.cint(view) else 'download'
