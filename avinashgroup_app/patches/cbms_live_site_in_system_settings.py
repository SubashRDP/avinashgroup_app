"""The IRD (CBMS) live-site switch moves from site_config.json to System Settings.

Only the site whose own name is typed in System Settings > CBMS Live Site
reports to IRD (custom_code/CBMS/utils.is_cbms_live_site). The value is the
site's NAME, not a tick, because a restore carries System Settings across with
the rest of the database: a copy restored under any other name (a demo, a
sandbox) still reads "ng-group.raindropinc.com" and so stays switched off.

The site that was switched on through site_config.json's `cbms_live_site` gets
its name copied into the field here, so it keeps reporting without anyone
having to type it. Every other site is left blank (off).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"System Settings": [
				{
					"fieldname": "custom_cbms_section",
					"label": "IRD (CBMS)",
					"fieldtype": "Section Break",
					"insert_after": "max_report_rows",
					"collapsible": 1,
				},
				{
					"fieldname": "custom_cbms_live_site",
					"label": "CBMS Live Site",
					"fieldtype": "Data",
					"insert_after": "custom_cbms_section",
					"description": (
						"The site name that reports sales to IRD, e.g. ng-group.raindropinc.com. "
						"Only the site with exactly this name creates CBMS Bills and sends them; "
						"a restored copy under any other name stays off. Blank: off."
					),
				},
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="System Settings")

	if frappe.conf.get("cbms_live_site") == frappe.local.site and not frappe.db.get_single_value(
		"System Settings", "custom_cbms_live_site", cache=False
	):
		frappe.db.set_single_value("System Settings", "custom_cbms_live_site", frappe.local.site)
