import frappe

from erpnext.accounts.party import get_party_account, get_party_advance_account

# Party Types handled here. Any other party type (Employee, Shareholder, …) keeps
# core behaviour.
PARTY_TYPES = frozenset(("Customer", "Supplier"))

# Account numbers (same in every company) that may switch to the advance account
# on save. Any other account stays as it is, even with an Unallocated Amount.
TRADE_ACCOUNT_NUMBERS = {
	"Customer": {"143101"},  # Debtors A/c - Domestic
	"Supplier": {"343100", "343201"},  # Trade Payables - Domestic / Foreign
}


def apply_patch():
	"""Stop core set_liability_account from switching the party account during validate.

	When the Company has "Book Advance Payments in Separate Party Account" on and no
	invoice is referenced, core set_liability_account() overwrites Account Paid From
	(Receive) / Account Paid To (Pay) with the advance account. It runs before the
	amounts are calculated, so it cannot look at the Unallocated Amount.

	For Customer / Supplier this patch puts back the account that was in the field
	(the default account if it held the party's advance account) and drops core's
	"Paid From account changed" alert. The final account is chosen
	later by set_party_account_by_unallocated (Payment Entry validate doc event),
	after core has worked out the Unallocated Amount.

	Patched on the base PaymentEntry class so it also covers HRMS's
	EmployeePaymentEntry subclass, which owns the override_doctype_class hook.
	"""
	from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry

	core_set_liability_account = PaymentEntry.set_liability_account

	def set_liability_account(self):
		chosen_account = self.get(self.party_account_field) if self.party_account_field else None

		messages_before = len(frappe.local.message_log)
		core_set_liability_account(self)
		# Drop core's "Paid From account changed from X to Y" alert so users don't see it
		frappe.local.message_log = frappe.local.message_log[:messages_before] + [
			msg for msg in frappe.local.message_log[messages_before:] if not msg.get("alert")
		]

		if self.party_type in PARTY_TYPES and chosen_account:
			# The advance account in the field was put there by an earlier save, not by
			# the user: go back to the default account so core's invoice checks pass.
			# set_party_account_by_unallocated switches it again if still needed.
			if chosen_account == get_party_advance_account(self.party_type, self.party, self.company):
				chosen_account = get_party_account(self.party_type, self.party, self.company)
			self.set(self.party_account_field, chosen_account)
			self.party_account = chosen_account

	PaymentEntry.set_liability_account = set_liability_account


def set_party_account_by_unallocated(doc, method=None):
	"""Pick the party account of a draft Customer / Supplier Payment Entry on save.

	Runs after core validate, so doc.unallocated_amount is up to date.
	Only when the Company has "Book Advance Payments in Separate Party Account" on.

	Looks at the account in the field (filled by the form or changed by the user);
	the party's advance account or an empty field counts as the default account.
	- that account is a trade account (TRADE_ACCOUNT_NUMBERS) and Unallocated
	  Amount > 0 -> advance account (party's own, then party group's, then Company
	  default advance received / paid account)
	- otherwise -> that account, booked as a normal payment
	"""
	if doc.docstatus != 0:
		return
	if doc.party_type not in PARTY_TYPES or not doc.party or not doc.party_account_field:
		return
	if not frappe.db.get_value("Company", doc.company, "book_advance_payments_in_separate_party_account"):
		return

	field = doc.party_account_field
	current_account = doc.get(field)
	default_account = get_party_account(doc.party_type, doc.party, doc.company)
	advance_account = get_party_advance_account(doc.party_type, doc.party, doc.company)

	# The advance account here was put in by an earlier save: start again from the default.
	if not current_account or current_account == advance_account:
		current_account = default_account

	account_number = frappe.db.get_value("Account", current_account, "account_number") if current_account else None
	is_trade_account = account_number in TRADE_ACCOUNT_NUMBERS[doc.party_type]

	if is_trade_account and doc.unallocated_amount > 0 and advance_account:
		account = advance_account
		doc.book_advance_payments_in_separate_party_account = 1
	else:
		account = current_account
		doc.book_advance_payments_in_separate_party_account = 0
		# Same as core does for every payment that is not booked as an advance
		doc.is_opening = "No"

	doc.set(field, account)
	doc.party_account = account
