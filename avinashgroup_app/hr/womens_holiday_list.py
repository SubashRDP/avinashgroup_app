"""Put every woman on her company's (Women) holiday list, automatically.

Each company keeps two lists per fiscal year (policy 2.4): `<ABBR> 83/84`, the
Company default everybody inherits, and `<ABBR> Women 83/84`, the same days plus
Teej. HRMS reads one list per person (Employee.holiday_list, else the Company
default), so the women's list only works if it is set on each woman's Employee.

Set by hand, it is forgotten for the next woman hired, and she is marked Absent
on Teej. Discovered at payroll, if at all.

Rule, on every Employee save:
    Female                    the company's Women list for the current year
    anyone else, on a Women   cleared, so the Company default applies
    list (gender or company
    changed)
    anyone else               left alone, so a hand-set list is kept

Registered in hooks.py on Employee validate. `hr.holiday_year_switch` moves
everyone to the next year's lists on 1 Shrawan; this only decides WHICH of a
company's two lists a person belongs on. patches/assign_womens_holiday_lists.py
runs it once over existing staff.
"""

import frappe
from frappe.utils import getdate, today

WOMEN_MARKER = "Women"  # in the list name, as hr/year_setup.ensure_holiday_list names it


def set_holiday_list(doc, method=None):
	"""Pick the Employee's holiday list from gender and company. Hook: validate."""
	current = doc.get("holiday_list")
	on_womens = bool(current) and WOMEN_MARKER in (
		frappe.db.get_value("Holiday List", current, "holiday_list_name") or ""
	)

	if doc.get("gender") == "Female" and doc.get("company"):
		womens = womens_list(doc.company, doc.get("date_of_joining"))
		if womens:
			doc.holiday_list = womens
		return

	# Not (or no longer) a woman, or moved company: a Women list is wrong here.
	if on_womens and (
		doc.get("gender") != "Female"
		or frappe.db.get_value("Holiday List", current, "custom_company") != doc.get("company")
	):
		doc.holiday_list = None


def womens_list(company, on_date=None):
	"""The company's Women holiday list covering today (or the joining date, if later)."""
	day = max(getdate(today()), getdate(on_date)) if on_date else getdate(today())
	rows = frappe.get_all(
		"Holiday List",
		filters={
			"custom_company": company,
			"holiday_list_name": ("like", f"%{WOMEN_MARKER}%"),
			"from_date": ("<=", day),
			"to_date": (">=", day),
		},
		pluck="name",
		limit=1,
	)
	return rows[0] if rows else None
