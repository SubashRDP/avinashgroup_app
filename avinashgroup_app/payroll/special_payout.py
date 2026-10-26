"""Dashain allowance and leave encashment paid on their own slip, not the month's salary.

Until 2026-10-26 both rode the regular monthly slip: a tick on the Bhadra or
Ashwin Payroll Entry posted the Additional Salary and HRMS put it beside Basic,
overtime and SSF. The user asked for them "calculated separately with that only
component ... without binding with another month": one payout, one slip, one
journal, that shows the festival allowance (or the encashment) and the tax it
causes, and nothing else.

How it fits HRMS:

  * A Payroll Entry with **Payout** (`custom_payout_type`) set to "Dashain
    Allowance" or "Leave Encashment" is a payout entry. It has the month's
    dates like the salary entry, and makes its slips, accrual journal and bank
    entry the HRMS way (payroll/payroll_entry.py). Its slips carry the same
    Payout value; a blank Payout is the monthly salary.
  * The Additional Salary that pays it is tagged with the same Payout
    (`tag_additional_salary`): a festival-allowance component, or the
    Additional Salary of a Leave Encashment. A tagged row is also ticked
    `disabled`, which is the one thing HRMS's own `get_additional_salaries`
    filters on — so the monthly slip never sees it. Leave Recovery (a
    deduction) is not tagged and stays on the monthly / final slip.
  * HRMS's `check_existing` refuses a second slip for the same dates only within
    one Payroll Entry, so a payout slip and the salary slip coexist. Across
    entries, `validate_existing_salary_slips` and Get Employees are overridden
    to compare a slip only with slips of its own kind.

The payout slip (`build_payout_slip`, Salary Slip validate, first of the app's
hooks). HRMS builds it as it builds any slip — structure, allowances, the
month's Additional Salary — and this hook adds the payout's own rows, so for a
moment the slip is exactly the merged slip the old flow would have made. From
that it takes the year's projected taxable income A (HRMS's own
`total_taxable_earnings`, with the payout in it) and the payout P, and charges

    payout tax = (slab(A + excess) − slab(A − P + excess)) × (1 − women's rebate)

i.e. the whole tax the payout adds to the year, in this payout — what HRMS's
"Deduct Full Tax on Selected Payroll Date" charged on the merged slip, with
payroll/tax_relief.py's retirement excess and rebate applied the same way.
Then everything but the payout rows and the tax row is dropped. The month's
salary slip (which cannot see the payout, it shares its dates) charges the
year's structured tax as before; the next month's slip sums both earlier slips,
earnings and tax, so the year stays right whatever order the two are made in.
A payout made before the month's overtime is posted projects the year without
that overtime; the next month's slip re-spreads the year's tax and absorbs it.

Landmines:

  * `disabled` is HRMS's field for a stopped recurring Additional Salary. Do not
    untick it on a payout row: the monthly slip would then pay it a second time.
  * A Salary Slip made by hand (no Payroll Entry) for an employee who already
    has a payout slip that month is refused by HRMS's `check_existing` (it
    compares with every slip when there is no entry). Make salary slips from a
    Payroll Entry.
  * Code that asks "is this month paid?" (attendance guards, arrears, the
    already-paid checks) must look at regular slips only: `REGULAR_SLIPS`.

Boundary: which amounts are due, and when, is festival_allowance.py's and
leave_encashment.py's business, unchanged. This module only decides on which
slip they are paid and what that slip's tax is. Docs: docs/user-guide/
05-monthly-payroll.md ("Dashain and leave encashment: their own payout").
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from hrms.payroll.doctype.salary_slip.salary_slip import calculate_tax_by_tax_slab, get_salary_component_data

#: The field on Payroll Entry, Salary Slip and Additional Salary (patch setup_special_payout).
PAYOUT_FIELD = "custom_payout_type"
DASHAIN = "Dashain Allowance"
ENCASHMENT = "Leave Encashment"
PAYOUT_TYPES = (DASHAIN, ENCASHMENT)
#: frappe.get_all filter fragment: the monthly salary slips, never a payout slip.
REGULAR_SLIPS = {PAYOUT_FIELD: ("is", "not set")}
#: The same for raw SQL on `tabSalary Slip` aliased `ss`.
REGULAR_SLIPS_SQL = "ifnull(ss.custom_payout_type, '') = ''"


def slip_kind_filter(payout_type) -> dict:
	"""Filter fragment for slips of the same kind: this payout, or the monthly salary."""
	return {PAYOUT_FIELD: payout_type} if payout_type else dict(REGULAR_SLIPS)


def payout_type_for(doc) -> str | None:
	"""The payout an Additional Salary belongs to, by what it pays; None for monthly pay.

	Earnings only: a Leave Encashment's Additional Salary, or any festival
	allowance component (the tick on the Salary Component), whoever made it.
	"""
	if doc.type and doc.type != "Earning":
		return None
	if doc.ref_doctype == "Leave Encashment":
		return ENCASHMENT
	if doc.salary_component and frappe.get_cached_value(
		"Salary Component", doc.salary_component, "custom_is_festival_allowance"
	):
		return DASHAIN
	return None


def tag_additional_salary(doc, method=None):
	"""Tag a payout's Additional Salary and keep it off the monthly slip.

	Hook: doc_events → Additional Salary → validate, which runs on save and on
	submit (HRMS's Leave Encashment submits its row without saving it first),
	never again once submitted: a row already submitted keeps what it had.
	Throws for a recurring payout row (a payout is one month's amount).
	"""
	if doc.docstatus == 2:
		return
	payout = doc.get(PAYOUT_FIELD) or payout_type_for(doc)
	if not payout:
		return
	if doc.is_recurring:
		frappe.throw(_("{0} is paid once, on its own payout; it cannot be recurring.").format(payout))
	doc.set(PAYOUT_FIELD, payout)
	# HRMS's get_additional_salaries reads only disabled = 0: this is what keeps
	# the payout off the month's salary slip. build_payout_slip reads it instead.
	doc.disabled = 1


def payout_additional_salaries(employee: str, payout_type: str, start_date, end_date) -> list:
	"""Submitted payout rows of this type for the employee, dated in the period."""
	return frappe.get_all(
		"Additional Salary",
		filters={
			"employee": employee,
			"docstatus": 1,
			"type": "Earning",
			PAYOUT_FIELD: payout_type,
			"payroll_date": ("between", [getdate(start_date), getdate(end_date)]),
		},
		fields=["name", "salary_component", "amount", "deduct_full_tax_on_selected_payroll_date"],
		order_by="payroll_date, name",
	)


def employees_due(employees: list, payout_type: str, start_date, end_date) -> set:
	"""Of `employees`, those with something to be paid on this payout in the period."""
	if not employees:
		return set()
	return set(
		frappe.get_all(
			"Additional Salary",
			filters={
				"employee": ("in", list(employees)),
				"docstatus": 1,
				"type": "Earning",
				PAYOUT_FIELD: payout_type,
				"payroll_date": ("between", [getdate(start_date), getdate(end_date)]),
			},
			pluck="employee",
		)
	)


def set_slip_payout_type(doc, method=None):
	"""A slip made by a Payroll Entry is of the entry's kind. Hook: Salary Slip before_validate."""
	if doc.docstatus != 0 or not doc.payroll_entry:
		return
	doc.set(PAYOUT_FIELD, frappe.db.get_value("Payroll Entry", doc.payroll_entry, PAYOUT_FIELD) or None)


def build_payout_slip(doc, method=None):
	"""Reduce a payout slip to the payout's rows and the tax they cause.

	Hook: doc_events → Salary Slip → validate, first of the app's slip hooks
	(after the controller has built the slip as a monthly one). Runs on submit
	too: Frappe validates a slip again as it submits it (docstatus 1), and the
	controller has just rebuilt it as a monthly slip. A monthly slip is left
	alone. Throws when the employee has nothing to be paid on this payout in
	the slip's period.
	"""
	payout = doc.get(PAYOUT_FIELD)
	if not payout or doc.docstatus == 2:
		return
	due = payout_additional_salaries(doc.employee, payout, doc.start_date, doc.end_date)
	if not due:
		frappe.throw(
			_("{0} has no {1} to be paid between {2} and {3}.").format(
				doc.employee_name or doc.employee, payout, doc.start_date, doc.end_date
			),
			title=_("Nothing to pay"),
		)

	for row in due:
		doc.update_component_row(
			get_salary_component_data(row.salary_component),
			row.amount,
			"earnings",
			frappe._dict(
				name=row.name,
				overwrite=0,
				deduct_full_tax_on_selected_payroll_date=row.deduct_full_tax_on_selected_payroll_date,
			),
		)
	# The slip is now the merged slip: the month's pay with the payout in it.
	# Recalculate it as the monthly slip would be (fixed allowances included),
	# so HRMS's annual projection is the one the old flow taxed.
	from avinashgroup_app.payroll.salary_slip import apply_employee_allowances

	if not apply_employee_allowances(doc):
		doc.calculate_net_pay()

	amounts = {row.name: flt(row.amount) for row in due}
	payout_rows = [d for d in doc.earnings if d.additional_salary in amounts]
	taxable = sum(amounts[d.additional_salary] for d in payout_rows if d.is_tax_applicable)
	tax = payout_tax(doc, taxable)

	from avinashgroup_app.payroll.income_tax import get_tax_row

	tax_row = get_tax_row(doc)
	for d in payout_rows:
		# Fixed amount: never prorated by the month's payment days.
		d.amount = d.additional_amount = amounts[d.additional_salary]
		d.default_amount = 0
	doc.set("earnings", payout_rows)
	doc.set("deductions", [tax_row] if tax_row else [])
	if tax_row:
		tax_row.amount = tax_row.default_amount = flt(tax, tax_row.precision("amount"))
		tax_row.additional_amount = 0

	doc.gross_pay = sum(flt(d.amount) for d in doc.earnings if not d.do_not_include_in_total)
	doc.base_gross_pay = flt(doc.gross_pay * flt(doc.exchange_rate or 1), doc.precision("base_gross_pay"))
	doc.set_net_pay()
	doc.current_month_income_tax = flt(tax_row.amount) if tax_row else 0
	doc.compute_year_to_date()
	doc.compute_month_to_date()
	doc.compute_component_wise_year_to_date()


def payout_tax(doc, payout_taxable: float) -> float:
	"""The whole year's tax that `payout_taxable` adds, from the merged slip's projection.

	`doc` must still hold HRMS's figures for the merged slip (monthly pay plus
	the payout). Other payout slips of the same month, already submitted, are
	counted under the payout, so two payouts in one month are taxed as one.
	Returns 0 when the slip computed no tax (no tax component, no payroll period).
	"""
	from avinashgroup_app.payroll.tax_relief import retirement_excess, women_rebate_fraction

	slab = getattr(doc, "tax_slab", None)
	if not slab or not payout_taxable or not hasattr(doc, "total_taxable_earnings"):
		return 0.0
	year = flt(doc.total_taxable_earnings) + other_payouts_taxable(doc) + retirement_excess(doc)
	rebate = women_rebate_fraction(doc, slab)
	eval_locals, __ = doc.get_data_for_eval()
	with_payout, __ = calculate_tax_by_tax_slab(year, slab, doc.whitelisted_globals, eval_locals)
	without, __ = calculate_tax_by_tax_slab(year - payout_taxable, slab, doc.whitelisted_globals, eval_locals)
	return max(0.0, (flt(with_payout) - flt(without)) * (1 - rebate))


def other_payouts_taxable(doc) -> float:
	"""Taxable earnings on the employee's other submitted payout slips for the same dates.

	HRMS counts a slip as "previous" only when it ends before this one starts,
	so a second payout in the same month would not see the first.
	"""
	rows = frappe.db.sql(
		"""select sum(sd.amount) from `tabSalary Detail` sd
		join `tabSalary Slip` ss on ss.name = sd.parent and sd.parenttype = 'Salary Slip'
		where ss.employee = %(employee)s and ss.docstatus = 1
		  and ss.start_date = %(start)s and ss.end_date = %(end)s
		  and ifnull(ss.custom_payout_type, '') != '' and ss.name != %(name)s
		  and sd.parentfield = 'earnings' and sd.is_tax_applicable = 1""",
		{"employee": doc.employee, "start": doc.start_date, "end": doc.end_date, "name": doc.name or ""},
	)
	return flt(rows[0][0]) if rows else 0.0


def is_payout_slip(doc) -> bool:
	return bool(doc.get(PAYOUT_FIELD))
