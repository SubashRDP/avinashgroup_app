"""PDC lifecycle — which step a cheque may take next, and what each step records.

    Received:  In Hand ─deposit→ Deposited ─clear→ Cleared
               In Hand ─clear→ Cleared               (deposit skipped)
               Deposited / Cleared ─bounce→ Bounced ─re-deposit→ Deposited
               In Hand / Bounced ─return→ Returned
    Issued:    Issued ─clear→ Cleared,  Issued / Cleared ─bounce→ Bounced,
               Issued ─stop→ Returned
    Both:      Bounced / Returned ─replace→ (new cheque) ; original → Replaced

Every step appends one row to the cheque's History table (`PDC Cheque Event`)
carrying the JE it posted and a JSON snapshot of the lifecycle fields before it.
"Undo Last Step" is therefore generic: cancel that JE, put the snapshot back,
delete the row. A step is written with `db_set` / `db_insert` rather than a
save of the submitted cheque, so Update After Submit rules never get in the way
and nothing on the cheque besides the lifecycle fields can change.

Boundary: the entries themselves are built in `pdc/accounting.py`; SMS in
`pdc/notifications.py`. The cheque's own submit / cancel live in its controller.

Landmine: steps run as whoever clicks, but post JEs with ignore_permissions —
the gate is `_check_role` below, not the JE's permissions.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, getdate, nowdate

from avinashgroup_app.pdc import accounting, notifications

ACTIVE_STATUSES = ("In Hand", "Issued", "Deposited", "Cleared")
OPEN_STATUSES = ("In Hand", "Issued", "Deposited")

# The fields a step may change, and therefore what an undo restores.
LIFECYCLE_FIELDS = (
	"status", "deposit_date", "deposit_account", "presentation_count", "clearance_date",
	"bounce_date", "bounce_reason", "bounce_charges", "charges_recovered", "return_date",
	"replaced_by", "replaced_by_payment_entry",
)

# What a Payment Entry's "Cheque Bounce" flag shows while its cheque is in these states.
PE_BOUNCED_STATUSES = ("Bounced", "Returned", "Replaced")

# Events whose JE settles the party side — the entry a bounce or return reverses.
SETTLING_EVENTS = ("Received", "Issued", "Re-deposited", "Re-presented")

STEP_ROLES = ("Accounts User", "Accounts Manager", "System Manager")
UNDO_ROLES = ("Accounts Manager", "System Manager")


def _check_role(roles):
	if not set(roles) & set(frappe.get_roles()):
		frappe.throw(_("You need one of these roles: {0}").format(", ".join(roles)), frappe.PermissionError)


def _require(cheque, cheque_type=None, statuses=()):
	if cheque.docstatus != 1:
		frappe.throw(_("Submit the cheque first."))
	if cheque_type and cheque.cheque_type != cheque_type:
		frappe.throw(_("This step is only for {0} cheques.").format(_(cheque_type)))
	if statuses and cheque.status not in statuses:
		frappe.throw(
			_("Cheque {0} is {1}; this step needs it to be {2}.").format(
				cheque.name, _(cheque.status), " / ".join(_(s) for s in statuses)
			)
		)


def record_event(cheque, event, event_date, values, journal_entry=None, account=None, remarks=None,
		payment_entry=None):
	"""Apply `values` to the cheque and append the History row. One call per step."""
	before = {f: cheque.get(f) for f in LIFECYCLE_FIELDS}
	values = dict(values)
	cheque.db_set(values, notify=False)
	row = cheque.append(
		"events",
		{
			"event": event,
			"event_date": event_date,
			"status_after": values.get("status", cheque.status),
			"journal_entry": journal_entry,
			"payment_entry": payment_entry,
			"account": account,
			"remarks": remarks,
			"user": frappe.session.user,
			"previous_values": json.dumps(before, default=str),
		},
	)
	row.db_insert()
	sync_payment_entry_flag(cheque)
	cheque.notify_update()
	return row


def sync_payment_entry_flag(cheque):
	"""Keep the Payment Entry's "Cheque Bounce" flag in step with the cheque's status."""
	if not cheque.get("payment_entry") or not frappe.get_meta("Payment Entry").has_field("custom_cheque_bounce"):
		return
	flag = "Cheque Bounced" if cheque.status in PE_BOUNCED_STATUSES else ""
	frappe.db.set_value("Payment Entry", cheque.payment_entry, "custom_cheque_bounce", flag, update_modified=False)


def settling_entry(cheque):
	"""(doctype, name) of the entry that last settled the party: what a bounce reverses."""
	for row in reversed(cheque.events):
		if row.event in SETTLING_EVENTS:
			if row.journal_entry:
				return "Journal Entry", row.journal_entry
			if row.payment_entry:
				return "Payment Entry", row.payment_entry
	frappe.throw(_("Cheque {0} has no settling entry in its history.").format(cheque.name))


def validate_presentable(cheque, on_date):
	"""Not before the cheque's date, not after it has gone stale."""
	on_date = getdate(on_date)
	if on_date < getdate(cheque.cheque_date):
		frappe.throw(
			_("Cheque {0} is dated {1}; it cannot be presented on {2}.").format(
				cheque.cheque_no, frappe.format(cheque.cheque_date, "Date"), frappe.format(on_date, "Date")
			),
			title=_("Too early"),
		)
	months = cint(frappe.db.get_single_value("PDC Settings", "cheque_validity_months"))
	if months and on_date > getdate(add_months(cheque.cheque_date, months)):
		frappe.throw(
			_("Cheque {0} is stale: it was valid for {1} months from {2}. Ask for a replacement.").format(
				cheque.cheque_no, months, frappe.format(cheque.cheque_date, "Date")
			),
			title=_("Stale cheque"),
		)


def _bank_account(cheque, account):
	account = account or cheque.deposit_account or cheque.bank_account
	if not account:
		frappe.throw(_("Choose the bank account."))
	company, account_type, is_group = frappe.get_cached_value(
		"Account", account, ["company", "account_type", "is_group"]
	)
	if company != cheque.company or is_group or account_type not in ("Bank", "Cash"):
		frappe.throw(_("{0} is not a bank account of {1}.").format(account, cheque.company))
	return account


# ── Steps ─────────────────────────────────────────────────────────────────────


def deposit(cheque, posting_date=None, bank_account=None):
	posting_date = posting_date or nowdate()
	_require(cheque, "Received", ("In Hand",))
	validate_presentable(cheque, posting_date)
	bank_account = _bank_account(cheque, bank_account)
	record_event(
		cheque, "Deposited", posting_date,
		{
			"status": "Deposited", "deposit_date": posting_date, "deposit_account": bank_account,
			"presentation_count": cint(cheque.presentation_count) + 1,
		},
		account=bank_account,
	)


def redeposit(cheque, posting_date=None, bank_account=None):
	"""Present a bounced cheque again. Re-settles the invoices it paid first time."""
	posting_date = posting_date or nowdate()
	_require(cheque, "Received", ("Bounced",))
	validate_presentable(cheque, posting_date)
	bank_account = _bank_account(cheque, bank_account)
	je = accounting.post_settlement(cheque, posting_date, _("Re-deposited"), cap_to_outstanding=True)
	record_event(
		cheque, "Re-deposited", posting_date,
		{
			"status": "Deposited", "deposit_date": posting_date, "deposit_account": bank_account,
			"presentation_count": cint(cheque.presentation_count) + 1,
			"bounce_date": None, "bounce_reason": None, "bounce_charges": 0, "charges_recovered": 0,
		},
		journal_entry=je, account=bank_account,
	)


def clear(cheque, posting_date=None, bank_account=None):
	posting_date = posting_date or nowdate()
	if cheque.cheque_type == "Received":
		_require(cheque, statuses=("In Hand", "Deposited"))
		validate_presentable(cheque, posting_date)
		if cheque.status == "Deposited" and getdate(posting_date) < getdate(cheque.deposit_date):
			frappe.throw(_("A cheque cannot clear before the day it was deposited."))
	else:
		_require(cheque, statuses=("Issued",))
		if getdate(posting_date) < getdate(cheque.cheque_date):
			frappe.throw(_("An issued cheque cannot clear before its cheque date."))
		bank_account = bank_account or cheque.bank_account

	bank_account = _bank_account(cheque, bank_account)
	je = accounting.post_clearance(cheque, posting_date, bank_account)
	values = {"status": "Cleared", "clearance_date": posting_date}
	if cheque.cheque_type == "Received" and not cheque.deposit_date:
		values.update(
			deposit_date=posting_date, deposit_account=bank_account,
			presentation_count=cint(cheque.presentation_count) + 1,
		)
	record_event(cheque, "Cleared", posting_date, values, journal_entry=je, account=bank_account)
	notifications.send_party_sms(cheque, "clearance")


def bounce(cheque, posting_date=None, reason=None, charges=0, recover_charges=0, bank_account=None,
		jv_type=None):
	posting_date = posting_date or nowdate()
	if cheque.cheque_type == "Received":
		_require(cheque, statuses=("Deposited", "Cleared"))
	else:
		_require(cheque, statuses=("Issued", "Cleared"))
	if not reason:
		frappe.throw(_("Give the bounce reason the bank wrote on the return memo."))

	after_clearance = cheque.status == "Cleared"
	if cheque.cheque_type == "Received":
		bank_account = cheque.deposit_account
	else:
		bank_account = cheque.bank_account
	if after_clearance or flt(charges) > 0:
		bank_account = _bank_account(cheque, bank_account)

	je = accounting.post_bounce(
		cheque, posting_date, settling_entry(cheque), after_clearance, bank_account,
		charges=charges, recover_charges=cint(recover_charges), jv_type=jv_type,
	)
	record_event(
		cheque, "Bounced", posting_date,
		{
			"status": "Bounced", "bounce_date": posting_date, "bounce_reason": reason,
			"bounce_charges": flt(charges), "charges_recovered": cint(recover_charges),
			"clearance_date": None,
		},
		journal_entry=je, account=bank_account, remarks=reason,
	)
	notifications.send_party_sms(cheque, "bounce")


def return_cheque(cheque, posting_date=None, remarks=None):
	"""Received: hand the cheque back. Issued: stop / take it back from the supplier."""
	posting_date = posting_date or nowdate()
	if cheque.cheque_type == "Received":
		_require(cheque, statuses=("In Hand", "Bounced"))
	else:
		_require(cheque, statuses=("Issued",))

	je = None
	# A bounced cheque's settlement is already reversed; returning the paper is
	# only a note. Anything else still holds the party settled and must unwind.
	if cheque.status != "Bounced":
		event = _("Returned") if cheque.cheque_type == "Received" else _("Stopped")
		je = accounting.post_reversal(cheque, posting_date, settling_entry(cheque), event)
	record_event(
		cheque, "Returned" if cheque.cheque_type == "Received" else "Stopped", posting_date,
		{"status": "Returned", "return_date": posting_date},
		journal_entry=je, remarks=remarks,
	)


def represent(cheque, posting_date=None):
	"""A bounced cheque that was entered in a Payment Entry, presented again.

	Straight to the bank, as the Payment Entry did: no holding account and no
	separate deposit step. (A cheque booked as a PDC uses Re-deposit instead.)
	"""
	posting_date = posting_date or nowdate()
	if not cheque.get("payment_entry"):
		frappe.throw(_("Re-present is for cheques entered in a Payment Entry. Use Re-deposit."))
	_require(cheque, statuses=("Bounced",))
	if cheque.cheque_type == "Received":
		validate_presentable(cheque, posting_date)
	je = accounting.post_represent(cheque, posting_date)
	bank_account = cheque.deposit_account or cheque.bank_account
	record_event(
		cheque, "Re-presented", posting_date,
		{
			"status": "Cleared", "clearance_date": posting_date, "deposit_date": posting_date,
			"presentation_count": cint(cheque.presentation_count) + 1,
		},
		journal_entry=je, account=bank_account,
	)
	notifications.send_party_sms(cheque, "clearance")


def undo_last_step(cheque):
	_require(cheque)
	if not cheque.events:
		frappe.throw(_("Nothing to undo."))
	last = cheque.events[-1]
	if last.event in ("Received", "Issued"):
		frappe.throw(_("The first step cannot be undone — cancel the cheque instead."))
	if last.event == "Replaced":
		frappe.throw(_("Cancel the replacement {0} to undo this step.").format(
			cheque.replaced_by or cheque.replaced_by_payment_entry))

	accounting.cancel_journal_entry(last.journal_entry)
	before = json.loads(last.previous_values or "{}")
	cheque.db_set({f: before.get(f) for f in LIFECYCLE_FIELDS if f in before}, notify=False)
	frappe.db.delete("PDC Cheque Event", {"name": last.name})
	cheque.status = before.get("status", cheque.status)
	sync_payment_entry_flag(cheque)
	cheque.add_comment("Info", _("Undid step: {0} ({1})").format(last.event, last.journal_entry or _("no entry")))
	cheque.notify_update()


def mark_replaced(original, replacement):
	"""`replacement` is a PDC Cheque, or a Payment Entry the customer paid with instead."""
	_require(original, statuses=("Bounced", "Returned"))
	if replacement.doctype == "Payment Entry":
		values = {"status": "Replaced", "replaced_by_payment_entry": replacement.name}
		cheque_no = replacement.reference_no or replacement.mode_of_payment
		payment_entry = replacement.name
	else:
		values = {"status": "Replaced", "replaced_by": replacement.name}
		cheque_no = replacement.cheque_no
		payment_entry = None
	record_event(
		original, "Replaced", replacement.posting_date, values,
		remarks=_("Replaced by {0} ({1})").format(replacement.name, cheque_no or ""),
		payment_entry=payment_entry,
	)


def unmark_replaced(original, replacement):
	"""The replacement was cancelled: the original goes back to Bounced / Returned."""
	last = original.events[-1] if original.events else None
	link = "replaced_by_payment_entry" if replacement.doctype == "Payment Entry" else "replaced_by"
	if not last or last.event != "Replaced" or original.get(link) != replacement.name:
		return
	before = json.loads(last.previous_values or "{}")
	original.db_set({f: before.get(f) for f in LIFECYCLE_FIELDS if f in before}, notify=False)
	frappe.db.delete("PDC Cheque Event", {"name": last.name})
	original.status = before.get("status", original.status)
	sync_payment_entry_flag(original)
	original.notify_update()


# ── Whitelisted entry points ──────────────────────────────────────────────────

ACTIONS = {
	"deposit": deposit,
	"redeposit": redeposit,
	"clear": clear,
	"bounce": bounce,
	"return": return_cheque,
	"represent": represent,
}


def _load(name):
	cheque = frappe.get_doc("PDC Cheque", name, for_update=True)
	cheque.check_permission("write")
	return cheque


@frappe.whitelist()
def run_action(name, action, **kwargs):
	_check_role(STEP_ROLES)
	if action not in ACTIONS:
		frappe.throw(_("Unknown action {0}").format(action))
	kwargs.pop("cmd", None)
	ACTIONS[action](_load(name), **kwargs)
	return frappe.get_doc("PDC Cheque", name).status


@frappe.whitelist()
def undo(name):
	_check_role(UNDO_ROLES)
	undo_last_step(_load(name))


@frappe.whitelist()
def bulk_action(names, action, posting_date=None, bank_account=None):
	"""Deposit or clear many cheques; each in its own savepoint so one bad cheque
	does not stop the rest. Returns {"done": [...], "failed": [{name, error}]}."""
	_check_role(STEP_ROLES)
	if action not in ("deposit", "clear"):
		frappe.throw(_("Bulk {0} is not supported.").format(action))
	if isinstance(names, str):
		names = json.loads(names)

	done, failed = [], []
	for name in names:
		frappe.db.savepoint("pdc_bulk")
		try:
			ACTIONS[action](_load(name), posting_date=posting_date, bank_account=bank_account)
			done.append(name)
		except Exception as e:
			frappe.db.rollback(save_point="pdc_bulk")
			frappe.clear_last_message()
			failed.append({"name": name, "error": frappe.utils.strip_html(str(e)) or repr(e)})
	frappe.message_log = []
	return {"done": done, "failed": failed}


@frappe.whitelist()
def make_replacement(name):
	"""A new draft cheque for the same party and invoices; the user types the new number and date."""
	_check_role(STEP_ROLES)
	original = frappe.get_doc("PDC Cheque", name)
	_require(original, statuses=("Bounced", "Returned"))
	new = frappe.copy_doc(original)
	new.update({
		"replacement_of": original.name, "cheque_no": None, "cheque_date": None,
		"posting_date": nowdate(), "status": "Draft", "events": [],
	})
	for ref in new.references:
		ref.outstanding_amount = flt(
			frappe.db.get_value(ref.reference_doctype, ref.reference_name, "outstanding_amount")
		)
	return _unsaved(new)


def _unsaved(doc):
	"""as_dict for the desk to open as an unsaved form (frappe.model.sync names it)."""
	out = doc.as_dict()
	out.update({"name": None, "__islocal": 1, "__unsaved": 1, "docstatus": 0})
	for table in doc.meta.get_table_fields():
		for row in out.get(table.fieldname) or []:
			row.update({"name": None, "parent": None, "__islocal": 1, "docstatus": 0})
	return out


@frappe.whitelist()
def make_from_invoice(doctype, name):
	"""PDC Cheque draft for one Sales or Purchase Invoice's outstanding amount."""
	if doctype not in ("Sales Invoice", "Purchase Invoice"):
		frappe.throw(_("Only Sales and Purchase Invoices"))
	inv = frappe.get_doc(doctype, name)
	inv.check_permission("read")
	is_sale = doctype == "Sales Invoice"
	cheque = frappe.new_doc("PDC Cheque")
	cheque.update({
		"cheque_type": "Received" if is_sale else "Issued",
		"company": inv.company,
		"party_type": "Customer" if is_sale else "Supplier",
		"party": inv.customer if is_sale else inv.supplier,
		"party_account": inv.debit_to if is_sale else inv.credit_to,
		"cost_center": inv.get("cost_center"),
		"amount": flt(inv.outstanding_amount),
	})
	cheque.append("references", {
		"reference_doctype": doctype, "reference_name": name, "due_date": inv.due_date,
		"grand_total": inv.grand_total, "outstanding_amount": inv.outstanding_amount,
		"allocated_amount": inv.outstanding_amount,
		"account": inv.debit_to if is_sale else inv.credit_to,
	})
	cheque.set_missing_values()
	return _unsaved(cheque)


@frappe.whitelist()
def get_outstanding_invoices(company, party_type, party, amount=None):
	"""Open invoices of the party, oldest due first, allocated up to `amount`."""
	doctype = {"Customer": "Sales Invoice", "Supplier": "Purchase Invoice"}.get(party_type)
	if not doctype:
		return []
	party_field = "customer" if doctype == "Sales Invoice" else "supplier"
	account_field = "debit_to" if doctype == "Sales Invoice" else "credit_to"
	rows = frappe.get_all(
		doctype,
		filters={"company": company, party_field: party, "docstatus": 1, "outstanding_amount": [">", 0]},
		fields=["name", "due_date", "grand_total", "outstanding_amount", f"{account_field} as account"],
		order_by="due_date asc, posting_date asc, name asc",
	)
	remaining = flt(amount) if amount else None
	out = []
	for r in rows:
		alloc = flt(r.outstanding_amount)
		if remaining is not None:
			alloc = min(alloc, max(remaining, 0))
			remaining -= alloc
		out.append({
			"reference_doctype": doctype, "reference_name": r.name, "due_date": r.due_date,
			"grand_total": r.grand_total, "outstanding_amount": r.outstanding_amount,
			"allocated_amount": alloc, "account": r.account,
		})
	return out
