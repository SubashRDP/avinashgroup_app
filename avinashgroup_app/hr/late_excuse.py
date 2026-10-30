"""Excuse a day's lateness from the Monthly Attendance BS grid.

HR sees the late minutes in the grid, so that is where they decide a day should
not count (the bus strike, the funeral). Ticking the Late Excused cell opens a
small dialog; saving sets Late Excused and its reason on the day's Attendance,
the same fields as on the form. The rules that follow from the tick live with
the Attendance itself (biometric/attendance_override.py): a reason is required,
a day whose salary slip is submitted is refused, and a half day caused only by
lateness goes back to Present. Nothing here repeats them.
"""

import frappe
from frappe import _
from frappe.utils import cint

from avinashgroup_app.hr.punch_correction import CORRECTION_ROLES


@frappe.whitelist()
def set_late_excuse(attendance: str, excused: int, reason: str | None = None) -> dict:
	"""Tick or untick Late Excused on one Attendance and return the day's status."""
	frappe.only_for(CORRECTION_ROLES)
	doc = frappe.get_doc("Attendance", attendance)
	if doc.docstatus == 2:
		frappe.throw(_("Attendance {0} is cancelled.").format(attendance))

	doc.custom_late_excused = cint(excused)
	doc.custom_late_excuse_reason = (reason or "").strip() if doc.custom_late_excused else None
	doc.flags.ignore_permissions = True
	doc.save()
	doc.reload()
	return {"status": doc.status, "late_excused": doc.custom_late_excused}
