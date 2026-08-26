"""Remove the standalone Monthly Attendance Summary BS report.

Its content now lives behind the View filter on Monthly Attendance BS — one
report, two shapes of the same month. The module is gone from the app, so the
Report record left on a site would point at code that no longer exists and
fail on open.

Worth removing rather than leaving disabled: the report never worked from the
desk anyway. Its client script set `bs_year` while its Python required
`fiscal_year`, so opening it always threw "Select Fiscal Year + BS Month or
From Date + To Date to run the report."
"""

import frappe


def execute():
	name = "Monthly Attendance Summary BS"
	if not frappe.db.exists("Report", name):
		return

	# Prepared Reports link back by name; clear them so the delete cannot fail
	# on a link check.
	frappe.db.delete("Prepared Report", {"report_name": name})
	frappe.delete_doc("Report", name, force=True, ignore_permissions=True, delete_permanently=True)
