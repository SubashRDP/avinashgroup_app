"""Widen every Shift Type's punch window to 3 h before start / 4 h after end.

Shifts were built with 2 h / 2 h. Anyone who checked out more than 2 h after
shift end (overtime, common at every company) had the OUT punch ignored by
HRMS, so the day kept only its IN punch, 0 hours worked, and was marked Absent:
200 worked days on avinas1 in Bhadra 2083 alone. Values and reasoning:
hr/year_setup.py CHECK_IN_BEFORE_START_MINUTES / CHECK_OUT_AFTER_END_MINUTES.

Only widens, never narrows: a shift someone deliberately set wider is left alone.
Days already marked are re-marked with Attendance Fix; this patch changes
configuration only.
"""

import frappe

from avinashgroup_app.hr.year_setup import CHECK_IN_BEFORE_START_MINUTES, CHECK_OUT_AFTER_END_MINUTES


def execute():
	for st in frappe.get_all(
		"Shift Type",
		fields=["name", "begin_check_in_before_shift_start_time", "allow_check_out_after_shift_end_time"],
	):
		values = {}
		if (st.begin_check_in_before_shift_start_time or 0) < CHECK_IN_BEFORE_START_MINUTES:
			values["begin_check_in_before_shift_start_time"] = CHECK_IN_BEFORE_START_MINUTES
		if (st.allow_check_out_after_shift_end_time or 0) < CHECK_OUT_AFTER_END_MINUTES:
			values["allow_check_out_after_shift_end_time"] = CHECK_OUT_AFTER_END_MINUTES
		if values:
			frappe.db.set_value("Shift Type", st.name, values, update_modified=False)
