"""The four leave types the group actually uses, plus the unpaid catch-all.

Client decisions of 2026-09-15, refined 2026-09-17
(`docs/hr-decisions/00-policy-minutes-2026-09-15.txt`):

  Casual Leave      credited every month, sandwich counted, encashed at year end
  Sick Leave        same
  Maternity Leave   granted when a child is born, women only, never encashed
  Paternity Leave   granted when a child is born, fathers only, never encashed
  Leave Without Pay everything else an employee takes is unpaid

The day counts are NOT here: they differ per company (NGK 8 casual + 12 sick,
the others 21 + 12) and live in each company's Leave Policy. This patch only
settles how each type behaves.

Idempotent: an existing type is updated in place, so a site that already has
"Home Leave" (the old name for Casual Leave) keeps its allocations.
"""

import frappe

# Sandwich rule (minute 3.5): a holiday between two leave days counts as leave.
INCLUDE_HOLIDAY = 1

LEAVE_TYPES = {
	"Casual Leave": {
		"is_earned_leave": 1,
		"earned_leave_frequency": "Monthly",
		"rounding": "0.25",
		"allocate_on_day": "Last Day",
		"include_holiday": INCLUDE_HOLIDAY,
		"allow_encashment": 1,
		"is_carry_forward": 0,
		"allow_negative": 0,
	},
	"Sick Leave": {
		"is_earned_leave": 1,
		"earned_leave_frequency": "Monthly",
		"rounding": "0.25",
		"allocate_on_day": "Last Day",
		"include_holiday": INCLUDE_HOLIDAY,
		"allow_encashment": 1,
		"is_carry_forward": 0,
		"allow_negative": 0,
	},
	"Maternity Leave": {
		"is_earned_leave": 0,
		"include_holiday": INCLUDE_HOLIDAY,
		"allow_encashment": 0,
		"is_carry_forward": 0,
		# Labour Act 2074: 98 days, of which 60 are paid. The unpaid remainder is
		# taken as Leave Without Pay, so this type carries the paid days only.
		"max_continuous_days_allowed": 98,
	},
	"Paternity Leave": {
		"is_earned_leave": 0,
		"include_holiday": INCLUDE_HOLIDAY,
		"allow_encashment": 0,
		"is_carry_forward": 0,
		"max_continuous_days_allowed": 15,  # Labour Act 2074
	},
	"Leave Without Pay": {
		"is_lwp": 1,
		"is_earned_leave": 0,
		"allow_encashment": 0,
		"is_carry_forward": 0,
	},
}


def execute():
	# The first cut of this setup called Casual Leave "Home Leave"; rename rather
	# than create a second type, or every allocation made so far is orphaned.
	if frappe.db.exists("Leave Type", "Home Leave") and not frappe.db.exists("Leave Type", "Casual Leave"):
		frappe.rename_doc("Leave Type", "Home Leave", "Casual Leave", force=True)

	for name, values in LEAVE_TYPES.items():
		if frappe.db.exists("Leave Type", name):
			doc = frappe.get_doc("Leave Type", name)
		else:
			doc = frappe.new_doc("Leave Type")
			doc.leave_type_name = name
		doc.update(values)
		doc.save(ignore_permissions=True)
