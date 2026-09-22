"""Everything a company needs in place before a Nepali fiscal year can run.

A year cannot start until eight things exist for every company: a holiday list
with its Saturdays, the shifts people work, the two employee categories, the
allowance (tea) groups, the leave period, the leave policies, the payroll period
and the income tax slab — and then every employee has to be given their leave
policy. Miss one and the failure comes much later, as a person silently missing
from a payroll run or a leave balance stuck at zero.

So this is one callable that puts the whole year in place, and is safe to run
again: everything is created only if it is not already there.

    bench --site <site> execute avinashgroup_app.hr.year_setup.setup_year \\
        --kwargs "{'fiscal_year': '83/84'}"

What it deliberately does NOT do:

  * Salary structures and each person's pay — those come from the company's own
    salary sheet, through `payroll.onboarding`.
  * Festival holidays — only the weekly Saturdays are known in advance. Add the
    festivals with Holiday Bulk Update once the dates are published.
  * Teej — the women's holiday list is created empty of festivals beside the
    common one; Teej goes on it, and on it alone.
"""

import frappe
from frappe import _
from frappe.utils import getdate

#: The three shifts the group works, with the rules that make a day a half day.
SHIFTS = (
	("6 AM - 2 PM", "06:00:00", "14:00:00"),
	("9 AM - 6 PM", "09:00:00", "18:00:00"),
	("12 PM - 8 PM", "12:00:00", "20:00:00"),
)

#: Policy 1.2 (client meeting 2026-09-15): more than two hours late is a half
#: day, and there is no grace period.
HALF_DAY_IF_LATE_BY_HOURS = 2

EMPLOYEE_CATEGORIES = (
	("Plant", 1, 0, "Paid overtime for extra hours and for holiday work."),
	("Officer & Admin", 0, 1, "Earns replacement leave for holiday work instead of overtime pay."),
)

#: Leave a year, per company. Karnali gives 8 casual where the rest give 21.
LEAVE_BY_COMPANY = {"NGK": {"Casual Leave": 8, "Sick Leave": 12}}
LEAVE_DEFAULT = {"Casual Leave": 21, "Sick Leave": 12}
LEAVE_PROBATION = {"Casual Leave": 12}

WEEKLY_OFF = "Saturday"

#: The festivals the group closes for, per fiscal year: (AD date, name, who).
#: Four of the five move with the moon, so they are typed from the Nepali
#: calendar each year and cannot be calculated — only Maghe Sankranti is fixed
#: (Magh 1). `women` marks a day that goes on the women's list alone.
#: Confirmed with the client for 83/84 on 2026-09-22: Dashain 5 days, Tihar 3.
FESTIVALS = {
	"83/84": (
		("2026-08-28", "Janai Purnima", "all"),
		("2026-09-14", "Haritalika Teej", "women"),
		("2026-10-18", "Fulpati", "all"),
		("2026-10-19", "Maha Ashtami", "all"),
		("2026-10-20", "Maha Nawami", "all"),
		("2026-10-21", "Vijaya Dashami", "all"),
		("2026-10-22", "Ekadashi", "all"),
		("2026-11-09", "Laxmi Puja", "all"),
		("2026-11-10", "Gobardhan Puja", "all"),
		("2026-11-11", "Bhai Tika", "all"),
		("2027-01-15", "Maghe Sankranti", "all"),
	),
}


def setup_year(fiscal_year, companies=None, assign_leave=True):
	"""Put one fiscal year in place for every company. Safe to run twice."""
	year = frappe.db.get_value(
		"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not year:
		frappe.throw(_("Fiscal Year {0} does not exist — create it first.").format(fiscal_year))

	ensure_nepali_payroll()
	# The app names a Shift Type and a Holiday List per company, so both carry
	# `custom_company`. Shifts themselves are shared across the group — one set
	# of three, tagged to the first company, as on the working site.
	ensure_shift_types(companies[0] if companies else default_company())
	ensure_employee_categories()
	ensure_leave_types()

	report = {"fiscal_year": fiscal_year, "companies": {}}
	for company in companies or frappe.get_all("Company", pluck="name"):
		abbr = frappe.db.get_value("Company", company, "abbr")
		done = {}
		done["holiday_list"] = ensure_holiday_list(company, abbr, fiscal_year, year)
		done["womens_holiday_list"] = ensure_holiday_list(company, abbr, fiscal_year, year, womens=True)
		done["company_defaults"] = ensure_company_defaults(company, abbr, done["holiday_list"])
		done["leave_period"] = ensure_leave_period(company, fiscal_year, year)
		done["leave_policies"] = ensure_leave_policies(company, abbr, fiscal_year)
		done["payroll_period"] = ensure_payroll_period(company, abbr, fiscal_year, year)
		done["income_tax_slab"] = ensure_income_tax_slab(company, abbr, fiscal_year, year)
		if assign_leave:
			done["leave_assigned"] = assign_leave_policies(
				company, done["leave_period"], done["leave_policies"]
			)
		report["companies"][abbr] = done

	frappe.db.commit()
	return report


# ─────────────────────────────────────────────────────────── group-wide ──


def ensure_nepali_payroll():
	"""Every salary run covers one BS month."""
	settings = frappe.get_single("Nepal HRMS Settings")
	if not settings.process_payroll_in_nepali_month:
		settings.process_payroll_in_nepali_month = 1
		settings.flags.ignore_permissions = True
		settings.save()


def default_company():
	return frappe.defaults.get_defaults().get("company") or frappe.get_all(
		"Company", order_by="creation", limit=1, pluck="name"
	)[0]


def ensure_shift_types(company):
	for name, start, end in SHIFTS:
		if frappe.db.exists("Shift Type", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Shift Type",
				"__newname": name,
				"start_time": start,
				"end_time": end,
				"enable_auto_attendance": 1,
				"determine_check_in_and_check_out": "Alternating entries as IN and OUT during the same shift",
				"working_hours_calculation_based_on": "First Check-in and Last Check-out",
				"begin_check_in_before_shift_start_time": 120,
				"allow_check_out_after_shift_end_time": 120,
				"working_hours_threshold_for_half_day": 5,
				"working_hours_threshold_for_absent": 2,
				"enable_late_entry_marking": 1,
				"late_entry_grace_period": 0,
				"custom_half_day_if_late_by_hours": HALF_DAY_IF_LATE_BY_HOURS,
				"custom_company": company,
			}
		).insert(ignore_permissions=True)


def ensure_leave_types():
	"""The four leave types the group uses, plus the unpaid catch-all.

	How each behaves is settled in one place — `patches.setup_leave_types`, which
	is written to be re-runnable. Calling it here means a site whose leave types
	were deleted gets them back, instead of the year setup quietly building
	policies that point at nothing.
	"""
	from avinashgroup_app.patches.setup_leave_types import execute as build_leave_types

	build_leave_types()


def ensure_employee_categories():
	for name, ot, comp, description in EMPLOYEE_CATEGORIES:
		if frappe.db.exists("Employee Category", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Employee Category",
				"category_name": name,
				"ot_eligible": ot,
				"compensatory_leave": comp,
				"description": description,
			}
		).insert(ignore_permissions=True)


# ────────────────────────────────────────────────────────── per company ──


def ensure_holiday_list(company, abbr, fiscal_year, year, womens=False):
	"""The year's list, with every Saturday on it.

	Two per company: the common one, and one for women — identical until Teej is
	added to the women's list and nowhere else (policy 2.4).
	"""
	title = f"{abbr} {'Women ' if womens else ''}{fiscal_year}"
	existing = frappe.db.get_value("Holiday List", {"holiday_list_name": title}, "name")
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Holiday List",
			"holiday_list_name": title,
			"from_date": year.year_start_date,
			"to_date": year.year_end_date,
			"weekly_off": WEEKLY_OFF,
			"custom_company": company,
		}
	)
	doc.get_weekly_off_dates()
	add_festivals(doc, fiscal_year, womens)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def add_festivals(doc, fiscal_year, womens):
	"""Put the year's festivals on the list, without doubling a Saturday.

	A festival that lands on the weekly off is already a holiday; adding it again
	would show the day twice and count it twice in any report.
	"""
	taken = {getdate(h.holiday_date) for h in doc.holidays}
	for date_str, name, audience in FESTIVALS.get(fiscal_year, ()):
		if audience == "women" and not womens:
			continue
		day = getdate(date_str)
		if day < getdate(doc.from_date) or day > getdate(doc.to_date) or day in taken:
			continue
		doc.append("holidays", {"holiday_date": day, "description": name})
		taken.add(day)


def ensure_company_defaults(company, abbr, holiday_list):
	"""The three company fields payroll reads, filled from the company's chart.

	Found by account NAME, not by code: the codes are not the same in every
	company — Grihalaxmi's Salary Payable is 347201, while its 347301 is a
	payable to another group company. Matching on the code would have pointed
	payroll at the wrong ledger.
	"""
	values, missing = {}, []
	if not frappe.db.get_value("Company", company, "default_holiday_list"):
		values["default_holiday_list"] = holiday_list

	for field, account_name in (
		("default_payroll_payable_account", "Salary Payable"),
		("default_employee_advance_account", "Staff Advance"),
	):
		if frappe.db.get_value("Company", company, field):
			continue
		account = frappe.db.get_value(
			"Account", {"company": company, "account_name": account_name, "is_group": 0}, "name"
		)
		if account:
			values[field] = account
		else:
			missing.append(f"{account_name} ({abbr})")

	if values:
		frappe.db.set_value("Company", company, values)
	return {"set": [v for v in values if not v.startswith("modified")], "missing_accounts": missing}


def ensure_leave_period(company, fiscal_year, year):
	existing = frappe.db.get_value(
		"Leave Period", {"company": company, "from_date": year.year_start_date}, "name"
	)
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Leave Period",
			"company": company,
			"from_date": year.year_start_date,
			"to_date": year.year_end_date,
			"is_active": 1,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def ensure_leave_policies(company, abbr, fiscal_year):
	"""Two policies per company: the regular one, and one for probation."""
	out = {}
	for kind, allocations in (
		("Regular", LEAVE_BY_COMPANY.get(abbr, LEAVE_DEFAULT)),
		("Probation", LEAVE_PROBATION),
	):
		title = f"{abbr} {kind} {fiscal_year}"
		existing = frappe.db.get_value("Leave Policy", {"title": title, "docstatus": 1}, "name")
		if existing:
			out[kind] = existing
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Leave Policy",
				"title": title,
				"leave_policy_details": [
					{"leave_type": leave_type, "annual_allocation": days}
					for leave_type, days in allocations.items()
					if frappe.db.exists("Leave Type", leave_type)
				],
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		out[kind] = doc.name
	return out


def ensure_payroll_period(company, abbr, fiscal_year, year):
	existing = frappe.db.get_value(
		"Payroll Period", {"company": company, "start_date": year.year_start_date}, "name"
	)
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Payroll Period",
			"__newname": f"{fiscal_year} - {abbr}",
			"company": company,
			"start_date": year.year_start_date,
			"end_date": year.year_end_date,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def ensure_income_tax_slab(company, abbr, fiscal_year, year):
	"""This year's tax table. Next year's rates are a new slab, never an edit."""
	from avinashgroup_app.payroll.income_tax import FY_8384_SLABS

	existing = frappe.db.get_value(
		"Income Tax Slab",
		{"company": company, "effective_from": year.year_start_date, "docstatus": 1},
		"name",
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Income Tax Slab",
			"__newname": f"Nepal {fiscal_year} - {abbr}",
			"company": company,
			"effective_from": year.year_start_date,
			"currency": frappe.db.get_value("Company", company, "default_currency") or "NPR",
			"allow_tax_exemption": 1,
			"standard_tax_exemption_amount": 0,
			"slabs": [
				{
					"from_amount": from_amount,
					"to_amount": to_amount,
					"percent_deduction": percent,
					"condition": condition,
				}
				for from_amount, to_amount, percent, condition in FY_8384_SLABS
			],
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc.name


def assign_leave_policies(company, leave_period, policies):
	"""Give every active employee their policy for the year, once.

	Probation staff get the probation policy — one day a month instead of 2.75
	— and everyone else the regular one. The allocation itself starts at zero
	and grows each BS month (`hr.utils.allocate_earned_leaves_bs`).
	"""
	assigned, failed = [], []
	for employee in frappe.get_all(
		"Employee",
		filters={"company": company, "status": "Active"},
		fields=["name", "employment_type"],
	):
		if frappe.db.exists(
			"Leave Policy Assignment",
			{"employee": employee.name, "leave_period": leave_period, "docstatus": 1},
		):
			continue

		on_probation = (employee.employment_type or "").lower().startswith("probation")
		policy = policies.get("Probation" if on_probation else "Regular")
		if not policy:
			continue

		try:
			frappe.db.savepoint("lpa")
			doc = frappe.get_doc(
				{
					"doctype": "Leave Policy Assignment",
					"employee": employee.name,
					"leave_policy": policy,
					"assignment_based_on": "Leave Period",
					"leave_period": leave_period,
					"company": company,
				}
			)
			doc.flags.ignore_permissions = True
			doc.insert()
			doc.submit()
			assigned.append(employee.name)
		except Exception as e:
			frappe.db.rollback(save_point="lpa")
			failed.append((employee.name, str(e)[:120]))

	return {"assigned": len(assigned), "failed": failed}
