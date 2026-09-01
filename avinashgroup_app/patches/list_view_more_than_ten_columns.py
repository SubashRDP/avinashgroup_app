# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Let a list view show more than ten columns.

`List View Settings.total_fields` ("Maximum Number of Fields") is a Select
whose options stop at 10, so the column picker offers nothing beyond that --
and the ceiling is enforced server-side too, not just in the dialog:

    Maximum Number of Fields cannot be "15".
    It should be one of "", "4", "5", "6", "7", "8", "9", "10"

Frappe v16 drops the field entirely and lets the list scroll instead. Short of
that, extending the Select's options is enough: the render side already honours
whatever the value says --

    this.columns = this.columns.slice(0, this.list_view_settings.total_fields || total_fields)

-- so nothing in list_view.js needs patching, and the dialog builds its picker
from the same value.

A Property Setter is the supported way to change a Select's options: it leaves
frappe's own JSON untouched, so `bench update` cannot revert it.

Idempotent -- reruns just rewrite the same value."""

import frappe

DOCTYPE = "List View Settings"
FIELD = "total_fields"

# Stock is "" plus 4..10. Keep the blank (it means "use the screen-size
# default") and the existing rungs so no saved setting becomes invalid, then
# carry on to 20.
OPTIONS = "\n".join([""] + [str(n) for n in range(4, 21)])


def execute():
	meta_field = frappe.get_meta(DOCTYPE).get_field(FIELD)
	if not meta_field:
		# Field is gone -- the site is on a version that removed it (v16+),
		# where the cap does not exist in the first place.
		return

	frappe.make_property_setter(
		{
			"doctype": DOCTYPE,
			"fieldname": FIELD,
			"property": "options",
			"value": OPTIONS,
			"property_type": "Text",
		},
		is_system_generated=False,
	)
	frappe.clear_cache(doctype=DOCTYPE)
