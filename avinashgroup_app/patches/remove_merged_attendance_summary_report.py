"""Delete the Report record left behind when the two attendance reports merged.

`Monthly Attendance Summary BS` became the Summary view of Monthly Attendance
BS, and its module was removed — but the Report record stayed on the site, so
opening it from the report list raises ModuleNotFoundError.
"""

import frappe

REPORT = "Monthly Attendance Summary BS"


def execute():
	if frappe.db.exists("Report", REPORT):
		frappe.delete_doc("Report", REPORT, force=True, ignore_permissions=True)
