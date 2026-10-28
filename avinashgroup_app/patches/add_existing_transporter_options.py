# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Add suppliers already ticked "Is Transporter" to the "Name of Transportor"
list on Purchase Invoice / Purchase Receipt. New ones are added on Supplier
save (custom_code/transporter_options.py)."""

import frappe

from avinashgroup_app.custom_code.transporter_options import add_option


def execute():
	for name in frappe.get_all(
		"Supplier", filters={"is_transporter": 1}, pluck="supplier_name", order_by="creation"
	):
		if name:
			add_option(name)
