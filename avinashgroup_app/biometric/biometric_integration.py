import frappe
from avinashgroup_app.biometric.utils import process_attendance_records

@frappe.whitelist(methods=["POST"])
def zkteco_push_attendance(**kwargs):
    """
    Single-record endpoint called by k40_bridge.py for each punch.

    Expects JSON body:
        {
            "device_id": "A6F5215360564",
            "employee_id": "1",
            "punch_time": "2026-02-16 09:00:00",
            "punch_type": "IN"
        }
    """


    data = frappe.local.form_dict
    device_id = data.get("device_id", "")
    employee_id = data.get("employee_id", "")
    punch_time = data.get("punch_time", "")

    if not employee_id or not punch_time:
        return {"success": False, "message": "Missing employee_id or punch_time"}

    records = [{"user_id": employee_id, "timestamp": punch_time}]
    result = process_attendance_records(records, device_identifier=device_id)
    return result
