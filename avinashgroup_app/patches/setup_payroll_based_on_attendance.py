"""Pay follows attendance, not just approved leave.

Payroll Settings shipped as "Payroll Based On: Leave", so a salary slip only lost
pay for an approved Leave Application. Attendance was never read — which made two
rules the client asked for cost nothing at all:

  * more than 2 hours late is a half day (policy 1.2)
  * absent is absent

On nepalgas one employee with 22 half days and 2 absences in Bhadra was paid 31
days of 31. With "Attendance" he is paid 18: each half day costs half a day
(daily_wages_fraction_for_half_day = 0.5) and each absence a whole one. Approved
leave is still paid, because HRMS marks those days On Leave rather than Absent.

The trade this makes: attendance becomes the source of truth for pay, so a missing
punch is a pay cut until it is repaired — which is what the hourly self-heal job
and Attendance Fix are for.
"""

import frappe


def execute():
	frappe.db.set_single_value("Payroll Settings", "payroll_based_on", "Attendance")
	frappe.db.set_single_value("Payroll Settings", "daily_wages_fraction_for_half_day", 0.5)
