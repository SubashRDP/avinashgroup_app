"""Shared helpers for the CBMS (Central Billing Monitoring System / IRD) integration.

Bikram Sambat (BS) dates come from the `nepali_datetime` package. The IRD fiscal-year
string is resolved from the Fiscal Year record the posting date falls in (per company),
reformatted from the site's short names ("82/83") to the dotted format the IRD API
expects ("2082.083").
"""

import frappe
import nepali_datetime
from erpnext.accounts.utils import get_fiscal_year
from frappe.utils import get_datetime, getdate


def user_display_name(user):
	"""A user's full name for CBMS Bill.created_by, falling back to the user id.

	The bill stores a NAME, not a User link, so the annexure's "Entered By"
	column survives a user being renamed, disabled or deleted — an IRD record
	must not lose its author, and the legacy print history it sits beside
	carries names from the old software that were never Frappe users at all.
	"""
	if not user:
		return None
	return frappe.db.get_value("User", user, "full_name") or user


def to_bs_date(ad_date):
	"""Convert a Gregorian date (date, datetime or "YYYY-MM-DD" string — doc fields can
	be any of these depending on where the doc came from) to a nepali_datetime.date."""
	return nepali_datetime.date.from_datetime_date(getdate(ad_date))


def bs_date_str(ad_date, sep="-"):
	"""BS date as e.g. "2082-03-17" (sep="-") or "2082.03.17" (sep=".")."""
	bs = to_bs_date(ad_date)
	return f"{bs.year:04d}{sep}{bs.month:02d}{sep}{bs.day:02d}"


# BS month names, index 0 == Baisakh (month 1). Kept here rather than imported
# from rdp_common_app so the CBMS date path stays on nepali_datetime alone —
# that app's copy sits next to a second, different BS conversion library.
BS_MONTH_NAMES = (
	"Baisakh",
	"Jestha",
	"Ashadh",
	"Shrawan",
	"Bhadra",
	"Ashwin",
	"Kartik",
	"Mangsir",
	"Poush",
	"Magh",
	"Falgun",
	"Chaitra",
)


def bs_long_date(ad_date):
	"""BS date in the long form the IRD annexure header uses: "Shrawan 1, 2082"."""
	bs = to_bs_date(ad_date)
	return f"{BS_MONTH_NAMES[bs.month - 1]} {bs.day}, {bs.year}"


def bs_datetime_str(ad_datetime, sep="/", twelve_hour=False):
	"""BS date + clock time, e.g. "2082/04/01 10:54:12", or with twelve_hour
	"2082/04/01 10:53:33 AM".

	The date converts to BS; the time is carried over unchanged (BS and AD share
	a clock). Returns None for a missing timestamp, so a report cell stays
	genuinely empty rather than holding a blank string.
	"""
	if not ad_datetime:
		return None
	ad_datetime = get_datetime(ad_datetime)
	time_fmt = "%I:%M:%S %p" if twelve_hour else "%H:%M:%S"
	return f"{bs_date_str(ad_datetime.date(), sep=sep)} {ad_datetime.strftime(time_fmt)}"


def cbms_fiscal_year(ad_date, company=None):
	"""Fiscal-year for a posting date, as OUR Fiscal Year names it: "82/83".

	Finds the Fiscal Year record the posting date falls in (year_start_date..
	year_end_date, respecting company-specific fiscal years) and returns its name
	unchanged, so the value on a CBMS record is the same string as the Fiscal Year
	doctype's — a link the reports and the annexure can rely on.

	CBMS itself wants the dotted form ("82.83"). That conversion now happens in
	api_client's payload builders, at the moment of transmission, so what the IRD
	receives is byte-identical to the 248,966 bills it has already accepted.

	Raises FiscalYearError if no record covers the date, so a missing Fiscal Year
	surfaces in the Error Log instead of a wrong year being reported to IRD.
	"""
	fy = get_fiscal_year(date=getdate(ad_date), company=company, as_dict=True)
	return fy.name


@frappe.whitelist()
def get_fiscal_year_dates(fiscal_year):
	"""AD start/end dates of a Fiscal Year, resolved on the server.

	Report filters that turn a picked fiscal year into a date window call this so
	the dates always come from the backend (the Fiscal Year record) rather than
	being computed in the browser. Returns {"from_date", "to_date"} as ISO
	strings, or {} if the fiscal year does not exist.
	"""
	fy = frappe.get_cached_value(
		"Fiscal Year",
		fiscal_year,
		["year_start_date", "year_end_date"],
		as_dict=True,
	)
	if not fy:
		return {}
	return {"from_date": str(fy.year_start_date), "to_date": str(fy.year_end_date)}


def cbms_invoice_number(sales_invoice):
	"""The number sent to CBMS as invoice_number / credit_note_number.

	This is the Sales Invoice's per-branch running number (`custom_branch_name`), which
	naming_series.py guarantees is always set — to a real branch-wise number for
	Grishma Enterprises, and to `doc.name` for every other company. Falling back to
	`doc.name` here as well only guards against that field being blank on older data.
	"""
	return getattr(sales_invoice, "custom_branch_name", None) or sales_invoice.name
