"""Overtime Sheet: install it with the audit fields Dynamic Approval keys on.

Dynamic Approval picks a document's approval section from criteria, and on this
site those criteria are written against `custom_created_by` — an audit field that
exists only on doctypes in the audit list. Without it no approval rule could ever
match an Overtime Sheet.

Also removes Holiday Duty Sheet, the holiday-only first cut this replaced, from
any site that installed it.
"""

import frappe

from avinashgroup_app.utils.audit_file_manager import AuditFieldsManager


def execute():
	for doctype in ("Holiday Duty Sheet", "Holiday Duty Sheet Employee"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
	for field in frappe.get_all("Custom Field", {"dt": "Holiday Duty Sheet"}, pluck="name"):
		frappe.delete_doc("Custom Field", field, force=True, ignore_permissions=True)

	frappe.reload_doc("avinash_group_app", "doctype", "overtime_sheet_employee")
	frappe.reload_doc("avinash_group_app", "doctype", "overtime_sheet")
	AuditFieldsManager(["Overtime Sheet"]).create_fields()
