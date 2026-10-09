"""Payroll Entry is chosen by Fiscal Year + BS month (payroll/payroll_month.py).

Adds the month calendar and the two fields it fills at the top of the form and fills them on existing
entries from their start date, so old entries read the same way as new ones.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from avinashgroup_app.hr.bs_calendar import MONTH_OPTIONS, fiscal_year_of, month_of_date, month_option


def execute():
	create_custom_fields(
		{
			"Payroll Entry": [
				{
					"fieldname": "custom_month_calendar",
					"label": "Month",
					"fieldtype": "HTML",
					"insert_after": "select_payroll_period",
				},
				{
					"fieldname": "custom_fiscal_year",
					"label": "Fiscal Year",
					"fieldtype": "Link",
					"options": "Fiscal Year",
					"insert_after": "custom_month_calendar",
					"in_list_view": 1,
					"in_standard_filter": 1,
					"description": "e.g. 83/84: Shrawan 2083 to Ashadh 2084.",
				},
				{
					"fieldname": "custom_bs_month",
					"label": "Month (BS)",
					"fieldtype": "Select",
					"options": "\n" + "\n".join(MONTH_OPTIONS),
					"insert_after": "custom_fiscal_year",
					"in_list_view": 1,
					"in_standard_filter": 1,
					"description": (
						"The month being paid. Dates, posting date, accounts and employees are filled "
						"from it on save. Month borders come from Nepal BS Period."
					),
				},
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Payroll Entry")

	for entry in frappe.get_all(
		"Payroll Entry",
		filters={"start_date": ("is", "set"), "custom_bs_month": ("in", ("", None))},
		fields=["name", "company", "start_date"],
	):
		month = month_of_date(entry.company, entry.start_date)
		frappe.db.set_value(
			"Payroll Entry",
			entry.name,
			{"custom_fiscal_year": fiscal_year_of(month.start_date), "custom_bs_month": month_option(month.bs_month)},
			update_modified=False,
		)
