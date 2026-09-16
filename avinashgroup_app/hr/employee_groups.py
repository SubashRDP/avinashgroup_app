"""Employee Group decides who is paid overtime and who gets replacement leave.

Policy, from the client meeting of 2026-09-15 as corrected on 2026-09-16
(`docs/hr-decisions/00-policy-minutes-2026-09-15.txt`, 2.2 and 2.5):

    Plant            worked a holiday or a Saturday -> paid OT + meals,
                     and NO replacement leave
    Officer & Admin  worked a holiday or a Saturday -> replacement leave
                     (compensatory off), and NO overtime

Membership lives in the `Employee Group` document's own table, and nothing on
the Employee record points back at it, so payroll, leave and our allowance engine
cannot see it: they all read `Employee.custom_ot_eligibility`. Saving a group
therefore mirrors its membership onto that field, and the groups stay the one
place HR edits.

Registered as a `doc_events` hook on Employee Group (on_update), and callable as
`sync_all()` for a backfill after the groups are first filled.

Deliberately narrow: it writes one checkbox. Granting the replacement leave for a
holiday actually worked is a separate step that reads the same checkbox — it is
not done here, because leave may only be granted once and that needs its own
record, not a side effect of saving a group.
"""

import frappe

# The two groups the 2026-09-15 policy splits the staff into. Names as created on
# the site; a group that does not exist is simply skipped, so a site that has not
# been set up yet does not break every Employee Group save.
OT_ELIGIBLE_GROUP = "Plant"
COMPENSATORY_LEAVE_GROUP = "Officer & Admin"


def sync_ot_eligibility(doc=None, method=None):
	"""Mirror group membership onto Employee.custom_ot_eligibility.

	Hook: doc_events -> Employee Group -> on_update. Saving either group syncs
	both, because moving somebody out of Plant only means anything once the other
	group has them.
	"""
	sync_all()


def sync_all():
	"""Set the flag for every member of both groups. Returns what changed."""
	wanted = {}
	for group, eligible in ((OT_ELIGIBLE_GROUP, 1), (COMPENSATORY_LEAVE_GROUP, 0)):
		if not frappe.db.exists("Employee Group", group):
			continue
		for employee in frappe.get_all("Employee Group Table", {"parent": group}, pluck="employee"):
			if not employee:
				continue
			if employee in wanted and wanted[employee] != eligible:
				# In both groups: the policy has no answer, so leave the employee
				# as they are and make the contradiction visible.
				frappe.log_error(
					title="Employee in both HR groups",
					message=f"{employee} is in {OT_ELIGIBLE_GROUP} and {COMPENSATORY_LEAVE_GROUP}; "
					"OT eligibility left unchanged",
				)
				wanted[employee] = None
				continue
			wanted[employee] = eligible

	changed = []
	for employee, eligible in wanted.items():
		if eligible is None:
			continue
		if (frappe.db.get_value("Employee", employee, "custom_ot_eligibility") or 0) == eligible:
			continue
		# db_set, not save(): this mirrors a decision made elsewhere and must never
		# block saving the group because some unrelated Employee field is invalid.
		frappe.db.set_value("Employee", employee, "custom_ot_eligibility", eligible)
		changed.append(employee)

	return changed
