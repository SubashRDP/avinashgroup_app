"""Hide the Approval Hierarchy table on the Memo Log form.

patches/setup_memo_log_approval.py added the engine's "Approval Hierarchy"
table, where a creator can add extra approvers ahead of the rule's approvers.
For memos only the Purchase Order rule decides who approves, so the table is
hidden here. MemoLog.validate also empties it, so an API or import cannot sneak
approvers in.

Approval History and the level/approver fields stay visible, as on Purchase
Order. Only Memo Log is touched.
Landmine: pressing "Setup Workflow" for Memo Log (or re-running
_ensure_custom_fields) un-hides the table again, so run this patch's execute()
again after that.
"""

import frappe

DOCTYPE = "Memo Log"
FIELDS = ("custom_section_approval_hierarchy", "custom_approval_approvers")


def execute():
	for fieldname in FIELDS:
		name = frappe.db.get_value("Custom Field", {"dt": DOCTYPE, "fieldname": fieldname})
		if name:
			frappe.db.set_value("Custom Field", name, "hidden", 1)
	frappe.clear_cache(doctype=DOCTYPE)
