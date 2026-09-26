"""Rebuild past attendance when a shift change reaches back in time.

Shift Requests and Shift Assignments may be backdated: "Ram worked 12-8 all of
last week, not 6-2". The assignment dates change, but every Attendance row
already marked for those days was computed against the OLD shift and keeps it:

    NGI-EMP-00029  Asoj 12  punched 11:58 → 20:03
      before  shift 6 AM - 2 PM   Half Day (6 h late), LWP ½ day, 6 h "OT"
      after   shift 12 PM - 8 PM  Present, on time, no OT

Nothing in HRMS revisits a marked day, and the check-ins themselves still carry
the old shift, so even Attendance Fix would rebuild the day on the wrong shift.
Pay (late fine, half-day LWP, tea, meals, OT) reads those rows, so a backdated
change that is not followed through is a wrong salary.

What this does, for each past day the change covers (up to yesterday; today's
shift may still be running and is left to the normal flow):

  * Leave rows (On Leave, Work From Home, or anything tied to a Leave
    Application) keep their status. Only the shift on the row is corrected.
  * A day with no punches keeps its row (manual entry or Absent); its shift is
    corrected.
  * A day with punches is rebuilt: the row is removed, the check-ins forget
    their old shift, and `reconcile_employee_day` (the same primitive Attendance
    Fix and self-heal use) marks it again on the new shift. If the punches do
    not fit the new shift (nothing marked, or a worked day turning Absent), the
    old verdict is kept on the new shift and the day is flagged.
  * Approved Overtime Sheet rows for those days are re-measured, because
    "hours outside the shift" moved with the shift.

Payroll already paid is a hard stop: a change reaching into a period with a
submitted Salary Slip is refused, since rebuilding attendance under a paid slip
would silently disagree with the money. Cancel the slip first.

HRMS refuses to cancel a Shift Assignment while any Attendance or Employee
Checkin in its range still names its shift, so a backdated change could never be
undone. Before an assignment is cancelled (or split, on submit) the covered days
are detached: their attendance and check-ins forget the shift, and are re-marked
straight after on whatever shift the roster now says.

Registered in hooks.py:
  Shift Request     validate → guard_paid_period
                    before_submit / before_cancel → prepare_request
                    on_submit / on_cancel → rebuild_for_request
  Shift Assignment  validate → guard_paid_period
                    before_cancel → prepare_assignment_cancel
                    on_submit / on_cancel → rebuild_for_assignment
Assignments that `hr.shift_change` creates or cancels while processing a
request are skipped (flag `in_shift_request`); the request rebuilds once, after
the whole split is in place.

Long ranges go to the `long` queue so a permanent move backdated by months does
not hold the approver's browser.
"""

from datetime import datetime, time

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, getdate, today

from avinashgroup_app.avinash_group_app.doctype.attendance_fix.attendance_fix import (
	cancel_and_delete_attendance,
	reconcile_employee_day,
)

# A request spanning more days than this is rebuilt in the background. One day is
# a handful of queries; a month inline stays well under a request timeout.
INLINE_REBUILD_DAYS = 45

# Statuses that come from leave, not punches: never rebuilt, only re-shifted.
LEAVE_STATUSES = ("On Leave", "Work From Home")

CHECKIN_SHIFT_FIELDS = ("shift", "shift_start", "shift_end", "shift_actual_start", "shift_actual_end")


# ──────────────────────────────────────────────────────────────── hooks ──


def guard_paid_period(doc, method=None):
	"""Refuse a backdated change into a period already paid. Hook: validate.

	Works for both Shift Request (from_date/to_date) and Shift Assignment
	(start_date/end_date); the prepare hooks call it again on cancel, which
	does not run validate.
	"""
	start, end = _covered_range(doc, until_today=True)
	if not start:
		return
	slip = frappe.db.get_value(
		"Salary Slip",
		{
			"employee": doc.employee,
			"docstatus": 1,
			"start_date": ("<=", end),
			"end_date": (">=", start),
		},
		["name", "start_date", "end_date"],
		as_dict=True,
	)
	if slip:
		frappe.throw(
			_(
				"{0} has already been paid for {1} to {2} on {3}. Changing the shift for "
				"those days would change attendance under a paid salary. Cancel the salary "
				"slip first, or start the change after {2}."
			).format(
				doc.get("employee_name") or doc.employee,
				slip.start_date,
				slip.end_date,
				frappe.bold(slip.name),
			),
			title=_("Payroll Already Submitted"),
		)


def prepare_request(doc, method=None):
	"""Clear the way before HRMS and hr.shift_change move assignments.

	Hook: Shift Request before_submit, before_cancel.

	  * Tells the Shift Assignment hooks to stand aside: HRMS inserts / cancels
	    the request's own assignment and hr.shift_change splits the standing
	    one; rebuilding after each step would mark the same days three times on
	    half-finished rosters. The request rebuilds once, in rebuild_for_request.
	  * Detaches the covered days (see `detach_days`), because HRMS refuses to
	    cancel an assignment while any attendance or check-in in its range still
	    names its shift. Without this a backdated request can never be undone.
	"""
	if method == "before_submit" and doc.status != "Approved":
		return
	frappe.flags.in_shift_request = True
	if method == "before_cancel":
		guard_paid_period(doc)
	start, end = _covered_range(doc, until_today=True, whole_tail=(method == "before_cancel"))
	if start:
		detach_days(doc.employee, start, end)


def rebuild_for_request(doc, method=None):
	"""Re-mark the past days a Shift Request covers. Hook: on_submit, on_cancel."""
	if method == "on_submit" and doc.status != "Approved":
		return
	frappe.flags.in_shift_request = False
	_schedule(doc.employee, *_covered_range(doc, whole_tail=(method == "on_cancel")))
	refetch_todays_checkins(doc.employee)


def prepare_assignment_cancel(doc, method=None):
	"""Detach a directly-cancelled assignment's days. Hook: Shift Assignment before_cancel."""
	if frappe.flags.in_shift_request:
		return
	guard_paid_period(doc)
	start, end = _covered_range(doc, until_today=True)
	if start:
		detach_days(doc.employee, start, end)


def rebuild_for_assignment(doc, method=None):
	"""Re-mark the past days a directly-edited Shift Assignment covers.

	Hook: on_submit, on_cancel. Skipped when the assignment belongs to a Shift
	Request being processed; that request rebuilds once at the end.
	"""
	if frappe.flags.in_shift_request:
		return
	_schedule(doc.employee, *_covered_range(doc))
	refetch_todays_checkins(doc.employee)


# ───────────────────────────────────────────────────────────── the work ──


def _covered_range(doc, until_today=False, whole_tail=False):
	"""(start, end) of the already-lived days this change covers, or (None, None).

	until_today: include today. Detaching must, since today's punches also block
	an assignment cancel; rebuilding stops at yesterday, as today's shift may
	still be running.
	whole_tail: run to the last lived day regardless of the end date. Cancelling a
	temporary request also cancels the "resumed" assignment after it, so every
	day from the request's start is re-marked.
	"""
	start = getdate(doc.get("from_date") or doc.get("start_date"))
	last = getdate(today()) if until_today else getdate(add_days(today(), -1))
	to = doc.get("to_date") if doc.doctype == "Shift Request" else doc.get("end_date")
	end = last if (whole_tail or not to) else min(getdate(to), last)
	if start > end:
		return None, None
	return start, end


def detach_days(employee, start, end):
	"""Make these days forget their shift, so HRMS lets the assignment go.

	Attendance keeps its status and its check-in links; only the `shift` column is
	cleared, on every row whatever its docstatus (HRMS counts cancelled rows too).
	Check-ins lose their resolved shift window, which `fetch_shift` re-derives from
	the roster once it has changed. The days are re-marked straight after by
	rebuild_days / refetch_todays_checkins.
	"""
	frappe.db.sql(
		"""update `tabAttendance` set shift = null
		where employee = %s and attendance_date between %s and %s""",
		(employee, start, end),
	)
	frappe.db.sql(
		f"""update `tabEmployee Checkin`
		set {", ".join(f"{f} = null" for f in CHECKIN_SHIFT_FIELDS)}
		where employee = %s and time between %s and %s""",
		(employee, datetime.combine(getdate(start), time.min), datetime.combine(getdate(end), time.max)),
	)


def refetch_todays_checkins(employee):
	"""Give today's detached punches their shift back, for the normal auto-attendance run."""
	day = getdate(today())
	for name in frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": employee,
			"shift": ("is", "not set"),
			"time": ("between", [datetime.combine(day, time.min), datetime.combine(day, time.max)]),
		},
		pluck="name",
	):
		checkin = frappe.get_doc("Employee Checkin", name)
		checkin.fetch_shift()
		checkin.db_update()


def _schedule(employee, start, end):
	if not start:
		return
	if date_diff(end, start) + 1 > INLINE_REBUILD_DAYS:
		frappe.enqueue(
			"avinashgroup_app.hr.shift_backdate.rebuild_days",
			queue="long",
			timeout=3600,
			enqueue_after_commit=True,
			employee=employee,
			start=start,
			end=end,
		)
		frappe.msgprint(
			_("Attendance from {0} to {1} is being re-marked on the new shift in the background.").format(
				start, end
			),
			alert=True,
		)
		return
	log = rebuild_days(employee, start, end)
	if log:
		frappe.msgprint(
			"<br>".join(log), title=_("Attendance re-marked on the new shift"), indicator="blue"
		)


def rebuild_days(employee, start, end):
	"""Re-mark every day from `start` to `end` on the shift now assigned. Returns log lines."""
	from avinashgroup_app.hr.overtime import get_shift_window

	log, cache = [], {}
	day = getdate(start)
	while day <= getdate(end):
		shift_type = get_shift_window(employee, day)[0]
		if shift_type:
			if shift_type not in cache:
				cache[shift_type] = frappe.get_doc("Shift Type", shift_type)
			line = _rebuild_day(employee, day, cache[shift_type])
			if line:
				log.append(line)
		day = add_days(day, 1)

	log.extend(_remeasure_overtime(employee, start, end))
	return log


def _rebuild_day(employee, day, shift_doc):
	existing = frappe.db.get_value(
		"Attendance",
		{"employee": employee, "attendance_date": day, "docstatus": ("<", 2)},
		["name", "status", "shift", "docstatus", "leave_application", "leave_type"],
		as_dict=True,
	)
	checkins = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": employee,
			"time": ("between", [datetime.combine(day, time.min), datetime.combine(day, time.max)]),
		},
		pluck="name",
	)

	if existing and (existing.status in LEAVE_STATUSES or existing.leave_application or not checkins):
		if existing.shift != shift_doc.name:
			frappe.db.set_value("Attendance", existing.name, "shift", shift_doc.name, update_modified=False)
			return f"{day}: {existing.status} kept, shift set to {shift_doc.name}"
		return None
	if not checkins:
		return None  # nothing marked and nothing punched: not ours to invent

	savepoint = f"shift_backdate_{employee}_{day}".replace("-", "_")[:60]
	frappe.db.savepoint(savepoint)
	try:
		if existing:
			cancel_and_delete_attendance(existing)
		frappe.db.sql(
			f"""update `tabEmployee Checkin`
			set attendance = null, skip_auto_attendance = 0,
			    {", ".join(f"{f} = null" for f in CHECKIN_SHIFT_FIELDS)}
			where name in %(names)s""",
			{"names": checkins},
		)
		counters = {"attendance_created_or_updated": 0, "absent_rows_deleted": 0, "checkins_relinked": 0}
		reconcile_employee_day(
			shift_doc,
			employee,
			day,
			holiday_dates=frozenset(),  # a punch on a holiday still needs marking
			counters=counters,
			log_lines=[],
			include_skipped=True,
			mark_absent_when_no_checkins=False,
		)
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		frappe.log_error(
			title=f"Backdated shift rebuild failed: {employee} {day}",
			message=frappe.get_traceback(),
		)
		return f"{day}: could not be re-marked, old attendance kept (see Error Log)"

	after = frappe.db.get_value(
		"Attendance",
		{"employee": employee, "attendance_date": day, "docstatus": ("<", 2)},
		["name", "status"],
		as_dict=True,
	)
	worked_before = existing and existing.status in ("Present", "Half Day")
	if not after or (worked_before and after.status == "Absent"):
		# The punches do not fit the new shift (e.g. they fall before its check-in
		# window). A day somebody worked must not silently become "never came":
		# keep the old verdict, on the new shift, and say so. HR can still repair
		# the day by hand if Absent really is right.
		frappe.db.rollback(save_point=savepoint)
		if existing:
			frappe.db.set_value("Attendance", existing.name, "shift", shift_doc.name, update_modified=False)
		return f"{day}: punches do not fit {shift_doc.name}; kept {existing.status if existing else 'no attendance'}, please check"

	# `shift` on the old row is usually already cleared by detach_days.
	was = (existing.status + (f" on {existing.shift}" if existing.shift else "")) if existing else "no attendance"
	return f"{day}: {was} → {after.status} on {shift_doc.name}"


def _remeasure_overtime(employee, start, end):
	"""Re-measure approved Overtime Sheet rows for these days: the shift moved."""
	from avinashgroup_app.hr.overtime_settlement import measure_row

	rows = frappe.db.sql(
		"""select r.name, r.work_type, r.entitlement, s.work_date, s.name as sheet
		from `tabOvertime Sheet Employee` r join `tabOvertime Sheet` s on s.name = r.parent
		where s.docstatus = 1 and r.employee = %s and s.work_date between %s and %s""",
		(employee, start, end),
		as_dict=True,
	)
	log = []
	for row in rows:
		measured = measure_row(employee, row.work_date, row.work_type, row.entitlement)
		frappe.db.set_value(
			"Overtime Sheet Employee",
			row.name,
			{
				"worked_hours": measured["hours"],
				"attendance": measured["attendance"],
				"settlement_note": measured["note"],
			},
			update_modified=False,
		)
		total = frappe.db.sql(
			"select coalesce(sum(worked_hours), 0) from `tabOvertime Sheet Employee` where parent = %s",
			row.sheet,
		)[0][0]
		frappe.db.set_value("Overtime Sheet", row.sheet, "total_worked_hours", total, update_modified=False)
		log.append(f"{row.work_date}: {row.sheet} re-measured, {measured['hours']} h")
	return log
