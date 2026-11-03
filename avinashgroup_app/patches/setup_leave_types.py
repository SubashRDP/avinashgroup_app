"""The leave types the group actually uses, plus the unpaid catch-all.

Client decisions of 2026-09-15, refined 2026-09-17
(`docs/hr-decisions/00-policy-minutes-2026-09-15.txt`), and 2026-11-03: there
is no Casual or Sick Leave, only Home Leave — 33 days a year (Karnali 20).

  Home Leave        the one paid leave: credited every month, sandwich counted,
                    encashed at year end
  Maternity Leave   granted when a child is born, women only, never encashed
  Paternity Leave   granted when a child is born, fathers only, never encashed
  Leave Without Pay everything else an employee takes is unpaid
  Replacement Leave officer / admin staff who work a holiday (policy 2.2, 2.5),
                    credited per day by hr/replacement_leave.py through a
                    Compensatory Leave Request — never by the Leave Policy

The day counts are NOT here: they differ per company (NGK 20, the others 33)
and live in each company's Leave Policy. This patch only settles how each type
behaves.

Idempotent: an existing type is updated in place. A site that still has Casual
Leave gets it renamed to Home Leave, so its allocations and applications follow.
Sick Leave is left as it is: its allocations are data, folded into Home Leave
by HR (a new Leave Policy), not by a patch.
"""

import frappe

#: Settings HR changes in the desk; only seeded on a new type.
HR_OWNED = ("allow_encashment",)

# Sandwich rule (minute 3.5): a holiday between two leave days counts as leave.
INCLUDE_HOLIDAY = 1

LEAVE_TYPES = {
	"Home Leave": {
		"is_earned_leave": 1,
		# The largest year any company grants (minute 3.3); each company's own
		# figure (NGK 20) is its Leave Policy, held by hr/leave_ceiling.
		"max_leaves_allowed": 33,
		"earned_leave_frequency": "Monthly",
		"rounding": "0.25",
		"allocate_on_day": "Last Day",
		"include_holiday": INCLUDE_HOLIDAY,
		"allow_encashment": 1,
		"is_carry_forward": 0,
		# Taken ahead of the credit, capped at the year (user 2026-10-15,
		# patches/setup_leave_recovery). Set here too: year_setup re-runs this.
		"allow_negative": 1,
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
	"Replacement Leave": {
		"is_compensatory": 1,
		"is_earned_leave": 0,
		"include_holiday": INCLUDE_HOLIDAY,
		"allow_encashment": 0,
		"is_carry_forward": 0,
	},
	"Leave Without Pay": {
		"is_lwp": 1,
		"is_earned_leave": 0,
		"allow_encashment": 0,
		"is_carry_forward": 0,
	},
}


def execute():
	# Home Leave was renamed Casual Leave on 2026-09-17 and back on 2026-11-03;
	# rename rather than create a second type, or every allocation is orphaned.
	if frappe.db.exists("Leave Type", "Casual Leave") and not frappe.db.exists("Leave Type", "Home Leave"):
		frappe.rename_doc("Leave Type", "Casual Leave", "Home Leave", force=True)

	for name, values in LEAVE_TYPES.items():
		if frappe.db.exists("Leave Type", name):
			doc = frappe.get_doc("Leave Type", name)
			# Whether a type is encashed is HR's switch (policy minute 7.2): seeded
			# when the type is created, never reset by a later run (year_setup
			# re-runs this every year).
			values = {k: v for k, v in values.items() if k not in HR_OWNED}
		else:
			doc = frappe.new_doc("Leave Type")
			doc.leave_type_name = name
		doc.update(values)
		doc.save(ignore_permissions=True)
