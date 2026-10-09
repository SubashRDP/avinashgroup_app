"""A Payroll Entry is made by choosing a Fiscal Year and a BS month.

HR runs "Bhadra's salary", not "17 August to 16 September". Asking them for an
English posting date and deriving the month from it was the root of the
mistake bs_period_guard.py refuses: Bhadra's payroll typed on 2 Ashwin becomes
an Ashwin payroll. So the entry carries `custom_fiscal_year` and
`custom_bs_month`, and everything that follows from them is filled here:

  * start and end date: the month's dates from hr/bs_calendar.py (Nepal BS
    Period when it has the month, the Nepali calendar until then);
  * posting date: the month's last day. The salary slip finds its month from
    the posting date, so the slips cover the same days, and the accrual
    journal sits in the month it belongs to;
  * frequency Monthly, the company's currency, and the company's payroll
    payable account and cost centre when still blank (a deliberate choice is
    kept);
  * the employee list, when it is empty or the month changed (HRMS's own Get
    Employees, with any branch / department / designation filter set).

The form picks the month on a calendar (`month_calendar`, drawn by
public/js/payroll_entry.js): a fiscal year's months with their dates and any
entry already made for each.

Runs from AvinashPayrollEntry.validate (payroll/payroll_entry.py), before HRMS
and before the BS period guard. Drafts only; a submitted entry is history.
"""

import frappe
from frappe import _

from frappe.utils import add_days, today

from avinashgroup_app.hr.bs_calendar import (
	MONTH_OPTIONS,
	bs_year_of,
	fiscal_year_of,
	last_closed_month,
	month_of_date,
	month_option,
	month_period,
	parse_bs_month,
)


def fill_from_bs_month(doc):
	if doc.docstatus != 0 or not doc.company:
		return
	if not (doc.get("custom_fiscal_year") and doc.get("custom_bs_month")):
		return

	bs_month = parse_bs_month(doc.custom_bs_month)
	doc.custom_bs_month = month_option(bs_month)
	period = month_period(doc.company, bs_year_of(doc.custom_fiscal_year, bs_month), bs_month)

	doc.start_date = period.start_date
	doc.end_date = period.end_date
	doc.posting_date = period.end_date
	doc.payroll_frequency = "Monthly"

	company = frappe.get_cached_value(
		"Company", doc.company, ["default_currency", "default_payroll_payable_account", "cost_center"], as_dict=True
	)
	doc.currency = company.default_currency
	doc.exchange_rate = 1
	doc.payroll_payable_account = doc.payroll_payable_account or company.default_payroll_payable_account
	doc.cost_center = doc.cost_center or company.cost_center
	if not doc.payroll_payable_account:
		frappe.throw(
			_("Set Default Payroll Payable Account on Company {0}, or choose one on this entry.").format(doc.company)
		)

	# Who is paid depends on the month (joiners, leavers): refill on a new month.
	if not doc.employees or (not doc.is_new() and doc.has_value_changed("start_date")):
		doc.fill_employee_details()


def warn_missing_attendance(doc):
	"""Tell HR, before the slips are made, who has no attendance in the month.

	Payroll Settings count an unmarked day as Present, so a month with no
	attendance pays everyone in full and posts no tea, meal, overtime or late
	fine, and nothing said so: both Bhadra 2083 payrolls ran that way. A
	warning, not a refusal: until the devices are live there is no attendance
	anywhere, and HR may knowingly pay a full month.

	Runs from AvinashPayrollEntry.validate and before_submit, on drafts.
	"""
	if doc.docstatus != 0 or not (doc.start_date and doc.end_date and doc.employees):
		return
	if frappe.db.get_single_value("Payroll Settings", "payroll_based_on") != "Attendance":
		return
	employees = [e.employee for e in doc.employees]
	with_attendance = set(
		frappe.get_all(
			"Attendance",
			filters={
				"employee": ("in", employees),
				"docstatus": 1,
				"attendance_date": ("between", [doc.start_date, doc.end_date]),
			},
			pluck="employee",
			distinct=True,
		)
	)
	missing = len(set(employees) - with_attendance)
	if not missing:
		return
	unmarked = frappe.db.get_single_value("Payroll Settings", "consider_unmarked_attendance_as") or "Absent"
	frappe.msgprint(
		_(
			"{0} of {1} employees have no submitted attendance between {2} and {3}. "
			"Their unmarked days count as {4}, and they get no tea, meal, overtime or late fine. "
			"Mark the attendance first unless this is intended."
		).format(missing, len(employees), doc.start_date, doc.end_date, frappe.bold(unmarked)),
		title=_("Attendance missing"),
		indicator="orange",
	)


@frappe.whitelist()
def default_month(company=None) -> dict:
	"""The month a new Payroll Entry starts on: the one after the company's
	last payroll, never later than the month now running; with no payroll yet,
	the last finished month.

	The last finished month alone (bs_calendar.get_default_month, right for
	reports) opened a new entry on Bhadra after Bhadra had been paid.
	"""
	running = month_of_date(company, today())
	month = last_closed_month(company)
	if company:
		last_end = frappe.db.get_value(
			"Payroll Entry", {"company": company, "docstatus": ("<", 2)}, "end_date", order_by="end_date desc"
		)
		if last_end:
			month = month_of_date(company, add_days(last_end, 1))
			if month.start_date > running.start_date:
				month = running
	return {
		"fiscal_year": fiscal_year_of(month.start_date),
		"bs_year": month.bs_year,
		"bs_month": month_option(month.bs_month),
		"label": month.label,
	}


@frappe.whitelist()
def month_calendar(company, fiscal_year=None, exclude=None) -> dict:
	"""The month calendar on the Payroll Entry form: a fiscal year's twelve
	months with their dates, whether each has ended, and the payroll entries
	already made for it (so a month is not paid twice by accident)."""
	running = month_of_date(company, today())
	fiscal_year = fiscal_year or fiscal_year_of(last_closed_month(company).start_date)
	years = frappe.get_all("Fiscal Year", filters={"disabled": 0}, order_by="year_start_date", pluck="name")
	at = years.index(fiscal_year) if fiscal_year in years else -1

	entries = {}
	for e in frappe.get_all(
		"Payroll Entry",
		filters={
			"company": company,
			"custom_fiscal_year": fiscal_year,
			"docstatus": ("<", 2),
			"name": ("!=", exclude or ""),
		},
		fields=["name", "custom_bs_month", "docstatus"],
		order_by="creation",
	):
		entries.setdefault(e.custom_bs_month, []).append({"name": e.name, "docstatus": e.docstatus})

	months = []
	for option in MONTH_OPTIONS:
		period = month_period(company, bs_year_of(fiscal_year, option), option)
		state = (
			"running"
			if period.start_date <= running.end_date and period.end_date >= running.start_date
			else "ended" if period.end_date < running.start_date else "future"
		)
		months.append(
			{
				"option": option,
				"bs_month": period.bs_month,
				"bs_year": period.bs_year,
				"start_date": str(period.start_date),
				"end_date": str(period.end_date),
				"source": period.source,
				"state": state,
				"entries": entries.get(option, []),
			}
		)
	return {
		"fiscal_year": fiscal_year,
		"previous": years[at - 1] if at > 0 else None,
		"next": years[at + 1] if 0 <= at < len(years) - 1 else None,
		"months": months,
	}
