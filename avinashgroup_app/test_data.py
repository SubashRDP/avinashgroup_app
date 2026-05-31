"""Test data generation utilities."""

import frappe
from frappe.utils import getdate
from datetime import datetime


@frappe.whitelist()
def create_checkin_for_ashish():
    """Create one day of Employee Checkin records for testing."""
    # Find Ashish employee
    emp = frappe.db.get_value('Employee', {'first_name': 'Ashish'}, 'name')
    if not emp:
        return {"success": False, "message": "Employee 'Ashish' not found"}

    # Create checkin data for just 1 day (Baisakh 1, 2025-04-14)
    date = getdate('2025-04-14')
    company = frappe.db.get_value('Employee', emp, 'company')

    # Create in checkin
    in_time = datetime.combine(date, datetime.min.time().replace(hour=9, minute=0))
    checkin_in = frappe.new_doc('Employee Checkin')
    checkin_in.employee = emp
    checkin_in.checkin_time = in_time
    checkin_in.checkin_device = 'API'
    checkin_in.company = company
    checkin_in.insert(ignore_permissions=True)

    # Create out checkin (5 PM)
    out_time = datetime.combine(date, datetime.min.time().replace(hour=17, minute=0))
    checkin_out = frappe.new_doc('Employee Checkin')
    checkin_out.employee = emp
    checkin_out.checkin_time = out_time
    checkin_out.checkin_device = 'API'
    checkin_out.company = company
    checkin_out.insert(ignore_permissions=True)

    frappe.db.commit()

    return {
        "success": True,
        "message": f"Created 2 checkin records for {emp}",
        "employee": emp,
        "date": str(date),
        "checkin_in": checkin_in.name,
        "checkin_out": checkin_out.name,
    }
