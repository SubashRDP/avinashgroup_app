"""Attendance Fix — manual repair tool for offline-bridge gaps.

HR picks a Shift Type + date range. On submit, for every (employee, date) in
that range we look at what's actually in the database and reconcile it:

  - Checkins exist, no Attendance      → create Attendance, link the checkins.
  - Checkins exist, Attendance Absent  → delete stale Absent, create from checkins.
  - Checkins exist, other Attendance   → link any orphan checkins to the row
    (Present / Half Day / On Leave / WFH — never overwritten).
  - No checkins, no Attendance         → mark Absent (skipping holidays).
  - No checkins, Attendance exists     → leave it (HR may have entered it).

Reuses stock HRMS primitives so attendance status / working-hours computation
matches everywhere else in the system.

The per-day reconciliation lives in module-level functions (reconcile_employee_day
and friends) so the scheduled self-heal job (biometric/attendance_self_heal.py)
shares the exact same logic.
"""

from datetime import datetime, time, timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, getdate

from hrms.hr.doctype.attendance.attendance import mark_attendance
from hrms.hr.doctype.employee_checkin.employee_checkin import (
    mark_attendance_and_link_log,
    update_attendance_in_checkins,
)


class AttendanceFix(Document):
    def validate(self):
        if getdate(self.from_date) > getdate(self.to_date):
            frappe.throw(_("From Date must be on or before To Date."))

    def on_submit(self):
        """Enqueue the heavy reconciliation in the background worker.

        We never run _run_fix() inside the HTTP request — a wide range can iterate
        tens of thousands of (employee, date) pairs (each one calling stock HRMS
        mark_attendance_and_link_log, which fires every Attendance hook on the
        site). Synchronous execution times out the desk.

        Flow: on_submit returns immediately with status=Queued. The worker
        picks it up, sets Running, runs _run_fix, persists Fixed/Failed.
        """
        self.db_set("status", "Queued", update_modified=False)
        frappe.enqueue(
            "avinashgroup_app.avinash_group_app.doctype.attendance_fix.attendance_fix.run_attendance_fix_in_background",
            queue="long",
            timeout=14400,
            doc_name=self.name,
            enqueue_after_commit=True,
        )

    def on_cancel(self):
        self.db_set("status", "Pending", update_modified=False)

    # ──────────────────────────────────────────────────────────────────────

    def _run_fix(self):
        shift_doc = frappe.get_doc("Shift Type", self.shift_type)
        employees = self._resolve_employees(shift_doc)

        from_date = getdate(self.from_date)
        to_date = getdate(self.to_date)
        date_list = [from_date + timedelta(days=i) for i in range((to_date - from_date).days + 1)]

        counters = {
            "employees_processed": 0,
            "absent_rows_deleted": 0,
            "attendance_created_or_updated": 0,
            "checkins_relinked": 0,
        }
        log_lines: list[str] = []

        # Calculate total work items for progress
        total_items = len(employees) * len(date_list)
        items_done = 0

        for emp_idx, employee in enumerate(employees):
            counters["employees_processed"] += 1
            holiday_dates = _get_holiday_dates(employee, from_date, to_date)

            # Publish progress update for new employee
            self._publish_progress(emp_idx, len(employees), f"Processing {employee}...")

            for d in date_list:
                savepoint = f"af_{employee}_{d}".replace("-", "_").replace(" ", "_")[:60]
                frappe.db.savepoint(savepoint)
                try:
                    self._reconcile_day(
                        shift_doc, employee, d, holiday_dates, counters, log_lines
                    )
                except Exception as e:
                    frappe.db.rollback(save_point=savepoint)
                    log_lines.append(f"{employee} {d}: SKIPPED — {str(e)[:120]}")
                    frappe.log_error(
                        message=frappe.get_traceback(),
                        title=f"Attendance Fix {self.name}: {employee} {d}",
                    )

                items_done += 1
                if items_done % 10 == 0:  # Update every 10 items to avoid too many updates
                    progress = int((items_done / total_items) * 100) if total_items > 0 else 0
                    self._publish_progress(progress, 100, f"{items_done}/{total_items} days processed")

        self.employees_processed = counters["employees_processed"]
        self.absent_rows_deleted = counters["absent_rows_deleted"]
        self.attendance_created_or_updated = counters["attendance_created_or_updated"]
        self.checkins_relinked = counters["checkins_relinked"]
        self.log = "\n".join(log_lines[-500:])  # cap to last 500 lines

        # Final progress update
        self._publish_progress(100, 100, "✅ Reconciliation complete!")

    def _publish_progress(self, current, total, message=""):
        """Publish realtime progress update to client."""
        progress_pct = int((current / total) * 100) if total > 0 else 0
        self.db_set({
            "progress_percentage": progress_pct,
            "progress_message": message,
        }, update_modified=False)
        frappe.publish_realtime(
            "attendance_fix_progress",
            {
                "doc_name": self.name,
                "progress": progress_pct,
                "message": message,
            },
            user=self.owner
        )

    def _resolve_employees(self, shift_doc) -> list[str]:
        # Stock helper returns employees with this shift assigned (or default shift).
        employees = shift_doc.get_assigned_employees(
            getdate(self.from_date), consider_default_shift=True
        )
        employees = list(dict.fromkeys(employees))  # dedup, preserve order

        if self.employee:
            employees = [e for e in employees if e == self.employee]

        if self.company:
            employees = [
                e
                for e in employees
                if frappe.db.get_value("Employee", e, "company") == self.company
            ]

        device_serials = self._selected_device_serials()
        if device_serials:
            day_start = datetime.combine(getdate(self.from_date), time.min)
            day_end = datetime.combine(getdate(self.to_date), time.max)
            employees_with_device_checkins = set(
                frappe.get_all(
                    "Employee Checkin",
                    filters={
                        "employee": ("in", employees),
                        "time": ("between", [day_start, day_end]),
                        "device_id": ("in", device_serials),
                    },
                    pluck="employee",
                )
            )
            employees = [e for e in employees if e in employees_with_device_checkins]

        # Skip inactive employees
        active = set(
            frappe.get_all(
                "Employee",
                filters={"name": ("in", employees), "status": "Active"},
                pluck="name",
            )
        )
        return [e for e in employees if e in active]

    def _selected_device_serials(self) -> list[str]:
        """Return device serials (the value the bridge stamps on Employee Checkin.device_id)
        for each Biometric Device the user selected. Empty list = no filter."""
        device_names = [row.device for row in (self.devices or []) if row.device]
        if not device_names:
            return []
        rows = frappe.get_all(
            "Biometric Device",
            filters={"name": ("in", device_names)},
            fields=["device_serial"],
        )
        return [r.device_serial for r in rows if r.device_serial]

    def _reconcile_day(
        self, shift_doc, employee, attendance_date, holiday_dates, counters, log_lines
    ):
        reconcile_employee_day(
            shift_doc, employee, attendance_date, holiday_dates, counters, log_lines
        )


def reconcile_employee_day(
    shift_doc,
    employee,
    attendance_date,
    holiday_dates,
    counters,
    log_lines,
    include_skipped=False,
    mark_absent_when_no_checkins=True,
):
    """Reconcile one (employee, date) against whatever is in the database.

    Shared by Attendance Fix (manual, HR-submitted) and the hourly self-heal
    job (biometric/attendance_self_heal.py).

    include_skipped: also consider checkins flagged skip_auto_attendance=1.
        Stock HRMS sets that flag permanently whenever attendance creation
        fails (e.g. DuplicateAttendanceError on a day already marked Absent,
        or any ValidationError) — for repair flows those are exactly the
        checkins that need processing. The flag is cleared on the logs that
        end up linked to an attendance.
    mark_absent_when_no_checkins: the self-heal job passes False — marking
        absentees is stock HRMS's job; self-heal only acts on days that have
        punches.
    """
    if attendance_date in holiday_dates:
        return

    day_start = datetime.combine(attendance_date, time.min)
    day_end = datetime.combine(attendance_date, time.max)

    checkins = frappe.get_all(
        "Employee Checkin",
        filters={
            "employee": employee,
            "time": ("between", [day_start, day_end]),
        },
        fields=[
            "name",
            "employee",
            "log_type",
            "time",
            "shift",
            "shift_start",
            "shift_end",
            "shift_actual_start",
            "shift_actual_end",
            "device_id",
            "attendance",
            "skip_auto_attendance",
        ],
        order_by="time asc",
    )

    existing = frappe.db.get_value(
        "Attendance",
        {
            "employee": employee,
            "attendance_date": attendance_date,
            "docstatus": ("<", 2),
        },
        ["name", "status", "docstatus"],
        as_dict=True,
    )

    if not checkins:
        if existing or not mark_absent_when_no_checkins:
            return  # leave as-is
        marked = mark_attendance(employee, attendance_date, "Absent", shift_doc.name)
        if marked:
            _ensure_posting_date(marked, attendance_date)
            counters["attendance_created_or_updated"] += 1
            log_lines.append(f"{employee} {attendance_date}: marked Absent (no checkins)")
        return

    # Checkins exist for this day. Any non-Absent attendance (Present, Half Day,
    # On Leave, Work From Home, manual entries) is kept — we only attach the
    # orphan punches to it. Falling through to mark_attendance_and_link_log
    # here would raise DuplicateAttendanceError and poison the checkins.
    if existing and existing.status != "Absent":
        orphan_names = [c.name for c in checkins if not c.attendance]
        if orphan_names:
            update_attendance_in_checkins(orphan_names, existing.name)
            counters["checkins_relinked"] += len(orphan_names)
            log_lines.append(
                f"{employee} {attendance_date}: relinked {len(orphan_names)} orphan checkin(s) to {existing.name}"
            )
        return

    # Prepare logs BEFORE touching the existing Absent. If we can't produce a
    # replacement (no resolvable checkins for this shift, all skip_auto_attendance,
    # fetch_shift failed) we leave the Absent in place rather than nuke evidence.
    prepared_logs = prepare_checkins_for_shift(checkins, shift_doc, include_skipped)
    if not prepared_logs:
        log_lines.append(
            f"{employee} {attendance_date}: kept existing "
            f"({existing.status if existing else 'no row'}) — no checkins resolvable to this shift"
        )
        return

    if existing and existing.status == "Absent":
        cancel_and_delete_attendance(existing)
        counters["absent_rows_deleted"] += 1
        existing = None

    (
        status,
        working_hours,
        late_entry,
        early_exit,
        in_time,
        out_time,
    ) = shift_doc.get_attendance(prepared_logs)

    attendance = mark_attendance_and_link_log(
        prepared_logs,
        status,
        attendance_date,
        working_hours,
        late_entry,
        early_exit,
        in_time,
        out_time,
        shift_doc.name,
    )
    if attendance:
        _ensure_posting_date(attendance, attendance_date)
        # Linked logs are no longer skipped — clear stale poison flags so the
        # data reads consistently.
        for c in prepared_logs:
            if c.skip_auto_attendance:
                frappe.db.set_value(
                    "Employee Checkin", c.name, "skip_auto_attendance", 0,
                    update_modified=False,
                )
        counters["attendance_created_or_updated"] += 1
        log_lines.append(
            f"{employee} {attendance_date}: created {attendance.name} ({status}, "
            f"hours={flt(working_hours, 2)})"
        )
    else:
        # mark_attendance_and_link_log swallowed a ValidationError and poisoned
        # the logs (comment added on each checkin by stock HRMS).
        log_lines.append(
            f"{employee} {attendance_date}: attendance creation rejected by HRMS — see checkin comments"
        )


def _ensure_posting_date(attendance, attendance_date):
    """Some deployments add a posting_date custom field on Attendance; set it
    only when the field actually exists. `attendance` may be a doc
    (mark_attendance_and_link_log) or a name string (mark_attendance)."""
    if not frappe.get_meta("Attendance").has_field("posting_date"):
        return
    name = attendance if isinstance(attendance, str) else attendance.name
    if not frappe.db.get_value("Attendance", name, "posting_date"):
        frappe.db.set_value(
            "Attendance", name, "posting_date", attendance_date, update_modified=False
        )


def prepare_checkins_for_shift(checkins, shift_doc, include_skipped=False):
    """Make sure each checkin has shift fields populated. We call stock
    Employee Checkin.fetch_shift() if shift is missing, mirroring what the
    scheduled auto-attendance does. Re-fetching also repairs checkins stored
    before the employee had a shift assignment."""
    prepared = []
    for c in checkins:
        if c.skip_auto_attendance and not include_skipped:
            continue
        if not c.shift or not c.shift_actual_end:
            ck_doc = frappe.get_doc("Employee Checkin", c.name)
            ck_doc.fetch_shift()
            ck_doc.db_update()
            c.shift = ck_doc.shift
            c.shift_start = ck_doc.shift_start
            c.shift_end = ck_doc.shift_end
            c.shift_actual_start = ck_doc.shift_actual_start
            c.shift_actual_end = ck_doc.shift_actual_end

        if c.shift != shift_doc.name:
            continue
        prepared.append(c)
    return prepared


def cancel_and_delete_attendance(existing):
    if existing.docstatus == 1:
        att = frappe.get_doc("Attendance", existing.name)
        att.flags.ignore_permissions = True
        att.cancel()
    frappe.delete_doc(
        "Attendance", existing.name, force=True, ignore_permissions=True
    )


def run_attendance_fix_in_background(doc_name: str):
    """Background worker entry point.

    Opens the queued Attendance Fix doc, flips status to Running, executes
    _run_fix(), and persists Fixed/Failed plus counters and log.

    Runs as Administrator so HR users without write-on-submit perms don't
    block the worker, and so stock HRMS helpers that do their own
    permission checks don't fail mid-loop.
    """
    frappe.set_user("Administrator")

    doc = frappe.get_doc("Attendance Fix", doc_name)
    if doc.docstatus != 1:
        return  # cancelled/amended before worker picked it up
    if doc.status not in ("Queued", "Running"):
        return  # already finished — don't redo

    doc.db_set("status", "Running", update_modified=False)
    frappe.db.commit()

    # The worker runs as Administrator (above), but audit fields on the
    # Attendance rows it creates should credit whoever created this fix.
    frappe.flags.audit_user = doc.owner

    try:
        doc._run_fix()
        doc.db_set(
            {
                "status": "Fixed",
                "employees_processed": doc.employees_processed,
                "absent_rows_deleted": doc.absent_rows_deleted,
                "attendance_created_or_updated": doc.attendance_created_or_updated,
                "checkins_relinked": doc.checkins_relinked,
                "log": doc.log,
            },
            update_modified=False,
        )
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        traceback = frappe.get_traceback()
        doc.db_set(
            {
                "status": "Failed",
                "log": (doc.log or "") + "\n\nFATAL:\n" + traceback[-4000:],
            },
            update_modified=False,
        )
        frappe.db.commit()
        frappe.log_error(message=traceback, title=f"Attendance Fix {doc_name} failed")
        raise
    finally:
        frappe.flags.audit_user = None


def _get_holiday_dates(employee, from_date, to_date) -> set:
    holiday_list = frappe.db.get_value("Employee", employee, "holiday_list")
    if not holiday_list:
        company = frappe.db.get_value("Employee", employee, "company")
        if company:
            holiday_list = frappe.db.get_value("Company", company, "default_holiday_list")
    if not holiday_list:
        return set()
    rows = frappe.get_all(
        "Holiday",
        filters={
            "parent": holiday_list,
            "holiday_date": ("between", [from_date, to_date]),
        },
        pluck="holiday_date",
    )
    return {getdate(d) for d in rows}
