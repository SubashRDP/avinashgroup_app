"""Remove Employee Category: the Employee link, the doctype and its bulk tool.

Since holiday_work_rule_on_employee (2026-10-13) overtime vs replacement leave
is two ticks on the Employee — `custom_ot_eligibility` and
`custom_compensatory_leave` — and the category decided nothing any more. HR
asked for it to go from the Employee form.

  * Custom Field `Employee-custom_employee_category` is deleted. The column is
    left in tabEmployee, as with drop_orphan_allowance_category_field.
  * DocType `Employee Category Tool` (single, bulk-assigned the category) and
    DocType `Employee Category` are deleted, and its table with the two
    records (Operation, Officer & Admin) dropped. Their folders
    are gone from the app, so a migrate would not bring them back.
  * The hidden `employee_category` column on Overtime Sheet Employee was taken
    out of the child doctype JSON; old values stay in the table, unread.

The field goes first: deleting the doctype while a Link still points to it
leaves the Employee form unable to open ("referring to non-existing doctype").
Does nothing where everything is already gone. Safe to run again.
"""

import frappe

FIELD = {"dt": "Employee", "fieldname": "custom_employee_category"}


def execute():
	for name in frappe.get_all("Custom Field", filters=FIELD, pluck="name"):
		frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)

	for doctype in ("Employee Category Tool", "Employee Category"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
		# delete_doc leaves a standard doctype's table behind during migrate.
		frappe.db.sql_ddl(f"drop table if exists `tab{doctype}`")

	frappe.clear_cache(doctype="Employee")
