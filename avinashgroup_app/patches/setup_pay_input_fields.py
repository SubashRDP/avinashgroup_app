"""The per-person pay inputs that were only ever created by hand.

Dearness, other, fuel, fixed and maintenance allowances are read by the salary
structures' formulas, but four of them were made on the working site with an
ad-hoc script and never as a patch. A fresh site therefore had no column for
them, and importing a company's salary sheet failed with
`Unknown column 'custom_dearness_allowance'`.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from avinashgroup_app.payroll.onboarding import EMPLOYEE_FIELDS


def execute():
	create_custom_fields({"Employee": EMPLOYEE_FIELDS}, update=True)
	frappe.clear_cache(doctype="Employee")
