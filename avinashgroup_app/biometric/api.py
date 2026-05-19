import json

import frappe
from frappe import _
from frappe.utils import now_datetime
import socket
import traceback

from avinashgroup_app.biometric.utils import process_attendance_records

# Check if pyzk is installed
try:
    from zk import ZK
    ZK_INSTALLED = True
except ImportError:
    ZK_INSTALLED = False


@frappe.whitelist()
def test_connection(device_ip, device_port=4370):
    """
    Test connection to biometric device

    Args:
        device_ip (str): IP address of device
        device_port (int): Port number (default: 4370)

    Returns:
        dict: Success status and message
    """
    if not ZK_INSTALLED:
        return {
            "success": False,
            "message": "pyzk library not installed. Run: pip install pyzk"
        }

    try:
        device_ip = device_ip.strip()
        device_port = int(device_port) if device_port else 4370

        zk = ZK(device_ip, port=device_port, timeout=5)
        conn = zk.connect()

        firmware = conn.get_firmware_version()
        serial = conn.get_serialnumber()

        users = conn.get_users()
        user_count = len(users) if users else 0

        conn.disconnect()

        return {
            "success": True,
            "message": "Connection successful!",
            "firmware": firmware,
            "serial": serial,
            "user_count": user_count
        }

    except socket.gaierror:
        frappe.log_error(
            title="Biometric Device Connection Test Failed",
            message=f"IP: {device_ip}, Port: {device_port}\nError: Could not resolve device address\n{traceback.format_exc()}"
        )
        return {
            "success": False,
            "message": f"Cannot resolve device address '{device_ip}'. Please verify the IP address is correct."
        }
    except (socket.timeout, OSError) as e:
        frappe.log_error(
            title="Biometric Device Connection Test Failed",
            message=f"IP: {device_ip}, Port: {device_port}\nError: {str(e)}\n{traceback.format_exc()}"
        )
        return {
            "success": False,
            "message": f"Cannot reach device at {device_ip}:{device_port}. Ensure the device is powered on and on the same network."
        }
    except Exception as e:
        error_msg = str(e)
        frappe.log_error(
            title="Biometric Device Connection Test Failed",
            message=f"IP: {device_ip}, Port: {device_port}\nError: {error_msg}\n{traceback.format_exc()}"
        )
        return {
            "success": False,
            "message": f"Connection failed: {error_msg}"
        }


@frappe.whitelist()
def sync_attendance_from_device(device_ip, device_port=4370, clear_after_sync=1):
    """
    Sync attendance from a ZK biometric device (pull model — server connects to device).
    Converts pyzk logs to plain dicts and delegates to process_attendance_records().
    """
    if not ZK_INSTALLED:
        frappe.throw(_("pyzk library not installed"))

    try:
        device_ip = device_ip.strip()
        device_port = int(device_port) if device_port else 4370

        zk = ZK(device_ip, port=device_port, timeout=5)
        conn = zk.connect()
        conn.disable_device()

        attendance_logs = conn.get_attendance()

        if not attendance_logs:
            conn.enable_device()
            conn.disconnect()
            return {"success": True, "synced": 0, "errors": 0, "message": "No logs"}

        # Convert pyzk log objects to plain dicts
        attendance_data = []
        for log in attendance_logs:
            attendance_data.append({
                "user_id": str(log.user_id),
                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            })

        conn.enable_device()
        conn.disconnect()

        return process_attendance_records(attendance_data, device_identifier=device_ip)

    except Exception as e:
        frappe.log_error(
            title="Sync Failed",
            message=f"Device: {device_ip}\nError: {str(e)}\n{traceback.format_exc()}",
        )
        frappe.throw(str(e))


@frappe.whitelist(methods=["POST"])
def receive_attendance(attendance_data, device_identifier=None):
    """
    Receive attendance records pushed from a remote script (push model).

    Args:
        attendance_data: JSON string or list of {"user_id": str, "timestamp": str} dicts
        device_identifier: optional device name or IP to update Biometric Device record

    Returns:
        dict: processing result from process_attendance_records()
    """
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


@frappe.whitelist()
def sync_employees_to_device(device_ip, device_port=4370):
    """
    Sync employees from ERPNext to biometric device
    """
    if not ZK_INSTALLED:
        frappe.throw(_("pyzk library not installed. Run: pip install pyzk"))

    try:
        device_ip = device_ip.strip()
        device_port = int(device_port) if device_port else 4370

        employees = frappe.get_all(
            "Employee",
            filters={
                "status": "Active",
                "attendance_device_id": ["!=", ""]
            },
            fields=["name", "employee_name", "attendance_device_id"]
        )

        if not employees:
            return {
                "success": False,
                "message": "No employees with Biometric Device ID found"
            }

        zk = ZK(device_ip, port=device_port, timeout=5)
        conn = zk.connect()
        conn.disable_device()

        synced_count = 0
        error_count = 0
        error_details = []

        for emp in employees:
            try:
                uid = int(emp.attendance_device_id)
                name = emp.employee_name[:24]

                conn.set_user(
                    uid=uid,
                    name=name,
                    privilege=0,
                    password='',
                    group_id='',
                    user_id=str(uid)
                )

                synced_count += 1

            except Exception as e:
                error_count += 1
                error_msg = str(e)[:100]
                error_details.append(f"{emp.employee_name}: {error_msg}")
                frappe.log_error(
                    title="Employee Sync Error",
                    message=f"Employee: {emp.name}\nError: {str(e)}"
                )

        conn.enable_device()
        conn.disconnect()

        result = {
            "success": True,
            "synced": synced_count,
            "errors": error_count,
            "message": f"Synced {synced_count} employees. {error_count} errors."
        }

        if error_details:
            result["error_details"] = error_details[:10]

        return result

    except Exception as e:
        frappe.log_error(
            title="Employee Sync to Device Failed",
            message=f"Device: {device_ip}\nError: {str(e)}\n{traceback.format_exc()}"
        )
        frappe.throw(_("Sync failed: {0}").format(str(e)))


@frappe.whitelist()
def clear_device_logs(device_ip, device_port=4370):
    """
    Clear all attendance logs from device
    """
    if not ZK_INSTALLED:
        frappe.throw(_("pyzk library not installed. Run: pip install pyzk"))

    try:
        device_ip = device_ip.strip()
        device_port = int(device_port) if device_port else 4370

        zk = ZK(device_ip, port=device_port, timeout=5)
        conn = zk.connect()
        conn.disable_device()

        conn.clear_attendance()

        conn.enable_device()
        conn.disconnect()

        return {
            "success": True,
            "message": "Device logs cleared successfully"
        }

    except Exception as e:
        frappe.log_error(
            title="Clear Device Logs Failed",
            message=f"Device: {device_ip}\nError: {str(e)}\n{traceback.format_exc()}"
        )
        frappe.throw(_("Failed to clear logs: {0}").format(str(e)))


@frappe.whitelist()
def get_device_users(device_ip, device_port=4370):
    """
    Get list of users from device
    """
    if not ZK_INSTALLED:
        frappe.throw(_("pyzk library not installed. Run: pip install pyzk"))

    try:
        device_ip = device_ip.strip()
        device_port = int(device_port) if device_port else 4370

        zk = ZK(device_ip, port=device_port, timeout=5)
        conn = zk.connect()

        users = conn.get_users()

        conn.disconnect()

        user_list = []
        for user in users:
            user_list.append({
                "uid": user.uid,
                "name": user.name,
                "user_id": user.user_id,
                "privilege": user.privilege
            })

        return {
            "success": True,
            "users": user_list,
            "count": len(user_list)
        }

    except Exception as e:
        frappe.log_error(
            title="Get Device Users Failed",
            message=f"Device: {device_ip}\nError: {str(e)}"
        )
        frappe.throw(_("Failed to get users: {0}").format(str(e)))


@frappe.whitelist()
def get_device_info(device_ip, device_port=4370):
    """
    Get device information
    """
    if not ZK_INSTALLED:
        frappe.throw(_("pyzk library not installed. Run: pip install pyzk"))

    try:
        device_ip = device_ip.strip()
        device_port = int(device_port) if device_port else 4370

        zk = ZK(device_ip, port=device_port, timeout=5)
        conn = zk.connect()

        info = {
            "firmware": conn.get_firmware_version(),
            "serialnumber": conn.get_serialnumber(),
            "platform": conn.get_platform(),
            "device_name": conn.get_device_name(),
            "face_version": conn.get_face_version(),
            "fp_version": conn.get_fp_version(),
        }

        users = conn.get_users()
        attendance = conn.get_attendance()

        info["user_count"] = len(users) if users else 0
        info["attendance_count"] = len(attendance) if attendance else 0

        conn.disconnect()

        return {
            "success": True,
            "info": info
        }

    except Exception as e:
        frappe.log_error(
            title="Get Device Info Failed",
            message=f"Device: {device_ip}\nError: {str(e)}"
        )
        return {
            "success": False,
            "message": str(e)
        }
