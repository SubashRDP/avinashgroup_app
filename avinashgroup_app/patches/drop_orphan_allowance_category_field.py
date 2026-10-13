"""Remove Employee.custom_allowance_category once its doctype is gone.

setup_allowance_kinds always deleted the Allowance Category doctype, but deleted
the Employee field that links to it only inside move_categories, which is
skipped when the old per-employee table is already gone and returns early when
the category-rate table is missing. A site that took either path kept the field
pointing at a doctype that no longer exists, and every Employee form failed to
open: "Field custom_allowance_category is referring to non-existing doctype
Allowance Category" (frappe/desk/form/meta.py, add_search_fields).

Only the field definition goes; the column is left, and it holds no data on any
site this was checked on. Does nothing where the doctype still exists or the
field is already gone. Safe to run again.
"""

import frappe

FIELD = {"dt": "Employee", "fieldname": "custom_allowance_category"}


def execute():
	if frappe.db.exists("DocType", "Allowance Category"):
		return
	for name in frappe.get_all("Custom Field", filters=FIELD, pluck="name"):
		frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
	frappe.clear_cache(doctype="Employee")
