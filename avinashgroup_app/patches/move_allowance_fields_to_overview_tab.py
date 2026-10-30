"""Put the Nepal HRMS fields on Salary Component onto its first tab (Overview).

They hung off `formula`, so Is Allowance, Allowance Kind, Pay on Holiday, the
attendance rule and the festival settings sat at the bottom of the Condition &
Formula tab, below the formula box, and HR setting up a component did not find
them. Moved on 2026-10-29 to sit on Overview after the standard ticks
(`disabled`) and before Accounts, open rather than collapsed.

Only the Allowance section moves: every other custom field on the form hangs
off it in a chain, so the whole block follows.
"""

import frappe


def execute():
	name = frappe.db.get_value(
		"Custom Field", {"dt": "Salary Component", "fieldname": "custom_allowance_section"}, "name"
	)
	if not name:
		return
	frappe.db.set_value("Custom Field", name, {"insert_after": "disabled", "collapsible": 0})
	frappe.clear_cache(doctype="Salary Component")
