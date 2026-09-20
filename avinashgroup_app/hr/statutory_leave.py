"""Maternity is for mothers, paternity is for fathers.

Both are ordinary leave here: HR allocates them when the case arises and the
employee applies for them like any other leave. The only rule worth enforcing is
who may take which — a mistake there is quiet and expensive, because the days are
long and paid.

Registered in hooks.py as a `validate` doc event on Leave Allocation and Leave
Application, so it catches the mistake at the allocation as well as at the
application.

Deliberately narrow: no day limits, no windows around the birth, no grant
document. The Labour Act figures (maternity 98 days, 60 of them paid; paternity
15) are guidance for HR, not something this refuses.
"""

import frappe
from frappe import _

# Leave type -> the gender that may take it.
GENDER_RESTRICTED_LEAVE = {
	"Maternity Leave": "Female",
	"Paternity Leave": "Male",
}


def validate_gender(doc, method=None):
	"""Refuse maternity for a man and paternity for a woman."""
	required = GENDER_RESTRICTED_LEAVE.get(doc.get("leave_type"))
	if not required or not doc.get("employee"):
		return

	gender, employee_name = frappe.db.get_value("Employee", doc.employee, ["gender", "employee_name"])
	if gender == required:
		return

	frappe.throw(
		_("{0} is only for employees whose gender is {1}. {2} is recorded as {3}.").format(
			frappe.bold(doc.leave_type), required, employee_name or doc.employee, gender or _("not set")
		),
		title=_("Not Eligible"),
	)
