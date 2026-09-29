"""Whether a turn-up allowance is also earned on a worked holiday.

Tea and conveyance are earned by turning up — condition `Status = Present`. A
holiday someone works is a Present day too, so the calculator paid them on it,
while NGI's salary sheet never did: the sheet pays the holiday itself through
Worked on Holiday and leaves tea to working days.

Which of the two is right is a per-component policy question, so it is now a
field. `Pay on Holiday` shows on the attendance-driven components that pay for
turning up, and is seeded `Pay` — today's behaviour — so no amount moves on
migrate. HR sets Tea to `Do Not Pay` to match the sheet.

Read in payroll/attendance_allowance.py, where a blank also reads as `Pay`, so a
component created before this patch behaves the same as one created after it.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

TURN_UP = 'eval:["Status = Present","Status = Half Day"].includes(doc.custom_condition_type)'


def execute():
	create_custom_fields(
		{
			"Salary Component": [
				{
					"fieldname": "custom_pay_on_holiday",
					"label": "Pay on Holiday",
					"fieldtype": "Select",
					"options": "Pay\nDo Not Pay",
					"default": "Pay",
					"insert_after": "custom_half_day_counts",
					"depends_on": TURN_UP,
					"description": "A holiday someone works is a Present day. NGI's sheet pays tea on working days only.",
				},
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Salary Component")

	for name in frappe.get_all(
		"Salary Component",
		filters={"custom_condition_type": ["in", ("Status = Present", "Status = Half Day")]},
		pluck="name",
	):
		if not frappe.db.get_value("Salary Component", name, "custom_pay_on_holiday"):
			frappe.db.set_value("Salary Component", name, "custom_pay_on_holiday", "Pay", update_modified=False)
