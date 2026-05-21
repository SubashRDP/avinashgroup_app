"""Attendance Fix — manual repair tool for offline-bridge gaps.

HR picks a Shift Type + date range. On submit, for every (employee, date) in
that range we look at what's actually in the database and reconcile it:

  - Checkins exist, no Attendance      → create Attendance, link the checkins.
  - Checkins exist, Attendance Absent  → delete stale Absent, create from checkins.
  - Checkins exist, Attendance Present → link any orphan checkins to the row.
  - No checkins, no Attendance         → mark Absent (skipping holidays).
  - No checkins, Attendance exists     → leave it (HR may have entered it).

Reuses stock HRMS primitives so attendance status / working-hours computation
matches everywhere else in the system.
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
        try:
            self._run_fix()
            self.db_set("status", "Fixed", update_modified=False)
        except Exception:
            self.db_set("status", "Failed", update_modified=False)
            frappe.log_error(
                title=f"Attendance Fix failed: {self.name}",
                message=frappe.get_traceback(),
            )
            raise

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

        for employee in employees:
            counters["employees_processed"] += 1
            holiday_dates = _get_holiday_dates(employee, from_date, to_date)
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

        self.employees_processed = counters["employees_processed"]
        self.absent_rows_deleted = counters["absent_rows_deleted"]
        self.attendance_created_or_updated = counters["attendance_created_or_updated"]
        self.checkins_relinked = counters["checkins_relinked"]
        self.log = "\n".join(log_lines[-500:])  # cap to last 500 lines

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
            if existing:
                return  # leave as-is
            marked = mark_attendance(employee, attendance_date, "Absent", shift_doc.name)
            if marked:
                counters["attendance_created_or_updated"] += 1
                log_lines.append(f"{employee} {attendance_date}: marked Absent (no checkins)")
            return

        # Checkins exist for this day.
        if existing and existing.status in ("Present", "Half Day"):
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
        prepared_logs = self._prepare_checkins_for_shift(checkins, shift_doc)
        if not prepared_logs:
            log_lines.append(
                f"{employee} {attendance_date}: kept existing "
                f"({existing.status if existing else 'no row'}) — no checkins resolvable to this shift"
            )
            return

        if existing and existing.status == "Absent":
            self._cancel_and_delete(existing)
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
            counters["attendance_created_or_updated"] += 1
            log_lines.append(
                f"{employee} {attendance_date}: created {attendance.name} ({status}, "
                f"hours={flt(working_hours, 2)})"
            )

    def _prepare_checkins_for_shift(self, checkins, shift_doc):
        """Make sure each checkin has shift fields populated. We call stock
        Employee Checkin.fetch_shift() if shift is missing, mirroring what the
        scheduled auto-attendance does."""
        prepared = []
        for c in checkins:
            if c.skip_auto_attendance:
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

    def _cancel_and_delete(self, existing):
        if existing.docstatus == 1:
            att = frappe.get_doc("Attendance", existing.name)
            att.flags.ignore_permissions = True
            att.cancel()
        frappe.delete_doc(
            "Attendance", existing.name, force=True, ignore_permissions=True
        )


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
