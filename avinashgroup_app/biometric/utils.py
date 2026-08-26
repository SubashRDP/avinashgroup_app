import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime
from datetime import datetime
from collections import defaultdict

from avinashgroup_app.biometric.attendance_sync import desired_log_type, sync_day

# Fallback de-duplication window (seconds) when the sending device has no
# Duplicate Threshold configured. Matches the Biometric Device field default.
DEFAULT_DUPLICATE_THRESHOLD_SECONDS = 60


def assert_known_device(serial: str) -> str:
    """Reject punches from unregistered or disabled biometric devices.

    Looks up Biometric Device by `device_serial` (the hardware serial the
    bridge / ADMS push sends) and requires `enabled = 1`. Raises
    PermissionError (HTTP 403) and writes one Error Log entry on miss.

    Returns the Biometric Device record name on success.
    """
    serial = (serial or "").strip()
    if not serial:
        frappe.log_error(
            title="Biometric Device Rejected",
            message="Empty device serial in request.",
        )
        frappe.throw(_("Device serial is required."), frappe.PermissionError)

    name = frappe.db.get_value(
        "Biometric Device",
        {"device_serial": serial, "enabled": 1},
        "name",
    )
    if not name:
        frappe.log_error(
            title="Biometric Device Rejected",
            message=f"Unregistered or disabled device serial: {serial!r}",
        )
        frappe.throw(
            _("Device serial {0} is not registered or is disabled.").format(serial),
            frappe.PermissionError,
        )
    return name


def resolve_employee_for_punch(user_id, device_company=None, device_name=None):
    """Find the Employee a punch belongs to. Two steps, in this order.

    1. An employee of the device's OWN company whose ``attendance_device_id``
       is ``user_id``. This is the normal path and always wins. (A device with
       no company set — legacy — matches across all companies here.)
    2. Only on a miss: the device's ``allowed_employees`` list, the employees of
       OTHER companies cleared to punch on this device. A row matches when its
       ``device_user_id`` equals ``user_id``, or — when that is blank — when the
       employee's own ``attendance_device_id`` does.

    Step 2 is unreachable for any ID step 1 could answer, so a visitor can never
    shadow one of the host company's own staff. Together with
    ``BiometricDevice.validate_allowed_employees`` (which refuses to save a list
    where two rows claim one ID, or where an ID is already taken by the host
    company) the result is unambiguous by construction — the matching side never
    has to guess, the same guarantee ``validate_unique_device_id`` gives within
    a company.

    Returns a dict of name / employee_name / company / default_shift, or None.
    """
    fields = ["name", "employee_name", "company", "default_shift"]

    emp_filters = {"attendance_device_id": user_id}
    if device_company:
        emp_filters["company"] = device_company
    employee = frappe.db.get_value("Employee", emp_filters, fields, as_dict=True)
    if employee:
        return employee

    if not device_name:
        return None

    rows = frappe.get_all(
        "Biometric Device Allowed Employee",
        filters={"parent": device_name, "parenttype": "Biometric Device"},
        fields=["employee", "device_user_id"],
    )
    if not rows:
        return None

    # An explicit Device User ID on the row wins over the employee's own ID:
    # it exists precisely to describe how this device numbers this visitor.
    explicit = [r.employee for r in rows if (r.device_user_id or "").strip() == user_id]
    if explicit:
        return frappe.db.get_value("Employee", explicit[0], fields, as_dict=True)

    inherited = [r.employee for r in rows if not (r.device_user_id or "").strip()]
    if not inherited:
        return None

    return frappe.db.get_value(
        "Employee",
        {"name": ["in", inherited], "attendance_device_id": user_id},
        fields,
        as_dict=True,
    )


def process_attendance_records(attendance_data, device_identifier=None):
    """
    Store biometric punches as Employee Checkin rows. For each (employee, date),
    new punches are merged with existing rows, de-duplicated within the sending
    device's Duplicate Threshold window (near-simultaneous repeats of one
    physical punch are dropped), sorted chronologically, and assigned
    alternating log_types: 1st → IN, 2nd → OUT, 3rd → IN, ... with the day's
    last punch forced to OUT (see attendance_sync.desired_log_type).

    Re-running with the same batch is idempotent. A late-arriving punch slots
    in by time and downstream rows flip IN↔OUT if needed.

    Args:
        attendance_data: list of {"user_id": str, "timestamp": str} dicts
        device_identifier: optional device name/IP

    Returns:
        dict with success, synced, errors, skipped, message, error_details,
        synced_punches, failed_punches, skipped_punches

    Outcome categories (so the caller knows what to retry):
      - synced_punches  → stored successfully.
      - skipped_punches → permanently unprocessable for a business reason
        (unknown device user_id, malformed timestamp). Retrying won't help, so
        the bridge stops resending and doesn't flag them as errors.
      - failed_punches  → transient failure (exception). Safe to retry.
    """
  
    if not attendance_data:
        return {
            "success": True,
            "synced": 0,
            "errors": 0,
            "skipped": 0,
            "message": "No attendance records to process",
            "synced_punches": [],
            "failed_punches": [],
            "skipped_punches": [],
        }

    synced = 0
    errors = 0
    skipped = 0
    error_details = []
    synced_punches = []
    failed_punches = []
    skipped_punches = []

    grouped = defaultdict(list)
    record_ids_by_group = defaultdict(list)

    # Company of the sending device — a punch maps only to an employee of this
    # company, so the same work-number (attendance_device_id) can be reused
    # across companies. None (legacy device with no company) = no company filter.
    device_company = None
    device_name = None
    threshold_seconds = DEFAULT_DUPLICATE_THRESHOLD_SECONDS
    if device_identifier:
        device_row = frappe.db.get_value(
            "Biometric Device",
            {"device_serial": device_identifier},
            ["name", "company", "duplicate_threshold_seconds"],
            as_dict=True,
        )
        if device_row:
            device_name = device_row.name
            device_company = device_row.company
            if device_row.duplicate_threshold_seconds is not None:
                threshold_seconds = device_row.duplicate_threshold_seconds

    for record in attendance_data:
        user_id = str(record.get("user_id", "")).strip()
        timestamp_str = str(record.get("timestamp", "")).strip()
        if not user_id or not timestamp_str:
            continue

        record_id = f"{user_id}_{timestamp_str}"

        ts = _parse_timestamp(timestamp_str)
        if not ts:
            # Malformed data the device will keep sending — permanent skip.
            skipped += 1
            error_details.append(f"Invalid timestamp: {timestamp_str}")
            skipped_punches.append(record_id)
            continue

        key = (user_id, ts.date())
        grouped[key].append(ts)
        record_ids_by_group[key].append(record_id)

    for (user_id, punch_date), new_timestamps in grouped.items():
        group_record_ids = record_ids_by_group[(user_id, punch_date)]

        # Each (employee, date) group is independent. Wrap it in a savepoint so a
        # failure partway through reconciliation (e.g. the 3rd of 5 check-in
        # inserts throws) rolls back just this group's partial writes instead of
        # leaving them to be committed by the final commit() — otherwise a group
        # could land half its punches and still be reported as failed/retryable.
        savepoint = "biometric_group"
        try:
            frappe.db.savepoint(savepoint)

            employee = resolve_employee_for_punch(user_id, device_company, device_name)

            if not employee:
                # No Employee maps to this device user_id — neither in the
                # device's own company nor in its cross-company allow-list. Not
                # our error and not retryable until someone registers the
                # employee (or adds them to the device) — skip.
                frappe.db.rollback(save_point=savepoint)
                skipped += len(group_record_ids)
                where = f" (company {device_company})" if device_company else ""
                error_details.append(
                    f"Employee not found having ID: {user_id}{where} in device {device_identifier}"
                )
                skipped_punches.extend(group_record_ids)
                continue

            inserted, updated = _reconcile_day_checkins(
                employee, punch_date, new_timestamps, device_identifier,
                threshold_seconds=threshold_seconds,
            )

            synced += len(new_timestamps)
            synced_punches.extend(group_record_ids)

            frappe.logger("biometric").info(
                f"{employee.name} {punch_date}: new={len(new_timestamps)} "
                f"inserted={inserted} relabeled={updated}"
            )

        except Exception as e:
            # Undo any partial writes from this group, then record it as failed.
            try:
                frappe.db.rollback(save_point=savepoint)
            except Exception:
                pass
            errors += 1
            error_details.append(f"{user_id}: {str(e)[:100]}")
            failed_punches.extend(group_record_ids)
            frappe.log_error(
                title="Biometric Processing Error",
                message=f"Employee Device ID: {user_id}\nDate: {punch_date}\nError: {str(e)}",
            )

    if device_identifier:
        _update_device_record(device_identifier, synced)

    frappe.db.commit()

    return {
        "success": True,
        "synced": synced,
        "errors": errors,
        "skipped": skipped,
        "message": f"Synced {synced} punches, {skipped} skipped, {errors} errors.",
        "error_details": error_details[:10],
        "synced_punches": synced_punches,
        "failed_punches": failed_punches,
        "skipped_punches": skipped_punches,
    }


def _reconcile_day_checkins(
    employee, punch_date, new_timestamps, device_identifier=None,
    threshold_seconds=DEFAULT_DUPLICATE_THRESHOLD_SECONDS,
):
    """Merge new punches with existing rows for the day and apply IN/OUT
    alternation in chronological order.

    De-duplication (``threshold_seconds``, "prevent new only"): existing
    Employee Checkin rows are always kept; a *new* punch is dropped when it
    falls within ``threshold_seconds`` of a punch already kept for the day
    (an existing row or an earlier new punch we've accepted). This collapses
    the repeated reads a device fires for a single physical punch. A threshold
    of 0 keeps only exact-timestamp de-duplication.

    Returns (inserted_count, relabeled_count).
    """

    day_start = datetime.combine(punch_date, datetime.min.time())
    day_end = datetime.combine(punch_date, datetime.max.time())

    existing_rows = frappe.db.get_all(
        "Employee Checkin",
        filters={
            "employee": employee.name,
            "time": ["between", [day_start, day_end]],
        },
        fields=["name", "time", "log_type"],
        order_by="time asc",
    )
    existing_by_time = {row.time: row for row in existing_rows}

    threshold_seconds = max(cint(threshold_seconds), 0)

    # Existing rows are always kept. Walk new punches in chronological order,
    # accepting one only when it is not within the threshold of an already-kept
    # punch for the day.
    kept_times = list(existing_by_time.keys())
    for ts in sorted(set(new_timestamps)):
        if ts in existing_by_time:
            continue  # exact duplicate of an existing row
        if threshold_seconds and any(
            abs((ts - kept).total_seconds()) < threshold_seconds for kept in kept_times
        ):
            continue  # near-duplicate within threshold — don't store again
        kept_times.append(ts)

    all_times = sorted(kept_times)

    inserted = 0
    relabeled = 0
    # Per-insert Employee Checkin hooks (attendance_sync) are suppressed here:
    # the pipeline itself labels the merged day and runs one sync_day for the
    # whole group below, instead of once per punch.
    frappe.flags.in_biometric_day_reconcile = True
    try:
        for idx, ts in enumerate(all_times):
            desired = desired_log_type(idx, len(all_times))
            existing = existing_by_time.get(ts)
            if existing:
                if existing.log_type != desired:
                    frappe.db.set_value(
                        "Employee Checkin", existing.name, "log_type", desired
                    )
                    relabeled += 1
            else:
                checkin = frappe.new_doc("Employee Checkin")
                checkin.employee = employee.name
                checkin.employee_name = employee.employee_name
                checkin.custom_company = employee.company
                checkin.time = ts
                checkin.log_type = desired
                checkin.skip_auto_attendance = 0
                if device_identifier:
                    checkin.device_id = device_identifier
                checkin.insert(ignore_permissions=True)
                inserted += 1
    finally:
        frappe.flags.in_biometric_day_reconcile = False

    # Late punches for a day whose attendance already exists must update its
    # computed values (in/out, working hours), not just get linked.
    sync_day(employee.name, punch_date)

    return inserted, relabeled


def _parse_timestamp(timestamp_str):
    """Parse timestamp string into datetime object."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(timestamp_str)
    except ValueError:
        return None


def _update_device_record(device_identifier, synced_count):
    """Update last_sync_time and total_synced on the Biometric Device record.

    Looks up by `device_serial` — the canonical key set by the bridge
    payload / ADMS push SN. The ingestion endpoints have already validated
    the serial via assert_known_device(), so a miss here would mean the row
    was deleted mid-request; we just no-op.
    """
    device_name = frappe.db.get_value(
        "Biometric Device",
        {"device_serial": device_identifier},
        "name",
    )
    if not device_name:
        return
    frappe.db.set_value(
        "Biometric Device",
        device_name,
        {
            "last_sync_time": now_datetime(),
            "total_synced": (
                frappe.db.get_value("Biometric Device", device_name, "total_synced")
                or 0
            )
            + synced_count,
        },
    )
