"""The retirement cap onto the form, and the women's rebate off its default.

Sites that ran setup_tax_exemptions before 2026-09-29 have the rebate field
defaulting to 10 and no fields for the cap, which lived in code as 5,00,000 and
one third. This brings them to the fields-only version of that patch.

Figures already entered stay as they are — this removes defaults, not data. A
site that relied on the coded cap has no cap until HR ticks the retirement
category and enters it; nothing is ticked for them.
"""

import frappe

from avinashgroup_app.patches.setup_tax_exemptions import add_fields

REBATE_FIELD = "Income Tax Slab-custom_women_rebate_percent"


def execute():
	add_fields()
	# create_custom_fields only updates the keys it is given, so the old "10"
	# survives it; cleared here.
	if frappe.db.exists("Custom Field", REBATE_FIELD):
		frappe.db.set_value("Custom Field", REBATE_FIELD, "default", None)
		frappe.clear_cache(doctype="Income Tax Slab")
