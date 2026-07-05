import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
	"""Make Employee.attendance_device_id unique per company, not globally.

	Stock ERPNext marks the field `unique: 1` (one namespace of device IDs for
	the whole site). This group runs one biometric device per company and every
	device numbers its users from 1, so the same work-number legitimately
	repeats across companies. Punch matching is already company-scoped (the
	sending device's company filters the employee lookup — biometric/utils.py)
	and per-company uniqueness is enforced by the
	`avinashgroup_app.biometric.employee.validate_unique_device_id` hook.

	Note: the stock HRMS field-based checkin API (add_log_based_on_employee_field)
	matches by attendance_device_id alone; it is not used on this site — all
	ingestion goes through avinashgroup_app.biometric, which is company-aware.
	"""
	make_property_setter(
		"Employee",
		"attendance_device_id",
		"unique",
		0,
		"Check",
		validate_fields_for_doctype=False,
	)

	# Swap the unique DB index for a plain one (schema sync won't drop it).
	unique_index = frappe.db.sql(
		"""
		SHOW INDEX FROM `tabEmployee`
		WHERE Column_name = 'attendance_device_id' AND Non_unique = 0
		"""
	)
	if unique_index:
		index_name = unique_index[0][2]
		frappe.db.sql_ddl(f"ALTER TABLE `tabEmployee` DROP INDEX `{index_name}`")

	plain_index = frappe.db.sql(
		"""
		SHOW INDEX FROM `tabEmployee`
		WHERE Column_name = 'attendance_device_id' AND Non_unique = 1
		"""
	)
	if not plain_index:
		frappe.db.sql_ddl(
			"ALTER TABLE `tabEmployee` ADD INDEX `attendance_device_id_index` (attendance_device_id)"
		)

	frappe.clear_cache(doctype="Employee")
