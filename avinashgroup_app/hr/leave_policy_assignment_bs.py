"""Leave Policy Assignment made mid-year: back-fill earned leave in BS months.

When a policy is assigned after the leave year has started — a joiner, a
probationer confirmed in Kartik, a late correction — HRMS credits the months
already gone at once (`LeavePolicyAssignment.get_leaves_for_passed_months`).
It counts them in AD months (`get_last_day`, `date.month`), while the monthly
instalments that follow come from `hr.utils.allocate_earned_leaves_bs`, on BS
months. The two disagree:

  Assigned 10 October 2026 (24 Ashwin 2083) for a year starting 1 Shrawan: BS
  has completed Shrawan and Bhadra — two instalments. HRMS counts July, August
  and September — three — and on 30 Ashwin the BS job adds Ashwin on top. The
  employee holds one month more than the policy gives, for the rest of the year.

This override counts the back-fill the way the BS job would have credited it
had the assignment existed from the start: one instalment for every BS month
whose credit day (its first or last day, per the leave type) is on or before
today, the joining month pro-rated over its BS days. Everything else — the
annual cap, rounding, allocation, ledger — stays HRMS's.

Deliberately narrow: Monthly earned leave with First Day / Last Day only,
the same configurations the BS accrual job handles. Anything else keeps the
stock calculation, exactly as that job leaves it alone.

Registered in `hooks.py` → `override_doctype_class`.
"""

import datetime

import frappe
from frappe.utils import flt, getdate

from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import LeavePolicyAssignment
from hrms.hr.utils import get_monthly_earned_leave

from avinashgroup_app.hr.utils import SUPPORTED_ALLOCATE_ON_DAY, SUPPORTED_FREQUENCY
from rdp_common_app.utils.bs_boundaries import get_bs_month_end, get_bs_month_start


class BSLeavePolicyAssignment(LeavePolicyAssignment):
	def get_leaves_for_passed_months(self, annual_allocation, leave_details, date_of_joining):
		if (
			leave_details.earned_leave_frequency != SUPPORTED_FREQUENCY
			or leave_details.allocate_on_day not in SUPPORTED_ALLOCATE_ON_DAY
		):
			return super().get_leaves_for_passed_months(annual_allocation, leave_details, date_of_joining)

		return bs_months_backfill(
			annual_allocation,
			leave_details,
			getdate(date_of_joining),
			getdate(self.effective_from),
			getdate(self.effective_to),
			getdate(frappe.flags.current_date or getdate()),
		)


def bs_months_backfill(annual_allocation, leave_details, date_of_joining, effective_from, effective_to, today):
	"""Leave the BS accrual job would have credited from `effective_from` to `today`."""
	start = max(effective_from, date_of_joining)
	month_start = getdate(get_bs_month_start(start))
	total = 0.0
	while month_start <= min(today, effective_to):
		month_end = getdate(get_bs_month_end(month_start))
		credit_day = month_end if leave_details.allocate_on_day == "Last Day" else month_start
		if credit_day > today:
			break
		# A First Day credit that fell before the person was on the policy was
		# never theirs; the BS job would not have given it either.
		if credit_day >= start or leave_details.allocate_on_day == "Last Day":
			total += get_monthly_earned_leave(
				date_of_joining,
				annual_allocation,
				leave_details.earned_leave_frequency,
				leave_details.rounding,
				period_start_date=month_start,
				period_end_date=month_end,
			)
		month_start = month_end + datetime.timedelta(days=1)
	return flt(total)
