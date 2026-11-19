"""Put Memo Log under the Dynamic Approval workflow.

Normally this is the "Setup Workflow" button on a Dynamic Approval Setting.
This patch runs the same steps for Memo Log on every site during migrate, so
the workflow exists before anyone creates a Memo Log setting. Pressing the
button later is harmless (it is idempotent), but it un-hides the Approval
Hierarchy table; the Memo Log form hides it again in its own JS.

It adds the hidden level/approver fields, the Approval Hierarchy and History
tables, and the workflow: Draft → Submit for Approval → Pending Approval →
Approve (each level) → Approved. Fieldnames: custom_approval_approvers /
custom_current_approval_level (use the same on the Memo Log settings).

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
