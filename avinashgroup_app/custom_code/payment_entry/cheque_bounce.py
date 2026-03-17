import frappe
from frappe import _
from frappe.utils import today
from erpnext.accounts.general_ledger import make_gl_entries


@frappe.whitelist()
def make_cheque_bounce_entry(payment_entry_name):
	"""
	Create reversed GL entries for a bounced cheque.
	Copies the exact GL entries of the Payment Entry with debit and credit swapped.
	voucher_type stays "Payment Entry", against_voucher stays the same.
	"""
	pe = frappe.get_doc("Payment Entry", payment_entry_name)

	if pe.docstatus != 1:
		frappe.throw(_("Cheque Bounce can only be processed for submitted Payment Entries."))

	# Prevent duplicate bounce entries
	already_bounced = frappe.db.exists(
		"GL Entry",
		{
			"voucher_type": "Payment Entry",
			"voucher_no": payment_entry_name,
			"remarks": ("like", "Cheque Bounce%"),
			"is_cancelled": 0,
		},
	)
	if already_bounced:
		frappe.throw(_("A Cheque Bounce entry already exists for Payment Entry {0}.").format(
			frappe.bold(payment_entry_name)
		))

	# Fetch original GL entries
	original_entries = frappe.db.get_all(
		"GL Entry",
		filters={
			"voucher_type": "Payment Entry",
			"voucher_no": payment_entry_name,
			"is_cancelled": 0,
		},
		fields=[
			"company",
			"account",
			"account_currency",
			"party_type",
			"party",
			"against",
			"debit",
			"credit",
			"debit_in_account_currency",
			"credit_in_account_currency",
			"cost_center",
			"project",
			"against_voucher_type",
			"against_voucher",
			"is_opening",
			"transaction_currency",
			"transaction_exchange_rate",
			"remarks",
		],
	)

	if not original_entries:
		frappe.throw(_("No GL Entries found for Payment Entry {0}.").format(payment_entry_name))

	# Build reversed gl_map — same voucher, same against_voucher, just debit ↔ credit
	gl_map = []
	for gle in original_entries:
		gl_map.append(frappe._dict({
			"company": gle.company,
			"account": gle.account,
			"account_currency": gle.account_currency,
			"party_type": gle.party_type or "",
			"party": gle.party or "",
			"against": gle.against,
			"posting_date": today(),
			"voucher_type": "Payment Entry",
			"voucher_no": payment_entry_name,
			# Swap debit and credit
			"debit": gle.credit,
			"credit": gle.debit,
			"debit_in_account_currency": gle.credit_in_account_currency,
			"credit_in_account_currency": gle.debit_in_account_currency,
			"cost_center": gle.cost_center,
			"project": gle.project,
			"against_voucher_type": gle.against_voucher_type,
			"against_voucher": gle.against_voucher,
			"is_opening": gle.is_opening or "No",
			"transaction_currency": gle.transaction_currency,
			"transaction_exchange_rate": gle.transaction_exchange_rate,
			"remarks": _("Cheque Bounce - {0}").format(payment_entry_name),
		}))

	make_gl_entries(gl_map, cancel=False, adv_adj=False, merge_entries=False, update_outstanding="Yes")

	# Mark PE as cheque bounced
	try:
		frappe.db.set_value(
			"Payment Entry",
			payment_entry_name,
			"custom_cheque_bounce",
			"Cheque Bounced",
			update_modified=True,
		)
		frappe.db.commit()

		# Verify the value was actually written
		saved_val = frappe.db.get_value("Payment Entry", payment_entry_name, "custom_cheque_bounce")
		if saved_val != "Cheque Bounced":
			frappe.log_error(
				f"custom_cheque_bounce was not updated for {payment_entry_name}. "
				f"Expected 'Cheque Bounced', got '{saved_val}'.",
				"Cheque Bounce - Field Update Failed"
			)

	except Exception:
		frappe.log_error(frappe.get_traceback(), "Cheque Bounce - set_value failed")

	# frappe.msgprint(
	# 	_("Cheque Bounce GL entries posted successfully for Payment Entry {0}.").format(
	# 		frappe.bold(payment_entry_name)
	# 	),
	# 	title=_("Cheque Bounce"),
	# 	indicator="green",
	# )
