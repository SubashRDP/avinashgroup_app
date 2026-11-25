"""Pay on a 30-day month: one day is always the monthly amount ÷ 30.

The slip cut an absent day as monthly ÷ the BS month's length, so the same day
cost Basic 30,000 ÷ 29 = 1,034.48 in Poush and ÷ 32 = 937.50 in Ashadh, and
overtime and the late fine moved with it. The client wants one day's value in
every month, absent, half day and overtime alike (user, 2026-11-25), as their
Excel sheets priced it (Basic / 30 / 8).

Sets Nepal HRMS Settings → Days per Month for Pay to 30. Every reader goes
through rdp_common_app's `get_pay_days_per_month`: the slip's proration
(BSSalarySlip), overtime and late fine (payroll/attendance_allowance
`_hourly_basic`), leave encashment, and pay-rise arrears. A value HR has already
set is left alone. Submitted slips are not touched; drafts follow on next save.
"""

import frappe

PAY_DAYS_PER_MONTH = 30  # the client's month (2026-11-25)


def execute():
	if not frappe.get_meta("Nepal HRMS Settings").has_field("pay_days_per_month"):
		return
	if frappe.db.get_single_value("Nepal HRMS Settings", "pay_days_per_month"):
		return
	frappe.db.set_single_value("Nepal HRMS Settings", "pay_days_per_month", PAY_DAYS_PER_MONTH)
	frappe.clear_document_cache("Nepal HRMS Settings", "Nepal HRMS Settings")
