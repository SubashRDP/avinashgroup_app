"""Outbound-polled tunnel: ERPNext ↔ Windows bridge command queue.

The Windows bridge is the only software on the LAN that can talk to the device.
For admin-triggered operations (force sync, ping device) we can't reach the
device from ERPNext directly, so instead:

  1. Admin enqueues a Biometric Device Command (Pending) via the desk.
  2. Bridge polls `poll_commands(device_serial)` every ~30s.
  3. Server atomically flips Pending → Running, returns the command(s).
  4. Bridge executes the command locally (via its existing pyzk client and
     internal force_sync() machinery), then POSTs to `report_command_result`.
  5. Server marks the command Done/Failed and stores the result. The desk UI,
     which has been polling the command row, surfaces the answer to admin.

Both endpoints are gated by `assert_known_device` so only a bridge whose
serial is registered + enabled can pull or report.
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from avinashgroup_app.biometric.utils import assert_known_device

SUPPORTED_COMMANDS = ("force_sync", "test_connection")


@frappe.whitelist(methods=["GET", "POST"])
def poll_commands(device_serial: str, max_commands: int = 5) -> dict:
    """Bridge polling endpoint: returns Pending commands for this device's serial.

    The bridge sends its `device_serial`. We look up the corresponding
    Biometric Device row and return any Pending commands for it, atomically
    flipping them to Running so a parallel poll from a second bridge process
    can't pick up the same command twice.
    """
    device_name = assert_known_device(device_serial)

    rows = frappe.get_all(
        "Biometric Device Command",
        filters={"device": device_name, "status": "Pending"},
        fields=["name", "command_type", "payload", "attempts"],
        order_by="requested_at asc",
        limit_page_length=int(max_commands),
    )

    claimed = []
    for r in rows:
        # Atomic claim: only flip if still Pending.
        updated = frappe.db.sql(
            """
            UPDATE `tabBiometric Device Command`
               SET status = 'Running',
                   started_at = %(now)s,
                   attempts = attempts + 1
             WHERE name = %(name)s
               AND status = 'Pending'
            """,
            {"name": r.name, "now": now_datetime()},
        )
        # rowcount == 1 means we won the race
        if frappe.db.sql("SELECT ROW_COUNT()")[0][0] == 1:
            claimed.append({
                "name": r.name,
                "command_type": r.command_type,
                "payload": _parse_payload(r.payload),
            })

    frappe.db.commit()

    return {
        "device": device_name,
        "commands": claimed,
    }


@frappe.whitelist(methods=["POST"])
def report_command_result(
    device_serial: str,
    command: str,
    status: str,
    result: str | None = None,
) -> dict:
    """Bridge reports back the outcome of a previously-claimed command.

    `status` must be 'Done' or 'Failed'. The bridge's serial must own the
    command (i.e. the command's device.device_serial matches the caller).
    """
    if status not in ("Done", "Failed"):
        frappe.throw(_("status must be 'Done' or 'Failed'."))

    device_name = assert_known_device(device_serial)

    cmd = frappe.db.get_value(
        "Biometric Device Command",
        command,
        ["name", "device", "status"],
        as_dict=True,
    )
    if not cmd:
        frappe.throw(_("Command {0} not found.").format(command))
    if cmd.device != device_name:
        frappe.throw(
            _("Command {0} does not belong to device {1}.").format(command, device_name),
            frappe.PermissionError,
        )
    if cmd.status not in ("Running", "Pending"):
        # Already completed — accept idempotent re-reports without changing the row.
        return {"name": cmd.name, "status": cmd.status, "no_op": True}

    frappe.db.set_value(
        "Biometric Device Command",
        command,
        {
            "status": status,
            "result": result or "",
            "completed_at": now_datetime(),
        },
        update_modified=True,
    )
    frappe.db.commit()
    return {"name": command, "status": status}


@frappe.whitelist()
def enqueue_command(device: str, command_type: str, payload: dict | str | None = None) -> str:
    """Desk-side helper: create a Pending command and return its name."""
    if command_type not in SUPPORTED_COMMANDS:
        frappe.throw(
            _("Unsupported command_type {0}. Supported: {1}").format(
                command_type, ", ".join(SUPPORTED_COMMANDS)
            )
        )

    payload_text = ""
    if payload:
        if isinstance(payload, str):
            payload_text = payload
        else:
            payload_text = json.dumps(payload)

    doc = frappe.new_doc("Biometric Device Command")
    doc.device = device
    doc.command_type = command_type
    doc.payload = payload_text
    doc.insert(ignore_permissions=False)
    frappe.db.commit()
    return doc.name


def _parse_payload(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {"raw": raw}
