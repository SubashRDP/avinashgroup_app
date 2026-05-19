import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	custom_fields = {
		"Salary Component": [
			{
				"fieldname": "custom_attendance_rule_section",
				"label": "Attendance-Driven Rule",
				"fieldtype": "Section Break",
				"insert_after": "formula",
				"collapsible": 1,
			},
			{
				"fieldname": "custom_is_attendance_driven",
				"label": "Is Attendance Driven",
				"fieldtype": "Check",
				"insert_after": "custom_attendance_rule_section",
				"default": "0",
				"description": (
					"If checked, this component is auto-calculated from attendance "
					"via the Nepal HRMS engine. Formula and Amount fields will be ignored."
				),
			},
			{
				"fieldname": "custom_condition_type",
				"label": "Condition Type",
				"fieldtype": "Select",
				"insert_after": "custom_is_attendance_driven",
				"options": (
					"\n"
					"Working Hours >= Threshold\n"
					"Status = Present\n"
					"Status = Half Day\n"
					"Worked on Holiday\n"
					"Early Entry Before\n"
					"Late Stay After\n"
					"Late Arrival After"
				),
				"depends_on": "eval:doc.custom_is_attendance_driven",
				"mandatory_depends_on": "eval:doc.custom_is_attendance_driven",
			},
			{
				"fieldname": "custom_threshold_hours",
				"label": "Threshold Hours",
				"fieldtype": "Float",
				"insert_after": "custom_condition_type",
				"depends_on": 'eval:doc.custom_condition_type=="Working Hours >= Threshold"',
				"description": (
					"e.g. 6 → counts a day if working hours ≥ 6. "
					"Half Day counts if hours ≥ threshold/2."
				),
			},
			{
				"fieldname": "custom_attendance_rule_col_break",
				"fieldtype": "Column Break",
				"insert_after": "custom_threshold_hours",
			},
			{
				"fieldname": "custom_time_offset_hours",
				"label": "Time Offset (Hours)",
				"fieldtype": "Float",
				"insert_after": "custom_attendance_rule_col_break",
				"depends_on": (
					'eval:["Early Entry Before","Late Stay After","Late Arrival After"]'
					".includes(doc.custom_condition_type)"
				),
				"description": (
					"Hours from shift start or end. "
					"e.g. 1 → Late Stay counts if out time ≥ shift end + 1h."
				),
			},
			{
				"fieldname": "custom_unit",
				"label": "Unit",
				"fieldtype": "Select",
				"insert_after": "custom_time_offset_hours",
				"options": "Per Day\nPer Hour\nFlat per Period",
				"default": "Per Day",
				"depends_on": "eval:doc.custom_is_attendance_driven",
			},
			{
				"fieldname": "custom_default_rate",
				"label": "Default Rate",
				"fieldtype": "Currency",
				"insert_after": "custom_unit",
				"depends_on": "eval:doc.custom_is_attendance_driven",
				"description": (
					"Used when an employee has no rate override "
					"in their Attendance Allowances table."
				),
			},
			{
				"fieldname": "custom_summary_group",
				"label": "Summary Group",
				"fieldtype": "Data",
				"insert_after": "custom_default_rate",
				"depends_on": "eval:doc.custom_is_attendance_driven",
				"description": (
					"Components sharing this label are summed into a single column "
					"in Monthly Attendance Summary BS. Leave blank to give this "
					"component its own column. e.g. 'Meal' on Food + Late Food, "
					"'Tea & Conveyance' on Tea + Commute."
				),
			},
		],
		"Attendance": [
			{
				"fieldname": "custom_worked_on_holiday",
				"label": "Worked on Holiday",
				"fieldtype": "Check",
				"insert_after": "status",
				"read_only": 1,
				"default": "0",
				"description": (
					"Set automatically: 1 if attendance_date matches a Holiday in the "
					"employee's Holiday List. Used by the Nepal HRMS attendance "
					"allowance engine."
				),
			},
		],
		"Employee": [
			{
				"fieldname": "custom_nepal_hrms_section",
				"label": "Nepal HRMS",
				"fieldtype": "Section Break",
				"insert_after": "salary_mode",
				"collapsible": 1,
			},
			{
				"fieldname": "custom_ot_eligibility",
				"label": "OT Eligible",
				"fieldtype": "Check",
				"insert_after": "custom_nepal_hrms_section",
				"default": "0",
				"description": (
					"If unchecked, Late Stay / Early Entry components "
					"are skipped for this employee."
				),
			},
			{
				"fieldname": "custom_attendance_allowances_section",
				"label": "Attendance Allowances",
				"fieldtype": "Section Break",
				"insert_after": "custom_ot_eligibility",
			},
			{
				"fieldname": "custom_attendance_allowances",
				"label": "Attendance Allowances",
				"fieldtype": "Table",
				"insert_after": "custom_attendance_allowances_section",
				"options": "Employee Attendance Allowance",
				"description": (
					"Per-employee rate overrides for attendance-driven Salary Components. "
					"Set eligible=0 to opt this employee out of a component."
				),
			},
		],
		"Additional Salary": [
			{
				"fieldname": "custom_source",
				"label": "Source",
				"fieldtype": "Data",
				"insert_after": "amended_from",
				"read_only": 1,
				"description": (
					"Tag set by automation (e.g. Nepal HRMS Attendance Allowance) "
					"so generated drafts can be safely re-created without touching manual entries."
				),
			},
		],
	}

	create_custom_fields(custom_fields, update=True)

	# Drop deprecated fields from earlier iterations of this patch.
	# Final approach: read-only custom_worked_on_holiday checkbox on Attendance,
	# auto-populated from the employee's Holiday List by a doc-event hook.
	for dt, fieldname in (
		("Holiday", "custom_holiday_type"),
		("Attendance", "custom_holiday_type"),
		("Salary Component", "custom_holiday_type"),
	):
		stale = frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname})
		if stale:
			frappe.delete_doc("Custom Field", stale, force=True, ignore_permissions=True)

	for dt in ("Salary Component", "Holiday", "Attendance", "Employee", "Additional Salary"):
		frappe.clear_cache(doctype=dt)

	# Backfill custom_worked_on_holiday on existing Attendance rows.
	from avinashgroup_app.payroll.attendance_allowance import recompute_holiday_flags

	recompute_holiday_flags()
