"""Superseded: per-person pay inputs no longer live on the Employee.

This patch used to create the Dearness, Other, Fuel, Fixed and Maintenance
Allowance custom fields on Employee from `payroll.onboarding.EMPLOYEE_FIELDS`.
Pay later moved to the Salary Structure Assignment (commit 77b9500c), which
removed `EMPLOYEE_FIELDS`. The later patch `move_pay_to_salary_assignment` also
deletes these Employee fields again, after copying any values it finds, and
skips a column that does not exist.

The import of a name that no longer exists broke `bench migrate` on every site
that had not run this patch yet. It is kept as a no-op so that its line in
patches.txt, and the Patch Log rows of sites that already ran it, stay valid.
"""


def execute():
	pass
