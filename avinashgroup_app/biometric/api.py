import json

import frappe
from frappe import _

from avinashgroup_app.biometric.utils import assert_known_device, process_attendance_records


@frappe.whitelist(methods=["POST"])
def receive_attendance(attendance_data, device_identifier=None):
    """
    Receive attendance records pushed from a remote script (push model).

    Args:
        attendance_data: JSON string or list of {"user_id": str, "timestamp": str} dicts
        device_identifier: hardware serial of the sending device. Required —
            must match a registered, enabled Biometric Device or the request
            is rejected with HTTP 403.

    Returns:
        dict: processing result from process_attendance_records()
    """
    # Reject punches from unregistered/disabled devices (403). Matches the
    # heartbeat / command-tunnel / ADMS endpoints, which all gate on this, and
    # the documented contract ("unknown serials get HTTP 403").
    assert_known_device(device_identifier)

    if isinstance(attendance_data, str):
        try:
            attendance_data = json.loads(attendance_data)
        except json.JSONDecodeError:
            frappe.throw(_("attendance_data must be a valid JSON array"))

    if not isinstance(attendance_data, list):
        frappe.throw(_("attendance_data must be a list of records"))

    for record in attendance_data:
        if not isinstance(record, dict):
            frappe.throw(_("Each record must be a dict with 'user_id' and 'timestamp'"))
        if "user_id" not in record or "timestamp" not in record:
            frappe.throw(_("Each record must have 'user_id' and 'timestamp' keys"))

    return process_attendance_records(attendance_data, device_identifier=device_identifier)
