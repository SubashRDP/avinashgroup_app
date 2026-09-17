"""Holiday Duty Sheet: install it with the audit fields Dynamic Approval keys on.

Dynamic Approval picks a document's approval section from criteria, and on this
site those criteria are written against `custom_created_by` — an audit field that
exists only on doctypes in the audit list. Without it, no approval rule could
ever match a Holiday Duty Sheet.
"""

import frappe

from avinashgroup_app.utils.audit_file_manager import AuditFieldsManager


def execute():
	frappe.reload_doc("avinash_group_app", "doctype", "holiday_duty_sheet_employee")
	frappe.reload_doc("avinash_group_app", "doctype", "holiday_duty_sheet")
	AuditFieldsManager(["Holiday Duty Sheet"]).create_fields()
