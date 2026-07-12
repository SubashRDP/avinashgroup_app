# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Backfill branch_name on existing Sales Invoice Print Log rows from the
invoice's custom_branch_name (the branch-wise document number). Rows whose
invoice has no branch-wise number yet stay empty — new prints stamp the value
at log time (print_count._log_print). Idempotent: only touches empty rows."""

import frappe


def execute():
	if not frappe.db.has_column("Sales Invoice", "custom_branch_name"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabSales Invoice Print Log` log
		JOIN `tabSales Invoice` si ON si.name = log.sales_invoice
		SET log.branch_name = si.custom_branch_name
		WHERE IFNULL(log.branch_name, '') = ''
		  AND IFNULL(si.custom_branch_name, '') != ''
		"""
	)
