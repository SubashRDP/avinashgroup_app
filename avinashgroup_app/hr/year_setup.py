"""Everything a Nepali fiscal year needs in place, for every company.

A year cannot start until a holiday list, a leave period, a payroll period, an
income tax slab and a leave policy assignment exist for every company. Miss one
and the failure comes much later, as a person silently missing from a payroll run
or a leave balance stuck at zero. So this is one callable that puts the year in
place, safe to run again: everything is created only if it is not already there.

    bench --site <site> execute avinashgroup_app.hr.year_setup.setup_year \\
        --kwargs "{'fiscal_year': '83/84'}"

For a year after the first it also carries everyone's pay across
(`payroll.year_rollover`): a new salary assignment from the year's first day
pointing at the new year's tax slab, because HRMS reads the slab from the
assignment and would otherwise tax the new year at last year's rates.

It creates only what belongs to the YEAR. The standing setup a year rests on —
the hours each company works, what an employee category entitles someone to, how
many leave days a year is worth — is the client's answer, not this module's, and
`require_standing_setup` refuses the run with the whole list of what is absent
rather than inventing any of it. This module used to hold those answers as tables
in code, and they were wrong in the ways guesses are wrong: four of the seven
companies got a nine-to-five nobody had confirmed, Leave Policies were submitted
from a dict, and the festival dates had to be retyped into Python every year or a
list came out with no Dashain on it. A wrong shift or entitlement is worse than a
missing one — it looks deliberate, and it surfaces in somebody's pay.

So before it will run, these must exist:

  * the Fiscal Year record itself;
  * the year's tax table — an Income Tax Slab already entered in the desk, or
    the year in `payroll.income_tax.TAX_SLABS_BY_YEAR`. Last year's rates are
    never copied;
  * per company: a Shift Type, and submitted Leave Policies titled
    `<ABBR> Regular <year>` and `<ABBR> Probation <year>`;
  * group-wide: an Employee Category for paid overtime and one for replacement
    leave.

What it deliberately does NOT do:

  * Invent a shift, a category or a leave entitlement — see above.
  * Put festivals on a holiday list. It builds the Saturdays; four of the five
    festivals move with the moon, so the dates are HR's to enter with Holiday
    Bulk Update, and every list it creates comes back with a warning saying so.
    Teej goes on the women's list alone (policy 2.4).
  * Build a first salary structure or anyone's first pay — that comes from the
    company's own salary sheet, through `payroll.onboarding`.
  * Change anyone's pay — a rise is a Salary Revision.
  * Switch people onto the new year's holiday lists. That has to happen on the
    year's first day, not before: `hr.holiday_year_switch` does it daily.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from avinashgroup_app.payroll.year_rollover import roll_salary_assignments

#: Nepal's weekly off. Not a policy dial — the group does not have companies
#: that rest on a different day — so the holiday list is built on it directly.
WEEKLY_OFF = "Saturday"


def setup_year(fiscal_year, companies=None, assign_leave=True, roll_pay=True):
	"""Put one fiscal year in place for every company. Safe to run twice.

	Raises before creating anything if the Fiscal Year or the year's tax table
	is missing. Returns a per-company report plus `warnings`.
	"""
	year = frappe.db.get_value(
		"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not year:
		frappe.throw(_("Fiscal Year {0} does not exist — create it first.").format(fiscal_year))

	companies = companies or frappe.get_all("Company", pluck="name")
	require_tax_table(fiscal_year, year, companies)

	# Run from bench there is no request, so the audit hook stamps no
	# custom_created_on — and Leave Allocation has no other date for the
	# numbering rule, which then refuses every one. Every employee would be
	# left without next year's leave. audit_user is the hook's own switch for
	# work done outside a request (utils/audit_file_manager.py).
	frappe.flags.audit_user = frappe.flags.audit_user or frappe.session.user

	ensure_leave_types()
	require_standing_setup(fiscal_year, companies)

	warnings = []
	ensure_nepali_payroll()

	report = {"fiscal_year": fiscal_year, "companies": {}, "warnings": warnings}
	for company in companies:
		abbr = frappe.db.get_value("Company", company, "abbr")
		done = {}
		done["holiday_list"], made = ensure_holiday_list(company, abbr, fiscal_year, year)
		done["womens_holiday_list"], made_w = ensure_holiday_list(
			company, abbr, fiscal_year, year, womens=True
		)
		if made or made_w:
			warnings.append(
				_(
					"{0}: holiday lists for {1} have Saturdays only. Enter the year's festivals "
					"with Holiday Bulk Update before the first one falls — Teej on the Women list "
					"alone (policy 2.4)."
				).format(abbr, fiscal_year)
			)
		done["company_defaults"] = ensure_company_defaults(company, abbr, done["holiday_list"])
		done["leave_period"] = ensure_leave_period(company, fiscal_year, year)
		done["leave_policies"] = find_leave_policies(abbr, fiscal_year)
		done["payroll_period"] = ensure_payroll_period(company, abbr, fiscal_year, year)
		done["income_tax_slab"] = ensure_income_tax_slab(company, abbr, fiscal_year, year)
		if roll_pay:
			done["salary_rolled"] = roll_salary_assignments(company, year.year_start_date)
		if assign_leave:
			done["leave_assigned"] = assign_leave_policies(
				company, done["leave_period"], done["leave_policies"]
			)
		report["companies"][abbr] = done

	for w in warnings:
		print("WARNING:", w)
	frappe.db.commit()
	return report


def require_standing_setup(fiscal_year, companies):
	"""Refuse to start a year until the standing setup it rests on exists.

	None of this is year data, so none of it is invented here. A shift's hours, a
	category's policy and a leave entitlement are the client's answers, and this
	module used to hold guesses at them: four of the seven companies got a 9-to-5
	nobody had confirmed, and a Leave Policy was submitted from a table in code.
	A wrong shift or entitlement is worse than a missing one, because it looks
	deliberate and is only found in somebody's pay.

	So the whole list of what is absent is collected and raised at once — one pass
	for HR to work through, rather than a refusal per run.
	"""
	missing = []

	for policy, label in (("ot_eligible", "paid overtime"), ("compensatory_leave", "replacement leave")):
		if not frappe.db.exists("Employee Category", {policy: 1}):
			missing.append(
				_("No Employee Category for {0} — one record per answer is needed").format(label)
			)

	for company in companies:
		abbr = frappe.db.get_value("Company", company, "abbr")

		if not frappe.db.exists("Shift Type", {"custom_company": company}):
			missing.append(
				_("{0}: no Shift Type. Enter the hours this company works, with its punch windows.").format(abbr)
			)

		for kind in ("Regular", "Probation"):
			title = f"{abbr} {kind} {fiscal_year}"
			if not frappe.db.exists("Leave Policy", {"title": title, "docstatus": 1}):
				missing.append(
					_("{0}: no submitted Leave Policy titled \"{1}\" — it carries the year's entitlement").format(
						abbr, title
					)
				)

	if missing:
		frappe.throw(
			_("Enter these before setting up {0}:").format(fiscal_year)
			+ "\n\n" + "\n".join(f"\u2022 {m}" for m in missing)
		)


def require_tax_table(fiscal_year, year, companies):
	"""Refuse to start a year whose tax rates nobody has entered."""
	from avinashgroup_app.payroll.income_tax import TAX_SLABS_BY_YEAR

	if fiscal_year in TAX_SLABS_BY_YEAR:
		return
	missing = [
		c
		for c in companies
		if not frappe.db.exists(
			"Income Tax Slab",
			{"company": c, "effective_from": year.year_start_date, "docstatus": 1, "disabled": 0},
		)
	]
	if missing:
		frappe.throw(
			_(
				"No income tax rates for {0}. Enter them first — add \"{0}\" to TAX_SLABS_BY_YEAR "
				"in payroll/income_tax.py from the Finance Act, or submit an Income Tax Slab "
				"effective {1} for: {2}. Last year's rates are never copied."
			).format(fiscal_year, year.year_start_date, ", ".join(missing))
		)


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


def ensure_leave_types():
	"""The four leave types the group uses, plus the unpaid catch-all.

	How each behaves is settled in one place — `patches.setup_leave_types`, which
	is written to be re-runnable. Calling it here means a site whose leave types
	were deleted gets them back, instead of the year setup quietly building
	policies that point at nothing.

	Restored after 70baa36 removed the function but left the call: `setup_year`
	has raised NameError on every site since, before creating anything at all.
	"""
	from avinashgroup_app.patches.setup_leave_types import execute as build_leave_types

	build_leave_types()


# ────────────────────────────────────────────────────────── per company ──


def ensure_holiday_list(company, abbr, fiscal_year, year, womens=False):
	"""The year's list, with every Saturday on it. Returns (name, was_created).

	Two per company: the common one, and one for women — identical until Teej is
	added to the women's list and nowhere else (policy 2.4).

	Saturdays only. The festivals are not seeded: four of the five move with the
	moon, so they were typed into this module from the published calendar every
	year, and a year nobody had typed silently produced a list with no Dashain on
	it. They are HR's to enter with Holiday Bulk Update, and setup_year says so in
	its warnings for every list it creates.
	"""
	title = f"{abbr} {'Women ' if womens else ''}{fiscal_year}"
	existing = frappe.db.get_value("Holiday List", {"holiday_list_name": title}, "name")
	if existing:
		return existing, False

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
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name, True


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


def find_leave_policies(abbr, fiscal_year):
	"""The two policies HR submitted for this company and year.

	Entitlements are the client's answer and differ by company — Karnali gives 8
	casual days where the rest give 21 — so they are read, never written.
	`require_standing_setup` has already refused the run if either is absent, so
	both are here.
	"""
	return {
		kind: frappe.db.get_value(
			"Leave Policy", {"title": f"{abbr} {kind} {fiscal_year}", "docstatus": 1}, "name"
		)
		for kind in ("Regular", "Probation")
	}


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
	"""This year's tax table. Next year's rates are a new slab, never an edit.

	An Income Tax Slab already entered for the year wins; otherwise it is built
	from TAX_SLABS_BY_YEAR (require_tax_table has made sure one of the two exists).
	"""
	from avinashgroup_app.payroll.income_tax import TAX_SLABS_BY_YEAR

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
				for from_amount, to_amount, percent, condition in TAX_SLABS_BY_YEAR[fiscal_year]
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
