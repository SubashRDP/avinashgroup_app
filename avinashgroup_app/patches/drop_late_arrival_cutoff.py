"""Remove Shift Type.custom_late_arrival_cutoff_time — the absolute lateness cutoff.

A late arrival is a half day by one rule only: in after the shift's start plus
`custom_half_day_if_late_by_hours` (biometric/attendance_override.py). The older
clock-time cutoff ran beside it, and the Shift Type form filled a blank one with
the time of the save: on the first run of test attendance that half-dayed 2,423
of 2,808 days, and demo shifts still carry such values. A guard
(hr/shift_type_guard.py) and a "cutoff at or before shift start" check kept it in
check; the user chose to remove the field instead (2026-10-13).

Only the field definition goes, as in drop_orphan_allowance_category_field: the
column and whatever stray times it holds are left, and nothing reads them. Does
nothing where the field is already gone. Safe to run again.

Older patches (add_site_only_hr_fields, setup_late_half_day_rule) no longer
create or touch the field, and this one is listed after both in patches.txt.
"""

import frappe

FIELD = {"dt": "Shift Type", "fieldname": "custom_late_arrival_cutoff_time"}


def execute():
	for name in frappe.get_all("Custom Field", filters=FIELD, pluck="name"):
		frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
	frappe.clear_cache(doctype="Shift Type")
