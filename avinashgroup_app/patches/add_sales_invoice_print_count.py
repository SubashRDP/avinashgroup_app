# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""IRD copy labeling: Sales Invoice keeps a count of how many times it has been
printed / downloaded as PDF. The print format uses it to title the output
Tax Invoice (1st) / Copy of Original (2nd) / Copy of Original 2 (3rd), etc.
Idempotent (create_custom_fields skips existing)."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Invoice": [
				{
					"fieldname": "custom_print_count",
					"label": "Print Count",
					"fieldtype": "Int",
					"insert_after": "select_print_heading",
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
					"allow_on_submit": 1,
					"default": "0",
					"description": "Times this invoice was printed or downloaded as PDF. "
					"Drives the IRD copy title on the print format.",
				}
			],
		},
		ignore_validate=True,
	)
