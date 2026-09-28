"""Bring past attendance in line when a holiday is added for a date already lived.

Holiday Bulk Update writes Holiday List rows only. For a future date that is all
it needs. For a past date ("the government declared last Friday a holiday") the
attendance already marked for that day still describes a working day:

  * someone who came in has `custom_worked_on_holiday` unticked, so the holiday
    meal / tea rules, holiday OT measurement, the Work On Holiday report and the
    leave report's holiday add-back all miss them;
  * someone who stayed home is still marked Absent. Payroll already ignores an
    Absent on a holiday (HRMS skips it unless Payroll Settings'
    consider_marked_attendance_on_holidays is on), but the row reads as an
    absence on every screen, and Attendance Fix will not touch it because it
    skips holidays.

What this does for the date, for every employee whose holiday list (their own,
else the company default) now carries it:

    Present / Half Day / other worked rows   tick Worked on Holiday
    Absent, no punches, no leave             removed: it was never an absence
    anything tied to a Leave Application     left alone (the sandwich rule
                                             already counts holidays inside leave)

Paid months are left alone: an employee with a submitted Salary Slip covering the
date is skipped and named in the report, so HR can decide whether to cancel and
redo the slip. The holiday itself is still added. A company-wide list cannot wait
on one person's payroll.

Approved Overtime Sheets for the date were written as working-day overtime; they
are listed, not rewritten. A submitted authorisation is HR's to amend.

Called by HolidayBulkUpdate.apply after the lists are written. Deliberately does
not handle a holiday being REMOVED from a list; that is done on the Holiday List
itself and re-marking those days is Attendance Fix's job.
"""

from datetime import datetime, time

import frappe
from frappe.utils import getdate, today

from avinashgroup_app.avinash_group_app.doctype.attendance_fix.attendance_fix import (
	cancel_and_delete_attendance,
)

# Statuses that mean the person turned up (Half Day included: half a day worked
# on a holiday is still holiday work).
WORKED_STATUSES = ("Present", "Half Day", "Work From Home")


def follow_up(holiday_date, holiday_lists):
	"""Re-mark attendance on `holiday_date` for employees on `holiday_lists`.

	No-op for a future date. Returns a report dict; every count is also a list of
	names so the form can show who.
	"""
	day = getdate(holiday_date)
	report = {"date": str(day), "worked": [], "absent_cleared": [], "paid_skipped": [], "overtime_sheets": []}
	if day > getdate(today()) or not holiday_lists:
		return report

	employees = _employees_on(holiday_lists)
	if not employees:
		return report

	paid = set(
		frappe.get_all(
			"Salary Slip",
			filters={
				"employee": ("in", employees),
				"docstatus": 1,
				"start_date": ("<=", day),
				"end_date": (">=", day),
			},
			pluck="employee",
		)
	)
	report["paid_skipped"] = sorted(paid)

	rows = frappe.get_all(
		"Attendance",
		filters={"employee": ("in", employees), "attendance_date": day, "docstatus": ("<", 2)},
		fields=["name", "employee", "status", "docstatus", "leave_application", "custom_worked_on_holiday"],
	)
	punched = set(
		frappe.get_all(
			"Employee Checkin",
			filters={
				"employee": ("in", employees),
				"time": ("between", [datetime.combine(day, time.min), datetime.combine(day, time.max)]),
			},
			pluck="employee",
		)
	)

	for row in rows:
		if row.employee in paid or row.leave_application:
			continue
		if row.status in WORKED_STATUSES:
			if not row.custom_worked_on_holiday:
				frappe.db.set_value("Attendance", row.name, "custom_worked_on_holiday", 1, update_modified=False)
				report["worked"].append(row.employee)
		elif row.status == "Absent" and row.employee not in punched:
			cancel_and_delete_attendance(row)
			report["absent_cleared"].append(row.employee)

	report["overtime_sheets"] = frappe.get_all(
		"Overtime Sheet",
		filters={"docstatus": 1, "work_date": day},
		pluck="name",
	)
	return report


def _employees_on(holiday_lists):
	"""Employees whose effective holiday list is one of these.

	Effective list = Employee.holiday_list, else the Company default, which is how
	HRMS resolves it (get_holiday_list_for_employee). Not only Active staff: a
	past date can carry attendance of someone who has left since.
	"""
	lists = tuple(holiday_lists)
	return [
		r[0]
		for r in frappe.db.sql(
			"""select e.name from `tabEmployee` e
			left join `tabCompany` c on c.name = e.company
			where coalesce(nullif(e.holiday_list, ''), c.default_holiday_list) in %(lists)s""",
			{"lists": lists},
		)
	]
