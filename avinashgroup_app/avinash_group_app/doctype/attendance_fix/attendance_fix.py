"""Attendance Fix — manual repair tool for offline-bridge gaps.

HR picks a Company and a period (a whole BS month, or a date range). On
submit, for every (employee, date) in that period we look at what's actually
in the database and reconcile it:

  - Checkins exist, no Attendance      → create Attendance, link the checkins.
  - Checkins exist, Attendance Absent  → delete stale Absent, create from checkins.
  - Checkins exist, other Attendance   → link any orphan checkins to the row
    (Present / Half Day / On Leave / WFH — never overwritten).
  - No checkins, no Attendance         → mark Absent (skipping holidays).
  - No checkins, Attendance exists     → leave it (HR may have entered it).

Shift is optional, because people here move between shifts day to day. With no
Shift Type picked, each (employee, day) is computed against the shift that
day's punches resolved to, falling back to the employee's Default Shift — the
same resolver the self-heal job and the one-day Repair button use. Picking a
Shift Type keeps the old behaviour: only that shift's roster, and every day
computed against that shift.

Each employee's days are clipped to their employment (joining to relieving
date). Without that, a month run on a new joiner marks Absent before they
existed, which HRMS rejects and logs as an error per day.

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

from rdp_common_app.utils.bs_boundaries import BS_MONTH_NAMES, ad_to_bs, get_bs_month_range

from avinashgroup_app.biometric.attendance_sync import (
    prepare_checkins_for_shift,
    refresh_attendance_values,
)


# Records submitted before the scope was widened to the whole company carry
# this value; they are read (and amended) as "All Employees".
LEGACY_ALL_SCOPE = "All Employees in Shift"

BS_MONTH_NUMBERS = {name: num for num, name in BS_MONTH_NAMES.items()}


class AttendanceFix(Document):
    def validate(self):
        if self.repair_scope == LEGACY_ALL_SCOPE:
            self.repair_scope = "All Employees"
        self.set_period_dates()
        if not (self.from_date and self.to_date):
            frappe.throw(_("Set From Date and To Date, or pick a BS Month."))
        if getdate(self.from_date) > getdate(self.to_date):
            frappe.throw(_("From Date must be on or before To Date."))
        self.validate_selected_employees()

    def set_period_dates(self):
        """Month mode: From/To Date are the BS month's first and last AD day.

        Computed here as well as in the form, so the dates can never disagree
        with the month that is shown (an API insert, or a form whose server
        call failed)."""
        if self.period != "Month":
            return
        if not (self.bs_year and self.bs_month):
            frappe.throw(_("Pick the BS Year and BS Month."))
        try:
            start, end = get_bs_month_range(int(self.bs_year), BS_MONTH_NUMBERS[self.bs_month])
        except (KeyError, ValueError):
            frappe.throw(_("{0} {1} is not a BS month the calendar knows.").format(self.bs_month, self.bs_year))
        self.from_date, self.to_date = start, end

    def validate_selected_employees(self):
        """Warn when a named employee cannot possibly be repaired by this run.

        In Selected Employees mode the list is honoured as given — the point of
        naming someone is to repair them. Two things can still make a name a
        no-op, and both are said at save time instead of being discovered in
        an empty log:

          * the employee belongs to another company (the run is company-scoped);
          * a Shift Type is picked and they are not on it — attendance is then
            computed against that shift, and prepare_checkins_for_shift only
            accepts check-ins that resolve to it.
        """
        if self.repair_scope != "Selected Employees":
            return
        if not self.employees:
            frappe.throw(
                _("Add at least one employee, or set Repair Scope to {0}.").format(
                    frappe.bold(_("All Employees"))
                )
            )

        seen = set()
        for row in self.employees:
            if row.employee in seen:
                frappe.throw(
                    _("Row {0}: {1} is listed more than once.").format(row.idx, frappe.bold(row.employee))
                )
            seen.add(row.employee)

        other_company = [
            r for r in self.employees
            if frappe.db.get_value("Employee", r.employee, "company") != self.company
        ]
        if other_company:
            frappe.throw(
                _("{0} do not belong to {1}. Remove them or change the Company.").format(
                    frappe.bold(", ".join(r.employee_name or r.employee for r in other_company[:8])),
                    frappe.bold(self.company),
                )
            )

        if not self.shift_type:
            return
        shift_doc = frappe.get_cached_doc("Shift Type", self.shift_type)
        assigned = set(
            shift_doc.get_assigned_employees(getdate(self.from_date), consider_default_shift=True)
        )
        stray = [r for r in self.employees if r.employee not in assigned]
        if stray:
            names = ", ".join(f"{r.employee_name or r.employee}" for r in stray[:8])
            more = f" (+{len(stray) - 8} more)" if len(stray) > 8 else ""
            frappe.msgprint(
                _(
                    "{0}{1} are not assigned to {2} on {3}. They will be processed, but their "
                    "check-ins will not resolve to this shift, so nothing will change for them."
                ).format(frappe.bold(names), more, frappe.bold(self.shift_type), self.from_date),
                title=_("Not on this shift"),
                indicator="orange",
            )

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
        # Lazy import: attendance_self_heal imports reconcile_employee_day from
        # this module, so a top-level import would be circular.
        from avinashgroup_app.biometric.attendance_self_heal import _resolve_shift

        shift_doc = frappe.get_doc("Shift Type", self.shift_type) if self.shift_type else None
        shift_cache = {}
        employees = self._resolve_employees(shift_doc)

        from_date = getdate(self.from_date)
        to_date = getdate(self.to_date)
        employment = _employment_spans(employees)

        counters = {
            "employees_processed": 0,
            "absent_rows_deleted": 0,
            "attendance_created_or_updated": 0,
            "checkins_relinked": 0,
        }
        log_lines: list[str] = []

        date_lists = {}
        for employee in employees:
            joined, relieved = employment.get(employee, (None, None))
            start = max(from_date, getdate(joined)) if joined else from_date
            end = min(to_date, getdate(relieved)) if relieved else to_date
            date_lists[employee] = [start + timedelta(days=i) for i in range((end - start).days + 1)]

        # Calculate total work items for progress
        total_items = sum(len(v) for v in date_lists.values())
        items_done = 0

        for emp_idx, employee in enumerate(employees):
            counters["employees_processed"] += 1
            holiday_dates = _get_holiday_dates(employee, from_date, to_date)
            date_list = date_lists[employee]

            # Publish progress update for new employee
            self._publish_progress(emp_idx, len(employees), f"Processing {employee}...")

            for d in date_list:
                savepoint = f"af_{employee}_{d}".replace("-", "_").replace(" ", "_")[:60]
                frappe.db.savepoint(savepoint)
                try:
                    day_shift = shift_doc or _resolve_shift(employee, d, shift_cache)
                    self._reconcile_day(
                        day_shift, employee, d, holiday_dates, counters, log_lines
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
        """The employees this run will walk, in one of two modes.

        All Employees — everyone in the company employed during the period; with
        a Shift Type picked, narrowed to those the stock helper reports as
        assigned to it (or carrying it as their default shift) on the start date.

        Selected Employees — exactly the names in the child table, used as given.
        They are NOT intersected with a shift's roster: someone whose assignment
        lapsed, or who was never assigned but has check-ins that resolve to this
        shift, is precisely who a targeted repair is for. validate() has already
        warned about names that cannot match.

        The company, employment-period and device filters apply to both modes.
        """
        if self.repair_scope == "Selected Employees":
            employees = [r.employee for r in (self.employees or []) if r.employee]
        elif shift_doc:
            # Stock helper returns employees with this shift assigned (or default shift).
            employees = shift_doc.get_assigned_employees(
                getdate(self.from_date), consider_default_shift=True
            )
        else:
            employees = _company_employees(self.company, self.from_date, self.to_date)
        employees = list(dict.fromkeys(employees))  # dedup, preserve order

        # Company, and employed at some point in the period: Active, or relieved
        # on/after its start (someone who left mid-month still needs that month).
        employed = set(_company_employees(self.company, self.from_date, self.to_date))
        employees = [e for e in employees if e in employed]

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

        return employees

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

    Shared by Attendance Fix (manual, HR-submitted) and the daily self-heal
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

    shift_doc may be None (Attendance Fix with no Shift Type, for an employee
    whose punches carry no shift and who has no Default Shift). An empty day
    is still marked Absent, with no shift; a day with punches is left as-is,
    because there are no rules to compute it against.
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
        marked = mark_attendance(
            employee, attendance_date, "Absent", shift_doc.name if shift_doc else None
        )
        if marked:
            _ensure_posting_date(marked, attendance_date)
            counters["attendance_created_or_updated"] += 1
            log_lines.append(f"{employee} {attendance_date}: marked Absent (no checkins)")
        return

    # Checkins exist for this day. Any non-Absent attendance (Present, Half Day,
    # On Leave, Work From Home, manual entries) is kept — we attach the orphan
    # punches to it, and for Present/Half Day also refresh the row's computed
    # values (working hours, in/out, late/early, deviations) from the full
    # punch set, so late punches correct the numbers instead of leaving them
    # stale forever. Status is changed only for policy 3.4: On Leave with
    # punches becomes Half Day. Falling through to
    # mark_attendance_and_link_log would raise DuplicateAttendanceError and
    # poison the checkins.
    if existing and existing.status != "Absent":
        if existing.status == "On Leave":
            from avinashgroup_app.biometric.attendance_override import half_day_if_came_in

            if half_day_if_came_in(employee, attendance_date):
                existing.status = "Half Day"
                counters["attendance_created_or_updated"] += 1
                log_lines.append(
                    f"{employee} {attendance_date}: came in while on leave, {existing.name} made Half Day (policy 3.4)"
                )
        orphan_names = [c.name for c in checkins if not c.attendance]
        if orphan_names:
            update_attendance_in_checkins(orphan_names, existing.name)
            counters["checkins_relinked"] += len(orphan_names)
            log_lines.append(
                f"{employee} {attendance_date}: relinked {len(orphan_names)} orphan checkin(s) to {existing.name}"
            )
        if shift_doc and existing.status in ("Present", "Half Day") and refresh_attendance_values(
            existing.name, shift_doc, checkins
        ):
            counters["attendance_created_or_updated"] += 1
            log_lines.append(
                f"{employee} {attendance_date}: refreshed values on {existing.name} from checkins"
            )
        return

    # Prepare logs BEFORE touching the existing Absent. If we can't produce a
    # replacement (no resolvable checkins for this shift, all skip_auto_attendance,
    # fetch_shift failed) we leave the Absent in place rather than nuke evidence.
    if not shift_doc:
        log_lines.append(
            f"{employee} {attendance_date}: kept existing "
            f"({existing.status if existing else 'no row'}) — punches carry no shift and "
            f"the employee has no Default Shift"
        )
        return

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


def _company_employees(company, from_date, to_date) -> list[str]:
    """Employees of the company who were employed at some point in the period:
    joined on/before its end, and either still Active or relieved on/after its
    start."""
    rows = frappe.get_all(
        "Employee",
        filters={"company": company, "status": ("!=", "Inactive")},
        fields=["name", "status", "date_of_joining", "relieving_date"],
        order_by="name asc",
    )
    from_date, to_date = getdate(from_date), getdate(to_date)
    out = []
    for r in rows:
        if r.date_of_joining and getdate(r.date_of_joining) > to_date:
            continue
        if r.status != "Active" and not (r.relieving_date and getdate(r.relieving_date) >= from_date):
            continue
        out.append(r.name)
    return out


def _employment_spans(employees) -> dict:
    """{employee: (date_of_joining, relieving_date)} — either may be None."""
    if not employees:
        return {}
    rows = frappe.get_all(
        "Employee",
        filters={"name": ("in", employees)},
        fields=["name", "date_of_joining", "relieving_date"],
    )
    return {r.name: (r.date_of_joining, r.relieving_date) for r in rows}


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


@frappe.whitelist()
def repair_attendance_day(employee, attendance_date):
	"""Reconcile ONE (employee, day) on demand, from the Attendance form.

	Attendance Fix is the bulk tool — a shift and a date range, run in a
	background worker. This is its single-record counterpart: you are looking
	at one wrong row and want that row rebuilt from the punches, without
	filing a range job to fix a single day.

	Same primitive underneath (reconcile_employee_day), so a repair means the
	same thing however it is triggered.

	Two differences from the scheduled self-heal:

	  * No shift gates. Self-heal skips shifts with auto attendance disabled
	    or a closed sync window because it must never race the realtime flow.
	    A human pressing Repair has made that judgement themselves, and the
	    tool would be useless on exactly the shifts that need it most.
	  * mark_absent_when_no_checkins stays False. Creating an Absent from an
	    empty day is a payroll decision; this button exists to make attendance
	    agree with the punches, not to invent a verdict where there are none.

	Returns what actually happened, including whether the row was REPLACED —
	a stale Absent with punches against it is deleted and rebuilt, so the
	document the user was looking at no longer exists and the form has to be
	sent somewhere new.
	"""
	frappe.only_for(("HR Manager", "System Manager"))

	attendance_date = getdate(attendance_date)
	if not frappe.db.exists("Employee", employee):
		frappe.throw(_("Employee {0} not found.").format(employee))

	# Lazy import: attendance_self_heal imports reconcile_employee_day from this
	# module, so a top-level import here would be circular.
	from avinashgroup_app.biometric.attendance_self_heal import _resolve_shift

	shift_doc = _resolve_shift(employee, attendance_date, {})
	if not shift_doc:
		frappe.throw(
			_(
				"No shift could be resolved for {0} on {1}. The day's check-ins carry no "
				"shift and the employee has no Default Shift, so there are no rules to "
				"compute attendance against. Assign a shift and try again."
			).format(frappe.bold(employee), frappe.bold(str(attendance_date))),
			title=_("No Shift"),
		)

	before = frappe.db.get_value(
		"Attendance",
		{"employee": employee, "attendance_date": attendance_date, "docstatus": ("<", 2)},
		["name", "status", "working_hours"],
		as_dict=True,
	)

	counters = {
		"attendance_created_or_updated": 0,
		"absent_rows_deleted": 0,
		"checkins_relinked": 0,
	}
	log_lines = []

	savepoint = "attendance_repair_one"
	try:
		frappe.db.savepoint(savepoint)
		reconcile_employee_day(
			shift_doc,
			employee,
			attendance_date,
			holiday_dates=frozenset(),  # a punch on a holiday still needs pairing up
			counters=counters,
			log_lines=log_lines,
			include_skipped=True,
			mark_absent_when_no_checkins=False,
		)
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		frappe.log_error(
			title=f"Attendance repair failed: {employee} {attendance_date}",
			message=frappe.get_traceback(),
		)
		raise

	after = frappe.db.get_value(
		"Attendance",
		{"employee": employee, "attendance_date": attendance_date, "docstatus": ("<", 2)},
		["name", "status", "working_hours", "in_time", "out_time"],
		as_dict=True,
	)

	changed = bool(
		counters["attendance_created_or_updated"]
		or counters["checkins_relinked"]
		or counters["absent_rows_deleted"]
	)
	return {
		"changed": changed,
		"replaced": bool(before and after and before.name != after.name),
		"shift": shift_doc.name,
		"before": before,
		"after": after,
		"counters": counters,
		"log": log_lines,
	}


@frappe.whitelist()
def get_roster(company, from_date, to_date, shift_type=None):
	"""Employees of the company employed in the period (and on the shift, if one
	is picked) — the seed list for the Selected Employees table, so it can be
	trimmed rather than typed."""
	frappe.only_for(("HR Manager", "System Manager"))
	names = _company_employees(company, from_date, to_date)
	if shift_type:
		shift_doc = frappe.get_cached_doc("Shift Type", shift_type)
		on_shift = set(shift_doc.get_assigned_employees(getdate(from_date), consider_default_shift=True))
		names = [n for n in names if n in on_shift]
	if not names:
		return []

	filters = {"name": ("in", names)}
	return frappe.get_all(
		"Employee",
		filters=filters,
		fields=["name", "employee_name", "department", "company"],
		order_by="employee_name asc",
	)


@frappe.whitelist()
def get_bs_month_dates(bs_year=None, bs_month=None):
	"""AD first/last day of a BS month, for the form's Month picker.

	With no month given, returns the current BS month — the form's default."""
	if not (bs_year and bs_month):
		today = ad_to_bs(getdate())
		bs_year, bs_month = today.year, BS_MONTH_NAMES[today.month]
	start, end = get_bs_month_range(int(bs_year), BS_MONTH_NUMBERS[bs_month])
	return {"bs_year": int(bs_year), "bs_month": bs_month, "from_date": start, "to_date": end}
