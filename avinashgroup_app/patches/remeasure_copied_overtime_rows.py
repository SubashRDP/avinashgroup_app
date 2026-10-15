"""Re-measure overtime rows that carry another day's measurement.

Duplicating an Overtime Sheet copied each row's worked hours, attendance and
note, and the automatic measuring skipped such rows as already measured. Ashish
Lama Tamang's OTS-2026-00005 to 00009, copies of 00004, each said 9 hours from
4 Sep's attendance: 54 hours paid in Bhadra for days he worked 0 to 8.6. Those
fields are no-copy now and hr/overtime_settlement re-measures a mismatched row;
this does it for the submitted sheets already there.
"""

import frappe

from avinashgroup_app.hr.overtime_settlement import measure_unmeasured


def execute():
	for name in frappe.get_all("Overtime Sheet", filters={"docstatus": 1}, pluck="name"):
		measure_unmeasured(frappe.get_doc("Overtime Sheet", name))
