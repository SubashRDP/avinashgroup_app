"""Carry Biometric Device de-duplication windows over from minutes to seconds.

`duplicate_threshold_minutes` (Float) became `duplicate_threshold_seconds`
(Int). Frappe adds the new column and leaves the old one in place, so without
this a device configured with `5` (five minutes) would silently start
de-duplicating over five SECONDS — collapsing far fewer repeat reads than the
operator asked for, and only visible as duplicate punches nobody ordered.

Renaming the column is not enough either: the stored number means something
different in the new unit, so each value is multiplied by 60.

Zero is the "already converted" sentinel rather than NULL: Frappe declares
Float columns NOT NULL, so the old column cannot be nulled out. A device left
at 0 minutes means the same thing in either unit (exact-timestamp matching
only), which makes re-running this harmless.
"""

import frappe


def execute():
	if not frappe.db.table_exists("Biometric Device"):
		return
	if not frappe.db.has_column("Biometric Device", "duplicate_threshold_minutes"):
		return
	if not frappe.db.has_column("Biometric Device", "duplicate_threshold_seconds"):
		return

	rows = frappe.db.sql(
		"""
		SELECT name, duplicate_threshold_minutes AS minutes
		FROM `tabBiometric Device`
		WHERE duplicate_threshold_minutes > 0
		""",
		as_dict=True,
	)
	for row in rows:
		frappe.db.set_value(
			"Biometric Device",
			row.name,
			"duplicate_threshold_seconds",
			int(round((row.minutes or 0) * 60)),
			update_modified=False,
		)

	if rows:
		frappe.db.sql(
			"UPDATE `tabBiometric Device` SET duplicate_threshold_minutes = 0"
			" WHERE duplicate_threshold_minutes > 0"
		)
