"""On a fiscal year's first day, point everyone at that year's holiday lists.

HRMS v15.49 gives an employee ONE holiday list, not one per year:
`get_holiday_list_for_employee` returns `Employee.holiday_list`, else
`Company.default_holiday_list`. Our lists are per fiscal year (`NGI 83/84`,
`NGI Women 83/84`, built by `year_setup`). On 1 Shrawan 2084 every company and
all 22 women would still point at the 83/84 lists, which end the day before —
so no Saturday and no festival would be a holiday for anyone, attendance would
mark those days Absent, and nothing would say why.

The switch cannot be made in advance: moving the pointer early takes the rest
of 83/84's holidays away instead. So it runs daily and acts only when a list
in use no longer covers today, replacing it with the same kind of list (common
or women's) for the fiscal year that does.

Deliberately narrow: it only repoints. It never creates a list — a missing
next-year list is logged as an error for someone to build with `setup_year` —
and it leaves alone any list that still covers today, including one somebody
chose by hand.

Scheduled in `hooks.py` (`daily`).
"""

import frappe
from frappe.utils import getdate, today

WOMENS_MARKER = "Women"  # year_setup titles the women's list "<ABBR> Women <FY>"


def switch_to_current_year_lists(on_date=None):
	"""Repoint company defaults and employees whose list has ended. Returns what moved."""
	on_date = getdate(on_date or today())
	fiscal_year = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ["<=", on_date], "year_end_date": [">=", on_date]},
		"name",
	)
	moved = {"companies": [], "employees": 0, "missing": []}
	if not fiscal_year:
		return moved

	for company, abbr, current in frappe.get_all(
		"Company", fields=["name", "abbr", "default_holiday_list"], as_list=True
	):
		if _covers(current, on_date):
			continue
		target = _list_for(abbr, fiscal_year, womens=False, moved=moved)
		if target:
			frappe.db.set_value("Company", company, "default_holiday_list", target)
			moved["companies"].append(abbr)

	for employee, company, current in frappe.get_all(
		"Employee",
		filters={"status": "Active", "holiday_list": ["is", "set"]},
		fields=["name", "company", "holiday_list"],
		as_list=True,
	):
		if _covers(current, on_date):
			continue
		title = frappe.db.get_value("Holiday List", current, "holiday_list_name") or ""
		abbr = frappe.get_cached_value("Company", company, "abbr")
		target = _list_for(abbr, fiscal_year, womens=WOMENS_MARKER in title, moved=moved)
		if target:
			frappe.db.set_value("Employee", employee, "holiday_list", target, update_modified=False)
			moved["employees"] += 1

	if moved["missing"]:
		frappe.log_error(
			title="Holiday lists missing for the new fiscal year",
			message=(
				f"No list titled {', '.join(sorted(set(moved['missing'])))} for {fiscal_year}. "
				"Everyone still on last year's list has no holidays until it exists — "
				"run hr.year_setup.setup_year for this fiscal year."
			),
		)
	frappe.db.commit()
	return moved


def _covers(holiday_list, on_date):
	if not holiday_list:
		return False
	span = frappe.db.get_value("Holiday List", holiday_list, ["from_date", "to_date"], as_dict=True)
	return bool(span) and getdate(span.from_date) <= on_date <= getdate(span.to_date)


def _list_for(abbr, fiscal_year, womens, moved):
	title = f"{abbr} {WOMENS_MARKER + ' ' if womens else ''}{fiscal_year}"
	name = frappe.db.get_value("Holiday List", {"holiday_list_name": title}, "name")
	if not name:
		moved["missing"].append(title)
	return name
