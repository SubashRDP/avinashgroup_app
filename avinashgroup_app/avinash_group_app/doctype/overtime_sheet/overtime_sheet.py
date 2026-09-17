"""Overtime Sheet — the company's approved request for extra work on one date.

One form for every kind of extra work: a festival holiday, a Saturday, or staying
beyond the shift on a normal day. HR only lists who was asked and when. What each
person earns is not chosen on the form; it is worked out per row by the rules in
`avinashgroup_app.hr.overtime` from that person's own holiday list, shift and
Employee Category — so a sheet can mix a holiday for some and a working day for
others, and nobody can pick the wrong outcome.

Approval runs through Dynamic Approval; a sheet authorises nothing until it is
submitted. Backdated sheets are allowed on purpose: extra work is often arranged
by phone and written up afterwards.

Deliberately thin: validation and totals only. The rules, and the read API that
settlement uses, live in `hr/overtime.py`.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from avinashgroup_app.hr.overtime import (
	ENTITLEMENT_OVERTIME,
	ENTITLEMENT_REPLACEMENT_LEAVE,
	OvertimeRuleError,
	evaluate,
)


class OvertimeSheet(Document):
	def validate(self):
		self.validate_rows()
		self.apply_rules()
		self.validate_not_already_authorised()
		self.set_totals()

	def validate_rows(self):
		seen = set()
		for row in self.employees:
			if row.employee in seen:
				frappe.throw(_("Row {0}: {1} is listed twice").format(row.idx, row.employee_name or row.employee))
			seen.add(row.employee)

			company = frappe.db.get_value("Employee", row.employee, "company")
			if company != self.company:
				frappe.throw(
					_("Row {0}: {1} belongs to {2}, not {3}").format(
						row.idx, row.employee_name or row.employee, company, self.company
					)
				)

	def apply_rules(self):
		"""Evaluate every row, then report ALL refusals at once.

		Stopping at the first problem makes HR fix a 30-row sheet one save at a
		time; one message listing every row is the friendlier failure.
		"""
		problems = []
		for row in self.employees:
			try:
				result = evaluate(row.employee, self.work_date, row.from_time, row.to_time)
			except OvertimeRuleError as e:
				problems.append(_("Row {0}: {1}").format(row.idx, str(e)))
				continue
			row.day_type = result["day_type"]
			row.entitlement = result["entitlement"]
			row.employee_category = result["employee_category"]
			row.shift = result["shift"]
			row.overtime_hours = result["overtime_hours"]
			row._day_name = result["day_name"]

		if problems:
			frappe.throw("<br>".join(problems), title=_("Rows the policy does not allow"))

	def validate_not_already_authorised(self):
		"""Nobody on two live sheets for one date — the work would be paid twice."""
		employees = [r.employee for r in self.employees]
		if not employees:
			return
		clash = frappe.db.sql(
			"""select row.employee, sheet.name
			from `tabOvertime Sheet Employee` row
			join `tabOvertime Sheet` sheet on sheet.name = row.parent
			where sheet.work_date = %(date)s and sheet.docstatus < 2
			  and sheet.name != %(name)s and row.employee in %(employees)s""",
			{"date": self.work_date, "name": self.name or "", "employees": employees},
			as_dict=True,
		)
		if clash:
			frappe.throw(
				_("Already on another Overtime Sheet for this date: {0}").format(
					", ".join(f"{c.employee} ({c.name})" for c in clash)
				),
				title=_("Authorised Twice"),
			)

	def set_totals(self):
		self.total_employees = len(self.employees)
		self.total_overtime_hours = sum(
			r.overtime_hours or 0 for r in self.employees if r.entitlement == ENTITLEMENT_OVERTIME
		)
		self.replacement_leave_days = sum(
			1 for r in self.employees if r.entitlement == ENTITLEMENT_REPLACEMENT_LEAVE
		)
		names = sorted({getattr(r, "_day_name", None) or r.day_type for r in self.employees if r.day_type})
		self.day_summary = " / ".join(names)
