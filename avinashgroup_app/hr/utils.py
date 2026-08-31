"""Shared HR helpers, mirroring hrms.hr.utils.

Two things live here today:

  resolve_holiday_lists  -- employee -> holiday list, honouring the company
                            fallback, in one query for a whole roster
  allocate_earned_leaves_bs -- monthly earned-leave accrual on BS months

--------------------------------------------------------------------------
Monthly earned-leave accrual on Bikram Sambat months
--------------------------------------------------------------------------

Stock HRMS accrues earned leave on Gregorian month boundaries. `allocate_on_day`
= "Last Day" resolves through `frappe.utils.get_last_day`, so the instalment
lands on 31 August rather than on the last day of Shrawan. For books that run
Shrawan -> Ashad this is wrong twice over:

  W1  Every credit is 14-17 days late, so an employee's leave balance and their
      payroll month never line up. Leave earned in Shrawan appears halfway
      through Bhadra.

  W2  The final instalment never happens at all. HRMS only accrues into an
      allocation while `today <= allocation.to_date` (hrms/hr/utils.py:478). A
      leave year ending 2027-07-16 is already expired when the stock job looks
      for the Ashad credit on 2027-07-31, so the allocation is skipped and
      **every employee silently receives 11 of their 12 days, every year.**

This module runs the same accrual with one substitution: the "is today the
day?" test uses BS month boundaries instead of AD ones. Everything downstream —
the instalment size, `max_leaves_allowed` capping, the annual-allocation guard,
pro-rating for mid-year joiners, the ledger write and the audit comment — is
HRMS's own `update_previous_leave_allocation`, called unchanged. We replace the
calendar, not the policy.

Deliberately narrow:

  - Monthly frequency only. Quarterly/Half-Yearly/Yearly are refused, because
    the stock frequency check they share reads inverted in 15.49.2
    (hrms/hr/utils.py:526-531 fires when the month count is *not* a multiple of
    3/6/12). Fixing that is a separate decision from changing the calendar.
  - Allocation, expiry and encashment are untouched. This job only ever adds.
  - It never creates an allocation. No allocation, no accrual — same as stock.

## Installation

This job REPLACES `hrms.hr.utils.allocate_earned_leaves`. Both running would
double-credit. Stop the stock job once per site:

    bench --site <site> set-value "Scheduled Job Type" \
        <name-of-hrms.hr.utils.allocate_earned_leaves> stopped 1

and register this one in hooks.py under `scheduler_events` -> `daily_long`:

    "avinashgroup_app.hr.utils.allocate_earned_leaves_bs"

`bin/verify_bs_accrual.py`-style checking is not provided; use
`preview_accrual_dates()` below to see what a given leave year will credit.
"""

import frappe
from frappe.utils import getdate

from rdp_common_app.utils.bs_boundaries import (
    ad_to_bs,
    get_bs_month_end,
    get_bs_month_start,
    BS_MONTH_NAMES,
)


# Which `allocate_on_day` values this job understands. "Date of Joining" is
# excluded on purpose: a BS joining day of 31 or 32 does not exist in every BS
# month, so an anniversary-based credit would silently skip months. Employees
# on that setting keep the stock behaviour and should be moved to Last Day.
SUPPORTED_ALLOCATE_ON_DAY = ("First Day", "Last Day")

# Only Monthly is honoured — see the module docstring.
SUPPORTED_FREQUENCY = "Monthly"


def allocate_earned_leaves_bs():
    """Credit one BS-monthly instalment to every eligible Leave Allocation.

    Registered as a `daily_long` scheduler event. Runs every day and does
    nothing on all but one day of each BS month. Safe to run twice on the same
    day: HRMS's `update_previous_leave_allocation` is a no-op once the
    allocation already holds the target total.
    """
    from hrms.hr.utils import (
        get_earned_leaves,
        get_leave_allocations,
        update_previous_leave_allocation,
    )

    today = frappe.flags.current_date or getdate()

    for leave_type in get_earned_leaves():
        if not _is_accrual_day(leave_type, today):
            continue

        for allocation in get_leave_allocations(today, leave_type.name):
            annual_allocation, date_of_joining = _get_policy_details(allocation, leave_type.name)
            if annual_allocation is None:
                continue

            try:
                update_previous_leave_allocation(
                    allocation, annual_allocation, leave_type, date_of_joining
                )
            except Exception:
                # One bad allocation must not stop the other 294. The failure is
                # logged with the allocation name so it can be replayed by hand.
                frappe.db.rollback()
                frappe.log_error(
                    title="BS earned leave: accrual failed",
                    message=f"allocation={allocation.name} leave_type={leave_type.name} "
                    f"date={today}\n{frappe.get_traceback()}",
                )
            else:
                frappe.db.commit()


def _is_accrual_day(leave_type, today) -> bool:
    """True when `today` is this leave type's credit day in the BS month.

    Returns False for any configuration this job does not handle, so those
    leave types simply never accrue here rather than accruing on a wrong date.
    """
    if leave_type.earned_leave_frequency != SUPPORTED_FREQUENCY:
        return False
    if leave_type.allocate_on_day not in SUPPORTED_ALLOCATE_ON_DAY:
        return False

    today = getdate(today)
    if leave_type.allocate_on_day == "First Day":
        return today == getdate(get_bs_month_start(today))
    return today == getdate(get_bs_month_end(today))


def _get_policy_details(allocation, leave_type_name):
    """Resolve the annual allocation and joining date behind one allocation.

    Returns `(annual_allocation, date_of_joining)`, or `(None, None)` when the
    allocation has no policy behind it — a hand-made allocation accrues nothing,
    because there is no annual figure to divide.
    """
    leave_policy = allocation.leave_policy
    if not leave_policy and allocation.leave_policy_assignment:
        leave_policy = frappe.db.get_value(
            "Leave Policy Assignment", allocation.leave_policy_assignment, "leave_policy"
        )
    if not leave_policy:
        return None, None

    annual_allocation = frappe.db.get_value(
        "Leave Policy Detail",
        {"parent": leave_policy, "leave_type": leave_type_name},
        "annual_allocation",
    )
    if annual_allocation is None:
        return None, None

    date_of_joining = frappe.db.get_value("Employee", allocation.employee, "date_of_joining")
    return annual_allocation, date_of_joining


@frappe.whitelist()
def preview_accrual_dates(from_date, to_date, allocate_on_day="Last Day"):
    """List the credit dates this job will fire on between two AD dates.

    Read-only. Use it to sanity-check a leave year before switching a leave type
    over, and to show HR when their staff will actually see each instalment:

        bench --site <site> console
        >>> from avinashgroup_app.hr.utils import preview_accrual_dates
        >>> for r in preview_accrual_dates("2026-07-17", "2027-07-16"):
        ...     print(r["bs_month"], r["bs_date"], r["ad_date"])
    """
    from frappe.utils import add_days

    rows, seen = [], set()
    day, last = getdate(from_date), getdate(to_date)

    while day <= last:
        bs = ad_to_bs(day)
        key = (bs.year, bs.month)
        if key not in seen:
            seen.add(key)
            credit = getdate(
                get_bs_month_start(day) if allocate_on_day == "First Day" else get_bs_month_end(day)
            )
            if from_date <= str(credit) <= str(last):
                credit_bs = ad_to_bs(credit)
                rows.append(
                    {
                        "bs_month": BS_MONTH_NAMES[credit_bs.month],
                        "bs_date": f"{credit_bs.year}-{credit_bs.month:02d}-{credit_bs.day:02d}",
                        "ad_date": str(credit),
                    }
                )
        day = add_days(day, 1)

    return rows


# ---------------------------------------------------------------------------
# Holiday list resolution
# ---------------------------------------------------------------------------

def resolve_holiday_lists(employees) -> dict:
    """Map each employee to the Holiday List that actually applies to them.

    `Employee.holiday_list` is blank for almost everyone here -- the list is set
    once on the Company and inherited. ERPNext resolves that fallback in
    `get_holiday_list_for_employee`, and so does this app's `set_holiday_flag`,
    but any code reading `Employee.holiday_list` directly sees a blank and
    concludes the employee has no holidays at all. In a report that turns every
    Saturday and every festival into a working day, silently.

    Priority, per employee:
      1. their own `holiday_list`      -- someone on a different roster
      2. their company's `default_holiday_list`
      3. nothing, and they have no holidays

    Takes an iterable of dicts/objects carrying `name`, `holiday_list` and
    `company` (what the reports already select) and resolves the whole roster
    with one query for the company defaults, rather than one per employee the
    way `get_holiday_list_for_employee` does.

    Returns `{employee_name: holiday_list_or_None}`.
    """
    get = lambda e, f: e.get(f) if isinstance(e, dict) else getattr(e, f, None)

    companies = {get(e, "company") for e in employees if not get(e, "holiday_list")}
    companies.discard(None)

    defaults = {}
    if companies:
        defaults = {
            row.name: row.default_holiday_list
            for row in frappe.get_all(
                "Company",
                filters={"name": ["in", list(companies)]},
                fields=["name", "default_holiday_list"],
            )
        }

    return {
        get(e, "name"): get(e, "holiday_list") or defaults.get(get(e, "company"))
        for e in employees
    }
