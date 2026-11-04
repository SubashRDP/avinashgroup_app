"""Leave taken ahead of the monthly credit, and recovered from a leaver's last slip.

The user's rule (2026-10-15): staff may take leave before it is credited; what
counts is that the year's leave does not pass the allocated days, otherwise it
is deducted. So Casual and Sick Leave allow a negative balance (hr/leave_ceiling
still refuses an application past the year's figure), a "Leave Recovery"
deduction exists for payroll/leave_encashment.recover_month to post, booked to
the same accounts as Leave Encashment so the two net off on the same expense,
and the Payroll Entry tick that settles leave says it does both.
"""

import frappe

COMPONENT = "Leave Recovery"
ENCASHMENT_COMPONENT = "Leave Encashment"
NEGATIVE_ALLOWED = ("Casual Leave", "Sick Leave")
SETTLE_FIELD = "Payroll Entry-custom_pay_leave_encashment"


def execute():
	for leave_type in NEGATIVE_ALLOWED:
		if frappe.db.exists("Leave Type", leave_type):
			frappe.db.set_value("Leave Type", leave_type, "allow_negative", 1)

	if not frappe.db.exists("Salary Component", COMPONENT):
		component = frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": COMPONENT,
				"salary_component_abbr": "LR",
				"type": "Deduction",
				"depends_on_payment_days": 0,
				"remove_if_zero_valued": 1,
				"description": "Leave taken beyond what was earned, deducted when a year or employment ends.",
			}
		)
		if frappe.db.exists("Salary Component", ENCASHMENT_COMPONENT):
			for row in frappe.get_doc("Salary Component", ENCASHMENT_COMPONENT).accounts:
				component.append(
					"accounts",
					{f: row.get(f) for f in ("company", "account", "custom_account_marketing", "custom_account_plant")},
				)
		component.flags.ignore_validate = True
		component.insert(ignore_permissions=True)

	if frappe.db.exists("Custom Field", SETTLE_FIELD):
		frappe.db.set_value(
			"Custom Field",
			SETTLE_FIELD,
			{
				"label": "Settle Leave (encash or recover)",
				"description": "Year end (Ashadh) and anyone relieved this month: leave left is paid, "
				"leave taken beyond what was earned is deducted, on this month's slips.",
			},
		)
		frappe.clear_cache(doctype="Payroll Entry")
