"""Show on the Salary Component only the fields its Condition Type reads.

Overtime and the late fine stopped reading most of the attendance-rule fields
(commits 7c71009, 9c1b54a): overtime is always hours × hourly basic × 1.5 for
OT-eligible staff, the late fine always minutes against the basic for everyone
not exempt. The form still showed Unit, Rate Basis and Only OT-Eligible Staff
on both, so HR saw settings that change nothing, and a hidden-in-code rule
looked like a forgotten tick. Each field now appears only for the conditions
that use it, and follows the Condition Type live as it is changed:

  Unit                    every condition but Authorised Overtime, Late Time,
                          Meal Entitlement (those count hours or meals)
  A Half Day Counts As    Status = Present only
  Only OT-Eligible Staff  every condition but Authorised Overtime (always
                          OT-eligible) and Late Time (always everyone)
  Rate Basis              every condition but Authorised Overtime and Late Time
                          (both always priced off the basic)
  Multiplier              Late Time, or Rate Basis = Hourly Basic; never
                          Authorised Overtime (fixed 1.5)
  Rate: Days / Hours      Authorised Overtime, Late Time, or Rate Basis =
                          Hourly Basic

The code ignores a hidden field the same way (attendance_allowance.py), so a
value left behind from before cannot change pay. Rate Basis also moves up
beside the other rule fields; it pointed at a field that no longer exists and
so sat at the bottom of the form.
"""

import frappe

DRIVEN = "doc.custom_is_attendance_driven"
C = "doc.custom_condition_type"
HOURLY = 'doc.custom_rate_basis=="Hourly Basic × Multiplier"'

DEPENDS_ON = {
	"custom_unit": f'eval:{DRIVEN} && !["Authorised Overtime","Late Time","Meal Entitlement"].includes({C})',
	"custom_half_day_counts": f'eval:{DRIVEN} && {C}=="Status = Present"',
	"custom_ot_eligible_only": f'eval:{DRIVEN} && !["Authorised Overtime","Late Time"].includes({C})',
	"custom_rate_basis": f'eval:{DRIVEN} && !["Authorised Overtime","Late Time"].includes({C})',
	"custom_rate_multiplier": f'eval:{DRIVEN} && ({C}=="Late Time" || ({C}!="Authorised Overtime" && {HOURLY}))',
	"custom_rate_days_per_month": f'eval:{DRIVEN} && (["Authorised Overtime","Late Time"].includes({C}) || {HOURLY})',
	"custom_rate_hours_per_day": f'eval:{DRIVEN} && (["Authorised Overtime","Late Time"].includes({C}) || {HOURLY})',
}


def execute():
	for fieldname, depends_on in DEPENDS_ON.items():
		name = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": fieldname})
		if name:
			frappe.db.set_value("Custom Field", name, "depends_on", depends_on, update_modified=False)

	basis = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": "custom_rate_basis"})
	if basis and frappe.db.exists("Custom Field", {"dt": "Salary Component", "fieldname": "custom_ot_eligible_only"}):
		frappe.db.set_value("Custom Field", basis, "insert_after", "custom_ot_eligible_only", update_modified=False)

	frappe.clear_cache(doctype="Salary Component")
