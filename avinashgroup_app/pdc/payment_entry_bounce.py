"""Cheque bounce, re-presentation and replacement for cheques entered in Payment Entry.

The group enters every cheque straight into a Payment Entry, to the bank — not
as a post-dated cheque. That stays exactly as it is. What this module adds is
what happens when the bank returns one of those cheques.

The earlier "Cheque Bounce" button (`custom_code/payment_entry/cheque_bounce.py`)
wrote the PE's GL rows back swapped, under the PE's own voucher, dated today:
no bounce date, no reason, no bank charges, no undo, and nothing to record a
second presentation or a replacement cheque. Here a bounce instead:

1. opens a PDC Cheque for the Payment Entry (`register_from_payment_entry`),
   already Cleared, its first History row pointing at the PE — no entry posted;
2. runs the PDC bounce on it: one Journal Entry, dated the bounce date, that
   swaps the PE's GL rows (invoices re-open, bank credited, deductions undone)
   plus any bank charges (`pdc/accounting.py` → `payment_entry_rows`).

From there the cheque is an ordinary PDC record: Re-present (`lifecycle.represent`),
Return, Undo Last Step, Replace with a new PDC Cheque — or with a new Payment
Entry (`make_replacement_payment_entry`), whose submit marks the bounced cheque
Replaced (`on_submit`) and whose cancel puts it back (`on_cancel`). The bounce
SMS and PDC Bounce Analysis cover these cheques like any other.

Boundary: the Payment Entry is never cancelled, amended or re-posted by this
module. It gets two links (`pdc_cheque`, `pdc_replacement_of`) and its existing
`custom_cheque_bounce` flag, kept in step by `lifecycle.sync_payment_entry_flag`.

Landmine: a PE already bounced the old way carries "Cheque Bounce -" GL rows
under its own voucher; reversing it again would double the bounce, so it is
refused here (and Party Ledger keeps reading those old rows as before).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

from avinashgroup_app.pdc import accounting, lifecycle
from avinashgroup_app.utils.bs_miti import set_mitis

# The remark the earlier cheque_bounce.py stamps on its reversed GL rows.
OLD_BOUNCE_REMARK = "Cheque Bounce -%"

# Cheque states in which the PE's cheque has a bounce standing against it.
BOUNCE_STANDING = ("Bounced", "Returned", "Replaced")


def _pe_party_account(pe):
	return pe.paid_from if pe.payment_type == "Receive" else pe.paid_to


def _pe_bank_account(pe):
	return pe.paid_to if pe.payment_type == "Receive" else pe.paid_from


def validate_payment_entry(pe):
	if pe.docstatus != 1:
		frappe.throw(_("Submit the Payment Entry first."))
	if pe.payment_type not in ("Receive", "Pay"):
		frappe.throw(_("Only a Receive or Pay Payment Entry carries a cheque that can bounce."))
	if pe.party_type not in ("Customer", "Supplier"):
		frappe.throw(_("Cheque bounce is for customer and supplier payments."))
	currency = frappe.get_cached_value("Company", pe.company, "default_currency")
	if (pe.paid_from_account_currency or currency) != currency or (pe.paid_to_account_currency or currency) != currency:
		frappe.throw(_("Payment Entry {0} is not in {1}; reverse it by hand.").format(pe.name, currency))
	if frappe.db.exists("GL Entry", {
		"voucher_type": "Payment Entry", "voucher_no": pe.name, "is_cancelled": 0,
		"remarks": ["like", OLD_BOUNCE_REMARK],
	}):
		frappe.throw(
			_("Payment Entry {0} was already bounced with the old Cheque Bounce button.").format(pe.name),
			title=_("Already bounced"),
		)


def register_from_payment_entry(pe):
	"""The PDC Cheque that tracks this PE's cheque: the existing one, or a new Cleared one."""
	existing = pe.get("pdc_cheque") or frappe.db.get_value(
		"PDC Cheque", {"payment_entry": pe.name, "docstatus": 1}, "name"
	)
	if existing:
		return frappe.get_doc("PDC Cheque", existing, for_update=True)

	received = pe.payment_type == "Receive"
	cheque = frappe.new_doc("PDC Cheque")
	cheque.update({
		"cheque_type": "Received" if received else "Issued",
		"company": pe.company,
		"posting_date": pe.posting_date,
		"party_type": pe.party_type,
		"party": pe.party,
		"party_name": pe.party_name,
		"party_account": _pe_party_account(pe),
		"cheque_no": pe.reference_no or pe.name,
		"cheque_date": pe.reference_date or pe.posting_date,
		"amount": flt(pe.paid_amount),
		"bank_account": _pe_bank_account(pe),
		"cost_center": pe.cost_center,
		"payment_entry": pe.name,
		"remarks": _("Cheque entered in Payment Entry {0}").format(pe.name),
	})
	for ref in pe.references:
		if ref.reference_doctype in ("Sales Invoice", "Purchase Invoice") and flt(ref.allocated_amount) > 0:
			cheque.append("references", {
				"reference_doctype": ref.reference_doctype,
				"reference_name": ref.reference_name,
				"allocated_amount": ref.allocated_amount,
			})
	cheque.flags.ignore_permissions = True
	cheque.insert()
	cheque.submit()
	frappe.db.set_value("Payment Entry", pe.name, "pdc_cheque", cheque.name, update_modified=False)
	return frappe.get_doc("PDC Cheque", cheque.name)


@frappe.whitelist()
def bounce(payment_entry, posting_date=None, reason=None, charges=0, recover_charges=0, jv_type=None):
	"""The "Cheque Bounced" dialog on a Payment Entry. Returns the PDC Cheque name."""
	lifecycle._check_role(lifecycle.STEP_ROLES)
	pe = frappe.get_doc("Payment Entry", payment_entry)
	pe.check_permission("read")
	validate_payment_entry(pe)
	cheque = register_from_payment_entry(pe)
	lifecycle.bounce(
		cheque, posting_date=posting_date or nowdate(), reason=reason,
		charges=flt(charges), recover_charges=cint(recover_charges), jv_type=jv_type,
	)
	return cheque.name


@frappe.whitelist()
def undo_bounce(payment_entry):
	"""The "Undo Bounce" button: a bounce recorded by mistake, taken back from the PE.

	Only while the bounce is the cheque's latest step. Once the cheque has been
	re-presented, returned or replaced, those steps come off first, on the cheque
	record, newest first.
	"""
	lifecycle._check_role(lifecycle.UNDO_ROLES)
	name = frappe.db.get_value("Payment Entry", payment_entry, "pdc_cheque")
	if not name:
		frappe.throw(_("Payment Entry {0} has no bounce recorded through the cheque record.").format(payment_entry))
	cheque = frappe.get_doc("PDC Cheque", name, for_update=True)
	cheque.check_permission("write")
	last = cheque.events[-1] if cheque.events else None
	if not last or last.event != "Bounced":
		frappe.throw(
			_("The cheque's latest step is {0}, not the bounce. Undo it on {1} first.").format(
				_(last.event) if last else _("none"), cheque.name
			),
			title=_("Cannot undo the bounce"),
		)
	lifecycle.undo_last_step(cheque)
	return cheque.name


@frappe.whitelist()
def make_replacement_payment_entry(name):
	"""Draft Payment Entry for the invoices a bounced cheque re-opened.

	Built fresh rather than copied, so the original's document number fields
	(custom_document_no …) are never carried over; the numbering engine gives
	the new one its own. Cheque no and date are left for the user to type.
	"""
	lifecycle._check_role(lifecycle.STEP_ROLES)
	cheque = frappe.get_doc("PDC Cheque", name)
	lifecycle._require(cheque, statuses=("Bounced", "Returned"))

	source = frappe.get_doc("Payment Entry", cheque.payment_entry) if cheque.payment_entry else None
	received = cheque.cheque_type == "Received"
	pe = frappe.new_doc("Payment Entry")
	pe.update({
		"payment_type": "Receive" if received else "Pay",
		"company": cheque.company,
		"posting_date": nowdate(),
		"party_type": cheque.party_type,
		"party": cheque.party,
		"party_name": cheque.party_name,
		"paid_from" if received else "paid_to": cheque.party_account,
		"paid_to" if received else "paid_from": cheque.deposit_account or cheque.bank_account,
		"mode_of_payment": source.mode_of_payment if source else None,
		"paid_amount": flt(cheque.amount),
		"received_amount": flt(cheque.amount),
		"source_exchange_rate": 1,
		"target_exchange_rate": 1,
		"pdc_replacement_of": cheque.name,
		"remarks": _("Replaces bounced cheque {0} ({1})").format(cheque.cheque_no, cheque.name),
	})
	if source and source.meta.has_field("custom_p_type"):
		pe.custom_p_type = source.custom_p_type

	remaining = flt(cheque.amount)
	for ref in cheque.references:
		inv = frappe.db.get_value(ref.reference_doctype, ref.reference_name,
			["outstanding_amount", "grand_total", "due_date"], as_dict=True)
		allocate = min(flt(inv.outstanding_amount), remaining)
		if allocate <= 0:
			continue
		pe.append("references", {
			"reference_doctype": ref.reference_doctype, "reference_name": ref.reference_name,
			"total_amount": inv.grand_total, "outstanding_amount": inv.outstanding_amount,
			"due_date": inv.due_date, "allocated_amount": allocate,
		})
		remaining -= allocate
	# The draft opens unsaved; its Posting Miti must show before the first save.
	set_mitis(pe)
	return lifecycle._unsaved(pe)


# ── Payment Entry doc events ─────────────────────────────────────────────────


def before_cancel(doc, method=None):
	"""Cancelling a bounced PE would reverse the payment a second time."""
	name = doc.get("pdc_cheque")
	if not name:
		return
	status = frappe.db.get_value("PDC Cheque", name, "status")
	if status in BOUNCE_STANDING:
		frappe.throw(
			_("The cheque of {0} is {1} on {2}. Undo the bounce there first (Undo Last Step).").format(
				doc.name, _(status), name
			),
			title=_("Cheque bounced"),
		)


def on_cancel(doc, method=None):
	# This PE replaced a bounced cheque: the cheque goes back to Bounced / Returned.
	if doc.get("pdc_replacement_of"):
		lifecycle.unmark_replaced(frappe.get_doc("PDC Cheque", doc.pdc_replacement_of), doc)
	# A record left Cleared after an undone bounce has no entry of its own to unwind.
	name = doc.get("pdc_cheque")
	if name and frappe.db.get_value("PDC Cheque", name, ["docstatus", "status"]) == (1, "Cleared"):
		cheque = frappe.get_doc("PDC Cheque", name)
		if len(cheque.events) == 1:
			cheque.flags.ignore_permissions = True
			cheque.cancel()


def on_submit(doc, method=None):
	if doc.get("pdc_replacement_of"):
		lifecycle.mark_replaced(frappe.get_doc("PDC Cheque", doc.pdc_replacement_of, for_update=True), doc)


def get_payment_entry_dashboard(data):
	"""Connections on a Payment Entry: its cheque record and the entries it posted."""
	data = frappe._dict(data or {})
	data.setdefault("non_standard_fieldnames", {})
	data.non_standard_fieldnames.update({"Journal Entry": "pdc_payment_entry", "PDC Cheque": "payment_entry"})
	data.fieldname = data.get("fieldname") or "pdc_payment_entry"
	data.setdefault("transactions", [])
	data.transactions.append({"label": _("Cheque Bounce"), "items": ["PDC Cheque", "Journal Entry"]})
	return data

