"""Employee-level rules that keep biometric punch matching unambiguous.

Registered as a doc_event `validate` hook on Employee (see hooks.py) rather than
an override_doctype_class subclass: it adds a single field constraint and runs
alongside HRMS's own Employee.validate(), so it never claims the controller or
collides with other Employee customizations.
"""

import frappe
from frappe import _


def validate_unique_device_id(doc, method=None):
    """Block two employees in the same company from sharing attendance_device_id.

    Biometric punches are matched to an Employee by the pair
    (attendance_device_id, company) — see biometric.utils.process_attendance_records.
    The same work-number may legitimately repeat ACROSS companies (each HTMS /
    device install numbers its users from 1), but within ONE company it must be
    unique: otherwise a punch is ambiguous and frappe.db.get_value would silently
    attribute it to whichever employee happens to come first.

    Enforcing it here means the ambiguous data can never be saved in the first
    place, so the matching side never has to guess.
    """
    device_id = (doc.attendance_device_id or "").strip()
    if not device_id or not doc.company:
        return

    clash = frappe.db.get_value(
        "Employee",
        {
            "attendance_device_id": device_id,
            "company": doc.company,
            "name": ["!=", doc.name],
        },
        ["name", "employee_name"],
        as_dict=True,
    )
    if clash:
        frappe.throw(
            _(
                "Attendance Device ID {0} is already used by {1} ({2}) in company {3}. "
                "It must be unique within a company so biometric punches map to the "
                "right person."
            ).format(
                frappe.bold(device_id),
                clash.employee_name,
                clash.name,
                frappe.bold(doc.company),
            ),
            title=_("Duplicate Attendance Device ID"),
        )
