"""Put Memo Log under the Dynamic Approval workflow.

Normally this is the "Setup Workflow" button on a Dynamic Approval Setting.
Memo Log has no setting of its own: it borrows the Purchase Order rules
(RULES_FROM_DOCTYPE in custom_code/dynamic_approval.py). Nobody would press that
button for it, so this patch runs the same setup steps for Memo Log.

It adds the hidden level/approver fields, the Approval Hierarchy and History
tables, and the workflow: Draft → Submit for Approval → Pending Approval →
Approve (each level) → Approved. The fieldnames match the Purchase Order
settings (custom_approval_approvers / custom_current_approval_level).

It is idempotent, and safe to run again.
"""

import frappe

from avinashgroup_app.custom_code.dynamic_approval import (
	_create_or_update_workflow,
	_ensure_custom_fields,
	_ensure_email_templates,
	_ensure_history_doctype,
)

DOCTYPE = "Memo Log"
# Same values as every Purchase Order Dynamic Approval Setting on the sites.
TABLE_FIELD = "custom_approval_approvers"
LEVEL_FIELD = "custom_current_approval_level"


def execute():
	frappe.reload_doc("avinash_group_app", "doctype", "memo_log")
	_ensure_history_doctype()
	_ensure_email_templates()
	_ensure_custom_fields(DOCTYPE, LEVEL_FIELD, TABLE_FIELD)
	_create_or_update_workflow(DOCTYPE, LEVEL_FIELD)
	frappe.clear_cache(doctype=DOCTYPE)
