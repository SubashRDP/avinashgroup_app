import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Add a Company link to Employee Checkin.

	Punches arrive from per-company biometric devices and the same
	attendance_device_id repeats across companies, so every checkin must
	say which company it belongs to. fetch_from keeps it in sync on any
	creation path (bridge, ADMS push, desk, API); the biometric ingestion
	code also sets it explicitly.
	"""
	create_custom_fields(
		{
			"Employee Checkin": [
				{
					"fieldname": "custom_company",
					"label": "Company",
					"fieldtype": "Link",
					"options": "Company",
					"fetch_from": "employee.company",
					"read_only": 1,
					"insert_after": "employee_name",
					"in_list_view": 1,
					"in_standard_filter": 1,
				}
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Employee Checkin")

	# Backfill existing checkins from the employee's current company.
	frappe.db.sql(
		"""
		UPDATE `tabEmployee Checkin` ec
		JOIN `tabEmployee` e ON e.name = ec.employee
		SET ec.custom_company = e.company
		WHERE IFNULL(ec.custom_company, '') = ''
		"""
	)
