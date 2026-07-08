"""Self-healing pass for the attendance pipeline.

Stock HRMS auto attendance is fire-and-forget: each (employee, day) gets
exactly one attempt, and several realistic situations make that attempt fail
permanently and silently:

  F1  Device offline for days — punches arrive after HRMS already marked the
      day Absent. mark_attendance_and_link_log hits DuplicateAttendanceError
      and sets skip_auto_attendance=1 on the checkins forever; the wrong
      Absent stays.
  F2  Any ValidationError while inserting the Attendance (broken link data
      like a missing Department, a misconfigured hook) poisons the checkins
      the same way.
  F3  Punch stored while the employee had no shift assignment — the checkin
      has no `shift`, so the auto-attendance job never selects it, even
      after a shift is assigned later.

This job runs hourly and re-reconciles every (employee, day) in a bounded
lookback window that still has unlinked checkins, using the same primitives
as the Attendance Fix doctype:

  - day already Present / Half Day / On Leave / WFH → link orphan punches
  - day marked Absent → replace it with attendance computed from the punches
  - no attendance yet → create it
  - shift missing on the checkin → re-run fetch_shift first

Deliberately narrow: it never marks anyone Absent (stock HRMS owns that,
with its one-day grace period), never touches a day whose shift may still
be running, and skips days before the shift's "Process Attendance After"
go-live date. Failures roll back per-day and are retried on the next run
instead of poisoning anything.
"""

from collections import Counter
from datetime import datetime, time, timedelta

import frappe
from frappe.utils import add_days, cint, get_datetime, getdate, today

from avinashgroup_app.avinash_group_app.doctype.attendance_fix.attendance_fix import (
    reconcile_employee_day,
)

# Days with unlinked checkins older than this are left for manual review via
# Attendance Fix — an unbounded scan would rework ancient unresolvable rows
# (e.g. holiday punches, ex-employees) every hour.
LOOKBACK_DAYS = 45

# Per-run cap so a huge backlog (first run after an outage) can't starve the
# long worker; the hourly cadence drains the rest.
MAX_GROUPS_PER_RUN = 500


def heal_unlinked_checkins():
    """Hourly scheduler entry point."""
    window_start = datetime.combine(add_days(getdate(today()), -LOOKBACK_DAYS), time.min)
    window_end = datetime.combine(getdate(today()), time.min)  # strictly before today

    groups = frappe.db.sql(
        """
        SELECT employee, DATE(`time`) AS punch_date
        FROM `tabEmployee Checkin`
        WHERE IFNULL(attendance, '') = ''
          AND `time` >= %s AND `time` < %s
        GROUP BY employee, DATE(`time`)
        ORDER BY punch_date, employee
        LIMIT %s
        """,
        (window_start, window_end, MAX_GROUPS_PER_RUN),
        as_dict=True,
    )
    if not groups:
        return

    log = frappe.logger("biometric")
    shift_cache = {}
    counters = {
        "attendance_created_or_updated": 0,
        "absent_rows_deleted": 0,
        "checkins_relinked": 0,
    }
    log_lines = []
    skipped = failed = 0

    for g in groups:
        employee, day = g.employee, getdate(g.punch_date)

        shift_doc = _resolve_shift(employee, day, shift_cache)
        if (
            not shift_doc
            or not cint(shift_doc.enable_auto_attendance)
            or not shift_doc.last_sync_of_checkin
            or (
                shift_doc.process_attendance_after
                and day < getdate(shift_doc.process_attendance_after)
            )
            or not _shift_window_closed(day, shift_doc)
        ):
            skipped += 1
            continue

        savepoint = "attendance_self_heal"
        try:
            frappe.db.savepoint(savepoint)
            reconcile_employee_day(
                shift_doc,
                employee,
                day,
                holiday_dates=frozenset(),  # punches on holidays still count, like stock
                counters=counters,
                log_lines=log_lines,
                include_skipped=True,
                mark_absent_when_no_checkins=False,
            )
        except Exception:
            frappe.db.rollback(save_point=savepoint)
            failed += 1
            frappe.log_error(
                title=f"Attendance self-heal failed: {employee} {day}",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()

    if counters["attendance_created_or_updated"] or counters["checkins_relinked"] or failed:
        log.info(
            "attendance self-heal: groups=%d created/updated=%d absents_replaced=%d "
            "relinked=%d skipped=%d failed=%d",
            len(groups),
            counters["attendance_created_or_updated"],
            counters["absent_rows_deleted"],
            counters["checkins_relinked"],
            skipped,
            failed,
        )
        for line in log_lines:
            log.info("  %s", line)


def _resolve_shift(employee, day, cache):
    """Shift Type doc for this (employee, day), or None.

    Prefer what the day's checkins already resolved to; otherwise the
    employee's default shift (covers F3, where the checkins predate the
    shift assignment)."""
    day_start = datetime.combine(day, time.min)
    day_end = datetime.combine(day, time.max)
    shifts = frappe.get_all(
        "Employee Checkin",
        filters={"employee": employee, "time": ("between", [day_start, day_end])},
        pluck="shift",
    )
    named = [s for s in shifts if s]
    shift_name = (
        Counter(named).most_common(1)[0][0]
        if named
        else frappe.db.get_value("Employee", employee, "default_shift")
    )
    if not shift_name:
        return None
    if shift_name not in cache:
        cache[shift_name] = frappe.get_doc("Shift Type", shift_name)
    return cache[shift_name]


def _shift_window_closed(day, shift_doc):
    """True once this day's shift instance (including the post-shift checkout
    buffer) has fully ended before the shift's last sync — the same horizon
    stock auto attendance uses, so self-heal never races the realtime flow."""
    end_dt = datetime.combine(day, time.min) + shift_doc.end_time
    if shift_doc.end_time < shift_doc.start_time:  # overnight shift
        end_dt += timedelta(days=1)
    end_dt += timedelta(minutes=cint(shift_doc.allow_check_out_after_shift_end_time or 0))
    return end_dt < get_datetime(shift_doc.last_sync_of_checkin)
