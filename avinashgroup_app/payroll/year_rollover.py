"""Carrying everyone's pay into a new fiscal year, so the new year's tax applies.

HRMS does not look up the income tax slab by date. Every salary slip reads it
from the employee's Salary Structure Assignment
(`hrms/payroll/doctype/salary_slip/salary_slip.py`, `get_income_tax_slabs`), and
its only check is that the slab took effect on or before the payroll period
began. All 205 assignments on avinas1 were written on 1 Shrawan 2083 pointing
at `Nepal 83/84 - <ABBR>`. So on 1 Shrawan 2084, with an 84/85 slab created and
the 84/85 payroll period in place, every slip would still be taxed at 83/84
rates — the old slab passes the check, and nothing anywhere complains.

The fix follows the rule this app already keeps for pay: a salary is a dated
fact, never an edit (see Salary Revision). On the new year's first day each
employee gets a new assignment — same structure, same basic, same payable
account — pointing at the new year's slab. The 83/84 assignment stays behind as
the record of what 83/84 paid.

Deliberately narrow:

  * It never changes anyone's pay. A rise is a Salary Revision.
  * It refuses to run for a company that has no slab effective from the year's
    first day. Guessing — reusing last year's rates — is exactly the silent
    failure it exists to prevent. The slab comes first (`year_setup`).
  * Someone who already has an assignment from the new year's first day or
    later (an early revision, a joiner) is left alone.

Called by `hr.year_setup.setup_year`; safe to run again.
"""

import frappe
from frappe import _
from frappe.utils import getdate


def tax_slab_for(company, on_date):
	"""The submitted, enabled Income Tax Slab in force for a company on a date."""
	return frappe.db.get_value(
		"Income Tax Slab",
		{
			"company": company,
			"docstatus": 1,
			"disabled": 0,
			"effective_from": ["<=", getdate(on_date)],
		},
		"name",
		order_by="effective_from desc",
	)


def roll_salary_assignments(company, year_start):
	"""Give every active employee of one company an assignment from `year_start`.

	Returns {"created": n, "already": n, "no_salary": n}. Raises if the company
	has no tax slab that starts on or after `year_start` — see the module notes.
	"""
	year_start = getdate(year_start)
	slab = tax_slab_for(company, year_start)
	slab_from = slab and frappe.db.get_value("Income Tax Slab", slab, "effective_from")
	if not slab or getdate(slab_from) < year_start:
		frappe.throw(
			_(
				"{0} has no Income Tax Slab effective from {1}. Create this year's slab first — "
				"the pay can only be rolled onto the new year's rates."
			).format(company, year_start)
		)

	created = already = no_salary = 0
	for employee in frappe.get_all(
		"Employee", filters={"company": company, "status": "Active"}, pluck="name"
	):
		if frappe.db.exists(
			"Salary Structure Assignment",
			{"employee": employee, "docstatus": 1, "from_date": [">=", year_start]},
		):
			already += 1
			continue

		current = frappe.db.get_value(
			"Salary Structure Assignment",
			{"employee": employee, "docstatus": 1, "from_date": ["<", year_start]},
			["salary_structure", "base", "variable", "currency", "payroll_payable_account"],
			as_dict=True,
			order_by="from_date desc",
		)
		if not current:
			no_salary += 1
			continue

		doc = frappe.new_doc("Salary Structure Assignment")
		doc.update(
			{
				"employee": employee,
				"company": company,
				"from_date": year_start,
				"salary_structure": current.salary_structure,
				"base": current.base,
				"variable": current.variable,
				"currency": current.currency,
				"payroll_payable_account": current.payroll_payable_account,
				"income_tax_slab": slab,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		created += 1

	return {"slab": slab, "created": created, "already": already, "no_salary": no_salary}
