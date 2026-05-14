# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _


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
	conditions = "si.docstatus = 1 AND si.is_return = 0"

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
			si.custom_invoice_miti                                                                                                        AS miti,
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
