import frappe
from frappe import _
from frappe.utils import now_datetime
from datetime import datetime
from collections import defaultdict


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


def process_attendance_records(attendance_data, device_identifier=None):
    """
    Store every biometric punch as its own Employee Checkin row. For each
    (employee, date), all punches (existing in DB + new from this batch) are
    merged, deduped by exact timestamp, sorted chronologically, and assigned
    alternating log_types: 1st → IN, 2nd → OUT, 3rd → IN, ...

    Re-running with the same batch is idempotent. A late-arriving punch slots
    in by time and downstream rows flip IN↔OUT if needed.

    Args:
        attendance_data: list of {"user_id": str, "timestamp": str} dicts
        device_identifier: optional device name/IP

    Returns:
        dict with success, synced, errors, message, error_details,
        synced_punches, failed_punches
    """
    if not attendance_data:
        return {
            "success": True,
            "synced": 0,
            "errors": 0,
            "message": "No attendance records to process",
        }

    synced = 0
    errors = 0
    error_details = []
    synced_punches = []
    failed_punches = []

    grouped = defaultdict(list)
    record_ids_by_group = defaultdict(list)

    for record in attendance_data:
        user_id = str(record.get("user_id", "")).strip()
        timestamp_str = str(record.get("timestamp", "")).strip()
        if not user_id or not timestamp_str:
            continue

        record_id = f"{user_id}_{timestamp_str}"

        ts = _parse_timestamp(timestamp_str)
        if not ts:
            errors += 1
            error_details.append(f"Invalid timestamp: {timestamp_str}")
            failed_punches.append(record_id)
            continue

        key = (user_id, ts.date())
        grouped[key].append(ts)
        record_ids_by_group[key].append(record_id)

    for (user_id, punch_date), new_timestamps in grouped.items():
        group_record_ids = record_ids_by_group[(user_id, punch_date)]

        try:
            employee = frappe.db.get_value(
                "Employee",
                {"attendance_device_id": user_id},
                ["name", "employee_name", "company", "default_shift"],
                as_dict=True,
            )

            if not employee:
                errors += 1
                error_details.append(f"Employee not found having ID: {user_id} in device {device_identifier}")
                failed_punches.extend(group_record_ids)
                continue

            inserted, updated = _reconcile_day_checkins(
                employee, punch_date, new_timestamps, device_identifier
            )

            synced += len(new_timestamps)
            synced_punches.extend(group_record_ids)

            frappe.logger("biometric").info(
                f"{employee.name} {punch_date}: new={len(new_timestamps)} "
                f"inserted={inserted} relabeled={updated}"
            )

        except Exception as e:
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
        "message": f"Synced {synced} punches, {errors} errors.",
        "error_details": error_details[:10],
        "synced_punches": synced_punches,
        "failed_punches": failed_punches,
    }


def _reconcile_day_checkins(employee, punch_date, new_timestamps, device_identifier=None):
    """Merge new punches with existing rows for the day, dedup by exact time,
    and apply IN/OUT alternation in chronological order.

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

    all_times = sorted(set(existing_by_time.keys()) | set(new_timestamps))

    inserted = 0
    relabeled = 0
    for idx, ts in enumerate(all_times):
        desired_log_type = "IN" if idx % 2 == 0 else "OUT"
        existing = existing_by_time.get(ts)
        if existing:
            if existing.log_type != desired_log_type:
                frappe.db.set_value(
                    "Employee Checkin", existing.name, "log_type", desired_log_type
                )
                relabeled += 1
        else:
            checkin = frappe.new_doc("Employee Checkin")
            checkin.employee = employee.name
            checkin.employee_name = employee.employee_name
            checkin.time = ts
            checkin.log_type = desired_log_type
            checkin.skip_auto_attendance = 0
            if device_identifier:
                checkin.device_id = device_identifier
            checkin.insert(ignore_permissions=True)
            inserted += 1

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
