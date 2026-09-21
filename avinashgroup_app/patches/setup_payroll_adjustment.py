"""Install Payroll Adjustment: the month's one-off amounts on one screen."""

import frappe


def execute():
	frappe.reload_doc("avinash_group_app", "doctype", "payroll_adjustment_row")
	frappe.reload_doc("avinash_group_app", "doctype", "payroll_adjustment")
