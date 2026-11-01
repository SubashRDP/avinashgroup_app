"""The company ended a shift early on one day: that day is still a full day.

Without this, a 9–5 shift sent home at 2 PM records 180 minutes of
`custom_early_exit` on every row (biometric/attendance_sync
.compute_shift_deviations). Those minutes show as "Before ofc. Time" in Monthly
Attendance BS and are fined through the Late Time component
(payroll/attendance_allowance.evaluate_rule) — three hours' pay docked from
everyone for leaving when they were told to. Late Excused could hide it, but it
is per person, also waives any real lateness that morning, and says "excused"
where the truth is "the office closed".

A submitted Shift Early Closure (company, date, closing time, optionally the
shifts) moves the end that early leaving is measured against, for that date
only:

  left at or after the closing time   → no early leaving, a full day
  left before it                      → early by the minutes before the closing
                                        time, not before the normal end
  stayed past the normal shift end    → late exit (overtime) from the normal end,
                                        unchanged; the hours between the closing
                                        time and the normal end are neither

Deliberately narrow:
  - Lateness in the morning is untouched, and so is the 2-hours-late half-day
    rule (attendance_override.enforce_late_arrival_half_day).
  - Somebody who did not come stays Absent. The closure pays those who came.
  - Status is not changed. Early leaving never demotes a day here; the
    half-day/absent hour thresholds are 0 on every Shift Type. If HR ever sets
    them, HRMS's own marking will need to learn about closures too.
  - A shift that is not running at the closing time (6–2 when the closure is at
    2 PM) is not affected, even when the closure names every shift.

Submitting or cancelling recomputes the deviation fields on that day's existing
Attendance rows, submitted ones included. Both are refused once a salary slip
covering the day is submitted: the fine has been paid by then, and the change
would silently mean nothing. The Late Time fine is posted when the month's slips
are made, so draft slips pick the change up on their own.

Entry points: the Shift Early Closure doctype, the "Close Shift Early" button on
Monthly Attendance BS (`close_shift_early`), and `closing_time`, which
compute_shift_deviations asks for every Attendance it measures.
"""

from datetime import datetime, time, timedelta

import frappe
from frappe import _
from frappe.utils import getdate, to_timedelta

from avinashgroup_app.payroll.special_payout import REGULAR_SLIPS

#: Who may close a shift early. Matches the doctype's submit permission.
CLOSURE_ROLES = ("HR Manager", "System Manager")

DEVIATION_FIELDS = ("custom_late_entry", "custom_early_entry", "custom_early_exit", "custom_late_exit")


def shift_span(shift_doc, day):
	"""(start, end) datetimes of `shift_doc` on `day`; an overnight shift ends the next day."""
	midnight = datetime.combine(getdate(day), time.min)
	start = midnight + to_timedelta(shift_doc.start_time)
	end = midnight + to_timedelta(shift_doc.end_time)
	if end <= start:
		end += timedelta(days=1)
	return start, end


def _closing_inside(shift_doc, day, close_at):
	"""The closing time as a datetime within the shift's span on `day`, or None
	when the shift is not running then (already over, or not yet begun)."""
	start, end = shift_span(shift_doc, day)
	closing = datetime.combine(getdate(day), time.min) + to_timedelta(close_at)
	if closing <= start:
		# An overnight shift closed after midnight: the time is on the next day.
		closing += timedelta(days=1)
	return closing if start < closing < end else None


def _closures_on(company, day, exclude=None):
	"""Submitted closures for the company on `day`: [(name, close_at, {shifts} or None)]."""
	filters = {"company": company, "closure_date": getdate(day), "docstatus": 1}
	if exclude:
		filters["name"] = ("!=", exclude)
	rows = frappe.get_all("Shift Early Closure", filters=filters, fields=["name", "close_at", "reason"])
	out = []
	for row in rows:
		shifts = set(
			frappe.get_all(
				"Shift Early Closure Shift",
				filters={"parent": row.name, "parenttype": "Shift Early Closure"},
				pluck="shift_type",
			)
		)
		out.append(frappe._dict(name=row.name, close_at=row.close_at, reason=row.reason, shifts=shifts or None))
	return out


def closing_time(company, shift_doc, day):
	"""The datetime the company closed `shift_doc` on `day`, or None on a normal day.

	Called by attendance_sync.compute_shift_deviations for every Attendance it
	measures. Two closures covering the same shift cannot both be submitted
	(validate_closure), but if they ever were, the earlier closing wins: it is
	the one that let people go.
	"""
	if not company or not shift_doc:
		return None
	found = None
	for closure in _closures_on(company, day):
		if closure.shifts and shift_doc.name not in closure.shifts:
			continue
		closing = _closing_inside(shift_doc, day, closure.close_at)
		if closing and (found is None or closing < found):
			found = closing
	return found


def validate_closure(doc):
	"""Shift Early Closure validate: the time must cut a named shift short, and no
	other submitted closure may already cover the same shift that day."""
	if not (doc.reason or "").strip():
		frappe.throw(_("Give the reason the shift was closed early."), title=_("Reason Needed"))

	named = [row.shift_type for row in doc.shifts or []]
	for shift in named:
		shift_doc = frappe.get_cached_doc("Shift Type", shift)
		if not _closing_inside(shift_doc, doc.closure_date, doc.close_at):
			frappe.throw(
				_("{0} is not running at {1}, so closing it then changes nothing. The closing time must fall between its start and end.").format(
					frappe.bold(shift), str(to_timedelta(doc.close_at))[:-3]
				),
				title=_("Not Within the Shift"),
			)

	for other in _closures_on(doc.company, doc.closure_date, exclude=doc.name):
		if not other.shifts or not named or other.shifts & set(named):
			frappe.throw(
				_("{0} already closes the same shift early on this day. Cancel it first, or amend it.").format(
					frappe.get_desk_link("Shift Early Closure", other.name)
				),
				title=_("Already Closed"),
			)


def _affected_attendance(doc):
	"""Attendance rows of the closure's company and date, on the named shifts if any."""
	filters = {"company": doc.company, "attendance_date": getdate(doc.closure_date), "docstatus": ("<", 2)}
	named = [row.shift_type for row in doc.shifts or []]
	if named:
		filters["shift"] = ("in", named)
	else:
		filters["shift"] = ("is", "set")
	return frappe.get_all(
		"Attendance",
		filters=filters,
		fields=["name", "employee", "shift", "attendance_date", "in_time", "out_time", *DEVIATION_FIELDS],
	)


def _refuse_if_paid(doc, rows):
	employees = sorted({r.employee for r in rows})
	if not employees:
		return
	paid = frappe.get_all(
		"Salary Slip",
		filters={
			"employee": ("in", employees),
			"docstatus": 1,
			"start_date": ("<=", getdate(doc.closure_date)),
			"end_date": (">=", getdate(doc.closure_date)),
			**REGULAR_SLIPS,
		},
		fields=["name", "employee"],
		limit=5,
	)
	if paid:
		frappe.throw(
			_("Salary is already submitted for this day ({0}), so the early-leaving fine has been paid. Cancel those slips first, or settle it as a Payroll Adjustment.").format(
				", ".join(p.name for p in paid)
			),
			title=_("Already Paid"),
		)


def apply_closure(doc, cancelling=False):
	"""Shift Early Closure on_submit / on_cancel: re-measure the day's Attendance.

	By the time this runs the closure's own docstatus is already saved, so
	compute_shift_deviations sees it on submit and no longer sees it on cancel —
	one code path for both. Written with db.set_value, as attendance_sync's
	refresh does, so submitted rows are updated without a cancel and amend.
	"""
	from avinashgroup_app.biometric.attendance_sync import compute_shift_deviations

	rows = _affected_attendance(doc)
	_refuse_if_paid(doc, rows)

	note = (
		_("Shift Early Closure {0} cancelled: early leaving measured against the normal shift end again.")
		if cancelling
		else _("Shift closed early ({0}): early leaving measured against the closing time.")
	).format(doc.name)

	updated = 0
	for row in rows:
		shift_doc = frappe.get_cached_doc("Shift Type", row.shift)
		values = compute_shift_deviations(shift_doc, row.attendance_date, row.in_time, row.out_time, company=doc.company)
		changed = {f: v for f, v in values.items() if int(row.get(f) or 0) != int(v)}
		if not changed:
			continue
		frappe.db.set_value("Attendance", row.name, changed, update_modified=False)
		frappe.get_doc("Attendance", row.name).add_comment("Info", note)
		updated += 1

	doc.db_set("attendance_updated", updated)
	if updated:
		frappe.msgprint(_("{0} attendance row(s) re-measured.").format(updated), alert=True)


def closures_between(company, start, end):
	"""{(company, date): [closure, ...]} for the report, each with `shifts` (a set or None)."""
	filters = {"closure_date": ("between", [getdate(start), getdate(end)]), "docstatus": 1}
	if company:
		filters["company"] = company
	out = {}
	for row in frappe.get_all("Shift Early Closure", filters=filters, fields=["company", "closure_date"], distinct=True):
		out[(row.company, getdate(row.closure_date))] = _closures_on(row.company, row.closure_date)
	return out


def closure_note(closures, shift_doc, day):
	"""Remark for one report row: "Closed early at 14:00 — reason", or ""."""
	for closure in closures or ():
		if closure.shifts and shift_doc.name not in closure.shifts:
			continue
		if _closing_inside(shift_doc, day, closure.close_at):
			# Escaped: the report's Remarks cell renders its text as HTML.
			return _("Closed early at {0} — {1}").format(
				str(to_timedelta(closure.close_at))[:-3], frappe.utils.escape_html(closure.reason)
			)
	return ""


@frappe.whitelist()
def close_shift_early(company: str, closure_date: str, close_at: str, reason: str, shifts=None) -> dict:
	"""Make and submit a Shift Early Closure from the Monthly Attendance BS button."""
	frappe.only_for(CLOSURE_ROLES)
	shifts = frappe.parse_json(shifts) if isinstance(shifts, str) else (shifts or [])
	doc = frappe.get_doc(
		{
			"doctype": "Shift Early Closure",
			"company": company,
			"closure_date": closure_date,
			"close_at": close_at,
			"reason": reason,
			"shifts": [{"shift_type": s} for s in shifts if s],
		}
	)
	doc.insert()
	doc.submit()
	return {"name": doc.name, "attendance_updated": doc.attendance_updated}
