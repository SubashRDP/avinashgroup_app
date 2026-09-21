"""The per-employee inputs NGI's salary formulas read.

The Falgun 2082 sheet does not compute everything from Basic. Four of its columns
are decided per person and looked up from an 'Employee Record' workbook:

    HRA        25% of INITIAL basic, and only for those flagged YES (48 of 92)
    Gas        a flat 1,690, flagged YES (48)
    Education  a flat 2,780, flagged YES (48)
    SSF        31% deducted and 20% added — but 9 people are out of the scheme

Initial Basic is a separate figure from Basic Salary and is what HRA is a
percentage of, so it cannot be derived from the salary structure's base.

These fields are what the Salary Structure formulas read, so they belong on the
Employee, not in the structure.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "custom_payroll_inputs_section",
					"label": "Payroll Inputs",
					"fieldtype": "Section Break",
					"insert_after": "custom_allowance_category",
					"collapsible": 1,
				},
				{
					"fieldname": "custom_initial_basic",
					"label": "Initial Basic",
					"fieldtype": "Currency",
					"insert_after": "custom_payroll_inputs_section",
					"description": "The grade's starting basic. HRA is a percentage of this, not of Basic Salary.",
				},
				{
					"fieldname": "custom_hra_eligible",
					"label": "HRA Eligible",
					"fieldtype": "Check",
					"insert_after": "custom_initial_basic",
				},
				{
					"fieldname": "custom_payroll_inputs_cb",
					"fieldtype": "Column Break",
					"insert_after": "custom_hra_eligible",
				},
				{
					"fieldname": "custom_gas_allowance",
					"label": "Gas Allowance",
					"fieldtype": "Check",
					"insert_after": "custom_payroll_inputs_cb",
				},
				{
					"fieldname": "custom_education_allowance",
					"label": "Education Allowance",
					"fieldtype": "Check",
					"insert_after": "custom_gas_allowance",
				},
				{
					"fieldname": "custom_ssf_applicable",
					"label": "SSF Applicable",
					"fieldtype": "Check",
					"insert_after": "custom_education_allowance",
					"default": "1",
					"description": "Untick for staff outside the scheme — 9 of NGI's 92 in Falgun 2082.",
				},
			]
		},
		update=True,
	)
	# Existing employees predate the field: default them into the scheme.
	frappe.db.sql("update `tabEmployee` set custom_ssf_applicable = 1 where custom_ssf_applicable is null")
