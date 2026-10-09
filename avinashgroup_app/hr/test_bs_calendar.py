"""The BS calendar (hr/bs_calendar.py) and the Payroll Entry built on it.

Covers: fiscal-year month → dates, Nepal BS Period overriding the calendar
(including a moved border, which the old lookup-by-calendar-date missed), the
slip's rule agreeing with the month lookup for every day, the default month,
and a Payroll Entry made from company + fiscal year + month alone.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from avinashgroup_app.hr import bs_calendar
from avinashgroup_app.hr.bs_calendar import (
	bs_year_of,
	get_month,
	last_closed_month,
	month_of_date,
	month_period,
)

COMPANY = "Nepal Gas Udhyog Pvt. Ltd."
FY = "83/84"


def moved_shrawan(company, name):
	"""A Nepal BS Period for FY 2083 whose Shrawan starts on 20 Jul."""
	period = frappe.get_doc(
		{"doctype": "Nepal BS Period", "period_name": name, "company": company, "bs_year": 2083}
	).insert()
	next(m for m in period.months if m.bs_month == 4).start_date = "2026-07-20"
	period.save()
	return period


class TestBSCalendar(FrappeTestCase):
	def test_fiscal_year_months(self):
		self.assertEqual(bs_year_of(FY, "04 - Shrawan"), 2083)
		self.assertEqual(bs_year_of(FY, "12 - Chaitra"), 2083)
		self.assertEqual(bs_year_of(FY, "01 - Baisakh"), 2084)
		self.assertEqual(bs_year_of(FY, "Ashadh"), 2084)

		shrawan = get_month(FY, "04 - Shrawan", COMPANY)
		self.assertEqual((shrawan["start_date"], shrawan["end_date"]), ("2026-07-17", "2026-08-16"))
		self.assertEqual(shrawan["label"], "Shrawan 2083")

	def test_months_tile_the_fiscal_year(self):
		"""Each month starts the day after the last one ends, and the slip's
		rule (month_of_date) finds the same month for every one of its days."""
		previous_end = None
		for option in bs_calendar.MONTH_OPTIONS:
			p = month_period(COMPANY, bs_year_of(FY, option), option)
			if previous_end:
				self.assertEqual(p.start_date, add_days(previous_end, 1), p.label)
			previous_end = p.end_date
			day = p.start_date
			while day <= p.end_date:
				self.assertEqual(month_of_date(COMPANY, day).label, p.label, day)
				day = add_days(day, 1)
		self.assertEqual(previous_end, getdate(frappe.db.get_value("Fiscal Year", FY, "year_end_date")))

	def test_nepal_bs_period_moves_a_border(self):
		"""A company's Shrawan from 20 Jul: the calendar's 17 Jul is not in it,
		so the old lookup (by the calendar start date) fell back to the
		calendar. Looking the month up by name finds it."""
		moved_shrawan(COMPANY, "TEST FY 2083 NGI")

		p = month_period(COMPANY, 2083, 4)
		self.assertEqual((p.start_date, p.source), (getdate("2026-07-20"), "Nepal BS Period"))
		# Another company keeps the calendar.
		self.assertEqual(month_period("Nepal Gas Udhyog (Gandaki) Pvt. Ltd.", 2083, 4).start_date, getdate("2026-07-17"))
		# The slip's rule agrees.
		self.assertEqual(month_of_date(COMPANY, "2026-08-16").start_date, getdate("2026-07-20"))

		# A global record applies to every company without its own.
		moved_shrawan(None, "TEST FY 2083 global")
		self.assertEqual(month_period("Nepal Gas Udhyog (Gandaki) Pvt. Ltd.", 2083, 4).start_date, getdate("2026-07-20"))

	def test_default_is_last_finished_month(self):
		self.assertEqual(last_closed_month(COMPANY, "2026-10-09").label, "Bhadra 2083")
		self.assertEqual(last_closed_month(COMPANY, "2026-07-20").label, "Ashadh 2083")
		with patch.object(bs_calendar, "today", return_value="2026-10-09"):
			default = bs_calendar.get_default_month(COMPANY)
		self.assertEqual((default["fiscal_year"], default["bs_month"]), (FY, "05 - Bhadra"))


class TestPayrollEntryByMonth(FrappeTestCase):
	def test_month_alone_fills_the_entry(self):
		entry = frappe.get_doc(
			{
				"doctype": "Payroll Entry",
				"company": COMPANY,
				"custom_fiscal_year": FY,
				"custom_bs_month": "05 - Bhadra",
				"posting_date": "2026-10-09",  # typed by mistake: replaced
			}
		)
		entry.insert()
		self.assertEqual(
			(entry.start_date, entry.end_date, entry.posting_date),
			(getdate("2026-08-17"), getdate("2026-09-16"), getdate("2026-09-16")),
		)
		self.assertEqual(entry.payroll_frequency, "Monthly")
		self.assertEqual(
			entry.payroll_payable_account,
			frappe.get_cached_value("Company", COMPANY, "default_payroll_payable_account"),
		)
		self.assertEqual(entry.cost_center, frappe.get_cached_value("Company", COMPANY, "cost_center"))
		self.assertTrue(entry.employees)

		entry.custom_bs_month = "06 - Ashwin"
		entry.save()
		self.assertEqual((entry.start_date, entry.posting_date), (getdate("2026-09-17"), getdate("2026-10-17")))
