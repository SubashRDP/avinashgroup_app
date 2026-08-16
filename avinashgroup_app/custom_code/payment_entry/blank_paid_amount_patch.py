import frappe
from frappe.utils import flt


def apply_patch():
	"""Guard PaymentEntry.allocate_amount_to_references against a blank Paid Amount.

	Clearing the Paid Amount field on the form immediately fires this whitelisted
	method with paid_amount=None, and core does `paid_amount -= sum(...)` on it
	with no flt() guard, raising TypeError (ERPNext v15 bug). Coerce the argument
	to a number so a blank field allocates 0 instead of crashing. The document
	field itself is never written — the form keeps showing the field as the user
	left it, and the mandatory check still blocks saving without a real amount.

	Patched on the base PaymentEntry class so it also covers HRMS's
	EmployeePaymentEntry subclass, which owns the override_doctype_class hook.
	"""
	from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry

	core_allocate = PaymentEntry.allocate_amount_to_references

	@frappe.whitelist()
	def allocate_amount_to_references(self, paid_amount, paid_amount_change, allocate_payment_amount):
		return core_allocate(self, flt(paid_amount), paid_amount_change, allocate_payment_amount)

	PaymentEntry.allocate_amount_to_references = allocate_amount_to_references
