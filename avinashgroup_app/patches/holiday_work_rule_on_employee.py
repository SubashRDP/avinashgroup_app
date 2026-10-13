"""Overtime or replacement leave is now ticked on the Employee, not via a category.

Policy 2.2 (as corrected 2026-09-16) and 2.5: for a holiday or Saturday worked,
a person is either paid overtime or given a replacement leave day — never both.
That used to be decided by the Employee Category the person was linked to, with
`custom_ot_eligibility` fetched read-only from it. HR asked for the two answers
on the Employee itself, so:

  * `custom_ot_eligibility` ("Overtime Eligible") stops fetching from the
    category and becomes an ordinary tick. Every reader (allowance engine,
    reports) already used this field, so its name is kept.
  * `custom_compensatory_leave` ("Replacement Leave for Holiday Work") is new.

Each employee's current answer is copied from their category, so nobody's pay
or leave changes on the day this runs. `hr.overtime.validate_employee_holiday_rule`
keeps the either/or rule.

The Employee Category link was kept as a label at first, then removed together
with the doctype (drop_employee_category). On a site that never had the
category there is nothing to copy, so that step is skipped.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "custom_ot_eligibility",
					"label": "Overtime Eligible",
					"fieldtype": "Check",
					"insert_after": "custom_nepal_hrms_section",
					"default": "0",
					"fetch_from": "",
					"fetch_if_empty": 0,
					"read_only": 0,
					"in_standard_filter": 1,
					"description": (
						"Paid overtime (and overtime meals) for a holiday or Saturday worked, and for "
						"authorised overtime on a working day. Do not tick together with Replacement Leave."
					),
				},
				{
					"fieldname": "custom_compensatory_leave",
					"label": "Replacement Leave for Holiday Work",
					"fieldtype": "Check",
					"insert_after": "custom_ot_eligibility",
					"default": "0",
					"in_standard_filter": 1,
					"description": (
						"A holiday or Saturday worked earns a replacement (compensatory) leave day instead "
						"of overtime pay — officer and admin level. Do not tick together with Overtime Eligible."
					),
				},
				{
					"fieldname": "custom_late_fine_exempt",
					"label": "Late Fine Exempt",
					"fieldtype": "Check",
					"insert_after": "custom_compensatory_leave",
					"description": "Late time is still recorded, but not fined — NGI's managers",
				},
			]
		},
		update=True,
	)

	# Copy each person's current answer from their category, so nothing changes.
	if not (
		frappe.db.table_exists("Employee Category")
		and frappe.db.has_column("Employee", "custom_employee_category")
	):
		frappe.clear_cache(doctype="Employee")
		return
	frappe.db.sql(
		"""update `tabEmployee` e
		join `tabEmployee Category` c on c.name = e.custom_employee_category
		set e.custom_ot_eligibility = ifnull(c.ot_eligible, 0),
			e.custom_compensatory_leave = ifnull(c.compensatory_leave, 0)"""
	)
	frappe.clear_cache(doctype="Employee")
