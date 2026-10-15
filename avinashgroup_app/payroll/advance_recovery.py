"""Advances recovered from salary, a month at a time, against a balance.

An advance is a loan, so the one question that matters is "how much is still
owed?". Typed month by month on the salary sheet, nothing can answer it — a
forgotten month is simply lost. So an advance is recorded once, as an Employee
Advance, when the money is handed over, with the instalment to take each month.

HRMS already keeps the balance: an Additional Salary that points at an Employee
Advance (`ref_doctype` / `ref_docname`) adds itself to that advance's
`return_amount` on submit and takes itself back on cancel, and the advance's
status follows. What HRMS lacks is the instalment. This posts it: for each open
advance, the smaller of the instalment and what is still outstanding, into the
payroll month, as a submitted `Salary Advance` deduction.

Re-running a month replaces that month's recoveries — it cancels the ones it
made before, which hands the amount back to the balance, and posts again — so
the button can be pressed as often as the attendance changes. A person whose
slip for the month is already submitted is left alone.

In the month an employee leaves (relieving date inside it) the whole balance is
taken, not one instalment: there is no later salary to take the rest from. More
than the last slip can bear is cut back to what it can (payroll/recovery_cap.py)
and the rest named on the Payroll Entry for HR to collect.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

COMPONENT = "Salary Advance"
SOURCE_TAG = "Advance Recovery"


def outstanding(advance):
	"""What the employee still owes on one advance."""
	return flt(advance.paid_amount) - flt(advance.claimed_amount) - flt(advance.return_amount)


def open_advances(employees, payroll_date):
	"""Advances to recover from this month's salary, oldest first."""
	if not employees:
		return []
	return frappe.get_all(
		"Employee Advance",
		filters={
			"employee": ["in", employees],
			"docstatus": 1,
			"repay_unclaimed_amount_from_salary": 1,
			"paid_amount": [">", 0],
			"status": ["not in", ("Claimed", "Returned", "Cancelled")],
		},
		fields=[
			"name",
			"employee",
			"company",
			"paid_amount",
			"claimed_amount",
			"return_amount",
			"custom_monthly_instalment",
			"custom_recover_from",
			"posting_date",
		],
		order_by="posting_date asc, creation asc",
	)


def post_recoveries(payroll_entry):
	"""Post this month's instalment for every open advance in the Payroll Entry."""
	if isinstance(payroll_entry, str):
		payroll_entry = frappe.get_doc("Payroll Entry", payroll_entry)

	from avinashgroup_app.payroll.attendance_allowance import paid_employees

	if not frappe.db.exists("Salary Component", COMPONENT):
		return []  # patches/setup_salary_advance_component.py makes it
	payroll_date = getdate(payroll_entry.end_date)
	start_date = getdate(payroll_entry.start_date)
	employees = [row.employee for row in payroll_entry.employees or []]
	# A submitted slip's recovery is final: neither cancelled nor posted again.
	paid = paid_employees(employees, payroll_date)
	employees = [e for e in employees if e not in paid]
	leaving = _leaving_in(employees, start_date, payroll_date)

	clear_month(employees, payroll_date)

	posted = []
	for advance in open_advances(employees, payroll_date):
		# Someone leaving this month repays now or never: the start date and
		# the instalment no longer apply.
		last_month = advance.employee in leaving
		if not last_month and advance.custom_recover_from and getdate(advance.custom_recover_from) > payroll_date:
			continue

		# Read again: clearing the month just handed earlier recoveries back.
		advance.return_amount = frappe.db.get_value("Employee Advance", advance.name, "return_amount")
		owed = outstanding(advance)
		if owed <= 0:
			continue

		amount = owed if last_month else min(flt(advance.custom_monthly_instalment) or owed, owed)
		doc = frappe.new_doc("Additional Salary")
		doc.update(
			{
				"employee": advance.employee,
				"company": advance.company,
				"salary_component": COMPONENT,
				"type": "Deduction",
				"amount": flt(amount, 2),
				"payroll_date": payroll_date,
				"overwrite_salary_structure_amount": 0,
				"ref_doctype": "Employee Advance",
				"ref_docname": advance.name,
				"custom_source": SOURCE_TAG,
				"notes": (
					_("Leaving this month: the whole {0} outstanding on {1}").format(flt(owed, 2), advance.name)
					if last_month
					else _("Instalment on {0}: {1} of {2} outstanding").format(advance.name, flt(amount, 2), flt(owed, 2))
				),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		posted.append(
			{
				"employee": advance.employee,
				"advance": advance.name,
				"amount": flt(amount, 2),
				"outstanding_before": flt(owed, 2),
				"additional_salary": doc.name,
			}
		)

	return posted


def _leaving_in(employees, start_date, end_date) -> set:
	"""Those of `employees` whose relieving date falls in the payroll month."""
	if not employees:
		return set()
	return set(
		frappe.get_all(
			"Employee",
			filters={"name": ("in", employees), "relieving_date": ("between", [start_date, end_date])},
			pluck="name",
		)
	)


def clear_month(employees, payroll_date):
	"""Take back the recoveries a previous run posted into this month."""
	if not employees:
		return
	for name in frappe.get_all(
		"Additional Salary",
		filters={
			"employee": ["in", employees],
			"payroll_date": payroll_date,
			"custom_source": SOURCE_TAG,
			"docstatus": 1,
		},
		pluck="name",
	):
		doc = frappe.get_doc("Additional Salary", name)
		doc.flags.ignore_permissions = True
		doc.cancel()
