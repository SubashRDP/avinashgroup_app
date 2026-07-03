"""Shared helpers for the CBMS (Central Billing Monitoring System / IRD) integration.

Bikram Sambat (BS) dates and the IRD fiscal-year string are derived directly from the
`nepali_datetime` package rather than this app's own Fiscal Year doctype, because the IRD
API expects a specific dotted format ("2081.082") that doesn't match this app's short BS
fiscal year names ("82/83").
"""

import nepali_datetime
from frappe.utils import getdate


def to_bs_date(ad_date):
	"""Convert a Gregorian date (date, datetime or "YYYY-MM-DD" string — doc fields can
	be any of these depending on where the doc came from) to a nepali_datetime.date."""
	return nepali_datetime.date.from_datetime_date(getdate(ad_date))


def bs_date_str(ad_date, sep="-"):
	"""BS date as e.g. "2082-03-17" (sep="-") or "2082.03.17" (sep=".")."""
	bs = to_bs_date(ad_date)
	return f"{bs.year:04d}{sep}{bs.month:02d}{sep}{bs.day:02d}"


def cbms_fiscal_year(ad_date):
	"""IRD fiscal-year string for a Gregorian date, e.g. "2081.082".

	The Nepali fiscal year runs Shrawan (BS month 4) through Ashadh (BS month 3 of the
	next BS year). Given a BS year/month, the fiscal year starting year is the current
	BS year for months 4-12, or the previous BS year for months 1-3.
	"""
	bs = to_bs_date(ad_date)
	start_year = bs.year if bs.month >= 4 else bs.year - 1
	end_year = start_year + 1
	return f"{start_year}.{end_year % 1000:03d}"


def cbms_invoice_number(sales_invoice):
	"""The number sent to CBMS as invoice_number / credit_note_number.

	This is the Sales Invoice's per-branch running number (`custom_branch_name`), which
	naming_series.py guarantees is always set — to a real branch-wise number for
	Grishma Enterprises, and to `doc.name` for every other company. Falling back to
	`doc.name` here as well only guards against that field being blank on older data.
	"""
	return getattr(sales_invoice, "custom_branch_name", None) or sales_invoice.name
