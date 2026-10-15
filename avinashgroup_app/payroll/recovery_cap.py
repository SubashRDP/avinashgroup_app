"""A recovery never takes a salary slip below zero; the rest is named for HR.

Two deductions can be bigger than the month's pay: leave taken beyond what was
earned (payroll/leave_encashment `recover_month`) and, in the month someone
leaves, the whole of an advance (payroll/advance_recovery). HRMS refuses to
submit a slip whose net pay is negative, so one such person used to stop the
whole Payroll Entry.

So before the slips are submitted, every draft slip of the entry with a negative
net pay has its recoveries cut, leave recovery first, then the advance, until the
net pay is zero. A cut is made on the Additional Salary itself (cancelled and
posted again smaller), not on the slip row, because the advance's balance is kept
from the Additional Salary: what was not taken stays owed on the advance. What
was cut is returned, for the Payroll Inputs Log and a warning: HR collects it
outside payroll.

Only these two sources are ever cut. Tea, fines, tax and SSF are what the month
owes and are left as they are.
"""

import frappe
from frappe import _
from frappe.utils import flt

from avinashgroup_app.payroll.advance_recovery import SOURCE_TAG as ADVANCE_SOURCE
from avinashgroup_app.payroll.leave_encashment import RECOVERY_SOURCE as LEAVE_SOURCE

#: Cut first to last: the advance stays on its own balance, a leave recovery
#: cut is lost unless HR collects it, so the leave recovery gives way first.
CAPPED_SOURCES = (LEAVE_SOURCE, ADVANCE_SOURCE)


def cap_recoveries(entry) -> list[dict]:
	"""Cut the entry's recoveries so no draft slip pays less than nothing.

	Returns [{"employee", "employee_name", "component", "amount"}] — what each
	person still owes outside payroll.
	"""
	shortfalls = []
	for name in frappe.get_all("Salary Slip", filters={"payroll_entry": entry.name, "docstatus": 0}, pluck="name"):
		shortfalls += cap_slip(frappe.get_doc("Salary Slip", name))
	return shortfalls


def cap_slip(slip) -> list[dict]:
	"""Cut one draft slip's recoveries until its net pay is not below zero."""
	over = -flt(slip.net_pay, 2)
	if over <= 0:
		return []
	shortfalls = []
	for row in _recovery_rows(slip):
		cut = min(over, flt(row.amount))
		_reduce(row.additional_salary, flt(row.amount) - cut)
		shortfalls.append(
			{"employee": slip.employee, "employee_name": slip.employee_name,
				"component": row.salary_component, "amount": flt(cut, 2)}
		)
		over = flt(over - cut, 2)
		if over <= 0:
			break
	slip.reload()
	slip.flags.ignore_permissions = True
	slip.save()
	return shortfalls


def _recovery_rows(slip):
	"""The slip's deduction rows posted by a capped source, in cutting order."""
	rows = [d for d in slip.deductions if d.additional_salary and flt(d.amount) > 0]
	source = dict(
		frappe.get_all(
			"Additional Salary",
			filters={"name": ("in", [d.additional_salary for d in rows] or [""])},
			fields=["name", "custom_source"],
			as_list=True,
		)
	)
	rows = [d for d in rows if source.get(d.additional_salary) in CAPPED_SOURCES]
	return sorted(rows, key=lambda d: CAPPED_SOURCES.index(source[d.additional_salary]))


def _reduce(name, new_amount):
	"""Replace a submitted Additional Salary by the same one for `new_amount` (none at 0)."""
	old = frappe.get_doc("Additional Salary", name)
	# A draft slip row links it and would block the cancel; the slip is
	# recalculated straight after.
	frappe.db.sql(
		"""delete sd from `tabSalary Detail` sd
		join `tabSalary Slip` ss on ss.name = sd.parent and sd.parenttype = 'Salary Slip'
		where sd.additional_salary = %s and ss.docstatus = 0""",
		name,
	)
	old.flags.ignore_permissions = True
	old.cancel()
	new_amount = flt(new_amount, 2)
	if new_amount <= 0:
		return
	new = frappe.copy_doc(old)
	new.docstatus = 0  # copied from the cancelled one
	new.amount = new_amount
	if flt(old.get("custom_rate")):
		new.custom_quantity = new_amount / flt(old.custom_rate)
	new.notes = ((old.get("notes") or "") + "\n" + _(
		"Cut from {0} to {1}: the last slip could not bear more. Collect the rest outside payroll."
	).format(flt(old.amount, 2), new_amount)).strip()
	new.flags.ignore_permissions = True
	new.insert()
	new.submit()
