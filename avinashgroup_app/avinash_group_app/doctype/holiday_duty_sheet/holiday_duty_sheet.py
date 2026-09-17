"""The company's written call-in for work on a holiday.

A holiday punch shows someone was on site, not that the company asked for it.
Policy 5.1 (client meeting 2026-09-15) makes this sheet the thing that decides
whether holiday work earns overtime (Plant) or replacement leave (Officer &
Admin): only employees on an approved sheet count.

One sheet is a date, a company, optionally a department, the reason, and the
employees called with their planned hours. Approval runs through Dynamic Approval
(set up per company on a Dynamic Approval Setting for this doctype); the sheet
counts once it is submitted.

Backdated sheets are allowed on purpose: duty is often arranged by phone and
written up afterwards, and someone who came in without being listed is put right
by adding them to a sheet, not by guessing from their punches.

Read side for later steps: `avinashgroup_app.hr.holiday_duty`.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours

from avinashgroup_app.hr.holiday_duty import get_holiday_for_employee


class HolidayDutySheet(Document):
	def validate(self):
		self.validate_employees()
		self.validate_holiday()
		self.validate_not_already_called()
		self.set_hours()
		self.total_employees = len(self.employees)

	def validate_employees(self):
		seen = set()
		for row in self.employees:
			if row.employee in seen:
				frappe.throw(_("Row {0}: {1} is listed twice").format(row.idx, row.employee))
			seen.add(row.employee)

			company = frappe.db.get_value("Employee", row.employee, "company")
			if company != self.company:
				frappe.throw(
					_("Row {0}: {1} belongs to {2}, not {3}").format(
						row.idx, row.employee_name or row.employee, company, self.company
					)
				)

	def validate_holiday(self):
		"""The date must be a holiday for every employee on the sheet.

		Checked per employee, not per company, because the lists differ: Teej is a
		holiday on the (Women) lists only, so calling a man in "for Teej" is just
		a normal working day and has nothing to compensate.
		"""
		not_holiday, names = [], set()
		for row in self.employees:
			is_holiday, description = get_holiday_for_employee(row.employee, self.holiday_date)
			if is_holiday:
				names.add(description)
			else:
				not_holiday.append(row.employee_name or row.employee)

		if not_holiday:
			frappe.throw(
				_("{0} is a normal working day, not a holiday, for: {1}").format(
					frappe.utils.formatdate(self.holiday_date), ", ".join(not_holiday)
				),
				title=_("Not a Holiday"),
			)
		self.holiday_name = ", ".join(sorted(n for n in names if n))

	def validate_not_already_called(self):
		"""Nobody on two live sheets for the same date — they would be paid twice."""
		employees = [r.employee for r in self.employees]
		if not employees:
			return

		clash = frappe.db.sql(
			"""select row.employee, sheet.name
			from `tabHoliday Duty Sheet Employee` row
			join `tabHoliday Duty Sheet` sheet on sheet.name = row.parent
			where sheet.holiday_date = %(date)s and sheet.docstatus < 2
			  and sheet.name != %(name)s and row.employee in %(employees)s""",
			{"date": self.holiday_date, "name": self.name or "", "employees": employees},
			as_dict=True,
		)
		if clash:
			frappe.throw(
				_("Already on another sheet for this date: {0}").format(
					", ".join(f"{c.employee} ({c.name})" for c in clash)
				),
				title=_("Called In Twice"),
			)

	def set_hours(self):
		for row in self.employees:
			if row.from_time and row.to_time:
				hours = time_diff_in_hours(row.to_time, row.from_time)
				if hours <= 0:
					frappe.throw(_("Row {0}: To must be after From").format(row.idx))
				row.planned_hours = hours
			else:
				row.planned_hours = 0
