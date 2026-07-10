# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


@frappe.whitelist()
def get_fiscal_years():
	# CBMS stores its own fiscal year string (e.g. "2082.083"), which does not
	# match the Fiscal Year doctype's names ("82/83"), so the dropdown is built
	# from the values actually present on the credit notes.
	years = frappe.get_all(
		"CBMS Bill Return",
		pluck="fiscal_year",
		filters={"fiscal_year": ["is", "set"]},
		distinct=True,
		order_by="fiscal_year desc",
	)
	return [y for y in years if y]


def get_columns():
	return [
		{"label": _("Fiscal Year"), "fieldname": "fiscal_year", "fieldtype": "Data", "width": 100},
		{"label": _("Credit Note Number"), "fieldname": "credit_note_number", "fieldtype": "Data", "width": 150},
		{"label": _("Ref Invoice Number"), "fieldname": "ref_invoice_number", "fieldtype": "Data", "width": 150},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
		{"label": _("Customer PAN"), "fieldname": "customer_pan", "fieldtype": "Data", "width": 130},
		{"label": _("Credit Note Date"), "fieldname": "credit_note_date", "fieldtype": "Data", "width": 130},
		{"label": _("Discount Amount"), "fieldname": "discount_amount", "fieldtype": "Float", "width": 130},
		{"label": _("Gross Amount"), "fieldname": "gross_amount", "fieldtype": "Float", "width": 130},
		{"label": _("Taxable Amount"), "fieldname": "taxable_amount", "fieldtype": "Float", "width": 130},
		{"label": _("VAT"), "fieldname": "vat", "fieldtype": "Float", "width": 100},
		{"label": _("Total Amount"), "fieldname": "total_amount", "fieldtype": "Float", "width": 130},
		{"label": _("Sync with IRD"), "fieldname": "synced_with_ird", "fieldtype": "Check", "width": 110},
		{
			"label": _("Sales Invoice"),
			"fieldname": "sales_invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 160,
		},
	]


def get_conditions(filters):
	conditions = []

	if filters.company:
		conditions.append("bill.company = %(company)s")
	if filters.fiscal_year:
		conditions.append("bill.fiscal_year = %(fiscal_year)s")
	if filters.sync_status:
		conditions.append("bill.sync_status = %(sync_status)s")
	if filters.from_date:
		conditions.append("bill.credit_note_date >= %(from_date)s")
	if filters.to_date:
		conditions.append("bill.credit_note_date <= %(to_date)s")

	return (" and " + " and ".join(conditions)) if conditions else ""


def get_data(filters):
	# total_amount is the credit note grand total: CBMS `total_sales` excludes exempt
	# sales (see build_cbms_fields), so adding them back reconstitutes it. Gross is
	# that total before VAT, which keeps Gross + VAT = Total on every row.
	return frappe.db.sql(
		"""
		select
			bill.fiscal_year,
			bill.credit_note_number,
			bill.ref_invoice_number,
			bill.buyer_name as customer_name,
			bill.buyer_pan as customer_pan,
			bill.credit_note_date_bs as credit_note_date,
			bill.discount as discount_amount,
			(bill.total_sales + bill.tax_exempted_sales - bill.vat) as gross_amount,
			bill.taxable_sales_vat as taxable_amount,
			bill.vat,
			(bill.total_sales + bill.tax_exempted_sales) as total_amount,
			case when bill.sync_status = 'Synced' then 1 else 0 end as synced_with_ird,
			bill.sales_invoice
		from `tabCBMS Bill Return` bill
		where 1 = 1 {conditions}
		order by bill.fiscal_year asc, bill.credit_note_date asc, bill.credit_note_number asc
		""".format(conditions=get_conditions(filters)),
		filters,
		as_dict=True,
	)
