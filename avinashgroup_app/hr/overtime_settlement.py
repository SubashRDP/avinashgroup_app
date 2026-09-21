"""Measure authorised overtime against what the punches actually show.

The Overtime Sheet says the company asked for the work; attendance says how long
it lasted. Neither alone can pay anybody: a sheet without punches is work that
was not done, and punches without a sheet are hours nobody asked for (policy 5.1
— the sheet decides eligibility).

This is the measuring step. For every row of a submitted Overtime Sheet it reads
that employee's Attendance for the date and writes back the hours:

    Work on Holiday   every hour worked that day
    Overtime          only the hours outside the rostered shift, which is what
                      `hr.overtime.hours_outside_shift` defines

Nothing is paid here. The hours land on the sheet row, where they can be seen
beside what was asked for, and payroll reads them from there.

Deliberately narrow:
  * submitted sheets only, and only rows whose entitlement is Overtime. A row
    that earns Replacement Leave has no hours to measure.
  * it never invents attendance. No attendance for the date means zero hours and
    a reason on the row — someone was called in and did not come, which HR needs
    to see rather than have smoothed over.
  * re-measuring is safe: it overwrites the same fields from the same source.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate

from avinashgroup_app.hr.shift_day import round_to_half_hour
from avinashgroup_app.hr.overtime import (
	ENTITLEMENT_OVERTIME,
	WORK_ON_HOLIDAY,
	get_shift_window,
	hours_outside_shift,
)


def measure_sheet(sheet_name):
	"""Measure every row of one Overtime Sheet. Returns the per-row report."""
	sheet = frappe.get_doc("Overtime Sheet", sheet_name)
	if sheet.docstatus != 1:
		frappe.throw(_("{0} is not approved yet, so there is nothing to settle").format(sheet_name))

	report = []
	for row in sheet.employees:
		measured = measure_row(row.employee, sheet.work_date, row.work_type, row.entitlement)
		row.db_set("worked_hours", measured["hours"], update_modified=False)
		row.db_set("attendance", measured["attendance"], update_modified=False)
		row.db_set("settlement_note", measured["note"], update_modified=False)
		report.append({"employee": row.employee, "employee_name": row.employee_name, **measured})

	sheet.db_set("total_worked_hours", sum(r["hours"] for r in report), update_modified=False)
	frappe.db.commit()
	return report


def measure_row(employee, work_date, work_type, entitlement):
	"""Hours this employee actually worked against an authorised row.

	Returns {"hours", "attendance", "note"}. Hours are 0 whenever they cannot be
	measured, and the note says why.
	"""
	if entitlement != ENTITLEMENT_OVERTIME:
		return {"hours": 0.0, "attendance": None, "note": _("Earns replacement leave, not overtime")}

	attendance = frappe.db.get_value(
		"Attendance",
		{"employee": employee, "attendance_date": getdate(work_date), "docstatus": 1},
		["name", "status", "in_time", "out_time", "working_hours", "shift"],
		as_dict=True,
	)
	if not attendance:
		return {"hours": 0.0, "attendance": None, "note": _("No attendance — called in but did not come")}
	if attendance.status == "Absent":
		return {"hours": 0.0, "attendance": attendance.name, "note": _("Marked absent")}
	if not (attendance.in_time and attendance.out_time):
		return {
			"hours": 0.0,
			"attendance": attendance.name,
			"note": _("Only one punch — the hours cannot be measured"),
		}

	if work_type == WORK_ON_HOLIDAY:
		# A holiday has no shift to work beyond: every hour counts.
		hours = flt(attendance.working_hours) or _punched_hours(attendance)
		return {
			"hours": round_to_half_hour(hours),
			"attendance": attendance.name,
			"note": _("Hours worked on a holiday"),
		}

	shift, shift_start, shift_end = get_shift_window(employee, work_date)
	if not shift:
		return {"hours": 0.0, "attendance": attendance.name, "note": _("No shift on this date")}

	hours = hours_outside_shift(
		get_datetime(attendance.in_time), get_datetime(attendance.out_time), shift_start, shift_end
	)
	# To the half hour, as the attendance sheet and the report both count it —
	# pay and the report must never disagree about the same day.
	return {
		"hours": round_to_half_hour(hours),
		"attendance": attendance.name,
		"note": _("Hours outside the {0} shift").format(shift),
	}


def _punched_hours(attendance):
	return (get_datetime(attendance.out_time) - get_datetime(attendance.in_time)).total_seconds() / 3600


@frappe.whitelist()
def measure(sheet_name):
	"""Button on the Overtime Sheet."""
	frappe.has_permission("Overtime Sheet", "write", throw=True)
	return measure_sheet(sheet_name)


def get_measured_hours(start_date, end_date, company=None):
	"""{employee: hours} authorised AND worked between two dates — what payroll pays.

	Only submitted sheets, only rows that earn overtime, only hours the punches
	back up.
	"""
	sheet = frappe.qb.DocType("Overtime Sheet")
	row = frappe.qb.DocType("Overtime Sheet Employee")
	query = (
		frappe.qb.from_(row)
		.join(sheet)
		.on(row.parent == sheet.name)
		.select(row.employee, row.worked_hours)
		.where(
			(sheet.docstatus == 1)
			& (sheet.work_date >= getdate(start_date))
			& (sheet.work_date <= getdate(end_date))
			& (row.entitlement == ENTITLEMENT_OVERTIME)
		)
	)
	if company:
		query = query.where(sheet.company == company)

	hours = {}
	for r in query.run(as_dict=True):
		hours[r.employee] = flt(hours.get(r.employee, 0)) + flt(r.worked_hours)
	return hours
