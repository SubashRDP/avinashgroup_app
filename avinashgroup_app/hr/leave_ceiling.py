"""A year's leave may arrive in any shape, but it may not exceed the year's figure.

The client's rule (2026-09-22): the monthly credit is a convenience, not the
policy. An admin may give three days one month and four the next — what must
never happen is a year totalling more than the days the company grants: 21
casual and 12 sick, or 8 and 12 at Karnali.

The monthly accrual already respects that: it credits the smaller of this
month's share and what is left of the year. Nothing, though, stopped a
hand-made Leave Allocation — or the Allocate Leaves button on a submitted one —
from pushing someone past it, and an over-allocation only shows up much later as
a leave balance nobody can explain.

So the ceiling is checked where leave is granted. The figure comes from the
employee's own Leave Policy, which is why Karnali's 8 is enforced as 8: a limit
typed on the Leave Type itself would be one number for the whole group.

Leave carried in from last year is not part of it. It was earned under last
year's ceiling, and counting it here would quietly shrink this year's.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate


def validate_within_policy(doc, method=None):
	"""Refuse an allocation that would take the year past the policy's figure."""
	annual = policy_allocation(doc.employee, doc.leave_type, doc.from_date, doc.to_date)
	if not annual:
		return

	granted = flt(doc.new_leaves_allocated) + already_granted(doc)
	if granted <= annual + 0.001:
		return

	frappe.throw(
		_(
			"{0} is allowed {1} days of {2} this year, and this would make {3}.<br><br>"
			"The month's amount can be anything — three days one month, four the next — "
			"but the year's total cannot pass {1}."
		).format(
			frappe.bold(doc.employee_name or doc.employee),
			frappe.bold(f"{annual:g}"),
			frappe.bold(doc.leave_type),
			frappe.bold(f"{granted:g}"),
		),
		title=_("Over the year's leave"),
	)


def policy_allocation(employee, leave_type, from_date, to_date):
	"""Days of this leave type the employee's own policy grants for the year."""
	assignment = frappe.db.sql(
		"""select lpa.leave_policy
		from `tabLeave Policy Assignment` lpa
		where lpa.employee = %s and lpa.docstatus = 1
		  and lpa.effective_from <= %s and lpa.effective_to >= %s
		order by lpa.effective_from desc limit 1""",
		(employee, getdate(to_date), getdate(from_date)),
	)
	if not assignment:
		return 0

	return flt(
		frappe.db.get_value(
			"Leave Policy Detail",
			{"parent": assignment[0][0], "leave_type": leave_type},
			"annual_allocation",
		)
	)


def already_granted(doc):
	"""What other allocations have granted for the same type and period.

	Only `new_leaves_allocated`: leave carried forward was earned last year and
	is not spent against this year's ceiling.
	"""
	rows = frappe.db.sql(
		"""select sum(new_leaves_allocated)
		from `tabLeave Allocation`
		where employee = %s and leave_type = %s and docstatus = 1
		  and name != %s and from_date <= %s and to_date >= %s""",
		(doc.employee, doc.leave_type, doc.name or "", getdate(doc.to_date), getdate(doc.from_date)),
	)
	return flt(rows[0][0]) if rows else 0.0
