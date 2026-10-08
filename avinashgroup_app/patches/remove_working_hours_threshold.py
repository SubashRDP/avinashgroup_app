"""Take "Working Hours >= Threshold" and its Threshold Hours field off Salary Component.

The condition was offered from the first version of the allowance engine but
never implemented: `evaluate_rule` has no branch for it, so a component set to
it paid nothing every day, whatever was typed in Threshold Hours. Tea uses
Status = Present and Meal uses Meal Entitlement (which has its own hour fields),
so nothing needs it. Removed on 2026-10-08 so nobody picks it by mistake.

A site where some component already uses the condition is left alone and
reported, for someone to move that component to a working condition first.
"""

import frappe

CONDITION = "Working Hours >= Threshold"


def execute():
	in_use = frappe.get_all("Salary Component", filters={"custom_condition_type": CONDITION}, pluck="name")
	if in_use:
		print(f"{CONDITION!r} kept: still used by {', '.join(in_use)}")
		return

	field = frappe.db.get_value(
		"Custom Field", {"dt": "Salary Component", "fieldname": "custom_condition_type"}, "name"
	)
	if field:
		options = (frappe.db.get_value("Custom Field", field, "options") or "").split("\n")
		if CONDITION in options:
			options.remove(CONDITION)
			frappe.db.set_value("Custom Field", field, "options", "\n".join(options))

	# The column break after it hangs off the field being removed.
	frappe.db.set_value(
		"Custom Field",
		{"dt": "Salary Component", "fieldname": "custom_attendance_rule_col_break"},
		"insert_after",
		"custom_condition_type",
	)

	threshold = frappe.db.exists("Custom Field", {"dt": "Salary Component", "fieldname": "custom_threshold_hours"})
	if threshold:
		frappe.delete_doc("Custom Field", threshold, force=True, ignore_permissions=True)

	frappe.clear_cache(doctype="Salary Component")
