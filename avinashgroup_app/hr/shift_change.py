"""Let an employee's Shift Request actually change their shift.

Everyone here holds one open-ended Shift Assignment from the start of the fiscal
year, which is what keeps attendance correct when it is marked weeks later. But
it also means a Shift Request for "I will come on 12-8 instead of 6-2 next
Monday" cannot be approved: ERPNext refuses a second assignment overlapping the
first, and every shift here overlaps every other.

    NGI-EMP-00029 already has an active Shift Assignment HR-SHA-26-09-00108
    for some/all of these dates.

So before the request creates its assignment, this makes room for it: the
standing assignment is ended the day before, and picked up again the day after.
Cancelling the request closes the gap again.

    before          6 AM - 2 PM  Shrawan 1 ─────────────────────────▶ open
    approved        6 AM - 2 PM  Shrawan 1 ──▶ Oct 4
                    12 PM - 8 PM              Oct 5 ─ Oct 7
                    6 AM - 2 PM                        Oct 8 ──────▶ open
    cancelled       6 AM - 2 PM  Shrawan 1 ─────────────────────────▶ open

A request with NO end date is the permanent move — "I work evenings from now on".
The old shift then stops for good and is not resumed:

    approved        6 AM - 2 PM  Shrawan 1 ──▶ Oct 4
                    12 PM - 8 PM              Oct 5 ─────────────────▶ open

Registered in hooks.py on Shift Request: `before_submit` (make room, before the
controller inserts its assignment) and `on_cancel` (give the days back).

Deliberately narrow: it only moves the dates of assignments that already exist.
It never invents a shift for somebody who had none, and it leaves the requested
assignment itself to HRMS.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate


def validate_request(doc, method=None):
	"""Refuse a request for the shift the employee is already on. Hook: validate.

	HRMS only compares the request against the Default Shift, which is empty for
	everyone here, so "9-6 instead of 9-6" would otherwise be approved and split
	the standing assignment into three pointless pieces.
	"""
	start, end = getdate(doc.from_date), getdate(doc.to_date or doc.from_date)
	for row in _overlapping_assignments(doc.employee, start, end):
		if frappe.db.get_value("Shift Assignment", row.name, "shift_type") == doc.shift_type:
			frappe.throw(
				_("{0} is already on {1} for these dates").format(
					doc.employee_name or doc.employee, frappe.bold(doc.shift_type)
				)
			)


def make_room_for_request(doc, method=None):
	"""Clear the requested dates of any standing assignment. Hook: before_submit."""
	if doc.status != "Approved":
		return

	start = getdate(doc.from_date)
	# No end date means the move is permanent: the old shift stops for good.
	permanent = not doc.to_date
	end = start if permanent else getdate(doc.to_date)

	for row in _overlapping_assignments(doc.employee, start, end if not permanent else None):
		assignment = frappe.get_doc("Shift Assignment", row.name)
		original_end = assignment.end_date
		assignment.flags.ignore_permissions = True

		if getdate(assignment.start_date) < start:
			# Standing shift starts earlier: stop it the day before the request.
			assignment.db_set("end_date", add_days(start, -1), update_modified=False)
		else:
			# Wholly inside the requested dates: it has nothing left to cover.
			assignment.cancel()
			frappe.delete_doc("Shift Assignment", assignment.name, force=1, ignore_permissions=True)

		if permanent:
			continue
		if original_end is None or getdate(original_end) > end:
			_resume(assignment, add_days(end, 1), original_end)


def close_gap_after_cancel(doc, method=None):
	"""Put the standing shift back over the cancelled dates. Hook: on_cancel."""
	start = getdate(doc.from_date)
	if not doc.to_date:
		# A permanent move, undone: let the shift that preceded it run on again.
		before = frappe.db.get_value(
			"Shift Assignment",
			{"employee": doc.employee, "docstatus": 1, "end_date": add_days(start, -1)},
			"name",
		)
		if before:
			frappe.db.set_value("Shift Assignment", before, "end_date", None)
		return

	end = getdate(doc.to_date)
	before = frappe.db.get_value(
		"Shift Assignment",
		{"employee": doc.employee, "docstatus": 1, "end_date": add_days(start, -1)},
		["name", "shift_type"],
		as_dict=True,
	)
	after = frappe.db.get_value(
		"Shift Assignment",
		{"employee": doc.employee, "docstatus": 1, "start_date": add_days(end, 1)},
		["name", "shift_type", "end_date"],
		as_dict=True,
	)

	if before and after and before.shift_type == after.shift_type:
		# One shift split in two by the request: join them back into one.
		frappe.db.set_value("Shift Assignment", before.name, "end_date", after.end_date)
		doc_after = frappe.get_doc("Shift Assignment", after.name)
		doc_after.flags.ignore_permissions = True
		doc_after.cancel()
		frappe.delete_doc("Shift Assignment", after.name, force=1, ignore_permissions=True)
	elif before:
		# Nothing followed: the standing shift simply runs on again.
		frappe.db.set_value("Shift Assignment", before.name, "end_date", end)
		_resume(frappe.get_doc("Shift Assignment", before.name), add_days(end, 1), None)


def _overlapping_assignments(employee, start, end=None):
	"""Submitted, active assignments covering any of these dates.

	`end=None` means "from `start` onwards", which is what a permanent move asks
	about: every assignment still running on or after that date.
	"""
	conditions = "and (end_date is null or end_date >= %(start)s)"
	if end is not None:
		conditions += " and start_date <= %(end)s"
	return frappe.db.sql(
		f"""select name from `tabShift Assignment`
		where employee = %(employee)s and docstatus = 1 and status = 'Active' {conditions}""",
		{"employee": employee, "start": start, "end": end},
		as_dict=True,
	)


def _resume(assignment, from_date, until):
	"""Start the same shift again on `from_date`, running to `until` (None = open)."""
	resumed = frappe.new_doc("Shift Assignment")
	resumed.update(
		{
			"employee": assignment.employee,
			"company": assignment.company,
			"shift_type": assignment.shift_type,
			"shift_location": assignment.get("shift_location"),
			"status": "Active",
			"start_date": from_date,
			"end_date": until,
		}
	)
	resumed.flags.ignore_permissions = True
	resumed.insert()
	resumed.submit()
	return resumed.name
