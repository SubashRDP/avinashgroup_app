# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""hrms.patches.v15_0.update_advance_payment_ledger_amount aborts every
migrate on our sites: our Payment Entry table carries an extra `amount`
column, and the hrms patch's multi-table UPDATE sets an unqualified
`amount`, which MariaDB rejects as ambiguous (error 1052) — before it can
discover there is nothing to update.

This patch runs pre_model_sync (all apps' pre patches run before any post
patches, and the hrms patch is post), applies the same data fix with fully
qualified column names, then records the hrms patch in Patch Log so the
broken original is skipped. The UPDATEs are no-ops on sites that never used
Employee Advance / Leave Encashment / Gratuity."""

import frappe
from frappe.modules.patch_handler import executed, update_patch_log

HRMS_PATCH = "hrms.patches.v15_0.update_advance_payment_ledger_amount #2025-09-23"
ADVANCE_DOCTYPES = ("Employee Advance", "Leave Encashment", "Gratuity")


def execute():
	if "hrms" not in frappe.get_installed_apps():
		return
	if executed(HRMS_PATCH):
		return

	# If the ledger table doesn't exist yet, this migrate is creating it —
	# it will be empty, so only the Patch Log entry is needed.
	if frappe.db.table_exists("Advance Payment Ledger Entry"):
		frappe.db.sql(
			"""
			UPDATE `tabAdvance Payment Ledger Entry` al
			INNER JOIN `tabPayment Entry` pe
				ON al.voucher_no = pe.name AND al.voucher_type = 'Payment Entry'
			INNER JOIN `tabPayment Entry Reference` per
				ON per.parent = pe.name
				AND al.against_voucher_type = per.reference_doctype
				AND al.against_voucher_no = per.reference_name
			SET al.amount = per.allocated_amount
			WHERE per.reference_doctype IN %(advance_doctypes)s
				AND pe.docstatus = 1
				AND pe.payment_type = 'Pay'
				AND al.amount < 0
			""",
			{"advance_doctypes": ADVANCE_DOCTYPES},
		)

		frappe.db.sql(
			"""
			UPDATE `tabAdvance Payment Ledger Entry` al
			INNER JOIN `tabJournal Entry` je
				ON al.voucher_no = je.name AND al.voucher_type = 'Journal Entry'
			INNER JOIN `tabJournal Entry Account` jea
				ON jea.parent = je.name
				AND al.against_voucher_type = jea.reference_type
				AND al.against_voucher_no = jea.reference_name
			SET al.amount = CASE
				WHEN jea.debit_in_account_currency > 0 AND al.amount <= 0
					THEN jea.debit_in_account_currency
				WHEN jea.credit_in_account_currency > 0 AND al.amount >= 0
					THEN jea.credit_in_account_currency * -1
				ELSE al.amount
			END
			WHERE jea.reference_type IN %(advance_doctypes)s
				AND jea.docstatus = 1
				AND (
					(jea.debit_in_account_currency > 0 AND al.amount <= 0)
					OR (jea.credit_in_account_currency > 0 AND al.amount >= 0)
				)
			""",
			{"advance_doctypes": ADVANCE_DOCTYPES},
		)

	update_patch_log(HRMS_PATCH)
