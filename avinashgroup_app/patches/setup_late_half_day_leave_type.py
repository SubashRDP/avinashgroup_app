"""Call the unpaid half of a late half day "Late Half Day", not Leave Without Pay.

Policy 1.2: more than 2 hours late is a half day, half of it unpaid. HRMS only
cuts pay for the unpaid half when the attendance row carries a leave type ticked
Is Leave Without Pay, so the late rule (biometric/attendance_override.py) wrote
"Leave Without Pay" there. Staff and reports then read "took unpaid leave" for
somebody who came in late.

  * Leave Type "Late Half Day", Is Leave Without Pay: pay works exactly as before.
  * Shift Type field "Late Half Day Leave Type", beside "Half Day if Late By
    (Hours)", so the leave type is set on the form; seeded on every shift.
  * Existing late half days renamed: Half Day rows carrying Leave Without Pay,
    no Leave Application, and late beyond their shift's limit. Real unpaid leave
    (a Leave Application) is left as it is.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

LEAVE_TYPE = "Late Half Day"


def execute():
	if not frappe.db.exists("Leave Type", LEAVE_TYPE):
		doc = frappe.new_doc("Leave Type")
		doc.leave_type_name = LEAVE_TYPE
		doc.update({"is_lwp": 1, "is_earned_leave": 0, "include_holiday": 0, "allow_encashment": 0, "is_carry_forward": 0})
		doc.insert(ignore_permissions=True)

	create_custom_fields(
		{
			"Shift Type": [
				{
					"fieldname": "custom_late_half_day_leave_type",
					"label": "Late Half Day Leave Type",
					"fieldtype": "Link",
					"options": "Leave Type",
					"insert_after": "custom_half_day_if_late_by_hours",
					"description": "Written on the unpaid half of a late half day. Must be ticked Is Leave Without Pay, or the half is not deducted.",
				}
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Shift Type")
	frappe.db.sql(
		"""update `tabShift Type` set custom_late_half_day_leave_type = %s
		where ifnull(custom_late_half_day_leave_type, '') = ''""",
		LEAVE_TYPE,
	)

	lwp = frappe.get_all("Leave Type", filters={"is_lwp": 1, "name": ("!=", LEAVE_TYPE)}, pluck="name")
	if lwp:
		frappe.db.sql(
			"""update `tabAttendance` a join `tabShift Type` st on st.name = a.shift
			set a.leave_type = %(new)s
			where a.status = 'Half Day' and a.leave_type in %(lwp)s
			  and ifnull(a.leave_application, '') = ''
			  and st.custom_half_day_if_late_by_hours > 0
			  and ifnull(a.custom_late_entry, 0) > st.custom_half_day_if_late_by_hours * 3600""",
			{"new": LEAVE_TYPE, "lwp": lwp},
		)
