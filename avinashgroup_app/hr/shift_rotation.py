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
    one "already applied for Shift ... that overlaps within this period". With
    an end date instead, the way back is refused as "your Default Shift".
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

Entry points: the "Move Staff to This Shift" button on a rotational Shift Type
(public/js/shift_type.js), which calls `preview` and `rotate` — open-ended, from
one date; and the Shift Roster page's Apply, which calls `set_periods` — bounded
ranges, one per painted run of months. Nothing here runs on a schedule and
nothing alternates by itself. Write-up: docs/shift-rotation.md.

`rotate` versus `set_period`: `rotate` moves people from a date onwards and
refuses anybody with a dated change already ahead. `set_period` puts a person on
a shift for [start, end] only — the assignment running through the range is cut
around it and resumes the day after — so it works whatever is booked later.

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


# ─────────────────────────────────────────────────── a bounded period ──


@frappe.whitelist()
def set_periods(company, changes):
	"""Put people on rotational shifts for bounded date ranges — the Shift Roster's Apply.

	`changes`: a list (or JSON list) of {"employee", "shift", "start", "end"}, one
	per run of painted cells, dates as YYYY-MM-DD with `end` inclusive. Each runs
	through `set_period` in date order (start, then employee), on its own
	savepoint, so one refusal does not stop the rest — same contract as `rotate`.

	Returns {"moved": [...], "refused": [...]}: every moved entry is what
	`set_period` returns; every refused entry is the change as sent plus
	"employee_name" and "reason" (plain text, worded for HR).
	"""
	frappe.has_permission("Shift Assignment", "create", throw=True)
	frappe.has_permission("Shift Assignment", "submit", throw=True)
	frappe.has_permission("Shift Assignment", "cancel", throw=True)

	changes = frappe.parse_json(changes) or []
	if not changes:
		frappe.throw(_("Nothing to apply."), title=_("No Changes"))
	shifts = rotational_shifts(company)

	changes = [{key: change.get(key) for key in ("employee", "shift", "start", "end")} for change in changes]
	moved, refused = [], []
	for change in sorted(changes, key=lambda c: (str(c["start"] or ""), c["employee"] or "")):
		savepoint = "shift_period"
		frappe.db.savepoint(savepoint)
		try:
			moved.append(
				set_period(company, change["employee"], change["shift"], change["start"], change["end"], shifts)
			)
		except frappe.ValidationError as e:
			# Ours, HRMS's overlap check and the paid-month guard all land here,
			# each already worded for HR. Anything else is a bug and must raise.
			frappe.db.rollback(save_point=savepoint)
			frappe.clear_last_message()
			refused.append(
				{
					**change,
					"employee_name": frappe.db.get_value("Employee", change["employee"], "employee_name"),
					"reason": strip_html(str(e)),
				}
			)
	return {"moved": moved, "refused": refused}


def set_period(company, employee, shift, start, end, shifts=None):
	"""Put `employee` on `shift` from `start` to `end` inclusive; every other day keeps its shift.

	The bounded form of `rotate`. Painting Kartik onto the evening shift for
	somebody on mornings all year ends the morning assignment on 30 Asoj, starts
	evenings on 1 Kartik ending 30 Kartik, and resumes mornings on 1 Mangsir with
	the end the morning assignment had. Unlike `rotate`, a dated change later on
	is not in the way: it lies outside the range and is left alone.

	The same rules as `rotate`, checked here: `shift` must be rotational and of
	`company`; the person must be of `company` and, on EVERY day of the range, on
	one of its rotational shifts (a day on the day shift, or on no shift, refuses
	the whole range); a range reaching into a paid month is refused; lived days
	are re-marked by `hr.shift_backdate`, as for a backdated Shift Assignment.

	`shifts`: the company's rotational shifts, when the caller already has them.
	Raises frappe.ValidationError (ShiftRotationError for the rotation rules)
	with a sentence HR can act on. Returns {"employee", "employee_name", "shift",
	"start", "end", "from_shifts" (the shifts the range held before, in date
	order), "shift_assignment" (the assignment now covering the range)}.
	"""
	if not (start and end):
		raise_rotation_error(_("Enter both the first and the last day of the period."))
	start, end = getdate(start), getdate(end)
	if start > end:
		raise_rotation_error(
			_("The period ends ({0}) before it starts ({1}).").format(formatdate(end), formatdate(start))
		)
	shifts = shifts if shifts is not None else rotational_shifts(company)
	_check_target(company, shift, shifts)

	person = frappe.db.get_value("Employee", employee, ["employee_name", "company"], as_dict=True)
	if not person:
		raise_rotation_error(_("Employee {0} does not exist.").format(employee))
	label = f"{person.employee_name} ({employee})"
	if person.company != company:
		raise_rotation_error(_("{0} belongs to {1}, not {2}.").format(label, person.company, company))

	held = _shifts_held(employee, start, end)
	period = f"{formatdate(start)} – {formatdate(end)}"
	if [s for s, _first, _last in held] == [shift]:
		raise_rotation_error(_("{0} is already on {1} for {2}.").format(label, frappe.bold(shift), period))
	for current, first, last in held:
		if current not in shifts:
			raise_rotation_error(
				_(
					"{0} is on {1} from {2} to {3}, which does not take part in rotation. Only staff on "
					"{4} rotate; for a one-off change use a Shift Request."
				).format(
					label,
					frappe.bold(current or _("no shift")),
					formatdate(first),
					formatdate(last),
					", ".join(shifts),
				)
			)

	# Lived days: refused if paid, detached now, re-marked once the roster is whole.
	change = frappe._dict(
		doctype="Shift Assignment",
		employee=employee,
		employee_name=person.employee_name,
		start_date=start,
		end_date=end,
	)
	shift_backdate.prepare_assignment_cancel(change)

	frappe.flags.in_shift_request = True  # one rebuild below, not one per piece
	try:
		assignment = _carve(employee, company, shift, start, end)
	finally:
		frappe.flags.in_shift_request = False

	shift_backdate.rebuild_for_assignment(change)
	return {
		"employee": employee,
		"employee_name": person.employee_name,
		"shift": shift,
		"start": str(start),
		"end": str(end),
		"from_shifts": list(dict.fromkeys(s for s, _first, _last in held)),
		"shift_assignment": assignment,
	}


def _shifts_held(employee, start, end):
	"""The range as [(shift, first day, last day)], one entry per run, HRMS's precedence (ShiftRoster)."""
	roster = ShiftRoster([employee], start, end)
	runs, day = [], start
	while day <= end:
		current = roster.shift_on(employee, day)
		if runs and runs[-1][0] == current:
			runs[-1][2] = day
		else:
			runs.append([current, day, day])
		day = add_days(day, 1)
	return [tuple(run) for run in runs]


def _carve(employee, company, shift, start, end):
	"""Make room for [start, end] in the person's assignments, then cover it with `shift`.

	Every overlapping assignment keeps the days outside the range:
	  * starts before and runs past it  → ends the day before; a copy resumes the day after
	  * starts before, ends inside      → ends the day before
	  * starts inside, runs past it     → starts the day after
	  * lies wholly inside              → cancelled (the record that it was replaced)
	Dates move with set_value rather than cancel-and-recreate, so no assignment
	outside the range is cancelled and HRMS never checks attendance outside it.
	Returns the name of the assignment that covers the range.
	"""
	day_before, day_after = add_days(start, -1), add_days(end, 1)
	for piece in _assignments_between(employee, start, end):
		piece_start = getdate(piece.start_date)
		piece_end = getdate(piece.end_date) if piece.end_date else None
		runs_past = piece_end is None or piece_end > end
		if piece_start < start:
			frappe.db.set_value("Shift Assignment", piece.name, "end_date", day_before, update_modified=False)
			if runs_past:
				create_shift_assignment(employee, company, piece.shift_type, day_after, piece_end, "Active")
		elif runs_past:
			frappe.db.set_value("Shift Assignment", piece.name, "start_date", day_after, update_modified=False)
		else:
			frappe.get_doc("Shift Assignment", piece.name).cancel()
	return _cover(employee, company, shift, start, end)


def _cover(employee, company, shift, start, end):
	"""Cover the now-empty [start, end] with `shift`, joining a neighbour on the same shift.

	Painting a month back to what surrounds it should leave one assignment, not
	three pieces of the same shift: the one ending the day before is stretched
	over the range (and over the one resuming the day after, if that has no lived
	day yet and can be cancelled cleanly); else the one starting the day after is
	pulled back to `start`; else a new assignment covers exactly the range.
	"""
	before = _neighbour(employee, shift, end_date=add_days(start, -1))
	after = _neighbour(employee, shift, start_date=add_days(end, 1))
	if before:
		if after and getdate(after.start_date) > getdate(today()):
			frappe.db.set_value("Shift Assignment", before.name, "end_date", after.end_date, update_modified=False)
			frappe.get_doc("Shift Assignment", after.name).cancel()
		else:
			frappe.db.set_value("Shift Assignment", before.name, "end_date", end, update_modified=False)
		return before.name
	if after:
		frappe.db.set_value("Shift Assignment", after.name, "start_date", start, update_modified=False)
		return after.name
	return create_shift_assignment(employee, company, shift, start, end, "Active").name


def _neighbour(employee, shift, **edge):
	"""The submitted, active assignment of `shift` with exactly this start_date or end_date."""
	return frappe.db.get_value(
		"Shift Assignment",
		{"employee": employee, "docstatus": 1, "status": "Active", "shift_type": shift, **edge},
		["name", "start_date", "end_date"],
		as_dict=True,
	)


def _assignments_between(employee, start, end):
	"""Submitted, active assignments overlapping [start, end], earliest first."""
	return frappe.db.sql(
		"""select name, shift_type, start_date, end_date from `tabShift Assignment`
		where employee = %s and docstatus = 1 and status = 'Active'
		  and start_date <= %s and (end_date is null or end_date >= %s)
		order by start_date""",
		(employee, end, start),
		as_dict=True,
	)


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
