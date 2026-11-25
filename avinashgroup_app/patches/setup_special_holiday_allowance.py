"""Special Holiday: a flat amount for everyone who works Dashain or Tihar.

The client pays 200 a day to anyone who comes in on a special festival day, on
top of whatever that holiday already earns them (overtime for OT-eligible staff,
replacement leave for officers — policy 2.2/2.5 is untouched). Saturdays and
ordinary public holidays do not earn it, so "Worked on Holiday" could not carry
it: that condition counts every date of the Holiday List.

This patch:
  1. adds `Special Holiday` (custom_special_holiday) to the Holiday row, so HR
     ticks which dates are special, per Holiday List (Holiday Bulk Update can
     tick a date across every list at once);
  2. adds the `Worked on Special Holiday` condition to Salary Component and hides
     the rule fields it does not read (Unit, Only OT-Eligible Staff, Rate Basis:
     it is always a flat rate per day, for everyone);
  3. adds `Special Holiday Rate` to Salary Component, shown (and required) only
     for that condition. Other allowances keep their rate on each person's
     assignment; this one is a single group-wide amount, so it sits on the
     component (user, 2026-11-25: "put in some setting or the component");
  4. creates the `Special Holiday Allowance` Earning at 200, with Basic's
     account rows for every company. A rate HR has set is never reset.

The paying lives in payroll/attendance_allowance.py (SPECIAL_HOLIDAY).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from avinashgroup_app.patches.setup_festival_allowance import copy_accounts_from_basic

CONDITION = "Worked on Special Holiday"
COMPONENT = "Special Holiday Allowance"
DEFAULT_RATE = 200  # the client's figure per special day worked (2026-11-25)

C = "doc.custom_condition_type"
#: The conditions each rule field is hidden for, now including this one. Same
#: expressions as salary_component_fields_by_condition, plus CONDITION.
DEPENDS_ON = {
	"custom_unit": (
		f'eval:doc.custom_is_attendance_driven && !["Authorised Overtime","Late Time","Meal Entitlement",'
		f'"{CONDITION}"].includes({C})'
	),
	"custom_ot_eligible_only": (
		f'eval:doc.custom_is_attendance_driven && !["Authorised Overtime","Late Time","{CONDITION}"].includes({C})'
	),
	"custom_rate_basis": (
		f'eval:doc.custom_is_attendance_driven && !["Authorised Overtime","Late Time","{CONDITION}"].includes({C})'
	),
}


def execute():
	create_custom_fields(
		{
			"Holiday": [
				{
					"fieldname": "custom_special_holiday",
					"label": "Special Holiday",
					"fieldtype": "Check",
					"insert_after": "weekly_off",
					"in_list_view": 1,
					"columns": 1,
					"default": "0",
					"description": "Dashain, Tihar: everyone who works this day gets the Special Holiday Allowance",
				}
			],
			"Salary Component": [
				{
					"fieldname": "custom_special_holiday_rate",
					"label": "Special Holiday Rate",
					"fieldtype": "Currency",
					"insert_after": "custom_condition_type",
					"depends_on": f'eval:{C}=="{CONDITION}"',
					"mandatory_depends_on": f'eval:{C}=="{CONDITION}"',
					"description": "Paid per special holiday worked, to everyone who comes in, on top of overtime",
				}
			],
		},
		update=True,
	)

	add_condition()
	for fieldname, depends_on in DEPENDS_ON.items():
		name = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": fieldname})
		if name:
			frappe.db.set_value("Custom Field", name, "depends_on", depends_on, update_modified=False)

	make_component()
	if not frappe.db.get_value("Salary Component", COMPONENT, "custom_special_holiday_rate"):
		frappe.db.set_value("Salary Component", COMPONENT, "custom_special_holiday_rate", DEFAULT_RATE)
	copy_accounts_from_basic(COMPONENT)
	frappe.clear_cache(doctype="Salary Component")
	frappe.clear_cache(doctype="Holiday List")


def add_condition():
	name = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": "custom_condition_type"})
	if not name:
		return
	options = (frappe.db.get_value("Custom Field", name, "options") or "").split("\n")
	if CONDITION not in options:
		options.append(CONDITION)
		frappe.db.set_value("Custom Field", name, "options", "\n".join(options))
		frappe.clear_cache(doctype="Salary Component")


def make_component():
	if frappe.db.exists("Salary Component", COMPONENT):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Salary Component",
			"salary_component": COMPONENT,
			"salary_component_abbr": "SHA",
			"type": "Earning",
			"is_tax_applicable": 1,
			"depends_on_payment_days": 0,
			"remove_if_zero_valued": 1,
			"custom_is_attendance_driven": 1,
			"custom_condition_type": CONDITION,
			"custom_unit": "Per Day",
			"custom_rate_basis": "Fixed Rate",
			"custom_special_holiday_rate": DEFAULT_RATE,
			"custom_summary_group": "Special Holiday",
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
