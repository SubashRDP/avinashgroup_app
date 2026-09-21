"""The festival bonus, decided once a year and paid on one screen.

Nepal's Labour Act makes the Dashain allowance compulsory: one month's pay to
anyone who has served the full year, and that fraction of a month to anyone who
joined part-way through. The two decisions a company actually makes each year
are whether it is paying at all and what "one month" means — basic alone, basic
with the dearness allowance, or the whole of last month's slip.

So this document holds the decision, not a formula buried in a salary structure.
Tick or untick `Bonus Given This Year` and the year is on record either way. When
it is given, Get Employees works out every person's months of service to the
payout date, caps them at twelve and prorates the month; every line stays
editable, because a manager settling an odd case should not have to fight the
arithmetic.

Submitting writes one submitted Additional Salary per line, dated in the payout
month, so the bonus lands on that month's salary slip and is taxed with it.
Cancelling takes them all back.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, date_diff, flt, getdate

COMPONENT = "Dashain Bonus"
MONTHS_IN_YEAR = 12


class DashainBonus(Document):
	def validate(self):
		self.set_bs_month()
		if not self.bonus_given:
			self.employees = []
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
			if flt(row.amount) < 0:
				frappe.throw(_("Row {0}: a bonus cannot be negative").format(row.idx))

	def set_bs_month(self):
		try:
			from rdp_common_app.utils.bs_boundaries import BS_MONTH_NAMES, ad_to_bs

			bs = ad_to_bs(getdate(self.payout_date))
			self.bs_month = f"{BS_MONTH_NAMES[bs.month]} {bs.year}"
		except Exception:
			# A missing BS calendar must not stop the bonus: the AD date still rules.
			self.bs_month = None

	def set_totals(self):
		self.employee_count = len(self.employees)
		self.total_amount = sum(flt(row.amount) for row in self.employees)

	def on_submit(self):
		if not self.bonus_given:
			return
		if not self.employees:
			frappe.throw(_("The bonus is marked as given, but nobody is listed."))

		for row in self.employees:
			if not flt(row.amount):
				continue
			doc = frappe.new_doc("Additional Salary")
			doc.update(
				{
					"employee": row.employee,
					"company": self.company,
					"salary_component": COMPONENT,
					"amount": row.amount,
					"payroll_date": self.payout_date,
					"currency": frappe.db.get_value("Company", self.company, "default_currency"),
					"overwrite_salary_structure_amount": 0,
					# TDS on the bonus in the month it is paid, not spread thin.
					"deduct_full_tax_on_selected_payroll_date": 1,
					"notes": row.note or _("Festival bonus {0}, {1}").format(self.fiscal_year, self.name),
				}
			)
			doc.flags.ignore_permissions = True
			doc.insert()
			doc.submit()
			row.db_set("additional_salary", doc.name, update_modified=False)

	def on_cancel(self):
		for row in self.employees:
			if not row.additional_salary or not frappe.db.exists("Additional Salary", row.additional_salary):
				continue
			doc = frappe.get_doc("Additional Salary", row.additional_salary)
			if doc.docstatus == 1:
				doc.flags.ignore_permissions = True
				doc.cancel()

	@frappe.whitelist()
	def get_employees(self):
		"""Fill the table with everyone the company owes a bonus to."""
		self.set("employees", [])
		no_salary = []

		for employee in fetch_eligible_employees(self.company, self.payout_date):
			months = months_of_service(employee.date_of_joining, self.payout_date)
			if flt(self.minimum_months) and months < flt(self.minimum_months):
				continue

			monthly = monthly_amount(employee.name, self.basis, self.payout_date)
			if not monthly:
				# No salary structure assignment, so there is no month to take a
				# bonus from. Left out rather than listed at zero, and named below
				# so nobody is quietly missed.
				no_salary.append(employee.employee_name or employee.name)
				continue

			self.append(
				"employees",
				{
					"employee": employee.name,
					"employee_name": employee.employee_name,
					"date_of_joining": employee.date_of_joining,
					"months_served": months,
					"monthly_amount": monthly,
					"amount": bonus_amount(monthly, months, self.percentage, self.prorate_new_joiners),
				},
			)

		self.set_totals()

		if no_salary:
			frappe.msgprint(
				_("Left out — no salary structure assigned: {0}").format(", ".join(no_salary)),
				title=_("{0} employees have no salary yet").format(len(no_salary)),
				indicator="orange",
			)

		return len(self.employees)


def fetch_eligible_employees(company, payout_date):
	"""Active staff who had joined by the payout date."""
	return frappe.get_all(
		"Employee",
		filters={
			"company": company,
			"status": "Active",
			"date_of_joining": ["<=", getdate(payout_date)],
		},
		fields=["name", "employee_name", "date_of_joining"],
		order_by="employee_name",
	)


def months_of_service(date_of_joining, payout_date):
	"""Months served to the payout date, capped at a full year.

	Counted as whole months plus the part month left over, so someone who joined
	on Shrawan 16 is credited half of Shrawan — the same arithmetic an HR
	officer does by hand, and visible on the row so it can be checked.
	"""
	start, end = getdate(date_of_joining), getdate(payout_date)
	if start >= end:
		return 0.0

	whole = 0
	while add_months(start, whole + 1) <= end:
		whole += 1
		if whole >= MONTHS_IN_YEAR:
			return float(MONTHS_IN_YEAR)

	anniversary = add_months(start, whole)
	next_anniversary = add_months(start, whole + 1)
	span = date_diff(next_anniversary, anniversary) or 1
	part = date_diff(end, anniversary) / span

	return min(MONTHS_IN_YEAR, round(whole + part, 2))


def monthly_amount(employee, basis, payout_date):
	"""What one month is worth for this person, under the chosen basis."""
	if basis == "Last Slip Gross":
		gross = frappe.db.get_value(
			"Salary Slip",
			{"employee": employee, "docstatus": 1, "start_date": ["<=", getdate(payout_date)]},
			"gross_pay",
			order_by="start_date desc",
		)
		if gross:
			return flt(gross)
		# No slip yet — fall back to the structure, so a new joiner is not paid nothing.

	base = flt(
		frappe.db.get_value(
			"Salary Structure Assignment",
			{"employee": employee, "docstatus": 1, "from_date": ["<=", getdate(payout_date)]},
			"base",
			order_by="from_date desc",
		)
	)

	if basis == "Basic + Dearness Allowance":
		base += flt(frappe.db.get_value("Employee", employee, "custom_dearness_allowance"))

	return base


def bonus_amount(monthly, months, percentage, prorate):
	"""One month at the chosen percentage, prorated unless a full year is served."""
	share = 1.0
	if cint(prorate) and months < MONTHS_IN_YEAR:
		share = months / MONTHS_IN_YEAR

	return flt(flt(monthly) * flt(percentage) / 100 * share, 2)
