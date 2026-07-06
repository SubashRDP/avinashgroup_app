import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Add a required Company link to Shift Type.

	Shift Type is listed in the naming override's NAMING_CONFIG
	(custom_code/Override/naming_series.py), whose before_insert guard
	requires a company abbreviation from `company` or `custom_company`.
	Shift Type has neither field in stock HRMS, so every Shift Type insert
	failed with "Company abbreviation is required for Shift Type" — which is
	why the site could never create a shift (and therefore never marked
	auto attendance). This field completes the naming contract.
	"""
	create_custom_fields(
		{
			"Shift Type": [
				{
					"fieldname": "custom_company",
					"label": "Company",
					"fieldtype": "Link",
					"options": "Company",
					"reqd": 1,
					"insert_after": "color",
					"in_list_view": 1,
					"in_standard_filter": 1,
				}
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Shift Type")
