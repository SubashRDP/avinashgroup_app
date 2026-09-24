import frappe


def apply_patch():
	"""Keep a manually chosen party account on Payment Entry instead of forcing the advance account.

	When the Company has "Book Advance Payments in Separate Party Account" on and no
	invoice is referenced, core set_liability_account() ticks that flag and overwrites
	Account Paid From (Receive) / Account Paid To (Pay) with the party's advance account
	on every save — even when the user picked a different account on purpose (e.g. a
	cylinder deposit account).

	After core runs, if the account the user had selected is neither the party's normal
	receivable/payable account nor its advance account, put the user's account back and
	untick the flag, so the entry posts as a normal payment against that account.
	Leaving the field on the normal receivable/payable account keeps core behaviour
	(switched to the advance account), but without core's "Paid From account changed"
	alert.

	Patched on the base PaymentEntry class so it also covers HRMS's
	EmployeePaymentEntry subclass, which owns the override_doctype_class hook.
	"""
	from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry
	from erpnext.accounts.party import get_party_account

	core_set_liability_account = PaymentEntry.set_liability_account

	def set_liability_account(self):
		chosen_account = self.get(self.party_account_field) if self.party_account_field else None

		messages_before = len(frappe.local.message_log)
		core_set_liability_account(self)
		# Drop core's "Paid From account changed from X to Y" alert so users don't see it
		frappe.local.message_log = frappe.local.message_log[:messages_before] + [
			msg for msg in frappe.local.message_log[messages_before:] if not msg.get("alert")
		]

		if not self.book_advance_payments_in_separate_party_account or not chosen_account:
			return

		advance_account = self.get(self.party_account_field)
		normal_account = get_party_account(self.party_type, self.party, self.company)

		if chosen_account in (advance_account, normal_account):
			return

		self.set(self.party_account_field, chosen_account)
		self.party_account = chosen_account
		self.book_advance_payments_in_separate_party_account = 0
		# Same as core does for every payment that is not booked as an advance
		self.is_opening = "No"

	PaymentEntry.set_liability_account = set_liability_account
