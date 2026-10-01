"""Move staff between the rotational shifts, many at a time, from one date.

Some staff change shift every month: this month on 6 AM - 2 PM, next month on
12 PM - 8 PM, and back again. Only those two shifts rotate; the day shift and the
other companies' shifts are fixed, and nobody is rotated into or out of them.

Nothing in the stock screens can do that for people who already hold a shift,
which here is everybody (one open-ended Shift Assignment from the start of the
fiscal year):

  * Shift Assignment (and the Shift Assignment Tool's "Assign Shift", which
    creates them) refuses, because the new dates overlap the standing one:
    "already has an active Shift Assignment ... for some/all of these dates".
    The tool does not even list such people — it offered 1 of 107 on nepalgas.
  * Shift Schedule repeats by weekday every 1-4 weeks, not by month, and creates
    the same overlapping assignments.
  * Shift Request works once (`hr.shift_change` makes room for it) but one
    request per person per month is the painful part, and the second month is
    refused outright: the first request has no end date, so HRMS calls the next
    one "already applied for Shift ... that overlaps within this period", and
    refuses the way back a second time as "your Default Shift".
  * None of them knows which shifts rotate. Any shift can be picked.

So this is the bulk form of the same move `hr.shift_change` makes for a permanent
Shift Request, done on the Shift Assignments directly: the standing assignment
ends the day before, the new shift runs on, open-ended, until HR moves the person
again.

    before          6 AM - 2 PM   Shrawan 1 ─────────────────────────▶ open
    1 Kartik        6 AM - 2 PM   Shrawan 1 ──▶ 30 Asoj
                    12 PM - 8 PM                1 Kartik ─────────────▶ open
    1 Mangsir       6 AM - 2 PM   Shrawan 1 ──▶ 30 Asoj
                    12 PM - 8 PM                1 Kartik ──▶ 30 Kartik
                    6 AM - 2 PM                              1 Mangsir ▶ open

Moving somebody back from the SAME date undoes the move: the rotated assignment
is cancelled and the one before it runs on again, as if nothing had happened.

Which shifts rotate is data, not code: `Shift Type.custom_in_rotation`, ticked by
HR (patches/setup_shift_rotation.py adds the field and ticks NGI's two). Both the
shift a person leaves and the one they join must be ticked and belong to the
person's own company; anything else is refused by name, here on the server — the
dialog only filters.

Entry point: the "Move Staff to This Shift" button on a rotational Shift Type
(public/js/shift_type.js), which calls `preview` and `rotate`. HR picks the date,
the shift and the people. Nothing here runs on a schedule and nothing alternates
by itself. Write-up: docs/shift-rotation.md.

Deliberately narrow:
  * Attendance is not touched here. A date already lived is re-marked by
    `hr.shift_backdate` — the same detach / rebuild a backdated Shift Assignment
    gets, including the refusal into a month already paid.
  * A person with a dated shift change still ahead of them (a Shift Request for
    next week) is refused, not untangled. Whose dates win is HR's call.
  * A single person, for a few days, is still a Shift Request. Untouched.
"""

import frappe
from frappe import _
from frappe.utils import add_days, formatdate, getdate, strip_html, today

from hrms.hr.doctype.shift_assignment_tool.shift_assignment_tool import create_shift_assignment
from rdp_common_app.utils.bs_boundaries import ad_to_bs, get_bs_month_end, get_bs_month_name

from avinashgroup_app.hr import shift_backdate
from avinashgroup_app.hr.overtime import get_shift_window
from avinashgroup_app.hr.shift_day import ShiftRoster

#: The Shift Type checkbox that says "this shift takes part in rotation".
ROTATION_FIELD = "custom_in_rotation"


class ShiftRotationError(frappe.ValidationError):
	"""A move the rotation rule does not allow. Raised with a sentence HR can act on."""


# ─────────────────────────────────────────────────────── which shifts rotate ──


def rotational_shifts(company):
	"""Names of the company's rotational Shift Types, earliest start first."""
	if not frappe.db.has_column("Shift Type", ROTATION_FIELD):
		frappe.throw(
			_("Shift rotation is not set up on this site yet. Run bench migrate."),
			title=_("Not Set Up"),
		)
	return frappe.get_all(
		"Shift Type",
		filters={"custom_company": company, ROTATION_FIELD: 1},
		order_by="start_time",
		pluck="name",
	)


def default_from_date():
	"""First day of the next BS month: rotation is by the month, and the books are BS."""
	return add_days(get_bs_month_end(getdate(today())), 1)


# ──────────────────────────────────────────────────────────────── the desk ──


@frappe.whitelist()
def preview(company, to_shift, from_date=None):
	"""Who could move to `to_shift` on `from_date`: staff on the company's OTHER rotational shifts.

	Read-only. Returns the date (defaulted to the next BS month's first day), its
	BS reading, the company's rotational shifts and one row per candidate.
	"""
	frappe.has_permission("Shift Assignment", "read", throw=True)
	start = getdate(from_date) if from_date else default_from_date()
	shifts = rotational_shifts(company)
	_check_target(company, to_shift, shifts)

	employees = frappe.get_all(
		"Employee",
		filters={"company": company, "status": "Active"},
		fields=["name", "employee_name", "department"],
		order_by="name",
	)
	roster = ShiftRoster(employees, start, start)
	rows = []
	for employee in employees:
		current = roster.shift_on(employee.name, start)
		if current in shifts and current != to_shift:
			rows.append(
				{
					"employee": employee.name,
					"employee_name": employee.employee_name,
					"department": employee.department,
					"from_shift": current,
				}
			)

	bs = ad_to_bs(start)
	return {
		"from_date": str(start),
		"from_miti": f"{bs.day} {get_bs_month_name(bs.month)} {bs.year}",
		"shifts": shifts,
		"employees": rows,
	}


@frappe.whitelist()
def rotate(company, to_shift, from_date, employees):
	"""Move each of `employees` onto `to_shift` from `from_date`, open-ended.

	One person's refusal does not stop the rest: a month's rotation is thirty
	names, and one of them holding a Shift Request should not send HR back to
	re-tick the other twenty-nine. Returns {"moved": [...], "refused": [...]},
	every refusal carrying the reason; the dialog shows both lists.
	"""
	frappe.has_permission("Shift Assignment", "create", throw=True)
	frappe.has_permission("Shift Assignment", "submit", throw=True)

	employees = frappe.parse_json(employees) or []
	if not employees:
		frappe.throw(_("Tick at least one employee to move."), title=_("Nobody Selected"))
	if not from_date:
		frappe.throw(_("Enter the date the new shift starts."), title=_("No Date"))
	start = getdate(from_date)
	shifts = rotational_shifts(company)
	_check_target(company, to_shift, shifts)

	moved, refused = [], []
	for employee in dict.fromkeys(employees):  # a name sent twice moves once
		savepoint = "shift_rotation"
		frappe.db.savepoint(savepoint)
		try:
			moved.append(_move(employee, company, to_shift, start, shifts))
		except frappe.ValidationError as e:
			# Ours, HRMS's overlap check and the paid-month guard all land here,
			# each already worded for HR. Anything else is a bug and must raise.
			frappe.db.rollback(save_point=savepoint)
			frappe.clear_last_message()
			refused.append(
				{
					"employee": employee,
					"employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
					"reason": strip_html(str(e)),
				}
			)
	return {"moved": moved, "refused": refused}


# ──────────────────────────────────────────────────────────────── the rule ──


def _check_target(company, to_shift, shifts):
	"""Refuse a destination that does not rotate in this company."""
	if to_shift in shifts:
		return
	owner = frappe.db.get_value("Shift Type", to_shift, "custom_company")
	if not owner:
		raise_rotation_error(_("Shift {0} does not exist.").format(frappe.bold(to_shift)))
	if owner != company:
		raise_rotation_error(
			_("{0} is a shift of {1}. Staff of {2} can only rotate between its own shifts.").format(
				frappe.bold(to_shift), owner, company
			)
		)
	raise_rotation_error(
		_(
			"{0} does not take part in rotation, so nobody can be rotated onto it. Rotational shifts of "
			"{1}: {2}. To make it one, tick Takes Part in Rotation on the Shift Type; to move one "
			"person onto a fixed shift, use a Shift Request."
		).format(frappe.bold(to_shift), company, ", ".join(shifts) or _("none"))
	)


def _move(employee, company, to_shift, start, shifts):
	"""Move one person. Raises frappe.ValidationError with the reason if they cannot."""
	person = frappe.db.get_value("Employee", employee, ["employee_name", "company", "status"], as_dict=True)
	if not person:
		raise_rotation_error(_("Employee {0} does not exist.").format(employee))
	label = f"{person.employee_name} ({employee})"
	if person.company != company:
		raise_rotation_error(_("{0} belongs to {1}, not {2}.").format(label, person.company, company))

	from_shift = get_shift_window(employee, start)[0]
	if from_shift == to_shift:
		raise_rotation_error(
			_("{0} is already on {1} on {2}.").format(label, frappe.bold(to_shift), formatdate(start))
		)
	if from_shift not in shifts:
		raise_rotation_error(
			_(
				"{0} is on {1} on {2}, which does not take part in rotation. Only staff on {3} rotate; "
				"for a one-off change use a Shift Request."
			).format(label, frappe.bold(from_shift or _("no shift")), formatdate(start), ", ".join(shifts))
		)

	standing = _assignments_from(employee, start)
	ahead = [a for a in standing if getdate(a.start_date) > start or a.end_date]
	if ahead or len(standing) > 1:
		raise_rotation_error(
			_(
				"{0} has a dated shift change on or after {1} ({2}). Cancel it first, or start the "
				"rotation after it ends."
			).format(label, formatdate(start), ", ".join(a.name for a in ahead or standing))
		)

	# The days already lived, exactly as a backdated Shift Assignment is handled:
	# refused if paid, detached now, re-marked once the roster is whole again.
	change = frappe._dict(
		doctype="Shift Assignment",
		employee=employee,
		employee_name=person.employee_name,
		start_date=start,
		end_date=None,
	)
	shift_backdate.prepare_assignment_cancel(change)

	# The Shift Assignment hooks stand aside while the roster is half-moved, as
	# they do for a Shift Request; one rebuild follows, below.
	frappe.flags.in_shift_request = True
	try:
		assignment = _swap(employee, person.company, to_shift, start, standing)
	finally:
		frappe.flags.in_shift_request = False

	shift_backdate.rebuild_for_assignment(change)
	return {
		"employee": employee,
		"employee_name": person.employee_name,
		"from_shift": from_shift,
		"to_shift": to_shift,
		"shift_assignment": assignment,
	}


def _swap(employee, company, to_shift, start, standing):
	"""End what runs into `start`, start `to_shift` there. Returns the assignment now covering it."""
	if standing:
		assignment = frappe.get_doc("Shift Assignment", standing[0].name)
		if getdate(assignment.start_date) < start:
			assignment.db_set("end_date", add_days(start, -1), update_modified=False)
		else:
			# It starts on this very date, so it has no day left to cover. Kept
			# cancelled rather than deleted: it is the record that the move was made.
			assignment.cancel()

	previous = frappe.db.get_value(
		"Shift Assignment",
		{
			"employee": employee,
			"docstatus": 1,
			"status": "Active",
			"shift_type": to_shift,
			"end_date": add_days(start, -1),
		},
		"name",
	)
	if previous:
		# Back onto the shift they were on until yesterday: that is the last move
		# being undone, so let the earlier assignment run on instead of adding a
		# second piece of the same shift beside it.
		frappe.db.set_value("Shift Assignment", previous, "end_date", None, update_modified=False)
		return previous

	return create_shift_assignment(employee, company, to_shift, start, None, "Active").name


def _assignments_from(employee, start):
	"""Submitted, active assignments still running on or after `start`, earliest first."""
	return frappe.db.sql(
		"""select name, start_date, end_date from `tabShift Assignment`
		where employee = %s and docstatus = 1 and status = 'Active'
		  and (end_date is null or end_date >= %s)
		order by start_date""",
		(employee, start),
		as_dict=True,
	)


def raise_rotation_error(message):
	frappe.throw(message, exc=ShiftRotationError, title=_("Shift Rotation"))
