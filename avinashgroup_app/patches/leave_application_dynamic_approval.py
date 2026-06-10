# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Leave Application is governed by the Dynamic Approval workflow
(custom_current_approver), so the native HRMS leave_approver is redundant.

This patch makes that switch permanent on every site that installs
avinashgroup_app:
  1. Hides the native `leave_approver` / `leave_approver_name` fields.
  2. Drops the native "leave approver is mandatory" requirement.

Idempotent and HRMS-optional: it no-ops on sites without HRMS installed,
and skips Property Setters that already exist.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
	# HRMS not installed on this site → nothing to do.
	if not frappe.db.exists("DocType", "Leave Application"):
		return

	# 1. Hide the native approver fields (replaced by Dynamic Approval workflow).
	for fieldname in ("leave_approver", "leave_approver_name"):
		ps_name = f"Leave Application-{fieldname}-hidden"
		if not frappe.db.exists("Property Setter", ps_name):
			make_property_setter(
				"Leave Application",
				fieldname,
				"hidden",
				1,
				"Check",
				validate_fields_for_doctype=False,
			)

	# 2. Remove the native mandatory requirement so the workflow owns approval.
	if frappe.db.exists("DocType", "HR Settings"):
		frappe.db.set_single_value(
			"HR Settings", "leave_approver_mandatory_in_leave_application", 0
		)
