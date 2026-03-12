import frappe


def execute():
    workflow_name = "Purchase Order Workflow"

    if not frappe.db.exists("Workflow", workflow_name):
        return

    workflow = frappe.get_doc("Workflow", workflow_name)

    updated = 0
    for t in workflow.transitions:
        if t.allowed == "Administrator" and t.condition:
            t.condition = None
            updated += 1

    if updated:
        workflow.save(ignore_permissions=True)
