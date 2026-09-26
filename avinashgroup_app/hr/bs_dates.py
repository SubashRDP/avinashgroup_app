"""BS (miti) dates beside the AD dates on the HR forms, and the slip's BS month.

HR, staff and the salary sheet all speak Bikram Sambat ("leave from 12 Asoj",
"Bhadra's salary"), but Leave Application, Payroll Entry, Employee and Salary
Slip showed only AD dates, so every reader converted in their head.

The desk side is rdp_common_app's existing Bs Conversion mechanism (a Nepali
date picker bound to a `custom_*_miti` Data field, both directions), the same
one Journal Entry and Payment Entry use; patches/setup_hr_bs_dates.py registers
these doctypes with it. This module is the server side: on every validate it
writes each miti from its AD date, so documents made by Payroll Entry, bulk
tools, imports or the API carry them too, and a typed miti can never disagree
with the AD date it mirrors (AD is authoritative).

`Salary Slip.custom_bs_month` ("Bhadra 2083") is what the BS payslip print
format and the salary-slip email subject show.

A mirror, so it fails quietly: a conversion error is logged with the document
name and never blocks the save it is decorating.
"""

import frappe
from frappe.utils import getdate

from rdp_common_app.utils.bs_boundaries import ad_to_bs, get_bs_month_name

# doctype → (AD field, miti field). The single source for this module, the
# setup patch (which creates the fields) and the Bs Conversion records.
BS_DATE_FIELDS = {
	"Leave Application": (
		("from_date", "custom_from_miti", "From Date (BS)"),
		("to_date", "custom_to_miti", "To Date (BS)"),
		("posting_date", "custom_posting_miti", "Posting Date (BS)"),
	),
	"Payroll Entry": (
		("posting_date", "custom_posting_miti", "Posting Date (BS)"),
		("start_date", "custom_start_miti", "Start Date (BS)"),
		("end_date", "custom_end_miti", "End Date (BS)"),
	),
	"Employee": (
		("date_of_birth", "custom_birth_miti", "Date of Birth (BS)"),
		("date_of_joining", "custom_joining_miti", "Date of Joining (BS)"),
		("relieving_date", "custom_relieving_miti", "Relieving Date (BS)"),
	),
	"Salary Slip": (
		("posting_date", "custom_posting_miti", "Posting Date (BS)"),
		("start_date", "custom_start_miti", "Start Date (BS)"),
		("end_date", "custom_end_miti", "End Date (BS)"),
	),
}


def to_miti(ad_date):
	"""'2083-06-11' for an AD date; None when blank or outside the BS calendar.

	Placeholder dates exist in real data (birth dates of 1900-01-01 on avinas1),
	and the converter only covers about 1913-2043 AD. Such a date simply has no
	miti; it must not cost the document its other BS dates.
	"""
	if not ad_date:
		return None
	try:
		bs = ad_to_bs(getdate(ad_date))
	except ValueError:
		return None
	return f"{bs.year:04d}-{bs.month:02d}-{bs.day:02d}"


def bs_month_label(ad_date):
	"""'Bhadra 2083' for the BS month an AD date falls in."""
	bs = ad_to_bs(getdate(ad_date))
	return f"{get_bs_month_name(bs.month)} {bs.year}"


def set_bs_dates(doc, method=None):
	"""Write every miti from its AD date. Hook: validate on the doctypes above."""
	try:
		for ad_field, miti_field, _label in BS_DATE_FIELDS.get(doc.doctype, ()):
			doc.set(miti_field, to_miti(doc.get(ad_field)))
		if doc.doctype == "Salary Slip" and doc.get("end_date"):
			# The month a slip pays is the month its period ends in (BS periods
			# may be overridden per company, but always end inside their month).
			doc.custom_bs_month = bs_month_label(doc.end_date)
	except Exception:
		frappe.log_error(
			title=f"BS date mirror failed: {doc.doctype}",
			message=f"{doc.name or '(new)'}\n{frappe.get_traceback()}",
		)
