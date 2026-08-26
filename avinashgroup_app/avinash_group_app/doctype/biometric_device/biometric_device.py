# Copyright (c) 2026, Dikshya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class BiometricDevice(Document):
	def validate(self):
		self.validate_allowed_employees()

	def validate_allowed_employees(self):
		"""Keep the cross-company allow-list unambiguous.

		A punch carries only a user_id. It is matched first against employees of
		this device's OWN company, and only on a miss against `allowed_employees`
		(see biometric.utils.resolve_employee_for_punch). For that fallback to be
		safe, every row must resolve to exactly one person, so this rejects the
		three ways it could not:

		  * no usable ID   — the row could never match a punch;
		  * shadowed ID    — an employee of the device's own company already uses
		                     that ID, so they win the first lookup and the visitor
		                     silently never matches;
		  * duplicate ID   — two rows claim the same ID.

		Same-company employees are rejected outright: they already match at step
		one, so the row does nothing. Set Attendance Device ID on the Employee
		instead. Blocking it here beats a row that silently has no effect.
		"""
		if not self.get("allowed_employees"):
			return

		seen_ids = {}
		seen_employees = set()

		for row in self.allowed_employees:
			emp = frappe.db.get_value(
				"Employee",
				row.employee,
				["employee_name", "company", "attendance_device_id"],
				as_dict=True,
			)
			if not emp:
				continue

			if row.employee in seen_employees:
				frappe.throw(
					_("Row {0}: {1} is listed more than once.").format(
						row.idx, frappe.bold(row.employee)
					),
					title=_("Duplicate Employee"),
				)
			seen_employees.add(row.employee)

			if self.company and emp.company == self.company:
				frappe.throw(
					_(
						"Row {0}: {1} already belongs to {2}, this device's own company, "
						"so punches already match them without this list. Set their "
						"Attendance Device ID on the Employee record instead."
					).format(row.idx, frappe.bold(emp.employee_name), frappe.bold(emp.company)),
					title=_("Same Company"),
				)

			user_id = (row.device_user_id or emp.attendance_device_id or "").strip()
			if not user_id:
				frappe.throw(
					_(
						"Row {0}: {1} has no Attendance Device ID, so a punch could never "
						"be matched to them. Set one on the Employee record, or enter the "
						"Device User ID they are enrolled under on this device."
					).format(row.idx, frappe.bold(emp.employee_name)),
					title=_("No Device User ID"),
				)

			# Would an employee of this device's own company win the lookup first?
			if self.company:
				shadow = frappe.db.get_value(
					"Employee",
					{"attendance_device_id": user_id, "company": self.company},
					["name", "employee_name"],
					as_dict=True,
				)
				if shadow:
					frappe.throw(
						_(
							"Row {0}: device user ID {1} is already used by {2} ({3}) in "
							"{4}, this device's own company. Their punches would be matched "
							"first and {5} would never be recognised. Enrol {5} under a "
							"different ID on this device and enter it as Device User ID."
						).format(
							row.idx,
							frappe.bold(user_id),
							shadow.employee_name,
							shadow.name,
							frappe.bold(self.company),
							frappe.bold(emp.employee_name),
						),
						title=_("Device User ID Shadowed"),
					)

			if user_id in seen_ids:
				frappe.throw(
					_(
						"Row {0}: device user ID {1} is already claimed by {2} in row {3}. "
						"A punch with this ID would be ambiguous."
					).format(row.idx, frappe.bold(user_id), seen_ids[user_id][0], seen_ids[user_id][1]),
					title=_("Duplicate Device User ID"),
				)
			seen_ids[user_id] = (emp.employee_name, row.idx)
