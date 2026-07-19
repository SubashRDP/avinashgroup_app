# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Backfill customer / customer_name on existing Sales Invoice Print Log rows
from the invoice. New prints stamp these at log time (print_count._log_print);
this fills the rows written before the columns existed. Idempotent: only touches
rows whose customer is still empty."""

import frappe


def execute():
	if not frappe.db.has_column("Sales Invoice Print Log", "customer"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabSales Invoice Print Log` log
		JOIN `tabSales Invoice` si ON si.name = log.sales_invoice
		SET log.customer = si.customer,
		    log.customer_name = si.customer_name
		WHERE IFNULL(log.customer, '') = ''
		"""
	)
