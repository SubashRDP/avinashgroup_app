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
def get_company_branches(company=None, txt=None):
	"""Branch options scoped to the selected company via the branch's custom_company."""
	company = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = ["(br.name LIKE %(txt)s OR br.branch LIKE %(txt)s)"]
	values = {"txt": like}
	if company:
		conditions.append("(br.custom_company IN %(company)s OR COALESCE(br.custom_company, '') = '')")
		values["company"] = tuple(company)
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT br.name AS value, br.branch AS label, br.name AS description
		FROM `tabBranch` br
		WHERE {where}
		ORDER BY br.branch
		LIMIT 50
		""",
		values,
		as_dict=True,
	)


@frappe.whitelist()
def get_invoice_options(company=None, from_date=None, to_date=None, customer=None, txt=None):
	"""Invoice No options (custom_branch_name) scoped to the filters already applied on
	the report, so the dropdown only offers bills the report would actually show."""
	company = _as_list(company)
	customer = _as_list(customer)
	like = f"%{(txt or '').strip()}%"
	conditions = ["si.docstatus = 1", "si.is_return = 0",
		"(COALESCE(si.custom_branch_name, si.name) LIKE %(txt)s OR si.name LIKE %(txt)s)"]
	values = {"txt": like}
	if company:
		conditions.append("si.company IN %(company)s")
		values["company"] = tuple(company)
	if customer:
		conditions.append("si.customer IN %(customer)s")
		values["customer"] = tuple(customer)
	if from_date:
		conditions.append("si.posting_date >= %(from_date)s")
		values["from_date"] = from_date
	if to_date:
		conditions.append("si.posting_date <= %(to_date)s")
		values["to_date"] = to_date
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT si.name AS value, COALESCE(si.custom_branch_name, si.name) AS label, si.name AS description
		FROM `tabSales Invoice` si
		WHERE {where}
		ORDER BY si.posting_date DESC
		LIMIT 50
		""",
		values,
		as_dict=True,
	)


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
def get_print_html(filters, selected_columns=None, orientation=None):
	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	if isinstance(selected_columns, str):
		selected_columns = json.loads(selected_columns)

	_, data = execute(filters)
	customer_display = _get_customer_display(filters)

	template_path = os.path.join(os.path.dirname(__file__), 'sales_bill_details_pdf.html')
	with open(template_path) as f:
		template_content = f.read()

	return frappe.render_template(template_content, {
		'filters': filters,
		'data': data,
		'fmt': _fmt_inr,
		'sc': selected_columns or [],
		'is_html_view': True,
		'orientation': orientation or 'Landscape',
		'customer_display': customer_display,
	})


@frappe.whitelist()
def download_pdf(filters, orientation=None, selected_columns=None, view=None):
	from frappe.utils.pdf import get_pdf

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	if isinstance(selected_columns, str):
		selected_columns = json.loads(selected_columns)

	orientation = orientation if orientation in ('Portrait', 'Landscape') else 'Landscape'

	_, data = execute(filters)
	customer_display = _get_customer_display(filters)

	template_path = os.path.join(os.path.dirname(__file__), 'sales_bill_details_pdf.html')
	with open(template_path) as f:
		template_content = f.read()

	html = frappe.render_template(template_content, {
		'filters': filters,
		'data': data,
		'fmt': _fmt_inr,
		'sc': selected_columns or [],
		'orientation': orientation,
		'customer_display': customer_display,
	})

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

	frappe.response.filename = 'sales_bill_details.pdf'
	frappe.response.filecontent = pdf_data
	# view=1 (Print) → open inline in the browser tab; otherwise download the file.
	frappe.response.type = 'pdf' if frappe.utils.cint(view) else 'download'


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()

	# Company is a required filter (see the report JS), so the UI blocks the report
	# with a "Please set the company first" prompt before execute runs. This guard
	# still protects any direct/API call from running the full query with no Company.
	if not _as_list(filters.get("company")):
		return columns, []

	data = get_data(filters)
	_attach_customer_addresses(data)

	if data:
		total = {"miti": None, "invoice_number": _("Total"), "customer": None, "vehicle_number": None,
			"price_list": None, "branch": None, "customer_address": None, "customer_phone": None, "bold": 1}
		for col in columns:
			if col.get("fieldtype") in ("Currency", "Float"):
				total[col["fieldname"]] = sum(row.get(col["fieldname"]) or 0 for row in data)
		data.append(total)
	return columns, data


def get_columns():
	return [
		{"fieldname": "miti",              "label": _("Miti"),                   "fieldtype": "Data",     "width": 110},
		{"fieldname": "invoice_number",     "label": _("Invoice Number"),         "fieldtype": "Data",     "width": 150},
		{"fieldname": "customer",           "label": _("Customer"),               "fieldtype": "Data",     "width": 170},
		{"fieldname": "branch",             "label": _("Branch"),                 "fieldtype": "Data",     "width": 130},
		{"fieldname": "total_qty",          "label": _("Total Quantity"),         "fieldtype": "Float",    "width": 110},
		{"fieldname": "amount_before_vat",  "label": _("Amount before VAT"),      "fieldtype": "Currency", "width": 140},
		{"fieldname": "vat_amount",         "label": _("VAT Amount"),             "fieldtype": "Currency", "width": 120},
		{"fieldname": "grand_total",        "label": _("Grand Total"),            "fieldtype": "Currency", "width": 130},
		{"fieldname": "vehicle_number",     "label": _("Vehicle Number"),         "fieldtype": "Data",     "width": 120},
		{"fieldname": "price_list",         "label": _("Price List"),             "fieldtype": "Data",     "width": 130},
		{"fieldname": "customer_address",   "label": _("Customer Address"),       "fieldtype": "Data",     "width": 180},
		{"fieldname": "customer_phone",     "label": _("Customer Phone Number"),  "fieldtype": "Data",     "width": 130},
	]


def get_data(filters):
	conditions = "si.docstatus = 1 AND si.is_return = 0"

	if filters.get("company"):
		placeholders = ", ".join(["'{}'".format(c) for c in _as_list(filters.get("company"))])
		conditions += " AND si.company IN ({})".format(placeholders)
	if filters.get("from_date"):
		conditions += " AND si.posting_date >= %(from_date)s"
	if filters.get("to_date"):
		conditions += " AND si.posting_date <= %(to_date)s"
	if filters.get("customer"):
		placeholders = ", ".join(["'{}'".format(c) for c in _as_list(filters.get("customer"))])
		conditions += " AND si.customer IN ({})".format(placeholders)
	if filters.get("invoice_no"):
		placeholders = ", ".join(["'{}'".format(v) for v in _as_list(filters.get("invoice_no"))])
		conditions += " AND si.name IN ({})".format(placeholders)
	if filters.get("vehicle"):
		conditions += " AND si.custom_vehicle_no LIKE %(vehicle)s"
		filters["vehicle"] = "%{}%".format(filters["vehicle"])
	if filters.get("branch"):
		placeholders = ", ".join(["'{}'".format(b) for b in _as_list(filters.get("branch"))])
		conditions += " AND si.custom_branch IN ({})".format(placeholders)

	return frappe.db.sql(
		f"""
		SELECT
			SUBSTRING_INDEX(si.custom_invoice_miti, ' ', 1)   AS miti,
			COALESCE(si.custom_branch_name, si.name)          AS invoice_number,
			si.name                                           AS invoice_name,
			si.customer                                       AS customer_id,
			si.customer_name                                  AS customer,
			br.branch                                          AS branch,
			SUM(sii.qty)                                       AS total_qty,
			si.custom_total_amount_including_excise           AS amount_before_vat,
			si.custom_total_vat_amount                        AS vat_amount,
			si.grand_total                                     AS grand_total,
			si.custom_vehicle_no                                AS vehicle_number,
			pl.price_list_name                                  AS price_list,
			c.custom_mobile_number                              AS customer_phone
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		JOIN `tabCustomer` c ON c.name = si.customer
		LEFT JOIN `tabPrice List` pl ON pl.name = si.selling_price_list
		LEFT JOIN `tabBranch` br ON br.name = si.custom_branch
		WHERE {conditions}
		GROUP BY si.name
		ORDER BY si.posting_date DESC
		""",
		filters,
		as_dict=True,
	)


def _attach_customer_addresses(data):
	"""address_line1 of each customer's primary Address record (per user);
	blank when the customer has none — no fallback."""
	customer_ids = {row["customer_id"] for row in data if row.get("customer_id")}
	if not customer_ids:
		return

	rows = frappe.db.sql(
		"""
		SELECT dl.link_name AS customer_id, addr.address_line1 AS address_line1
		FROM `tabDynamic Link` dl
		JOIN `tabAddress` addr ON addr.name = dl.parent
		WHERE dl.parenttype = 'Address' AND dl.link_doctype = 'Customer' AND dl.link_name IN %(customers)s
		ORDER BY addr.is_primary_address DESC, addr.creation DESC
		""",
		{"customers": tuple(customer_ids)},
		as_dict=True,
	)
	address_by_customer = {}
	for row in rows:
		address_by_customer.setdefault(row.customer_id, row.address_line1)

	for row in data:
		address = address_by_customer.get(row.get("customer_id")) or ""
		address = frappe.utils.strip_html(address.replace("<br>", ", ")).replace("\n", " ").strip().rstrip(",")
		row["customer_address"] = address
		row.pop("customer_id", None)
