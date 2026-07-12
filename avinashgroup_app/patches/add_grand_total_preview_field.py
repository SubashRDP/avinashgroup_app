# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Sales Invoice live total preview.

VAT/excise tax rows are built SERVER-side (salesinvoice_taxes.update_taxes_table
on validate), so while composing an invoice the form's grand_total shows only
the net amount — the real total appears only after Save & Submit. This adds a
virtual field (no DB column, never persisted) right below Total VAT Amount,
filled purely by client JS (public/js/sales_invoice.js) with

    Total Amount = Total Amount Including Excise + Total VAT Amount

which is exactly what grand_total becomes after the server builds the taxes
table. grand_total itself is never touched client-side.
Idempotent (create_custom_fields skips existing)."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Invoice": [
				{
					"fieldname": "custom_expected_grand_total",
					"label": "Total Amount",
					"fieldtype": "Currency",
					# For VIRTUAL fields `options` is NOT a currency source — Frappe
					# safe_evals it as a Python expression to produce the value
					# (base_document.get_valid_dict). Anything else here breaks save.
					"options": "(doc.custom_total_amount_including_excise or 0) + (doc.custom_total_vat_amount or 0)",
					"insert_after": "custom_total_vat_amount",
					"is_virtual": 1,
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
					"report_hide": 1,
					"bold": 1,
					"description": "Total Amount Including Excise + Total VAT Amount. "
					"Live browser-side preview of the grand total the server will "
					"compute on save; not stored in the database.",
				}
			],
		},
		ignore_validate=True,
	)
