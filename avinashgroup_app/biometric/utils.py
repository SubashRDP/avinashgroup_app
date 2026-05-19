import frappe
from frappe.utils import now_datetime
from datetime import datetime
from collections import defaultdict


def process_attendance_records(attendance_data, device_identifier=None):
    """
    Process biometric punch records: group by (user_id, date), then create/update
    exactly one IN checkin and one OUT checkin per employee per day.
    Attendance is handled by ERPNext's built-in auto attendance.

    Args:
        attendance_data: list of {"user_id": str, "timestamp": str} dicts
        device_identifier: optional device name/IP

    Returns:
        dict with success, synced, errors, message, error_details, synced_punches, failed_punches
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

    # Parse all punches and group by (user_id, date)
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

    # Process each (user_id, date) group
    for (user_id, punch_date), timestamps in grouped.items():
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
                error_details.append(f"Employee not found for device ID: {user_id}")
                failed_punches.extend(group_record_ids)
                continue

            timestamps.sort()
            batch_earliest = timestamps[0]
            batch_latest = timestamps[-1]

            day_start = datetime.combine(punch_date, datetime.min.time())
            day_end = datetime.combine(punch_date, datetime.max.time())
            existing_in = frappe.db.get_value(
                "Employee Checkin",
                {"employee": employee.name, "log_type": "IN", "time": ["between", [day_start, day_end]]},
                ["name", "time"], as_dict=True,
            )
            existing_out = frappe.db.get_value(
                "Employee Checkin",
                {"employee": employee.name, "log_type": "OUT", "time": ["between", [day_start, day_end]]},
                ["name", "time"], as_dict=True,
            )

            # Earliest seen so far across this batch + DB, latest similarly.
            desired_in = batch_earliest
            if existing_in and existing_in.time < desired_in:
                desired_in = existing_in.time
            desired_out = batch_latest
            if existing_out and existing_out.time > desired_out:
                desired_out = existing_out.time

            _apply_checkin(employee, "IN", desired_in, existing_in, device_identifier)
            if desired_out != desired_in:
                _apply_checkin(employee, "OUT", desired_out, existing_out, device_identifier)

            synced += len(timestamps)
            synced_punches.extend(group_record_ids)

            frappe.logger("biometric").info(
                f"Processed {employee.name} on {punch_date}: "
                f"IN={desired_in}, OUT={desired_out if desired_out != desired_in else 'N/A'}, "
                f"punches={len(timestamps)}"
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


def _apply_checkin(employee, log_type, desired_time, existing, device_identifier=None):
    """Insert a checkin or update an existing one if the time has moved."""
    if existing:
        if existing.time != desired_time:
            frappe.db.set_value("Employee Checkin", existing.name, "time", desired_time)
        return

    checkin = frappe.new_doc("Employee Checkin")
    checkin.employee = employee.name
    checkin.employee_name = employee.employee_name
    checkin.time = desired_time
    checkin.log_type = log_type
    checkin.skip_auto_attendance = 0
    if log_type == "OUT":
        checkin.latitude = 27.7228
        checkin.longitude = 85.3211
    if device_identifier:
        checkin.device_id = device_identifier
    checkin.insert(ignore_permissions=True)


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
    """Update last_sync_time and total_synced on the Biometric Device record."""
    device_name = frappe.db.get_value(
        "Biometric Device",
        {"device_name": device_identifier},
        "name",
    )
    if not device_name:
        device_name = frappe.db.get_value(
            "Biometric Device",
            {"device_ip": device_identifier},
            "name",
        )
    if device_name:
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
