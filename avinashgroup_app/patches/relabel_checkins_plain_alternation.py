"""Relabel every punch IN, OUT, IN, ... by its order in the day.

The day's last punch used to be forced to OUT, so a day with a missing punch
read IN, OUT, OUT and hid the gap. Labels now alternate plainly
(biometric.attendance_sync.desired_log_type) and an odd day ends on IN. Hours
do not move: every Shift Type uses "Alternating entries as IN and OUT", where
HRMS takes the first punch as in and the last as out whatever the labels say.
"""

import frappe


def execute():
	frappe.db.sql(
		"""
		UPDATE `tabEmployee Checkin` c
		JOIN (
			SELECT name,
				IF(MOD(ROW_NUMBER() OVER (PARTITION BY employee, DATE(`time`) ORDER BY `time`, name), 2) = 1, 'IN', 'OUT') AS label
			FROM `tabEmployee Checkin`
		) o ON o.name = c.name
		SET c.log_type = o.label
		WHERE IFNULL(c.log_type, '') != o.label
		"""
	)
