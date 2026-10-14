"""Correct one day's first IN / last OUT from the Monthly Attendance BS grid.

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

Refused, and why:

  * today or later — today's attendance is marked by HRMS after the shift ends;
  * a day inside a submitted Salary Slip — attendance under paid salary would
    silently disagree with the money (same rule as shift_backdate.guard_paid_period);
  * leave days (On Leave, Work From Home, anything with a Leave Application) —
    a leave decision is not a punch correction;
  * no shift rostered, or an overnight shift — punches are grouped by calendar
    day everywhere in this app (attendance_sync), which an overnight shift breaks;
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

# The same two roles Attendance Fix's single-day Repair allows
# (attendance_fix.repair_attendance_day).
CORRECTION_ROLES = ("HR Manager", "System Manager")


@frappe.whitelist(methods=["POST"])
def correct_day(employee, attendance_date, in_time, out_time, reason):
	"""Set one day's first IN and last OUT, and re-mark its attendance.

	`in_time` / `out_time` are clock times ("09:00" or "09:00:00") on
	`attendance_date`. Raises (and rolls everything back) on any refusal listed
	in the module docstring. Returns what the day now looks like, plus warnings
	the caller should show.
	"""
	frappe.only_for(CORRECTION_ROLES)
	if not _fields_installed():
		frappe.throw(_("Punch correction is not set up on this site yet. Run bench migrate."))

	day = getdate(attendance_date)
	reason = strip_html(reason or "").strip()
	if not reason:
		frappe.throw(_("Give a reason for the correction. It is kept on the punches."))
	if not frappe.db.exists("Employee", employee):
		frappe.throw(_("Employee {0} not found.").format(employee))
	if day >= getdate(today()):
		frappe.throw(
			_("Only past days can be corrected. Today's attendance is marked automatically once the shift ends."),
			title=_("Not Yet"),
		)

	new_in = datetime.combine(day, get_time(in_time))
	new_out = datetime.combine(day, get_time(out_time))
	if new_out <= new_in:
		frappe.throw(_("OUT ({0}) must be after IN ({1}).").format(_clock(new_out), _clock(new_in)))

	_guard_paid(employee, day)
	existing = _guard_leave(employee, day)
	shift_doc = _shift_for(employee, day, existing)
	window = _check_in_window(shift_doc, day)

	changes = _apply_punches(employee, day, new_in, new_out, reason)
	if not changes:
		# The punches already read this way but the attendance does not agree
		# (a desk-added punch HRMS gave to another shift, a stale row). Saving
		# unchanged times is how HR asks for the day to be re-marked from them.
		changes = [_("punches already {0} → {1}; attendance re-marked from them").format(_clock(new_in), _clock(new_out))]

	after = _rebuild(employee, day, shift_doc, existing)
	frappe.get_doc("Attendance", after.name).add_comment(
		"Info",
		_("First IN / last OUT corrected from Monthly Attendance BS: {0}. Reason: {1}").format(
			"; ".join(changes), frappe.utils.escape_html(reason)
		),
	)
	overtime = _remeasure_overtime(employee, day, day)

	warnings = _draft_slip_warning(employee, day)
	outside = [_clock(t) for t in (new_in, new_out) if not window[0] <= t <= window[1]]
	if outside:
		warnings.append(
			_("{0} is outside {1}'s check-in window ({2} to {3}); it is counted because HR set it.").format(
				", ".join(outside), shift_doc.name, _clock(window[0]), _clock(window[1])
			)
		)
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
		"changes": changes,
		"overtime": overtime,
		"warnings": warnings,
	}


# ─────────────────────────────────────────────────────────────── guards ──


def _guard_paid(employee, day):
	slip = frappe.db.get_value(
		"Salary Slip",
		{"employee": employee, "docstatus": 1, "start_date": ("<=", day), "end_date": (">=", day)},
		"name",
	)
	if slip:
		frappe.throw(
			_(
				"{0} is inside submitted salary slip {1}. Correcting attendance there would "
				"disagree with what was paid. Cancel the slip first."
			).format(frappe.bold(str(day)), frappe.bold(slip)),
			title=_("Payroll Already Submitted"),
		)


def _guard_leave(employee, day):
	"""The day's live Attendance (or None), refusing a leave day."""
	existing = frappe.db.get_value(
		"Attendance",
		{"employee": employee, "attendance_date": day, "docstatus": ("<", 2)},
		[
			"name", "status", "docstatus", "shift", "leave_application", "leave_type",
			"custom_late_excused", "custom_late_excuse_reason",
		],
		as_dict=True,
	)
	if existing and (existing.status in LEAVE_STATUSES or existing.leave_application or existing.leave_type):
		frappe.throw(
			_("{0} is {1} through leave. Change the leave, not the punches.").format(
				frappe.bold(str(day)), existing.status
			),
			title=_("Leave Day"),
		)
	return existing


def _shift_for(employee, day, existing):
	"""The rostered shift (what fetch_shift will resolve the punches to)."""
	shift_name = get_shift_window(employee, day)[0] or (existing and existing.shift)
	if not shift_name:
		frappe.throw(
			_("{0} has no shift on {1}. Assign one first, so there are rules to mark the day against.").format(
				employee, day
			),
			title=_("No Shift"),
		)
	shift_doc = frappe.get_doc("Shift Type", shift_name)
	if get_time(shift_doc.end_time) <= get_time(shift_doc.start_time):
		frappe.throw(
			_("{0} runs overnight. Punches are grouped by calendar day, so correct this day through Employee Checkin and Attendance Fix.").format(
				shift_name
			),
			title=_("Overnight Shift"),
		)
	return shift_doc


def _check_in_window(shift_doc, day):
	"""(opens, closes): where HRMS attaches punches to this shift on this day."""
	opens = datetime.combine(day, get_time(shift_doc.start_time)) - timedelta(
		minutes=cint(shift_doc.begin_check_in_before_shift_start_time)
	)
	closes = datetime.combine(day, get_time(shift_doc.end_time)) + timedelta(
		minutes=cint(shift_doc.allow_check_out_after_shift_end_time)
	)
	return opens, closes


def _draft_slip_warning(employee, day):
	slip = frappe.db.get_value(
		"Salary Slip",
		{"employee": employee, "docstatus": 0, "start_date": ("<=", day), "end_date": (">=", day)},
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
	"""Move / add punches so the day reads new_in → new_out. Returns change lines."""
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
	frappe.flags.in_biometric_day_reconcile = True
	try:
		for label, punch, target, log_type in (("IN", first, new_in, "IN"), ("OUT", last, new_out, "OUT")):
			if punch is None:
				_add_punch(employee, target, log_type, stamp)
				changes.append(_("{0} added at {1}").format(label, _clock(target)))
			elif get_datetime(punch.time) != target:
				_move_punch(punch, target, stamp)
				changes.append(_("{0} {1} → {2}").format(label, _clock(punch.time), _clock(target)))
	finally:
		frappe.flags.in_biometric_day_reconcile = False

	if changes:
		relabel_day_checkins(employee, day)
	return changes


def _move_punch(punch, target, stamp):
	"""Move a punch, keeping the device's first reading. db.set_value, because
	HRMS's validate refuses a time change on a linked punch — the link is
	dropped in _rebuild anyway."""
	original = frappe.db.get_value("Employee Checkin", punch.name, "custom_original_time") or punch.time
	frappe.db.set_value(
		"Employee Checkin",
		punch.name,
		{"time": target, "custom_original_time": original, **stamp},
	)


def _add_punch(employee, target, log_type, stamp):
	checkin = frappe.new_doc("Employee Checkin")
	checkin.update({"employee": employee, "time": target, "log_type": log_type, **stamp})
	checkin.insert(ignore_permissions=True)


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


def _fields_installed():
	"""The stamps arrive with a migrate; until then there is nothing to read or write."""
	return frappe.get_meta("Employee Checkin").has_field("custom_time_edited")


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
