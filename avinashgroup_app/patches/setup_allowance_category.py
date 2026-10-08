"""Allowance Category: a group's rate for an attendance-driven allowance.

NGI's Falgun sheet pays tea & conveyance at 235 a day to one group of staff and
40 to another, decided by a category on the employee — plant and office each
contain both, so it is not a department rule. Typing the rate on all 92 employees
would make "235 becomes 250" a 51-row edit.

Adds `Employee.custom_allowance_category`; the rate itself lives on the category.

Superseded on 2026-10-08 by setup_allowance_kinds: rates are per company on the
Salary Component's Accounts rows and per person on the employee's Allowance
Exceptions table, and the Allowance Category doctypes were removed from the app. Kept as a no-op so a
fresh site can run the patch list in order.
"""


def execute():
	pass
