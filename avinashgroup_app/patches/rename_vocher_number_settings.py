# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Fix the misspelled "Vocher Number Settings" DocType.

	Renames the parent DocType to "Voucher Number Settings". This runs in
	pre_model_sync so the existing table/records (and the child
	"Voucher Number Settings Item" parenttype references) are migrated before
	the new JSON is imported. Without this, migrate would create a second,
	empty DocType and orphan the old data.
	"""
	old, new = "Vocher Number Settings", "Voucher Number Settings"

	if not frappe.db.exists("DocType", old):
		return

	if frappe.db.exists("DocType", new):
		# Both exist (e.g. patch re-run after a partial sync): drop the stale one.
		return

	frappe.rename_doc("DocType", old, new, force=True)
	frappe.flags.ignore_in_install = True
