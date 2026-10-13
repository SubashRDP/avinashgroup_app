"""Leave encashment rules on Leave Type; Casual and Sick set up to be encashed.

payroll/leave_encashment.py prices HRMS's Leave Encashment at the person's own
basic and allows it only at the moments the Leave Type switches on. This patch:

  1. Leave Type, in HRMS's Encashment section: Encash at Year End, Encash at
     Separation, Encashment Days per Month (the per-day divisor; blank = the
     BS month's actual days).
  2. Leave Encashment: read-only Occasion, Monthly Basic, Days per Month and
     Rate per Day, so the reviewer sees the arithmetic.
  3. `Leave Encashment` component: not prorated by payment days (it was, so an
     absence in the paying month would have cut the encashment), taxable.
  4. Every type with Allow Encashment (Casual, Sick — policy minute 3.7) gets
     Earning Component = Leave Encashment if blank, and both occasions on —
     only the first time, when the fields are new (HR's later choices survive).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from avinashgroup_app.patches.setup_festival_allowance import copy_accounts_from_basic

COMPONENT = "Leave Encashment"


def execute():
	first_time = not frappe.db.exists("Custom Field", {"dt": "Leave Type", "fieldname": "custom_encash_at_year_end"})
	encash = "eval:doc.allow_encashment"
	create_custom_fields(
		{
			"Leave Type": [
				{
					"fieldname": "custom_encash_at_year_end",
					"fieldtype": "Check",
					"label": "Encash at Year End",
					"insert_after": "non_encashable_leaves",
					"depends_on": encash,
					"description": "The balance left on the allocation's last day is paid on that month's slip (Payroll Entry → Leave Encashment)",
				},
				{
					"fieldname": "custom_encash_at_separation",
					"fieldtype": "Check",
					"label": "Encash at Separation",
					"insert_after": "custom_encash_at_year_end",
					"depends_on": encash,
					"description": "The balance on the relieving date is paid on the last slip",
				},
				{
					"fieldname": "custom_encashment_days_per_month",
					"fieldtype": "Float",
					"label": "Encashment Days per Month",
					"insert_after": "custom_encash_at_separation",
					"depends_on": encash,
					"description": "Rate per day = monthly basic ÷ this. Blank: the actual days of the BS month the encashment is dated in",
				},
			],
			"Leave Encashment": [
				{
					"fieldname": "custom_occasion",
					"fieldtype": "Data",
					"label": "Occasion",
					"insert_after": "encashment_amount",
					"read_only": 1,
				},
				{
					"fieldname": "custom_monthly_basic",
					"fieldtype": "Currency",
					"label": "Monthly Basic",
					"options": "currency",
					"insert_after": "custom_occasion",
					"read_only": 1,
				},
				{
					"fieldname": "custom_days_per_month",
					"fieldtype": "Float",
					"label": "Days per Month",
					"insert_after": "custom_monthly_basic",
					"read_only": 1,
				},
				{
					"fieldname": "custom_rate_per_day",
					"fieldtype": "Currency",
					"label": "Rate per Day",
					"options": "currency",
					"insert_after": "custom_days_per_month",
					"read_only": 1,
				},
			],
		},
		update=True,
	)

	if frappe.db.exists("Salary Component", COMPONENT):
		frappe.db.set_value(
			"Salary Component",
			COMPONENT,
			{"type": "Earning", "is_tax_applicable": 1, "depends_on_payment_days": 0},
			update_modified=False,
		)
		copy_accounts_from_basic(COMPONENT)

	if not first_time:
		return
	for name in frappe.get_all("Leave Type", filters={"allow_encashment": 1}, pluck="name"):
		values = {"custom_encash_at_year_end": 1, "custom_encash_at_separation": 1}
		if not frappe.db.get_value("Leave Type", name, "earning_component") and frappe.db.exists(
			"Salary Component", COMPONENT
		):
			values["earning_component"] = COMPONENT
		frappe.db.set_value("Leave Type", name, values, update_modified=False)
