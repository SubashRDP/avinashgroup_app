import frappe

from erpnext.accounts.party import get_party_account, get_party_advance_account

# Party Types handled here. Any other party type (Employee, Shareholder, …) keeps
# core behaviour.
PARTY_TYPES = frozenset(("Customer", "Supplier"))


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

	- account in the field is neither the party's default nor its advance account
	  -> the user picked it: keep it, book as a normal payment
	- otherwise, Unallocated Amount > 0 -> advance account (party's own, then party
	  group's, then Company default advance received / paid account)
	- otherwise -> party's default receivable / payable account
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

	user_picked = current_account and current_account not in (default_account, advance_account)

	if not user_picked and doc.unallocated_amount > 0 and advance_account:
		account = advance_account
		doc.book_advance_payments_in_separate_party_account = 1
	else:
		account = current_account if user_picked else default_account
		doc.book_advance_payments_in_separate_party_account = 0
		# Same as core does for every payment that is not booked as an advance
		doc.is_opening = "No"

	doc.set(field, account)
	doc.party_account = account
