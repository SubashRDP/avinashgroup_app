"""Retired: Employee Category is gone (2026-10-13, see drop_employee_category).

This used to create the Employee Category doctype, the `custom_employee_category`
link on Employee, and make `custom_ot_eligibility` fetch from it. Overtime vs
replacement leave is now two ticks on the Employee (holiday_work_rule_on_employee)
and the category itself was removed, so a new site has nothing to set up here.
Kept as a no-op so patches.txt and the Patch Log stay consistent.
"""


def execute():
	pass
