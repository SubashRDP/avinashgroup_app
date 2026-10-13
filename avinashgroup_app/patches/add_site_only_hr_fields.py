"""Create the HR custom fields that existed only as site data, never in the repo.

Found in the HR/payroll audit of 2026-09-27: these fields were made in the desk
on avinas1 / nepalgas and the code came to depend on them, but no patch or
fixture creates them. On ng-group or any fresh site:

  Holiday List.custom_company     hr/year_setup.ensure_holiday_list writes it and
                                  hr/holiday_lists.py orders by it — setup_year
                                  fails before the first holiday list exists.
  Attendance.custom_late_entry …  biometric/attendance_override.py writes all four
                                  on every Attendance validate — every auto
                                  attendance and every manual save would fail.

(It also used to create Shift Type.custom_late_arrival_cutoff_time. That rule was
removed on 2026-10-13 — see drop_late_arrival_cutoff — so a new site never gets it.)

Definitions are copied from avinas1 as they stood that day, so on the sites that
already have them this is a no-op (`update=True` rewrites identical values).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Holiday List": [
				{
					"fieldname": "custom_company",
					"label": "Company",
					"fieldtype": "Link",
					"options": "Company",
					"reqd": 1,
					"in_standard_filter": 1,
				}
			],
			"Attendance": [
				{
					"fieldname": "custom_shift_deviation_section",
					"label": "Shift Deviation",
					"fieldtype": "Section Break",
					"insert_after": "modify_half_day_status",
				},
				{
					"fieldname": "custom_late_entry",
					"label": "Late Entry",
					"fieldtype": "Duration",
					"read_only": 1,
					"insert_after": "custom_shift_deviation_section",
					"description": "How late the employee punched in after shift start",
				},
				{
					"fieldname": "custom_early_entry",
					"label": "Early Entry",
					"fieldtype": "Duration",
					"read_only": 1,
					"insert_after": "custom_late_entry",
					"description": "How early the employee punched in before shift start",
				},
				{
					"fieldname": "custom_col_break_deviation",
					"fieldtype": "Column Break",
					"insert_after": "custom_early_entry",
				},
				{
					"fieldname": "custom_early_exit",
					"label": "Early Exit",
					"fieldtype": "Duration",
					"read_only": 1,
					"insert_after": "custom_col_break_deviation",
					"description": "How early the employee punched out before shift end",
				},
				{
					"fieldname": "custom_late_exit",
					"label": "Late Exit",
					"fieldtype": "Duration",
					"read_only": 1,
					"insert_after": "custom_early_exit",
					"description": "How late the employee punched out after shift end",
				},
			],
		},
		update=True,
	)
	for dt in ("Holiday List", "Attendance"):
		frappe.clear_cache(doctype=dt)
