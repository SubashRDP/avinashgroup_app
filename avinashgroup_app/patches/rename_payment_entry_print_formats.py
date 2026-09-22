# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

import frappe

# Old Print Format name -> new name, for the Payment Entry formats.
RENAMES = [
	("Brother Payment Entry Cheque Print", "NG Cheque Print Brother"),
	("Canon Payment Entry Cheque Print", "NG Cheque Print Canon"),
	("Payment Entry Voucher Details 2", "NG Vendor Payment Half"),
	("Payment Entry Voucher Details", "NG Vendor Payment A4"),
]


def execute():
	"""Rename the Payment Entry Print Formats to their "NG ..." names.

	Runs in pre_model_sync so each existing record is renamed before the
	renamed JSON (print_format/ng_cheque_print_brother, ...) is imported.
	Without this, migrate would create a second Print Format under the new
	name and leave the old one in the print menu.
	"""
	for old, new in RENAMES:
		if not frappe.db.exists("Print Format", old):
			continue

		if frappe.db.exists("Print Format", new):
			# Both exist (a sync created the new one before this patch ran):
			# the old record is stale, drop it.
			frappe.delete_doc("Print Format", old, force=True, ignore_permissions=True)
			continue

		frappe.rename_doc("Print Format", old, new, force=True)
