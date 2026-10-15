"""Re-measure overtime exactly, to the second.

Overtime hours were rounded to the nearest half hour (7:54:38 paid as 8,
7:19:21 as 7.5). The rule is now the exact time worked (user, 2026-10-15:
"we don't go up or down"), so every measured Overtime row of a submitted sheet
is measured again. A day inside a submitted salary slip is left as it was paid.
"""

import frappe

from avinashgroup_app.hr.overtime import ENTITLEMENT_OVERTIME
from avinashgroup_app.hr.overtime_settlement import measure_row


def execute():
	rows = frappe.db.sql(
		"""
		SELECT r.name, r.parent, r.employee, r.work_type, r.entitlement, s.work_date
		FROM `tabOvertime Sheet Employee` r
		JOIN `tabOvertime Sheet` s ON s.name = r.parent
		WHERE s.docstatus = 1 AND r.entitlement = %s
		  AND NOT EXISTS (
			SELECT 1 FROM `tabSalary Slip` p
			WHERE p.employee = r.employee AND p.docstatus = 1
			  AND s.work_date BETWEEN p.start_date AND p.end_date)
		""",
		ENTITLEMENT_OVERTIME,
		as_dict=True,
	)
	sheets = set()
	for r in rows:
		measured = measure_row(r.employee, r.work_date, r.work_type, r.entitlement)
		frappe.db.set_value(
			"Overtime Sheet Employee",
			r.name,
			{"worked_hours": measured["hours"], "attendance": measured["attendance"], "settlement_note": measured["note"]},
			update_modified=False,
		)
		sheets.add(r.parent)
	for sheet in sheets:
		total = frappe.db.sql(
			"select sum(worked_hours) from `tabOvertime Sheet Employee` where parent = %s", sheet
		)[0][0]
		frappe.db.set_value("Overtime Sheet", sheet, "total_worked_hours", total or 0, update_modified=False)
