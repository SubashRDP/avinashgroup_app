"""Stop the stock earned-leave job; this app credits on Bikram Sambat months.

The leave year runs Shrawan -> Ashad, so `hrms.hr.utils.allocate_earned_leaves`
is wrong twice over on these books (see `avinashgroup_app/hr/utils.py`):

  * every instalment lands 14-17 days late, on the Gregorian month end, so a
    balance never matches the payroll month it belongs to;
  * the Ashad instalment never runs at all — by 31 July the leave year that
    ended on 16 July is expired, HRMS skips the allocation, and every employee
    quietly receives 11 of their 12 instalments, every year.

`allocate_earned_leaves_bs` is registered in hooks.py as a `daily_long` event.
Both jobs running would credit twice, so this stops the stock Scheduled Job
Type. Idempotent, and it does nothing on a site where HRMS is not installed.
"""

import frappe

STOCK_JOB_METHOD = "hrms.hr.utils.allocate_earned_leaves"


def execute():
	for name in frappe.get_all("Scheduled Job Type", {"method": STOCK_JOB_METHOD}, pluck="name"):
		if not frappe.db.get_value("Scheduled Job Type", name, "stopped"):
			frappe.db.set_value("Scheduled Job Type", name, "stopped", 1)
			frappe.logger().info(f"[BS leave accrual] stopped stock job {name}")
