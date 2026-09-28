"""A late half day is "paid, but half": HRMS's half-absent, not a leave.

Policy 1.2: more than 2 hours late is a half day. The late rule
(biometric/attendance_override.py) used to put a leave type ticked Is Leave
Without Pay on the row ("Leave Without Pay", briefly "Late Half Day") so payroll
would cut the half. The client's point: nobody took leave. HRMS has the right
tool already: Half Day with Half Day Status "Absent" and no leave type is
counted as half a day absent by the salary slip (get_half_absent_days), and the
BS slip subtracts absent days the same way. Pay is identical.

Existing late half days are switched: Half Day rows carrying a Leave Without
Pay type, no Leave Application, late beyond their shift's limit. Real unpaid
leave (with a Leave Application) is untouched. The short-lived "Late Half Day"
leave type and its Shift Type field are removed.
"""

import frappe

OLD_TYPE = "Late Half Day"


def execute():
	lwp = frappe.get_all("Leave Type", filters={"is_lwp": 1}, pluck="name")
	if lwp:
		frappe.db.sql(
			"""update `tabAttendance` a join `tabShift Type` st on st.name = a.shift
			set a.leave_type = null, a.half_day_status = 'Absent'
			where a.status = 'Half Day' and a.leave_type in %(lwp)s
			  and ifnull(a.leave_application, '') = ''
			  and st.custom_half_day_if_late_by_hours > 0
			  and ifnull(a.custom_late_entry, 0) > st.custom_half_day_if_late_by_hours * 3600""",
			{"lwp": lwp},
		)

	if frappe.db.exists("Custom Field", "Shift Type-custom_late_half_day_leave_type"):
		frappe.delete_doc("Custom Field", "Shift Type-custom_late_half_day_leave_type", force=True)
		frappe.clear_cache(doctype="Shift Type")

	if frappe.db.exists("Leave Type", OLD_TYPE) and not any(
		frappe.db.exists(dt, {"leave_type": OLD_TYPE})
		for dt in ("Attendance", "Leave Application", "Leave Allocation", "Leave Ledger Entry")
	):
		frappe.delete_doc("Leave Type", OLD_TYPE, force=True, ignore_permissions=True)
