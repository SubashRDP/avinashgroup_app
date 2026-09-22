# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

import frappe

# Old Print Format name -> new name, for the Journal Entry voucher formats.
# Both the original names and the interim underscore names (NG_CV Payment
# Voucher_A4, ...) map to the final spaced names, so a site gets the final
# name whichever of the two it currently has.
RENAMES = [
	("NG Cash Payment(CV) Full Page", "NG CV Payment Voucher A4"),
	("NG_CV Payment Voucher_A4", "NG CV Payment Voucher A4"),
	("NG Cash Payment(CV) Voucher", "NG CV Payment Voucher Half"),
	("NG_CV Payment Voucher_Half", "NG CV Payment Voucher Half"),
	("Nepal Gas Journal Voucher A4 Full Page", "NG Journal Voucher A4"),
	("NG_Journal Voucher_A4", "NG Journal Voucher A4"),
	("Nepal Gas Journal Voucher", "NG Journal Voucher Half"),
	("NG_Journal Voucher_Half", "NG Journal Voucher Half"),
]


def execute():
	"""Rename the Journal Entry voucher Print Formats to their "NG ..." names.

	Runs in pre_model_sync so each existing record is renamed before the
	renamed JSON (print_format/ng_cv_payment_voucher_a4, ...) is imported.
	Without this, migrate would create a second Print Format under the new
	name and leave the old one in the print menu. Must run after
	rename_ng_cash_payment_cv_voucher, which produces "NG Cash Payment(CV) Voucher".
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
