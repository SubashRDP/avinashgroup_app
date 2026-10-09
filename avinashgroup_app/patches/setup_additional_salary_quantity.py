"""Additional Salary keeps the quantity and rate behind its amount.

Prepare Payroll Inputs prices tea, meals, overtime and the late fine as
quantity × rate (payroll/attendance_allowance.py) but kept only the amount: it
wrote "qty=… × rate=…" to a `notes` attribute that Additional Salary does not
have, so it was never stored. The salary sheet (Avinas Salary Statement) needs
the quantities: OT hours, meals, late hours, as the client's sheet shows them.

Adds `custom_quantity` and `custom_rate` (read only) and backfills the
attendance-posted rows: the quantity counted again from the same attendance,
the rate as amount ÷ quantity, so the two always multiply back to the amount.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt, getdate


def execute():
	create_custom_fields(
		{
			"Additional Salary": [
				{
					"fieldname": "custom_quantity",
					"label": "Quantity",
					"fieldtype": "Float",
					"insert_after": "amount",
					"read_only": 1,
					"description": "Days, meals or hours counted from attendance (Prepare Payroll Inputs).",
				},
				{
					"fieldname": "custom_rate",
					"label": "Rate",
					"fieldtype": "Currency",
					"options": "currency",
					"insert_after": "custom_quantity",
					"read_only": 1,
				},
			]
		},
		update=True,
	)
	backfill()


def backfill():
	from avinashgroup_app.payroll.attendance_allowance import (
		SOURCE_TAG,
		_attendance_period,
		_qty_for_employee,
	)

	for row in frappe.get_all(
		"Additional Salary",
		filters={"custom_source": SOURCE_TAG, "docstatus": 1, "custom_quantity": 0},
		fields=["name", "employee", "salary_component", "amount", "payroll_date"],
	):
		sc = frappe.get_cached_doc("Salary Component", row.salary_component)
		pe = frappe.db.get_value(
			"Salary Slip",
			{"employee": row.employee, "end_date": row.payroll_date, "docstatus": ("<", 2)},
			["start_date", "end_date"],
			as_dict=True,
		)
		if not pe:
			continue
		qty = _qty_for_employee(row.employee, sc, *_attendance_period(sc, getdate(pe.start_date), getdate(pe.end_date)))
		if qty > 0:
			frappe.db.set_value(
				"Additional Salary",
				row.name,
				{"custom_quantity": qty, "custom_rate": flt(row.amount) / qty},
				update_modified=False,
			)
