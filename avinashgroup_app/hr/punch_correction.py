"""Correct a day's first IN / last OUT, or its shift, from the Monthly Attendance BS grid.

The commonest attendance fault here is a missing punch: somebody tapped in and
forgot to tap out, or the device missed them at the door. The day then has one
punch, HRMS marks it on zero hours (Half Day or Absent), and every allowance,
late fine and overtime figure that reads the row is wrong. HR sees it in the
Monthly Attendance BS grid as a red "— —", but until now had to leave the
report, open Employee Checkin, discover that HRMS refuses to move a punch that
is linked to an attendance ("Please cancel the attendance before modifying
time"), cancel the attendance, fix the punch, and then run Attendance Fix for
the day. This does that sequence as one step, in one transaction, from the cell
HR is looking at.

What a correction does to the punches (never a delete):

  * the day's FIRST punch is moved to the new IN, the LAST to the new OUT;
  * a missing side is added as a new Employee Checkin (a day with one punch gets
    the other one; a day with none gets both). With one punch, it is taken as
    whichever of IN or OUT it is closer to, so a 17:05 tap is kept as the OUT;
  * punches in between are left alone, and must lie between the new IN and OUT —
    otherwise the "first" and "last" asked for would not be first and last, and
    the request is refused naming those punches;
  * every punch touched is stamped: `custom_time_edited`, the device's original
    time in `custom_original_time` (kept from the FIRST correction, so a second
    edit cannot launder the device's reading), who, when and why. The Monthly
    Attendance BS report highlights those days from these stamps, and they live
    on the punches rather than on the Attendance because the attendance row is
    rebuilt (below) and could be rebuilt again by self-heal.

Then the day is rebuilt the way a backdated shift change rebuilds one
(hr/shift_backdate.py): the old Attendance is cancelled and removed, the punches
lose their link, and `reconcile_employee_day` — the primitive Attendance Fix and
self-heal use — marks the day again.

One difference: every punch of the day is PINNED to the shift rostered for it,
instead of letting HRMS's fetch_shift choose per punch. fetch_shift gives a
punch outside the rostered shift's check-in window to the employee's Default
Shift, so a day could end up split across two shifts — seen on demo, a 09:00 IN
on a 12-8 day went to the 9-5 default, and the attendance (hours 3.92, IN 13:07)
silently ignored the very time HR had entered while the report showed 09:00.
The app groups punches by calendar day everywhere (attendance_sync), the report
shows the day's first and last punch whatever the window, and a time HR typed in
is meant to count, so the whole day is measured against its one rostered shift. Rebuilding rather than
patching the row is deliberate: status (Half Day by hours, the more-than-two-
hours-late half day), the deviation fields and the holiday flag are all decided
by Attendance hooks that only run on a real insert. Approved Overtime Sheet rows
for the day are re-measured, since their hours are read from the in/out times.

A misplaced SHIFT is corrected the same way, for the day or up to
MAX_SHIFT_DAYS from it. The roster is fixed as the app's roster tools fix it
(hr/shift_rotation.make_room): the standing Shift Assignment ends the day before
and resumes the day after, untouched outside the range, and one new assignment
covers exactly the corrected days — stamped with the shift it replaced, who,
when and why (`custom_shift_corrected` …, patches/setup_shift_correction_fields),
which is what the report's amber Shift cell reads. Every day of the range is
then re-marked on the new shift; a day without punches keeps its row with only
the shift corrected, as a backdated shift change does. HRMS's own Shift Request
cannot do this for staff who already hold an open-ended assignment (it refuses
the overlap), which here is everybody.

Every correction — punch moved, added or deleted, shift changed, from this
dialog or from the Employee Checkin form — writes an Attendance Correction Log
entry in the same transaction (`log_correction`): one list of who changed which
day, from what to what, and why.

Refused, and why:

  * today or later — today's attendance is marked by HRMS after the shift ends;
  * a day inside a submitted Salary Slip — attendance under paid salary would
    silently disagree with the money (same rule as shift_backdate.guard_paid_period);
  * a shift change on a leave day (On Leave, Work From Home, anything with a
    Leave Application) — a leave decision is not a shift correction. Punches on
    a leave day ARE corrected: the row is kept, not rebuilt, and a punch makes
    it a Half Day with the leave kept (policy 3.4,
    biometric.attendance_override.half_day_if_came_in);
  * no shift rostered, or an overnight shift (as the day's or as the new one) —
    punches are grouped by calendar day everywhere in this app (attendance_sync),
    which an overnight shift breaks;
  * a shift of another company, or a shift correction longer than
    MAX_SHIFT_DAYS (that is a roster change: the Shift Roster page);
  * no reason — it is kept on the punches, the assignment and the log;
  * HRMS declining to mark attendance from the corrected punches — everything is
    rolled back rather than leaving the day with no attendance.

A time outside the shift's check-in window is allowed and counted, with a
warning, since HRMS on its own would not have counted it.

A draft Salary Slip covering the day is allowed, with a warning: it does not
re-read attendance until it is recalculated (Prepare Payroll Inputs).

Who: HR Manager and System Manager, the roles that may run Attendance Fix and
the single-day Repair on the Attendance form.

Called by the edit dialog in monthly_attendance_bs.js.
"""

from datetime import datetime, time, timedelta

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, get_time, getdate, now_datetime, strip_html, today

from avinashgroup_app.avinash_group_app.doctype.attendance_fix.attendance_fix import (
	reconcile_employee_day,
)
from avinashgroup_app.biometric.attendance_sync import get_day_checkins, relabel_day_checkins
from avinashgroup_app.hr.overtime import get_shift_window
from avinashgroup_app.hr.shift_backdate import LEAVE_STATUSES, _remeasure_overtime
from avinashgroup_app.payroll.special_payout import REGULAR_SLIPS

# The same two roles Attendance Fix's single-day Repair allows
# (attendance_fix.repair_attendance_day).
CORRECTION_ROLES = ("HR Manager", "System Manager")


class Refused(Exception):
	"""A day this module will not re-mark. `title` and `message` are for the user.

	Raised by the guards so the two callers can answer differently: the edit
	dialog throws it at the user, the Employee Checkin hooks only warn, because
	the punch itself has been saved and must stay saved.
	"""

	def __init__(self, title, message):
		super().__init__(message)
		self.title = title
		self.message = message


# A shift correction is for a misplaced day or a few, not a roster change: a
# month or more belongs on the Shift Roster page (hr/shift_rotation.set_periods).
MAX_SHIFT_DAYS = 31


@frappe.whitelist(methods=["POST"])
def correct_day(
	employee, attendance_date, in_time=None, out_time=None, reason=None, shift=None, shift_to_date=None
):
	"""Correct one day's first IN / last OUT and/or the shift of one or more days,
	then re-mark the attendance. One transaction: any refusal rolls all of it back.

	`in_time` / `out_time`: clock times ("09:00" or "09:00:00") on
	`attendance_date`; both or neither. `shift`: the Shift Type the days should
	have been on, from `attendance_date` to `shift_to_date` (inclusive; default
	the same day). `reason` is required for either change and is kept on the
	punches, the Shift Assignment and the Attendance comment.

	Returns the clicked day as it now reads, the change lines, warnings, and one
	line per other day the shift change re-marked.
	"""
	frappe.only_for(CORRECTION_ROLES)
	if not _fields_installed() or (shift and not _shift_fields_installed()):
		frappe.throw(_("Attendance correction is not set up on this site yet. Run bench migrate."))

	day = getdate(attendance_date)
	reason = strip_html(reason or "").strip()
	if not reason:
		frappe.throw(_("Give a reason for the correction. It is kept with the change."), title=_("Reason Required"))
	if not frappe.db.exists("Employee", employee):
		frappe.throw(_("Employee {0} not found.").format(employee))

	if bool(in_time) != bool(out_time):
		frappe.throw(_("Enter both First IN and Last OUT, or neither."))
	new_in = new_out = None
	if in_time:
		new_in = datetime.combine(day, get_time(in_time))
		new_out = datetime.combine(day, get_time(out_time))
		if new_out <= new_in:
			frappe.throw(_("OUT ({0}) must be after IN ({1}).").format(_clock(new_out), _clock(new_in)))

	last = getdate(shift_to_date) if (shift and shift_to_date) else day
	if last < day:
		frappe.throw(_("The shift change ends ({0}) before it starts ({1}).").format(last, day))
	if (last - day).days + 1 > MAX_SHIFT_DAYS:
		frappe.throw(
			_("A shift correction covers at most {0} days. Use the Shift Roster for longer periods.").format(MAX_SHIFT_DAYS)
		)
	days = [getdate(frappe.utils.add_days(day, i)) for i in range((last - day).days + 1)]

	try:
		for d in days:
			_guard_past(d)
			_guard_paid(employee, d)
		existing = {d: _attendance_on(employee, d) for d in days}
		if shift:
			# A leave day's shift is not corrected: change the leave. Its punches
			# are — coming in on leave is a Half Day (policy 3.4).
			_refuse_leave(existing[day], day)
		entries = []
		if shift:
			entries += _apply_shift(employee, day, last, shift, reason)
		shift_doc = _shift_for(employee, day, existing[day])
	except Refused as refused:
		frappe.throw(refused.message, title=refused.title)

	window = _check_in_window(shift_doc, day)
	if new_in:
		entries += _apply_punches(employee, day, new_in, new_out, reason)
	if not entries:
		# Nothing to move, but the attendance does not agree with the punches
		# (a desk-added punch HRMS gave to another shift, a stale row). Saving
		# unchanged values is how HR asks for the day to be re-marked from them.
		entries = [{"line": _("nothing changed; attendance re-marked from the punches"), "type": "Re-marked"}]
	changes = [e["line"] for e in entries]

	note = _("Corrected from Monthly Attendance BS: {0}. Reason: {1}").format(
		"; ".join(changes), frappe.utils.escape_html(reason)
	)
	result, other_days, attendance_of = None, [], {}
	frappe.flags.in_report_correction = True  # Correction Log source for follow-on entries
	try:
		for d in days:
			line = _remark_after_correction(employee, d, existing[d], note)
			attendance_of[d] = line.get("attendance")
			if d == day:
				result = line
			elif line.get("line"):
				other_days.append(line["line"])
	finally:
		frappe.flags.in_report_correction = False

	for entry in entries:
		for d in entry.get("days") or [day]:
			log_correction(
				employee, d, entry["type"], SOURCE_REPORT, entry.get("old"), entry.get("new"), reason,
				attendance=attendance_of.get(d), checkin=entry.get("checkin"),
				shift_assignment=entry.get("shift_assignment"),
			)

	if new_in:
		outside = [_clock(t) for t in (new_in, new_out) if not window[0] <= t <= window[1]]
		if outside:
			result["warnings"].append(
				_("{0} is outside {1}'s check-in window ({2} to {3}); it is counted because HR set it.").format(
					", ".join(outside), shift_doc.name, _clock(window[0]), _clock(window[1])
				)
			)
	result["changes"] = changes
	result["other_days"] = other_days
	return result


def _remark_after_correction(employee, day, existing, note):
	"""Re-mark one day of a correction. A day with punches is rebuilt; a day
	without keeps its row (Absent, hand-entered) with only the shift corrected,
	as hr/shift_backdate does — punches are what a rebuild needs. A leave day
	keeps its row too, and its punches make it a Half Day (policy 3.4)."""
	shift_doc = _shift_for(employee, day, existing)
	is_leave = existing and _is_leave(existing)
	if get_day_checkins(employee, day) and not is_leave:
		result = remark_day(employee, day, existing, shift_doc, note)
		result["line"] = _("{0}: {1}, {2} → {3}").format(day, result["status"], result["in_time"], result["out_time"])
		return result

	if existing:
		frappe.db.set_value("Attendance", existing.name, "shift", shift_doc.name, update_modified=False)
		frappe.get_doc("Attendance", existing.name).add_comment("Info", note)
		if is_leave:
			# Not rebuilt — that would drop the leave. Policy 3.4 instead: punched
			# → Half Day, leave kept; then the row's times follow the punches.
			from avinashgroup_app.biometric.attendance_sync import sync_day

			sync_day(employee, day)
			existing = _attendance_on(employee, day)
	return {
		"attendance": existing.name if existing else None,
		"status": existing.status if existing else _("Not Marked"),
		"working_hours": existing.working_hours if existing else 0,
		"in_time": _clock(existing.in_time) if existing else "—",
		"out_time": _clock(existing.out_time) if existing else "—",
		"overtime": _remeasure_overtime(employee, day, day)
		+ _recheck_replacement_leave(employee, day, existing.name if existing else None),
		"warnings": _draft_slip_warning(employee, day),
		"line": _("{0}: {1} kept, shift set to {2}").format(
			day, existing.status if existing else _("no attendance"), shift_doc.name
		),
	}


def _apply_shift(employee, start, end, shift, reason):
	"""Put the employee on `shift` for [start, end] only. Returns change lines.

	The roster tools' own carving (shift_rotation.make_room) empties the range —
	the standing assignment ends the day before and resumes the day after, so no
	date outside the range changes — and one new assignment covers exactly the
	range, stamped with what it replaced and why. Exactly, not merged into a
	neighbour on the same shift, so the stamp marks only the corrected days.

	The days are detached first (shift_backdate.detach_days): HRMS will not
	cancel an assignment while attendance or punches still name its shift. They
	are re-marked by the caller once the roster is whole.
	"""
	from hrms.hr.doctype.shift_assignment_tool.shift_assignment_tool import create_shift_assignment

	from avinashgroup_app.hr import shift_rotation
	from avinashgroup_app.hr.shift_backdate import detach_days

	company = frappe.db.get_value("Employee", employee, "company")
	target = frappe.db.get_value("Shift Type", shift, ["name", "start_time", "end_time", "custom_company"], as_dict=True)
	if not target:
		raise Refused(_("No Such Shift"), _("Shift {0} does not exist.").format(shift))
	if target.custom_company and target.custom_company != company:
		raise Refused(
			_("Another Company's Shift"),
			_("{0} is a shift of {1}; {2} works for {3}.").format(shift, target.custom_company, employee, company),
		)
	if get_time(target.end_time) <= get_time(target.start_time):
		raise Refused(
			_("Overnight Shift"),
			_("{0} runs overnight. Punches are grouped by calendar day, so a day cannot be corrected onto it here.").format(shift),
		)

	held = shift_rotation._shifts_held(employee, start, end)
	if all(current == shift for current, _first, _last in held):
		return []
	before = ", ".join(dict.fromkeys(current or _("no shift") for current, _first, _last in held))

	detach_days(employee, start, end)
	frappe.flags.in_shift_request = True  # the Shift Assignment hooks stand aside; the caller re-marks
	try:
		shift_rotation.make_room(employee, company, start, end)
		assignment = create_shift_assignment(employee, company, shift, start, end, "Active")
	finally:
		frappe.flags.in_shift_request = False
	frappe.db.set_value(
		"Shift Assignment",
		assignment.name,
		{
			"custom_shift_corrected": 1,
			"custom_corrected_from_shift": before,
			"custom_shift_correction_reason": reason,
			"custom_shift_corrected_by": frappe.session.user,
			"custom_shift_corrected_on": now_datetime(),
		},
		update_modified=False,
	)
	span = str(start) if start == end else f"{start} – {end}"
	return [
		{
			"line": _("shift {0} → {1} for {2} ({3})").format(before, shift, span, assignment.name),
			"type": "Shift Changed",
			"old": before,
			"new": shift,
			"shift_assignment": assignment.name,
			"days": [getdate(frappe.utils.add_days(start, i)) for i in range((end - start).days + 1)],
		}
	]


def day_context(employee, day):
	"""(existing Attendance or None, rostered Shift Type doc) for a day that may
	be re-marked. Raises Refused for every day this module leaves alone."""
	day = getdate(day)
	_guard_past(day)
	_guard_paid(employee, day)
	existing = _attendance_on(employee, day)
	_refuse_leave(existing, day)
	return existing, _shift_for(employee, day, existing)


def remark_day(employee, day, existing, shift_doc, note):
	"""Rebuild the day's attendance from its punches, re-measure its overtime,
	and leave `note` on the new Attendance. The guards (day_context) must have
	passed. Returns the day as it now reads, with warnings for the user."""
	after = _rebuild(employee, day, shift_doc, existing)
	frappe.get_doc("Attendance", after.name).add_comment("Info", note)
	overtime = _remeasure_overtime(employee, day, day) + _recheck_replacement_leave(employee, day, after.name)

	warnings = _draft_slip_warning(employee, day)
	if existing and existing.shift and existing.shift != shift_doc.name:
		# The roster moved after the day was first marked (a rotation, a
		# backdated change). Rebuilding follows the roster, which can turn the
		# same punches late or a half day — say so rather than let it surprise.
		warnings.append(
			_("Re-marked on {0}, the shift rostered for this day; it was marked on {1} before.").format(
				shift_doc.name, existing.shift
			)
		)
	return {
		"attendance": after.name,
		"status": after.status,
		"working_hours": after.working_hours,
		"in_time": _clock(after.in_time),
		"out_time": _clock(after.out_time),
		"overtime": overtime,
		"warnings": warnings,
	}


# ────────────────────────────────────────────── Employee Checkin form ──
#
# The same correction, reached by editing punches directly: a time changed,
# a punch added by hand or deleted on the Employee Checkin form (or through
# the REST API). biometric/attendance_sync's doc-event handlers call these
# for past days; the device pipeline, HRMS auto attendance and the edit dialog
# above never reach them (the first and last set
# frappe.flags.in_biometric_day_reconcile, HRMS writes the link with a query).
#
# The punch is already saved when these run, so a refusal is a warning, not an
# error: the day keeps its attendance and the old value-only sync applies.

FORM_EDIT_REASON = "Edited on Employee Checkin form"
FORM_ADD_REASON = "Added on Employee Checkin form"


def stamp_form_change(checkin_name, original_time, reason):
	"""Mark a hand-edited or hand-added punch for the report's highlight.

	`original_time` is the device's reading for an edit (kept from the first
	edit if there was one) and None for a punch added by hand.
	"""
	if not _fields_installed():
		return
	frappe.db.set_value(
		"Employee Checkin",
		checkin_name,
		{
			"custom_time_edited": 1,
			"custom_original_time": _device_reading(checkin_name, original_time),
			"custom_edit_reason": reason,
			"custom_edited_by": frappe.session.user,
			"custom_edited_on": now_datetime(),
		},
		update_modified=False,
	)


FORM_DELETE_REASON = "Deleted on Employee Checkin form"


def log_form_change(employee, day, correction_type, old, new, checkin, reason):
	"""Log a punch changed on the Employee Checkin form, after the day was re-marked,
	so the entry names the attendance the day now has."""
	attendance = _attendance_on(employee, getdate(day))
	log_correction(
		employee, day, correction_type, SOURCE_FORM, old, new, reason,
		attendance=attendance.name if attendance else None, checkin=checkin,
	)


def can_detach(employee, days):
	"""True when every day may be re-marked, so a linked punch may be moved.

	HRMS's validate refuses a time change on a punch linked to an attendance;
	the before_validate hook drops the link first when this says the day will
	be rebuilt straight after. On a leave or today's day the link stays and
	HRMS's own refusal stands; on a paid day the refusal says why, which
	HRMS's ("cancel the attendance first") does not — cancelling it would be
	the wrong advice under a paid slip.
	"""
	try:
		for day in days:
			day_context(employee, day)
	except Refused as refused:
		if refused.title == _("Payroll Already Submitted"):
			frappe.throw(refused.message, title=refused.title)
		return False
	return True


def remark_from_form(employee, day, note):
	"""Re-mark one day after a punch changed on the form.

	Returns False when the day is not this module's to re-mark (today, paid,
	leave, no or overnight shift), so the caller falls back to the value-only
	sync it always did. True otherwise, including when the rebuild failed —
	that is logged and the user told, but the punch save stands.
	"""
	day = getdate(day)
	try:
		existing, shift_doc = day_context(employee, day)
	except Refused as refused:
		if refused.title == _("Leave Day"):
			_came_in_on_leave(employee, day)
		elif day < getdate(today()):
			frappe.msgprint(
				refused.message, title=_("Attendance for {0} not re-marked").format(day), indicator="orange"
			)
		return False

	if not get_day_checkins(employee, day):
		if existing:
			frappe.msgprint(
				_("No punches are left on {0}, so its attendance {1} ({2}) was left as it is. Correct it by hand if it is wrong.").format(
					day, existing.name, existing.status
				),
				indicator="orange",
			)
		return True

	if _defer():
		frappe.enqueue(
			"avinashgroup_app.hr.punch_correction.remark_day_job",
			queue="short",
			job_id=f"remark_day::{employee}::{day}",
			deduplicate=True,
			enqueue_after_commit=True,
			employee=employee,
			day=str(day),
			note=note,
		)
		return True

	savepoint = "punch_form_remark"
	frappe.db.savepoint(savepoint)
	try:
		result = remark_day(employee, day, existing, shift_doc, note)
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		frappe.log_error(
			title=f"Re-marking {employee} {day} after a punch edit failed",
			message=frappe.get_traceback(),
		)
		frappe.msgprint(
			_("The punch was saved, but the attendance for {0} could not be re-marked (see Error Log). Use Correct First IN / Last OUT in Monthly Attendance BS.").format(day),
			indicator="orange",
		)
		return True

	lines = [
		_("Attendance for {0} re-marked: {1}, {2} → {3}.").format(
			day, result["status"], result["in_time"], result["out_time"]
		)
	] + result["warnings"] + result["overtime"]
	frappe.msgprint("<br>".join(lines), indicator="green", alert=not result["warnings"])
	return True


def _came_in_on_leave(employee, day):
	"""A punch on a leave day is not re-marked like a working day: policy 3.4
	makes it a Half Day with the leave kept. Say that, not "not re-marked" — the
	old warning read as a refusal although the punch was saved and counted."""
	from avinashgroup_app.biometric.attendance_override import half_day_if_came_in

	half_day_if_came_in(employee, day)
	att = _attendance_on(employee, day)
	if att and att.status == "Half Day" and att.leave_type:
		frappe.msgprint(
			_("Came in while on leave: {0} is a Half Day, the other half Present, {1} kept (policy 3.4).").format(
				frappe.bold(str(day)), att.leave_type
			),
			title=_("Punch saved"),
			indicator="green",
		)


def remark_day_job(employee, day, note):
	"""Background re-mark for punches edited in bulk (Data Import). Deduplicated
	per (employee, day), so an import of ten punches for one day rebuilds it once."""
	day = getdate(day)
	try:
		existing, shift_doc = day_context(employee, day)
	except Refused:
		return
	if get_day_checkins(employee, day):
		remark_day(employee, day, existing, shift_doc, note)


def _defer():
	"""Bulk writes rebuild in the background; a single form save does it inline,
	so the report shows the change as soon as the save returns."""
	return bool(frappe.flags.in_import or frappe.flags.in_patch or frappe.flags.in_migrate)


# ─────────────────────────────────────────────────────────────── guards ──


def _guard_paid(employee, day):
	slip = frappe.db.get_value(
		"Salary Slip",
		# A Dashain / encashment payout slip does not pay the days.
		{"employee": employee, "docstatus": 1, "start_date": ("<=", day), "end_date": (">=", day), **REGULAR_SLIPS},
		"name",
	)
	if slip:
		raise Refused(
			_("Payroll Already Submitted"),
			_(
				"{0} is inside submitted salary slip {1}. Correcting attendance there would "
				"disagree with what was paid. Cancel the slip first."
			).format(frappe.bold(str(day)), frappe.bold(slip)),
		)


def _guard_past(day):
	if getdate(day) >= getdate(today()):
		raise Refused(
			_("Not Yet"),
			_("Only past days can be corrected. Today's attendance is marked automatically once the shift ends."),
		)


def _attendance_on(employee, day):
	return frappe.db.get_value(
		"Attendance",
		{"employee": employee, "attendance_date": day, "docstatus": ("<", 2)},
		[
			"name", "status", "docstatus", "shift", "leave_application", "leave_type",
			"custom_late_excused", "custom_late_excuse_reason", "working_hours", "in_time", "out_time",
		],
		as_dict=True,
	)


def _is_leave(existing):
	return existing.status in LEAVE_STATUSES or existing.leave_application or existing.leave_type


def _refuse_leave(existing, day):
	if existing and _is_leave(existing):
		raise Refused(
			_("Leave Day"),
			_("{0} is {1} through leave. Its shift is not corrected here: change the leave itself.").format(
				frappe.bold(str(day)), existing.status
			),
		)


def _shift_for(employee, day, existing):
	"""The rostered shift (what fetch_shift will resolve the punches to)."""
	shift_name = get_shift_window(employee, day)[0] or (existing and existing.shift)
	if not shift_name:
		raise Refused(
			_("No Shift"),
			_("{0} has no shift on {1}. Assign one first, so there are rules to mark the day against.").format(
				employee, day
			),
		)
	shift_doc = frappe.get_doc("Shift Type", shift_name)
	if get_time(shift_doc.end_time) <= get_time(shift_doc.start_time):
		raise Refused(
			_("Overnight Shift"),
			_("{0} runs overnight. Punches are grouped by calendar day, so correct this day through Employee Checkin and Attendance Fix.").format(
				shift_name
			),
		)
	return shift_doc


def _check_in_window(shift_doc, day):
	"""(opens, closes): where HRMS attaches punches to this shift on this day (0 = to the day's edge)."""
	from avinashgroup_app.hr.shift_window import window_minutes

	before, after = window_minutes(shift_doc)
	opens = datetime.combine(day, get_time(shift_doc.start_time)) - timedelta(minutes=before)
	closes = datetime.combine(day, get_time(shift_doc.end_time)) + timedelta(minutes=after)
	return opens, closes


def _draft_slip_warning(employee, day):
	slip = frappe.db.get_value(
		"Salary Slip",
		{"employee": employee, "docstatus": 0, "start_date": ("<=", day), "end_date": (">=", day), **REGULAR_SLIPS},
		"name",
	)
	if not slip:
		return []
	return [
		_("Draft salary slip {0} covers this day. Run Prepare Payroll Inputs on its Payroll Entry before submitting, so it picks this up.").format(
			slip
		)
	]


# ─────────────────────────────────────────────────────────────── punches ──


def _apply_punches(employee, day, new_in, new_out, reason):
	"""Move / add punches so the day reads new_in → new_out. Returns one entry
	per punch touched: {"line", "type", "old", "new", "checkin"}."""
	punches = get_day_checkins(employee, day)

	middle = punches[1:-1]
	stray = [p for p in middle if not new_in <= get_datetime(p.time) <= new_out]
	if stray:
		frappe.throw(
			_(
				"The day also has punches at {0}, outside {1} to {2}. They would stay first or last. "
				"Choose times around them, or correct them in Employee Checkin."
			).format(", ".join(_clock(p.time) for p in stray), _clock(new_in), _clock(new_out)),
			title=_("Other Punches in the Way"),
		)

	first = last = None
	if len(punches) == 1:
		only = get_datetime(punches[0].time)
		if abs(only - new_out) < abs(only - new_in):
			last = punches[0]
		else:
			first = punches[0]
	elif punches:
		first, last = punches[0], punches[-1]

	stamp = {
		"custom_time_edited": 1,
		"custom_edit_reason": reason,
		"custom_edited_by": frappe.session.user,
		"custom_edited_on": now_datetime(),
	}
	changes = []
	# The attendance_sync hooks would relabel and sync after every single write;
	# the rebuild below does that once, for the finished day.
	previous = frappe.flags.in_biometric_day_reconcile
	frappe.flags.in_biometric_day_reconcile = True
	try:
		for label, punch, target, log_type in (("IN", first, new_in, "IN"), ("OUT", last, new_out, "OUT")):
			if punch is None:
				name = _add_punch(employee, target, log_type, stamp)
				changes.append({
					"line": _("{0} added at {1}").format(label, _clock(target)),
					"type": "Punch Added", "old": None, "new": f"{label} {_clock(target)}", "checkin": name,
				})
			elif get_datetime(punch.time) != target:
				_move_punch(punch, target, stamp)
				changes.append({
					"line": _("{0} {1} → {2}").format(label, _clock(punch.time), _clock(target)),
					"type": "Punch Time Edited",
					"old": f"{label} {_clock(punch.time)}", "new": f"{label} {_clock(target)}", "checkin": punch.name,
				})
	finally:
		frappe.flags.in_biometric_day_reconcile = previous

	if changes:
		relabel_day_checkins(employee, day)
	return changes


def _move_punch(punch, target, stamp):
	"""Move a punch, keeping the device's first reading. db.set_value, because
	HRMS's validate refuses a time change on a linked punch — the link is
	dropped in _rebuild anyway."""
	frappe.db.set_value(
		"Employee Checkin",
		punch.name,
		{"time": target, "custom_original_time": _device_reading(punch.name, punch.time), **stamp},
	)


def _device_reading(checkin_name, time_before):
	"""What the device recorded for this punch, if it ever did.

	A punch already corrected keeps the reading its first correction saved —
	None for one added by hand — so a second edit cannot pass a typed time off
	as the device's. An untouched punch's time before this edit IS the reading.
	"""
	edited, original = frappe.db.get_value(
		"Employee Checkin", checkin_name, ["custom_time_edited", "custom_original_time"]
	)
	return original if edited else time_before


def _add_punch(employee, target, log_type, stamp):
	checkin = frappe.new_doc("Employee Checkin")
	checkin.update({"employee": employee, "time": target, "log_type": log_type, **stamp})
	checkin.insert(ignore_permissions=True)
	return checkin.name


# ─────────────────────────────────────────────────────────────── rebuild ──


def _rebuild(employee, day, shift_doc, existing):
	"""Re-mark the day from its punches. Returns the new Attendance (name, status, ...)."""
	if existing:
		att = frappe.get_doc("Attendance", existing.name)
		att.flags.ignore_permissions = True
		# An approved Overtime Sheet row links this attendance; it is re-measured
		# onto the new row straight after, so the link must not block the cancel.
		att.flags.ignore_links = True
		if att.docstatus == 1:
			att.cancel()
		frappe.delete_doc("Attendance", att.name, force=True, ignore_permissions=True)

	# Pinned to the rostered shift, not re-fetched — see the module docstring.
	names = [p.name for p in get_day_checkins(employee, day)]
	opens, closes = _check_in_window(shift_doc, day)
	frappe.db.sql(
		f"""update `tabEmployee Checkin`
		set attendance = null, skip_auto_attendance = 0,
		    shift = %(shift)s, shift_start = %(start)s, shift_end = %(end)s,
		    shift_actual_start = %(opens)s, shift_actual_end = %(closes)s
		where name in %(names)s""",
		{
			"names": names,
			"shift": shift_doc.name,
			"start": datetime.combine(day, get_time(shift_doc.start_time)),
			"end": datetime.combine(day, get_time(shift_doc.end_time)),
			"opens": opens,
			"closes": closes,
		},
	)
	log = []
	reconcile_employee_day(
		shift_doc,
		employee,
		day,
		holiday_dates=frozenset(),  # a punch on a holiday still needs marking
		counters={"attendance_created_or_updated": 0, "absent_rows_deleted": 0, "checkins_relinked": 0},
		log_lines=log,
		include_skipped=True,
		mark_absent_when_no_checkins=False,
	)

	after = frappe.db.get_value(
		"Attendance",
		{"employee": employee, "attendance_date": day, "docstatus": ("<", 2)},
		["name", "status", "working_hours", "in_time", "out_time", "half_day_status", "leave_type", "shift"],
		as_dict=True,
	)
	if not after:
		frappe.throw(
			_("HRMS would not mark attendance from these times, so nothing was changed. {0}").format(
				"<br>".join(log)
			),
			title=_("Attendance Not Marked"),
		)
	if existing and existing.custom_late_excused:
		_carry_late_excuse(after, existing)
	return after


def _carry_late_excuse(after, existing):
	"""Keep HR's waiver of the day's lateness on the rebuilt row, and with it the
	Present status the waiver restores (attendance_override._undo_excused_late_half_day)."""
	from avinashgroup_app.biometric.attendance_override import _undo_excused_late_half_day

	doc = frappe.get_doc("Attendance", after.name)
	doc.custom_late_excused = 1
	doc.custom_late_excuse_reason = existing.custom_late_excuse_reason
	_undo_excused_late_half_day(doc)
	values = {
		"custom_late_excused": 1,
		"custom_late_excuse_reason": doc.custom_late_excuse_reason,
		"status": doc.status,
		"half_day_status": doc.half_day_status,
	}
	frappe.db.set_value("Attendance", doc.name, values)
	after.update(values)


def _recheck_replacement_leave(employee, day, attendance):
	"""Grant, top up or take back the day's replacement leave after a correction
	(hr/replacement_leave.recheck_day), and put each outcome in the Correction Log.
	A refusal to take leave back is a warning, never a failure of the correction."""
	from avinashgroup_app.hr.replacement_leave import recheck_day

	lines = recheck_day(employee, day)
	for line in lines:
		log_correction(
			employee, day, "Replacement Leave", SOURCE_REPORT if frappe.flags.get("in_report_correction") else SOURCE_FORM,
			None, line.lstrip("⚠ "), _("Follows the corrected punches"), attendance=attendance,
		)
		if line.startswith("⚠"):
			frappe.msgprint(line, indicator="orange")
	return lines


SOURCE_REPORT = "Monthly Attendance BS"
SOURCE_FORM = "Employee Checkin Form"


def log_correction(
	employee, day, correction_type, source, old, new, reason,
	attendance=None, checkin=None, shift_assignment=None, leave_application=None,
):
	"""One Attendance Correction Log row, in the caller's transaction. No-op
	until the doctype is installed (bench migrate)."""
	if not frappe.db.exists("DocType", "Attendance Correction Log"):
		return None
	person = frappe.db.get_value("Employee", employee, ["employee_name", "company"], as_dict=True) or {}
	entry = frappe.get_doc(
		{
			"doctype": "Attendance Correction Log",
			"employee": employee,
			"employee_name": person.get("employee_name"),
			"company": person.get("company"),
			"attendance_date": getdate(day),
			"correction_type": correction_type,
			"source": source,
			"old_value": old,
			"new_value": new,
			"reason": reason,
			"done_by": frappe.session.user,
			"done_by_name": frappe.utils.get_fullname(frappe.session.user),
			"done_on": now_datetime(),
			"attendance": attendance,
			"employee_checkin": checkin,
			"shift_assignment": shift_assignment,
			"leave_application": leave_application,
		}
	)
	entry.insert(ignore_permissions=True)
	return entry.name


def _fields_installed():
	"""The stamps arrive with a migrate; until then there is nothing to read or write."""
	return frappe.get_meta("Employee Checkin").has_field("custom_time_edited")


def _shift_fields_installed():
	return frappe.get_meta("Shift Assignment").has_field("custom_shift_corrected")


def _clock(value):
	"""09:15, or 09:15:42 when the seconds matter — device punches carry them."""
	if not value:
		return "—"
	value = get_datetime(value)
	return value.strftime("%H:%M:%S" if value.second else "%H:%M")


# ─────────────────────────────────────────────────────────────── report ──


def get_edited_days(employees, start, end):
	"""{(employee, date): {punch time: note}} for every corrected punch.

	Read by Monthly Attendance BS, which highlights the IN or OUT cell whose punch
	is in here. A note is that cell's tooltip: what the device said, who changed
	it, when and why.
	"""
	if not employees or not _fields_installed():
		return {}
	rows = frappe.db.sql(
		"""select employee, `time`, custom_original_time, custom_edit_reason,
			custom_edited_by, custom_edited_on
		from `tabEmployee Checkin`
		where custom_time_edited = 1 and employee in %(names)s
		  and `time` >= %(start)s and `time` < %(end)s""",
		{
			"names": list(employees),
			"start": datetime.combine(getdate(start), time.min),
			"end": datetime.combine(getdate(end) + timedelta(days=1), time.min),
		},
		as_dict=True,
	)
	users = {}
	out = {}
	for r in rows:
		if r.custom_edited_by not in users:
			users[r.custom_edited_by] = frappe.utils.get_fullname(r.custom_edited_by) if r.custom_edited_by else ""
		was = (
			_("device read {0}").format(_clock(r.custom_original_time))
			if r.custom_original_time
			else _("no punch on the device")
		)
		note = _("{0} — was {1}. Changed by {2} on {3}. Reason: {4}").format(
			_clock(r.time),
			was,
			users[r.custom_edited_by] or _("unknown"),
			frappe.utils.format_datetime(r.custom_edited_on, "yyyy-MM-dd HH:mm") if r.custom_edited_on else "—",
			r.custom_edit_reason or "—",
		)
		out.setdefault((r.employee, getdate(r.time)), {})[get_datetime(r.time)] = note
	return out


def get_shift_corrections(employees, start, end):
	"""{(employee, date): note} for days a correction put on another shift.

	Read by Monthly Attendance BS to highlight the Shift cell. From the stamped
	Shift Assignments (custom_shift_corrected), which decide the day's shift and
	outlive any rebuild of its attendance.
	"""
	if not employees or not frappe.get_meta("Shift Assignment").has_field("custom_shift_corrected"):
		return {}
	rows = frappe.db.sql(
		"""select employee, shift_type, start_date, end_date, custom_corrected_from_shift,
			custom_shift_correction_reason, custom_shift_corrected_by, custom_shift_corrected_on
		from `tabShift Assignment`
		where custom_shift_corrected = 1 and docstatus = 1 and employee in %(names)s
		  and start_date <= %(end)s and (end_date is null or end_date >= %(start)s)""",
		{"names": list(employees), "start": getdate(start), "end": getdate(end)},
		as_dict=True,
	)
	out = {}
	for r in rows:
		note = _("Shift {0} → {1}. Changed by {2} on {3}. Reason: {4}").format(
			r.custom_corrected_from_shift or "—",
			r.shift_type,
			frappe.utils.get_fullname(r.custom_shift_corrected_by) if r.custom_shift_corrected_by else _("unknown"),
			frappe.utils.format_datetime(r.custom_shift_corrected_on, "yyyy-MM-dd HH:mm") if r.custom_shift_corrected_on else "—",
			r.custom_shift_correction_reason or "—",
		)
		d = max(getdate(r.start_date), getdate(start))
		last = min(getdate(r.end_date) if r.end_date else getdate(end), getdate(end))
		while d <= last:
			out[(r.employee, d)] = note
			d = getdate(frappe.utils.add_days(d, 1))
	return out
