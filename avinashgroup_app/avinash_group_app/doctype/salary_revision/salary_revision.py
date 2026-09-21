"""A pay rise, done the way payroll actually survives one: dated, not edited.

The standard practice — and the only one ERPNext supports safely — is that a
salary is a dated fact. You never edit someone's basic in place; you assign the
structure again from the date the new pay starts, and the old assignment stays
behind as the record of what was paid before. Every slip then picks the
assignment in force on the month it covers, so last year's payslips keep
reconciling with last year's journal entries.

Two things follow from that, and both are why this document exists:

  A slip is paid at one rate for its whole month. An increment effective
  mid-month cannot half-pay the month, so the effective date belongs on the
  first day of a BS month. Anything else silently takes effect the month after.

  Increments are agreed late. The rise runs from Shrawan, the meeting happens
  in Mangsir, and four months have already been paid at the old rate. That
  difference is arrears — a one-off amount in the month it is finally paid,
  never a backdated edit to submitted slips.

The dearness allowance is the one part of NGI's pay that is not dated: the
structure reads it off the Employee, so raising it changes the field. The old
value is written onto the row before it is overwritten, which makes this
document the history, and lets cancelling put it back.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

ARREARS_COMPONENT = "Salary Arrears"


class SalaryRevision(Document):
	def validate(self):
		self.set_bs_month()
		self.validate_rows()
		self.set_totals()

	def validate_rows(self):
		seen = set()
		for row in self.employees:
			if row.employee in seen:
				frappe.throw(
					_("Row {0}: {1} is listed twice").format(row.idx, row.employee_name or row.employee)
				)
			seen.add(row.employee)

			company = frappe.db.get_value("Employee", row.employee, "company")
			if company != self.company:
				frappe.throw(
					_("Row {0}: {1} belongs to {2}").format(row.idx, row.employee_name or row.employee, company)
				)
			if flt(row.new_base) <= 0:
				frappe.throw(_("Row {0}: the new basic must be more than zero").format(row.idx))

			current = current_assignment(row.employee, self.effective_date)
			if not current:
				frappe.throw(
					_("Row {0}: {1} has no salary structure assigned, so there is nothing to revise").format(
						row.idx, row.employee_name or row.employee
					)
				)
			row.salary_structure = current.salary_structure
			if not row.current_base:
				row.current_base = current.base

			if frappe.db.exists(
				"Salary Structure Assignment",
				{"employee": row.employee, "from_date": getdate(self.effective_date), "docstatus": 1},
			):
				frappe.throw(
					_("Row {0}: {1} already has a salary assigned from {2}").format(
						row.idx, row.employee_name or row.employee, self.effective_date
					)
				)

	def set_bs_month(self):
		try:
			from rdp_common_app.utils.bs_boundaries import BS_MONTH_NAMES, ad_to_bs

			bs = ad_to_bs(getdate(self.effective_date))
			self.bs_month = f"{BS_MONTH_NAMES[bs.month]} {bs.year}"
		except Exception:
			# A missing BS calendar must not stop an increment: the AD date still rules.
			self.bs_month = None

	def set_totals(self):
		self.employee_count = len(self.employees)
		self.total_increase = sum(
			flt(row.new_base)
			+ flt(row.new_dearness_allowance)
			- flt(row.current_base)
			- flt(row.current_dearness_allowance)
			for row in self.employees
		)
		self.total_arrears = sum(flt(row.arrears_amount) for row in self.employees)

	def on_submit(self):
		for row in self.employees:
			self.assign_new_salary(row)
			self.move_dearness_allowance(row)
			self.pay_the_arrears(row)

	def on_cancel(self):
		for row in self.employees:
			if row.arrears_additional_salary and frappe.db.exists(
				"Additional Salary", row.arrears_additional_salary
			):
				doc = frappe.get_doc("Additional Salary", row.arrears_additional_salary)
				if doc.docstatus == 1:
					doc.flags.ignore_permissions = True
					doc.cancel()

			if row.salary_structure_assignment and frappe.db.exists(
				"Salary Structure Assignment", row.salary_structure_assignment
			):
				doc = frappe.get_doc("Salary Structure Assignment", row.salary_structure_assignment)
				if doc.docstatus == 1:
					doc.flags.ignore_permissions = True
					doc.cancel()

			# Put the dearness allowance back: the field has no history of its own.
			if flt(row.new_dearness_allowance) != flt(row.current_dearness_allowance):
				frappe.db.set_value(
					"Employee", row.employee, "custom_dearness_allowance", flt(row.current_dearness_allowance)
				)

	def assign_new_salary(self, row):
		current = current_assignment(row.employee, self.effective_date)
		doc = frappe.new_doc("Salary Structure Assignment")
		doc.update(
			{
				"employee": row.employee,
				"salary_structure": row.salary_structure or current.salary_structure,
				"from_date": self.effective_date,
				"base": row.new_base,
				"variable": current.variable if current else 0,
				"company": self.company,
				"currency": (current and current.currency)
				or frappe.db.get_value("Company", self.company, "default_currency"),
				"income_tax_slab": current.income_tax_slab if current else None,
				"payroll_payable_account": current.payroll_payable_account if current else None,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		row.db_set("salary_structure_assignment", doc.name, update_modified=False)

	def move_dearness_allowance(self, row):
		if flt(row.new_dearness_allowance) == flt(row.current_dearness_allowance):
			return
		frappe.db.set_value(
			"Employee", row.employee, "custom_dearness_allowance", flt(row.new_dearness_allowance)
		)

	def pay_the_arrears(self, row):
		if not self.pay_arrears or not flt(row.arrears_amount):
			return

		ensure_arrears_component()
		doc = frappe.new_doc("Additional Salary")
		doc.update(
			{
				"employee": row.employee,
				"company": self.company,
				"salary_component": ARREARS_COMPONENT,
				"amount": row.arrears_amount,
				"payroll_date": self.arrears_payout_date,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"overwrite_salary_structure_amount": 0,
				"deduct_full_tax_on_selected_payroll_date": 1,
				"notes": row.note
				or _("Arrears of the revision effective {0} ({1})").format(self.effective_date, self.name),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		row.db_set("arrears_additional_salary", doc.name, update_modified=False)

	@frappe.whitelist()
	def get_employees(self):
		"""List everyone on a salary today, at the hike this document proposes."""
		self.set("employees", [])
		percent = flt(self.default_increment_percent)

		for employee in frappe.get_all(
			"Employee",
			filters={"company": self.company, "status": "Active"},
			fields=["name", "employee_name", "custom_dearness_allowance"],
			order_by="employee_name",
		):
			current = current_assignment(employee.name, self.effective_date)
			if not current or not flt(current.base):
				continue

			new_base = flt(flt(current.base) * (1 + percent / 100), 2)
			self.append(
				"employees",
				{
					"employee": employee.name,
					"employee_name": employee.employee_name,
					"salary_structure": current.salary_structure,
					"current_base": current.base,
					"increment_percent": percent,
					"new_base": new_base,
					"current_dearness_allowance": flt(employee.custom_dearness_allowance),
					"new_dearness_allowance": flt(employee.custom_dearness_allowance),
					"arrears_months": months_already_paid(employee.name, self.effective_date),
					"arrears_amount": arrears_for(
						employee.name, self.effective_date, new_base - flt(current.base)
					)
					if self.pay_arrears
					else 0,
				},
			)

		self.set_totals()
		return len(self.employees)


def current_assignment(employee, on_date):
	"""The assignment in force on the effective date — what is being replaced."""
	name = frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1, "from_date": ["<=", getdate(on_date)]},
		"name",
		order_by="from_date desc",
	)
	return frappe.get_doc("Salary Structure Assignment", name) if name else None


def months_already_paid(employee, effective_date):
	"""Submitted slips covering a month on or after the date the rise runs from."""
	return frappe.db.count(
		"Salary Slip",
		{"employee": employee, "docstatus": 1, "start_date": [">=", getdate(effective_date)]},
	)


def arrears_for(employee, effective_date, monthly_difference):
	return flt(months_already_paid(employee, effective_date) * flt(monthly_difference), 2)


def ensure_arrears_component():
	if frappe.db.exists("Salary Component", ARREARS_COMPONENT):
		return
	frappe.get_doc(
		{
			"doctype": "Salary Component",
			"salary_component": ARREARS_COMPONENT,
			"salary_component_abbr": "ARR",
			"type": "Earning",
			"is_tax_applicable": 1,
			"depends_on_payment_days": 0,
			"round_to_the_nearest_integer": 1,
		}
	).insert(ignore_permissions=True)
