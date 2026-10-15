"""Give leave for chosen days from the Monthly Attendance BS grid.

Leave normally arrives as a Leave Application the employee files and the
Dynamic Approval workflow approves. Not all of it does: someone phones in sick,
a supervisor agrees a day off verbally, and HR only meets it at month end as an
Absent in the attendance grid. Fixing that meant leaving the report, filing an
application per run of days on the employee's behalf, walking it through every
approval level, and coming back. This files it from the grid instead, for the
days HR ticks.

Done the HRMS way, because balances, payroll and the leave ledger all read it:
one Leave Application per run of consecutive days, status Approved, submitted.
HRMS's own validate runs in full — balance, overlap with other leave, an
allocation and Leave Period, attendance already marked Present ("Attendance
for employee … is already marked") — and its refusal text goes back to HR
unchanged. On submit HRMS writes the attendance itself (On Leave, or Half Day
on the half-day date; holidays skipped unless the type includes them) and the
ledger entries. Nothing here writes leave attendance directly.

Two deliberate departures, both about who approves:

  * the Dynamic Approval workflow is not walked. HR giving the leave IS the
    approval; the application records HR as Leave Approver, says where it came
    from in a comment, and goes in the Attendance Correction Log. The
    application is inserted at the workflow's first state and moved to its
    submitted state ("Approved") directly, so no approver is asked and no
    "pending" notification is sent.
  * a day with punches. HRMS marks every day of the leave On Leave over an
    existing Absent; it does not know the person came in. Policy 3.4 says
    coming in while on leave is a Half Day with the leave kept, so those days
    are set Half Day / half Present after HRMS has written them — by
    biometric.attendance_override.on_leave_submit, as for any leave approved. The leave balance still drops by the whole
    day, as it does for any application; give a half day of leave if only half
    was taken.

Refused: a day inside a submitted Salary Slip (any leave type, not only LWP as
HRMS checks), no reason, and anything HRMS refuses. Future days are allowed —
leave is often given ahead. A draft slip covering a day is a warning: it reads
leave when Prepare Payroll Inputs recalculates it.

Who: HR Manager and System Manager, as for punch and shift corrections
(hr/punch_correction.CORRECTION_ROLES). Called by the "Give Leave" dialog in
monthly_attendance_bs.js.
"""

import frappe
from frappe import _
from frappe.model.workflow import get_workflow_name
from frappe.utils import add_days, flt, getdate, strip_html

from hrms.hr.doctype.leave_application.leave_application import (
	get_leave_balance_on,
	get_number_of_leave_days,
)

from avinashgroup_app.hr.punch_correction import CORRECTION_ROLES, SOURCE_REPORT, log_correction
from avinashgroup_app.hr.replacement_leave import shown_up

LOG_DOCTYPE = "Attendance Correction Log"


@frappe.whitelist()
def leave_types_for(employee, on_date):
	"""Leave types the employee can be given on `on_date`: those with an
	allocation covering the date, with the balance, plus every LWP type."""
	frappe.only_for(CORRECTION_ROLES)
	on_date = getdate(on_date)
	allocated = frappe.get_all(
		"Leave Allocation",
		filters={"employee": employee, "docstatus": 1, "from_date": ("<=", on_date), "to_date": (">=", on_date)},
		pluck="leave_type",
		distinct=True,
	)
	out = [
		{"leave_type": lt, "balance": flt(get_leave_balance_on(employee, lt, on_date), 2), "is_lwp": 0}
		for lt in sorted(set(allocated))
	]
	for lt in frappe.get_all("Leave Type", filters={"is_lwp": 1}, pluck="name"):
		if lt not in allocated:
			out.append({"leave_type": lt, "balance": None, "is_lwp": 1})
	return out


@frappe.whitelist()
def preview(employee, leave_type, dates, half_day_date=None):
	"""What giving this leave would do, before it is done: the runs, the days
	HRMS will deduct, the balance, and every day that will be refused or turned
	into a Half Day."""
	frappe.only_for(CORRECTION_ROLES)
	days = _parse_days(dates)
	if not (employee and leave_type and days):
		return {"runs": [], "deduct": 0, "balance": None, "notes": []}
	half = getdate(half_day_date) if half_day_date else None
	runs = _runs(days)
	deduct = sum(_days_for(employee, leave_type, start, end, half) for start, end in runs)
	lwp = frappe.db.get_value("Leave Type", leave_type, "is_lwp")
	balance = None if lwp else flt(get_leave_balance_on(employee, leave_type, days[0]), 2)
	return {
		"runs": [{"from": str(s), "to": str(e)} for s, e in runs],
		"deduct": deduct,
		"balance": balance,
		"is_lwp": cint_bool(lwp),
		"include_holiday": cint_bool(frappe.db.get_value("Leave Type", leave_type, "include_holiday")),
		"notes": _notes(employee, days),
	}


@frappe.whitelist(methods=["POST"])
def give_leave(employee, leave_type, dates, reason, half_day_date=None):
	"""File and submit one approved Leave Application per run of consecutive
	`dates`, in one transaction. Returns the applications made and warnings."""
	frappe.only_for(CORRECTION_ROLES)
	if not frappe.db.exists("DocType", LOG_DOCTYPE):
		frappe.throw(_("Giving leave from the report is not set up on this site yet. Run bench migrate."))
	reason = strip_html(reason or "").strip()
	if not reason:
		frappe.throw(_("Give a reason. It is kept on the leave and in the Attendance Correction Log."), title=_("Reason Required"))
	days = _parse_days(dates)
	if not days:
		frappe.throw(_("Choose at least one day."))
	half = getdate(half_day_date) if half_day_date else None
	if half and half not in days:
		frappe.throw(_("The half day ({0}) must be one of the chosen days.").format(half))

	paid = frappe.db.get_value(
		"Salary Slip",
		{"employee": employee, "docstatus": 1, "start_date": ("<=", days[-1]), "end_date": (">=", days[0])},
		["name", "start_date", "end_date"],
		as_dict=True,
	)
	if paid and any(paid.start_date <= d <= paid.end_date for d in days):
		frappe.throw(
			_("{0} to {1} is inside submitted salary slip {2}. Leave there would disagree with what was paid. Cancel the slip first.").format(
				paid.start_date, paid.end_date, frappe.bold(paid.name)
			),
			title=_("Payroll Already Submitted"),
		)

	made, warnings = [], []
	for start, end in _runs(days):
		before = {
			d: frappe.db.get_value("Attendance", {"employee": employee, "attendance_date": d, "docstatus": ("<", 2)}, "status")
			for d in _span(start, end)
		}
		run_half = half if half and start <= half <= end else None
		application = _apply(employee, leave_type, start, end, run_half, reason)
		half_days = _half_day_where_came_in(application, run_half)
		total = flt(frappe.db.get_value("Leave Application", application, "total_leave_days"))
		span = str(start) if start == end else f"{start} – {end}"
		was = ", ".join(sorted({s or _("not marked") for s in before.values()}))
		for d in _span(start, end):
			log_correction(
				employee, d, "Leave Given", SOURCE_REPORT, before[d] or _("not marked"),
				f"{leave_type} ({application})", reason, leave_application=application,
			)
		made.append({"leave_application": application, "from": str(start), "to": str(end), "days": total, "was": was})
		if half_days:
			warnings.append(
				_("{0}: came in on {1}, so marked Half Day with the leave kept (policy 3.4). The balance still counts the full day.").format(
					application, ", ".join(map(str, half_days))
				)
			)

	draft = frappe.db.get_value(
		"Salary Slip",
		{"employee": employee, "docstatus": 0, "start_date": ("<=", days[-1]), "end_date": (">=", days[0])},
		"name",
	)
	if draft:
		warnings.append(
			_("Draft salary slip {0} covers these days. Run Prepare Payroll Inputs on its Payroll Entry before submitting, so it picks this up.").format(draft)
		)
	return {"made": made, "warnings": warnings}


def _apply(employee, leave_type, start, end, half_day_date, reason):
	"""One approved, submitted Leave Application for [start, end]. HRMS's
	validate runs on insert and its refusal reaches the user as is."""
	application = frappe.get_doc(
		{
			"doctype": "Leave Application",
			"employee": employee,
			"leave_type": leave_type,
			"from_date": start,
			"to_date": end,
			"half_day": 1 if half_day_date else 0,
			"half_day_date": half_day_date,
			"description": reason,
			"status": "Approved",
			"leave_approver": frappe.session.user,
			"posting_date": getdate(),
			"follow_via_email": 0,
		}
	)
	application.flags.ignore_permissions = True
	workflow = get_workflow_name("Leave Application")
	if workflow:
		states = frappe.get_cached_doc("Workflow", workflow).states
		field = frappe.get_cached_value("Workflow", workflow, "workflow_state_field")
		application.set(field, states[0].state)  # inserted where the workflow starts
		application.insert()
		# HR giving the leave is the approval: straight to the submitted state.
		submitted = next(s.state for s in states if str(s.doc_status) == "1")
		application.db_set(field, submitted, update_modified=False)
		application.reload()
	else:
		application.insert()
	application.submit()
	application.add_comment(
		"Info",
		_("Given from Monthly Attendance BS by {0}. Reason: {1}").format(
			frappe.utils.get_fullname(frappe.session.user), frappe.utils.escape_html(reason)
		),
	)
	return application.name


def _half_day_where_came_in(application, half_day_date):
	"""Days of the leave made Half Day because the person punched on them —
	done on submit by biometric.attendance_override.on_leave_submit (policy
	3.4); the half-day date asked for is not one of them."""
	return [
		getdate(d)
		for d in frappe.get_all(
			"Attendance",
			filters={"leave_application": application, "docstatus": 1, "status": "Half Day"},
			pluck="attendance_date",
			order_by="attendance_date",
		)
		if not half_day_date or getdate(d) != half_day_date
	]


def _notes(employee, days):
	"""Per-day warnings for the preview."""
	notes = []
	present = frappe.get_all(
		"Attendance",
		filters={
			"employee": employee,
			"attendance_date": ("in", days),
			"docstatus": 1,
			"status": ("in", ("Present", "Work From Home")),
			"half_day_status": ("!=", "Absent"),
		},
		pluck="attendance_date",
	)
	if present:
		notes.append(
			_("Marked Present on {0}: HRMS will refuse leave there. Untick those days, or correct the attendance first.").format(
				", ".join(str(getdate(d)) for d in sorted(present))
			)
		)
	leave = frappe.get_all(
		"Leave Application",
		filters={"employee": employee, "docstatus": ("<", 2), "status": ("!=", "Rejected"), "from_date": ("<=", days[-1]), "to_date": (">=", days[0])},
		fields=["name", "from_date", "to_date", "leave_type"],
	)
	for la in leave:
		if any(getdate(la.from_date) <= d <= getdate(la.to_date) for d in days):
			notes.append(_("Already on leave {0} ({1}, {2} – {3}): HRMS will refuse the overlap.").format(la.name, la.leave_type, la.from_date, la.to_date))
	came = [d for d in days if d <= getdate() and d not in [getdate(p) for p in present] and shown_up(employee, d)]
	if came:
		notes.append(
			_("Punched on {0}: those days become Half Day with the leave kept (policy 3.4).").format(", ".join(map(str, came)))
		)
	return notes


def _days_for(employee, leave_type, start, end, half):
	in_run = half and start <= half <= end
	return flt(get_number_of_leave_days(employee, leave_type, start, end, 1 if in_run else 0, half if in_run else None))


def _parse_days(dates):
	dates = frappe.parse_json(dates) if isinstance(dates, str) else dates
	return sorted({getdate(d) for d in (dates or []) if d})


def _runs(days):
	"""Consecutive calendar days grouped: [(start, end), ...]."""
	runs = []
	for d in days:
		if runs and getdate(add_days(runs[-1][1], 1)) == d:
			runs[-1][1] = d
		else:
			runs.append([d, d])
	return [tuple(r) for r in runs]


def _span(start, end):
	return [getdate(add_days(start, i)) for i in range((end - start).days + 1)]


def cint_bool(value):
	return 1 if frappe.utils.cint(value) else 0


def get_leave_notes(applications):
	"""{leave application: tooltip} for leave given from the report. Read by
	Monthly Attendance BS to mark those days apart from leave applied for."""
	if not applications or not frappe.db.exists("DocType", LOG_DOCTYPE):
		return {}
	if not frappe.get_meta(LOG_DOCTYPE).has_field("leave_application"):
		return {}
	rows = frappe.get_all(
		LOG_DOCTYPE,
		filters={"correction_type": "Leave Given", "leave_application": ("in", list(applications))},
		fields=["leave_application", "done_by_name", "done_on", "reason", "new_value"],
		order_by="done_on asc",
	)
	return {
		r.leave_application: _("Leave given from the report: {0}. By {1} on {2}. Reason: {3}").format(
			r.new_value,
			r.done_by_name or _("unknown"),
			frappe.utils.format_datetime(r.done_on, "yyyy-MM-dd HH:mm") if r.done_on else "—",
			r.reason or "—",
		)
		for r in rows
	}
