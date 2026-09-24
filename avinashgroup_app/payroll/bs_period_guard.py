"""A payroll run pays the BS month its posting date falls in — make that explicit.

The BS salary slip (`rdp_common_app...salary_slip_bs.BSSalarySlip.get_date_details`)
always recomputes a slip's start and end from its POSTING DATE, and a slip
created by a Payroll Entry takes the entry's posting date. Pay Bhadra's salary
on 2 Ashwin — the normal thing to do — and every slip silently becomes an
Ashwin slip: Ashwin's days, Ashwin's attendance, Ashwin's allowance rows, while
the entry itself still says Bhadra.

This refuses the mismatch at the two places it can enter:

  * Payroll Entry — its start and end must be the BS month of its posting date,
    with a message that says which date to use instead.
  * Salary Slip — a slip made from an entry must cover the entry's period.

It does not move dates for anyone; which month is meant is the user's call.
The slip's own calculation stays in rdp_common_app, which this app does not
edit. Runs only when BS payroll is on (Nepal HRMS Settings).

Hooked in `hooks.py` (doc_events → validate).
"""

import frappe
from frappe import _
from frappe.utils import formatdate, getdate

from rdp_common_app.nepal_hrms_common.doctype.nepal_bs_period.nepal_bs_period import (
	get_user_defined_period,
)
from rdp_common_app.nepal_hrms_common.doctype.nepal_hrms_settings.nepal_hrms_settings import (
	is_bs_payroll_enabled,
)
from rdp_common_app.utils.bs_boundaries import ad_to_bs, get_bs_month_name, get_salary_period


def period_for(posting_date, company):
	"""The BS period a slip posted on this date will cover — the slip's own rule."""
	return get_user_defined_period(getdate(posting_date), company) or get_salary_period(getdate(posting_date))


def _label(date):
	bs = ad_to_bs(getdate(date))
	return f"{get_bs_month_name(bs.month)} {bs.year}"


def validate_payroll_entry(doc, method=None):
	if not doc.posting_date or not doc.start_date or not is_bs_payroll_enabled(doc.company):
		return
	period = period_for(doc.posting_date, doc.company)
	if getdate(doc.start_date) == getdate(period.start_date) and getdate(doc.end_date) == getdate(period.end_date):
		return

	paying = _label(doc.start_date)
	frappe.throw(
		_(
			"This entry pays {0} ({1} – {2}) but is posted on {3}, which is in {4}. "
			"Every salary slip takes its month from the posting date, so the slips would "
			"be {4} slips. Post it inside {0} — for example on its last day, {5}."
		).format(
			paying,
			formatdate(doc.start_date),
			formatdate(doc.end_date),
			formatdate(doc.posting_date),
			_label(doc.posting_date),
			formatdate(doc.end_date),
		),
		title=_("Posting date is in another BS month"),
	)


def validate_salary_slip(doc, method=None):
	if not doc.payroll_entry or not doc.start_date:
		return
	entry = frappe.db.get_value("Payroll Entry", doc.payroll_entry, ["start_date", "end_date"], as_dict=True)
	if not entry or not entry.start_date:
		return
	if getdate(doc.start_date) != getdate(entry.start_date):
		frappe.throw(
			_("Salary slip covers {0} but its payroll entry {1} pays {2}. Fix the entry's posting date.").format(
				_label(doc.start_date), doc.payroll_entry, _label(entry.start_date)
			),
			title=_("Slip and payroll entry disagree on the month"),
		)
