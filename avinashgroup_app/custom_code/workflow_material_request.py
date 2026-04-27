import frappe
from avinashgroup_app.custom_code.workflow import set_reject_reason as _set_reject_reason


@frappe.whitelist()
def set_reject_reason(doctype, name, reason):
	return _set_reject_reason(doctype, name, reason)
