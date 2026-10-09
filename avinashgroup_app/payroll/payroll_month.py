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

Runs from AvinashPayrollEntry.validate (payroll/payroll_entry.py), before HRMS
and before the BS period guard. Drafts only; a submitted entry is history.
"""

import frappe
from frappe import _

from avinashgroup_app.hr.bs_calendar import bs_year_of, month_option, month_period, parse_bs_month


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
