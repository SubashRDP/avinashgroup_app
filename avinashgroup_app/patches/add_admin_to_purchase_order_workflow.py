import frappe


def execute():
    workflow_name = "Purchase Order Workflow"

    if not frappe.db.exists("Workflow", workflow_name):
        return

    if not frappe.db.exists("Role", "Administrator"):
        return

    workflow = frappe.get_doc("Workflow", workflow_name)

    existing = set()
    for t in workflow.transitions:
        existing.add(
            (
                t.state,
                t.action,
                t.next_state,
                t.allowed,
                t.condition or "",
                int(t.allow_self_approval or 0),
            )
        )

    new_rows = 0
    for t in list(workflow.transitions):
        if t.allowed == "Administrator":
            continue

        admin_key = (
            t.state,
            t.action,
            t.next_state,
            "Administrator",
            t.condition or "",
            int(t.allow_self_approval or 0),
        )
        if admin_key in existing:
            continue

        workflow.append(
            "transitions",
            {
                "state": t.state,
                "action": t.action,
                "next_state": t.next_state,
                "allowed": "Administrator",
                "condition": t.condition,
                "allow_self_approval": t.allow_self_approval,
            },
        )
        existing.add(admin_key)
        new_rows += 1

    if new_rows:
        workflow.save(ignore_permissions=True)
