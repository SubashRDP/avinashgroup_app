# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	# With zero rows the desk hides the table entirely ("Nothing to show");
	# a single blank row keeps the column headers visible.
	return get_columns(), data or [{}]


def get_columns():
	return [
		{"label": _("Fiscal Year"), "fieldname": "fiscal_year", "fieldtype": "Link", "options": "Fiscal Year", "width": 100},
		{"label": _("Invoice Number"), "fieldname": "invoice_number", "fieldtype": "Data", "width": 130},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
		{"label": _("Customer PAN"), "fieldname": "customer_pan", "fieldtype": "Data", "width": 130},
		{"label": _("Invoice Date"), "fieldname": "invoice_date", "fieldtype": "Data", "width": 110},
		{"label": _("Discount Amount"), "fieldname": "discount_amount", "fieldtype": "Float", "width": 130},
		{"label": _("Gross Amount"), "fieldname": "gross_amount", "fieldtype": "Float", "width": 130},
		{"label": _("Taxable Amount"), "fieldname": "taxable_amount", "fieldtype": "Float", "width": 130},
		{"label": _("VAT"), "fieldname": "vat", "fieldtype": "Float", "width": 100},
		{"label": _("Total Amount"), "fieldname": "total_amount", "fieldtype": "Float", "width": 130},
		{"label": _("Sync with IRD"), "fieldname": "synced_with_ird", "fieldtype": "Check", "width": 110},
	]


def get_conditions(filters):
	conditions = []

	if filters.company:
		conditions.append("bill.company = %(company)s")
	if filters.fiscal_year:
		# The report has no From/To Date filters — the date window is derived
		# here from the selected fiscal year. The Fiscal Year docname keeps the
		# slash form ("82/83"), so look up its AD start/end span before converting
		# to the dotted form ("82.83") that bills store in the fiscal_year field.
		fy = frappe.get_cached_value(
			"Fiscal Year",
			filters.fiscal_year,
			["year_start_date", "year_end_date"],
			as_dict=True,
		)
		if fy:
			filters.from_date = fy.year_start_date
			filters.to_date = fy.year_end_date
			conditions.append("bill.invoice_date >= %(from_date)s")
			conditions.append("bill.invoice_date <= %(to_date)s")

		filters.fiscal_year = filters.fiscal_year.replace("/", ".")
		conditions.append("bill.fiscal_year = %(fiscal_year)s")
	if filters.sync_status:
		conditions.append("bill.sync_status = %(sync_status)s")

	return (" and " + " and ".join(conditions)) if conditions else ""


def get_data(filters):
	# total_amount is the invoice grand total: CBMS `total_sales` excludes exempt
	# sales (see build_cbms_fields), so adding them back reconstitutes it. Gross is
	# that total before VAT, which keeps Gross + VAT = Total on every row.
	return frappe.db.sql(
		"""
		select
			replace(bill.fiscal_year, '.', '/') as fiscal_year,
			bill.invoice_number,
			bill.buyer_name as customer_name,
			bill.buyer_pan as customer_pan,
			bill.invoice_date_bs as invoice_date,
			bill.discount as discount_amount,
			(bill.total_sales + bill.tax_exempted_sales - bill.vat) as gross_amount,
			bill.taxable_sales_vat as taxable_amount,
			bill.vat,
			(bill.total_sales + bill.tax_exempted_sales) as total_amount,
			case when bill.sync_status = 'Synced' then 1 else 0 end as synced_with_ird
		from `tabCBMS Bill` bill
		where 1 = 1 {conditions}
		order by bill.fiscal_year asc, bill.invoice_date asc, bill.invoice_number asc
		""".format(conditions=get_conditions(filters)),
		filters,
		as_dict=True,
	)
