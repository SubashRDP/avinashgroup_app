# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Rename the "Nepal Gas Journal Voucher Cash Bank" Print Format to
	"NG Cash Payment(CV) Voucher".

	Runs in pre_model_sync so the existing record is renamed before the
	renamed JSON (print_format/ng_cash_payment_cv_voucher) is imported.
	Without this, migrate would create a second Print Format under the new
	name and leave the old one in the print menu.
	"""
	old, new = "Nepal Gas Journal Voucher Cash Bank", "NG Cash Payment(CV) Voucher"

	if not frappe.db.exists("Print Format", old):
		return

	if frappe.db.exists("Print Format", new):
		# Both exist (a sync created the new one before this patch ran):
		# the old record is stale, drop it.
		frappe.delete_doc("Print Format", old, force=True, ignore_permissions=True)
		return

	frappe.rename_doc("Print Format", old, new, force=True)
