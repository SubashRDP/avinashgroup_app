"""Which English dates a BS month covers: one answer for payroll and reports.

The books, the payroll and HR's own language run on BS months ("Bhadra's
salary"), but every document stores English dates. Each screen used to work
out a month's dates its own way: a report from the calendar and then a Nepal
BS Period row found by the calendar's start date (so a month whose border HR
had moved was missed), the deposit report by guessing "BS months start around
the 16th", a Payroll Entry from whatever English posting date was typed. They
could disagree, and a payroll posted on the wrong day silently became the next
month's payroll.

The month's borders live in rdp_common_app's **Nepal BS Period**: a fiscal
year's twelve months, company-specific or global, each with a start and end
date HR can move. This module reads it the way the BS salary slip does
(`rdp_common_app...salary_slip_bs.get_date_details`): the company's record
first, then the global one, then the plain Nepali calendar when the doctype
has no row for that month (it may not be filled yet). Because the slip uses
the same order, a payroll and its slips always cover the same days.

A month is named the way the BS reports already name it: a Fiscal Year
("83/84", Shrawan 2083 to Ashadh 2084) and a month option "05 - Bhadra"
(`MONTH_OPTIONS`, listed in fiscal-year order).
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from rdp_common_app.nepal_hrms_common.doctype.nepal_bs_period.nepal_bs_period import (
	get_user_defined_period,
)
from rdp_common_app.utils.bs_boundaries import (
	BS_MONTH_NAMES,
	ad_to_bs,
	get_bs_month_name,
	get_bs_month_range,
	get_salary_period,
)

#: Shrawan first: the order of a Nepali fiscal year.
FISCAL_ORDER = (4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3)
MONTH_OPTIONS = [f"{m:02d} - {BS_MONTH_NAMES[m]}" for m in FISCAL_ORDER]


def month_option(bs_month: int) -> str:
	return f"{int(bs_month):02d} - {BS_MONTH_NAMES[int(bs_month)]}"


def parse_bs_month(value) -> int:
	"""Accept 7, '7', '07 - Kartik' or 'Kartik'; return 1-12."""
	if value is None or value == "":
		frappe.throw(_("BS Month is required."))
	if isinstance(value, int):
		return value
	text = str(value).strip()
	digits = ""
	for ch in text:
		if not ch.isdigit():
			break
		digits += ch
	if digits:
		return int(digits)
	for number, name in BS_MONTH_NAMES.items():
		if name.lower() == text.lower():
			return number
	frappe.throw(_("Could not read BS Month: {0}").format(value))


def bs_year_of(fiscal_year: str, bs_month) -> int:
	"""A fiscal year opens on Shrawan 1: Shrawan-Chaitra are its opening BS
	year, Baisakh-Ashadh the next one ('83/84' Baisakh = 2084)."""
	start = frappe.get_cached_value("Fiscal Year", fiscal_year, "year_start_date")
	if not start:
		frappe.throw(_("Fiscal Year {0} not found.").format(fiscal_year))
	opening = ad_to_bs(getdate(start)).year
	return opening if parse_bs_month(bs_month) >= 4 else opening + 1


def fiscal_year_of(date) -> str | None:
	date = getdate(date)
	return frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ("<=", date), "year_end_date": (">=", date), "disabled": 0},
		"name",
	)


def month_period(company, bs_year, bs_month) -> frappe._dict:
	"""The dates of one BS month: Nepal BS Period (company, then global), else
	the calendar. Looked up by the month itself, never by a calendar date, so
	a border HR has moved is honoured."""
	bs_year, bs_month = int(bs_year), parse_bs_month(bs_month)
	row = stored_month(company, bs_year, bs_month) if company else None
	row = row or stored_month(None, bs_year, bs_month)
	if row:
		start, end, source = row.start_date, row.end_date, "Nepal BS Period"
	else:
		start, end = get_bs_month_range(bs_year, bs_month)
		source = "Nepali calendar"
	return frappe._dict(
		bs_year=bs_year,
		bs_month=bs_month,
		label=f"{get_bs_month_name(bs_month)} {bs_year}",
		start_date=getdate(start),
		end_date=getdate(end),
		source=source,
	)


def stored_month(company, bs_year, bs_month):
	company_clause = "p.company = %(company)s" if company else "ifnull(p.company, '') = ''"
	rows = frappe.db.sql(
		f"""
		select m.start_date, m.end_date
		from `tabNepal BS Period Month` m
		join `tabNepal BS Period` p on p.name = m.parent
		where {company_clause} and m.bs_year = %(bs_year)s and m.bs_month = %(bs_month)s
		order by p.modified desc
		limit 1
		""",
		{"company": company, "bs_year": bs_year, "bs_month": bs_month},
		as_dict=True,
	)
	return rows[0] if rows else None


def month_of_date(company, date) -> frappe._dict:
	"""The BS month a date falls in, by the BS salary slip's own rule."""
	date = getdate(date)
	period = get_user_defined_period(date, company) or get_salary_period(date)
	return frappe._dict(
		bs_year=int(period.bs_year),
		bs_month=int(period.bs_month),
		label=f"{get_bs_month_name(int(period.bs_month))} {int(period.bs_year)}",
		start_date=getdate(period.start_date),
		end_date=getdate(period.end_date),
	)


def last_closed_month(company, on_date=None) -> frappe._dict:
	"""The month before the one running on `on_date`: salary is paid after a
	month ends, and taxes deposited the month after."""
	running = month_of_date(company, on_date or today())
	return month_of_date(company, add_days(running.start_date, -1))


@frappe.whitelist()
def get_month(fiscal_year, bs_month, company=None) -> dict:
	"""For forms and report filters: the dates of a Fiscal Year + BS Month."""
	bs_month = parse_bs_month(bs_month)
	period = month_period(company, bs_year_of(fiscal_year, bs_month), bs_month)
	return {**period, "start_date": str(period.start_date), "end_date": str(period.end_date)}


@frappe.whitelist()
def get_default_month(company=None) -> dict:
	"""The last finished month, as the BS fields of a form or report hold it."""
	period = last_closed_month(company)
	return {
		"fiscal_year": fiscal_year_of(period.start_date),
		"bs_year": period.bs_year,
		"bs_month": month_option(period.bs_month),
		"label": period.label,
	}
