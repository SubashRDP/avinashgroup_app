"""Backfill Biometric Device.device_serial for rows created before the field existed.

The new device_serial field is reqd + unique. Existing rows would block migrate
unless we seed something. We copy device_name into device_serial as a sensible
default — admins can edit it to the real hardware serial afterwards.
"""

import frappe


def execute():
    if not frappe.db.has_column("Biometric Device", "device_serial"):
        return

    rows = frappe.db.sql(
        """
        SELECT name, device_name, device_serial
        FROM `tabBiometric Device`
        WHERE device_serial IS NULL OR device_serial = ''
        """,
        as_dict=True,
    )
    for row in rows:
        seed = (row.device_name or row.name or "").strip()
        if not seed:
            continue
        frappe.db.set_value(
            "Biometric Device",
            row.name,
            "device_serial",
            seed,
            update_modified=False,
        )

    frappe.db.commit()
