"""Bridge heartbeat: detect Biometric Devices that have stopped reporting and
email the configured recipients.

How it works:
  - For each enabled Biometric Device with at least one Alert Recipient, compare
    `last_contact_time` against `alert_threshold_minutes`. `last_contact_time`
    is updated every sync cycle by the bridge (via the heartbeat endpoint),
    whether or not new punches were found — that way a genuinely quiet device
    (no new punches) does NOT look indistinguishable from a dead bridge.
  - Only emails on a *transition*: Connected → Disconnected fires a "down" mail,
    Disconnected → Connected fires a "recovered" mail. So a permanently down
    device emails once, not every hour.
  - Connection state is persisted in the existing `connection_status` field
    (Select: Connected/Disconnected) on Biometric Device.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from avinashgroup_app.biometric.utils import assert_known_device


def check_bridge_heartbeats() -> dict:
    """Hourly scheduler entry point. Returns a summary dict for observability."""
    devices = frappe.get_all(
        "Biometric Device",
        filters={"enabled": 1},
        fields=[
            "name",
            "device_name",
            "device_serial",
            "device_ip",
            "last_contact_time",
            "last_sync_time",
            "alert_threshold_minutes",
            "connection_status",
        ],
    )

    now = now_datetime()
    transitions = {"to_disconnected": 0, "to_connected": 0, "unchanged": 0, "skipped_no_recipients": 0}

    for d in devices:
        recipients = _get_recipient_emails(d.name)
        if not recipients:
            transitions["skipped_no_recipients"] += 1
            continue

        threshold = int(d.alert_threshold_minutes or 120)
        stale_after = now - timedelta(minutes=threshold)

        # Prefer last_contact_time (every cycle). Fall back to last_sync_time
        # for legacy rows that pre-date the field — once the bridge upgrades
        # to ping the heartbeat endpoint, last_contact_time will start winning.
        contact_time = d.last_contact_time or d.last_sync_time
        is_connected = bool(contact_time and get_datetime(contact_time) >= stale_after)
        new_status = "Connected" if is_connected else "Disconnected"
        old_status = d.connection_status or ""

        if new_status == old_status:
            transitions["unchanged"] += 1
            continue

        frappe.db.set_value(
            "Biometric Device", d.name, "connection_status", new_status, update_modified=False
        )

        try:
            if new_status == "Disconnected":
                transitions["to_disconnected"] += 1
                _send_down_email(d, recipients, threshold, now)
            else:
                transitions["to_connected"] += 1
                _send_recovered_email(d, recipients, now)
        except Exception:
            # Outgoing email not configured, SMTP down, etc. — state already
            # persisted, so the next transition still goes through. Log and
            # continue so other devices aren't blocked by one mail failure.
            frappe.log_error(
                title=f"Biometric heartbeat email failed for {d.name}",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()
    return transitions


def _get_recipient_emails(device_name: str) -> list[str]:
    rows = frappe.get_all(
        "Biometric Device Alert Recipient",
        filters={"parent": device_name, "parenttype": "Biometric Device"},
        fields=["email"],
    )
    return [r.email for r in rows if r.email]


@frappe.whitelist(methods=["POST"])
def ping(device_serial: str) -> dict:
    """Bridge calls this every sync cycle to update `last_contact_time`,
    whether or not new punches were pushed. That's what lets the heartbeat
    distinguish "bridge is alive but device is quiet" from "bridge is dead".

    Gated by assert_known_device — unknown/disabled serial → 403.
    """
    device_name = assert_known_device(device_serial)
    frappe.db.set_value(
        "Biometric Device",
        device_name,
        "last_contact_time",
        now_datetime(),
        update_modified=False,
    )
    frappe.db.commit()
    return {"ok": True, "device": device_name}


def _send_down_email(d, recipients, threshold_minutes, now):
    last_contact = d.last_contact_time or d.last_sync_time
    last = get_datetime(last_contact).strftime("%Y-%m-%d %H:%M:%S") if last_contact else "never"
    subject = f"[Biometric] Bridge for '{d.device_name}' has stopped syncing"
    message = (
        f"<p>The biometric device <b>{d.device_name}</b> "
        f"(serial <code>{d.device_serial or '—'}</code>, IP <code>{d.device_ip or '—'}</code>) "
        f"has not reported a sync in over {threshold_minutes} minutes.</p>"
        f"<ul>"
        f"<li><b>Last sync:</b> {last}</li>"
        f"<li><b>Checked at:</b> {now.strftime('%Y-%m-%d %H:%M:%S')}</li>"
        f"</ul>"
        f"<p>Common causes: the Windows bridge PC is off, the device lost LAN connectivity, "
        f"or the bridge process crashed. Punches collected on the device are safe until its "
        f"memory fills up &mdash; check the bridge soon.</p>"
        f"<p>You will receive a follow-up email once syncing resumes.</p>"
    )
    frappe.sendmail(recipients=recipients, subject=subject, message=message, now=False)


def _send_recovered_email(d, recipients, now):
    last_contact = d.last_contact_time or d.last_sync_time
    last = get_datetime(last_contact).strftime("%Y-%m-%d %H:%M:%S") if last_contact else "—"
    subject = f"[Biometric] Bridge for '{d.device_name}' is syncing again"
    message = (
        f"<p>The biometric device <b>{d.device_name}</b> resumed syncing.</p>"
        f"<ul>"
        f"<li><b>Last sync:</b> {last}</li>"
        f"<li><b>Checked at:</b> {now.strftime('%Y-%m-%d %H:%M:%S')}</li>"
        f"</ul>"
        f"<p>If days were lost while the bridge was offline, run an <b>Attendance Fix</b> "
        f"for the affected date range so missing attendance is rebuilt from the catch-up checkins.</p>"
    )
    frappe.sendmail(recipients=recipients, subject=subject, message=message, now=False)
