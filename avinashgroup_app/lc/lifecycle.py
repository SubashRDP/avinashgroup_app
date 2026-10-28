"""LC lifecycle — which step a Letter of Credit may take next, and what each step records.

    Draft ─submit→ Applied ─open→ Opened ─(settle a shipment)→ Partly Settled ─→ Settled
                                   │                                         │
                                   └──────────── close ──────────────────────┴→ Closed / Expired

    Any time after submit:   add charge
    Opened and later:        deposit margin, amend, add shipment
    Per shipment:            Shipped ─docs received→ Docs Received ─accept (usance)→ Accepted
                             ─settle→ Settled ─customs proof→ (proof date recorded)
                             Purchase Receipt / Invoice can be linked until it settles.

Every step appends one row to the LC's History table (`LC Event`) carrying the
JE it posted and a JSON snapshot of what it changed: the LC's lifecycle and
amendable fields, the shipment row it touched, and the child rows it added.
"Undo Last Step" is therefore generic — cancel that JE, put the snapshot back,
delete the added rows. Steps write with `db_set` / `db_insert`, never a save of
the submitted LC, so Update After Submit rules never get in the way.

The LC's position (shipped, settled, available, margin held, charges, status)
is recomputed from its child rows after every step by `position()`, so no step
keeps a running total of its own.

Boundary: entries are built in `lc/accounting.py`; the LC's own submit / cancel
live in its controller. Regulatory checks on the terms (BCI, usance limit) are
in the controller's validate.

Landmine: steps run as whoever clicks but post JEs with ignore_permissions —
the gate is `_check_role`, not the JE's permissions.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from avinashgroup_app.lc import accounting

# Statuses in which shipments, margin and amendments are still possible.
OPEN_STATUSES = ("Opened", "Partly Settled", "Settled")
CLOSED_STATUSES = ("Closed", "Expired", "Cancelled")

# Fields only the lifecycle writes, and the terms an amendment may change:
# together, what an undo restores on the LC itself.
LIFECYCLE_FIELDS = (
	"status", "lc_no", "issue_date", "max_amount", "shipped_amount", "settled_amount", "available_amount",
	"margin_deposited", "margin_applied", "margin_released", "margin_balance", "charges_total",
	"settled_npr", "exchange_difference", "closed_on",
)
AMENDABLE_FIELDS = {
	"lc_amount": "LC Amount",
	"tolerance_plus": "Tolerance + %",
	"tolerance_minus": "Tolerance − %",
	"expiry_date": "Expiry Date",
	"latest_shipment_date": "Latest Shipment Date",
	"presentation_days": "Presentation Period (Days)",
	"partial_shipment": "Partial Shipment",
	"transhipment": "Transhipment",
	"port_of_loading": "Port / Place of Loading",
	"port_of_discharge": "Port of Discharge",
	"customs_point": "Nepal Customs Point",
	"usance_days": "Usance Days",
}
SNAPSHOT_FIELDS = LIFECYCLE_FIELDS + tuple(AMENDABLE_FIELDS)

SHIPMENT_FIELDS = (
	"status", "purchase_receipt", "purchase_invoice", "docs_received_date", "discrepancies",
	"acceptance_date", "maturity_date", "settlement_date", "exchange_rate", "amount_npr", "margin_applied",
	"exchange_difference", "settlement_journal_entry", "customs_declaration_no", "customs_date",
	"customs_proof_due", "customs_proof_submitted_on",
)

STEP_ROLES = ("Accounts User", "Accounts Manager", "System Manager")
UNDO_ROLES = ("Accounts Manager", "System Manager")


def _check_role(roles):
	if not set(roles) & set(frappe.get_roles()):
		frappe.throw(_("You need one of these roles: {0}").format(", ".join(roles)), frappe.PermissionError)


def _require(lc, statuses=()):
	if lc.docstatus != 1:
		frappe.throw(_("Submit the Letter of Credit first."))
	if statuses and lc.status not in statuses:
		frappe.throw(
			_("{0} is {1}; this step needs it to be {2}.").format(
				lc.name, _(lc.status), " / ".join(_(s) for s in statuses)
			)
		)


def _shipment(lc, shipment_no, statuses=()):
	row = next((s for s in lc.shipments if cint(s.shipment_no) == cint(shipment_no)), None)
	if not row:
		frappe.throw(_("{0} has no shipment {1}.").format(lc.name, shipment_no))
	if statuses and row.status not in statuses:
		frappe.throw(
			_("Shipment {0} is {1}; this step needs it to be {2}.").format(
				row.shipment_no, _(row.status), " / ".join(_(s) for s in statuses)
			)
		)
	return row


def _bank_account(lc, account):
	account = account or lc.bank_gl_account
	if not account:
		frappe.throw(_("Choose the bank account."))
	company, account_type, is_group = frappe.get_cached_value("Account", account, ["company", "account_type", "is_group"])
	if company != lc.company or is_group or account_type not in ("Bank", "Cash"):
		frappe.throw(_("{0} is not a bank account of {1}.").format(account, lc.company))
	return account


def _positive(value, label):
	if flt(value) <= 0:
		frappe.throw(_("{0} must be more than zero.").format(label))
	return flt(value, 2)


# ── Position ──────────────────────────────────────────────────────────────────


def position(lc):
	"""Totals and status from the LC's rows. Needs margin_deposited / released set."""
	shipped = sum(flt(s.amount) for s in lc.shipments)
	settled_rows = [s for s in lc.shipments if s.status == "Settled"]
	settled = sum(flt(s.amount) for s in settled_rows)
	max_amount = flt(lc.lc_amount) * (1 + flt(lc.tolerance_plus) / 100)
	margin_applied = sum(flt(s.margin_applied) for s in settled_rows)

	if lc.status in CLOSED_STATUSES or lc.closed_on:
		status = lc.status
	elif not lc.lc_no:
		status = "Applied"
	elif settled_rows and len(settled_rows) == len(lc.shipments) and settled >= flt(lc.lc_amount) * (1 - flt(lc.tolerance_minus) / 100) - 0.005:
		status = "Settled"
	elif settled_rows:
		status = "Partly Settled"
	else:
		status = "Opened"

	return {
		"status": status,
		"max_amount": flt(max_amount, 2),
		"shipped_amount": flt(shipped, 2),
		"settled_amount": flt(settled, 2),
		"available_amount": flt(max_amount - shipped, 2),
		"margin_applied": flt(margin_applied, 2),
		"margin_balance": flt(flt(lc.margin_deposited) - margin_applied - flt(lc.margin_released), 2),
		"charges_total": flt(sum(flt(c.amount) for c in lc.charges), 2),
		"settled_npr": flt(sum(flt(s.amount_npr) for s in settled_rows), 2),
		"exchange_difference": flt(sum(flt(s.exchange_difference) for s in settled_rows), 2),
	}


def record_event(lc, event, event_date, values=None, journal_entry=None, amount=None, remarks=None,
		shipment=None, shipment_values=None, added=()):
	"""Apply one step: LC values, shipment values, added rows; recompute; append History.

	`added` are child rows the step appended in memory (not yet inserted); they
	are inserted here so undo can delete exactly them.
	"""
	before = {
		"lc": {f: lc.get(f) for f in SNAPSHOT_FIELDS},
		"shipment": shipment.name if shipment else None,
		"shipment_values": {f: shipment.get(f) for f in SHIPMENT_FIELDS} if shipment else None,
		"added": [],
	}
	for row in added:
		row.db_insert()
		before["added"].append([row.doctype, row.name])

	if shipment and shipment_values:
		shipment.update(shipment_values)
		frappe.db.set_value(shipment.doctype, shipment.name, shipment_values, update_modified=False)

	values = dict(values or {})
	lc.update(values)
	values.update(position(lc))
	lc.db_set(values, notify=False)

	row = lc.append("events", {
		"event": event,
		"event_date": event_date,
		"status_after": values.get("status", lc.status),
		"shipment_no": shipment.shipment_no if shipment else None,
		"amount": amount,
		"journal_entry": journal_entry,
		"remarks": remarks,
		"user": frappe.session.user,
		"previous_values": json.dumps(before, default=str),
	})
	row.db_insert()
	lc.notify_update()
	return row


# ── Steps ─────────────────────────────────────────────────────────────────────


def open_lc(lc, lc_no=None, issue_date=None, margin=0, bank_account=None):
	"""The bank has issued the LC: record its number, and the margin it blocked."""
	_require(lc, ("Applied",))
	if not lc_no:
		frappe.throw(_("Give the LC number the bank issued."))
	issue_date = issue_date or nowdate()
	if getdate(issue_date) < getdate(lc.posting_date):
		frappe.throw(_("The LC cannot be issued before it was applied for."))
	duplicate = frappe.db.get_value(
		"Letter of Credit", {"lc_no": lc_no, "bank": lc.bank, "docstatus": 1, "name": ["!=", lc.name]}, "name"
	)
	if duplicate:
		frappe.throw(_("LC number {0} of this bank is already recorded as {1}.").format(lc_no, duplicate))

	je = None
	values = {"lc_no": lc_no, "issue_date": issue_date}
	if flt(margin) > 0:
		lc.lc_no = lc_no  # the JE's reference
		je = accounting.post_margin(lc, issue_date, _positive(margin, _("Margin")), _bank_account(lc, bank_account))
		values["margin_deposited"] = flt(lc.margin_deposited) + flt(margin, 2)
	record_event(lc, "Opened", issue_date, values, journal_entry=je, amount=flt(margin) or None,
		remarks=_("LC No. {0}").format(lc_no))


def deposit_margin(lc, posting_date=None, amount=0, bank_account=None):
	"""Margin top-up, or margin blocked after opening."""
	posting_date = posting_date or nowdate()
	_require(lc, OPEN_STATUSES)
	amount = _positive(amount, _("Margin"))
	je = accounting.post_margin(lc, posting_date, amount, _bank_account(lc, bank_account))
	record_event(lc, "Margin Deposited", posting_date, {"margin_deposited": flt(lc.margin_deposited) + amount},
		journal_entry=je, amount=amount)


def add_charge(lc, posting_date=None, charge_type=None, amount=0, bank_account=None, remarks=None):
	posting_date = posting_date or nowdate()
	_require(lc, ("Applied",) + OPEN_STATUSES)
	amount = _positive(amount, _("Charge"))
	charge_type = charge_type or "Other"
	bank_account = _bank_account(lc, bank_account)
	je = accounting.post_charge(lc, posting_date, amount, bank_account, _(charge_type))
	row = lc.append("charges", {
		"charge_type": charge_type, "charge_date": posting_date, "amount": amount,
		"bank_account": bank_account, "journal_entry": je, "remarks": remarks,
	})
	record_event(lc, charge_type, posting_date, journal_entry=je, amount=amount, remarks=remarks, added=[row])


def amend(lc, posting_date=None, changes=None, beneficiary_accepted=1, charge=0, bank_account=None, remarks=None):
	"""One amendment: any of AMENDABLE_FIELDS, with an optional amendment charge."""
	posting_date = posting_date or nowdate()
	_require(lc, OPEN_STATUSES)
	if isinstance(changes, str):
		changes = json.loads(changes)
	changes = {k: v for k, v in (changes or {}).items() if k in AMENDABLE_FIELDS and v not in (None, "")}
	changes = {k: v for k, v in changes.items() if str(lc.get(k) or "") != str(v)}
	if not changes:
		frappe.throw(_("Nothing changes in this amendment."))

	new = frappe._dict({f: lc.get(f) for f in AMENDABLE_FIELDS})
	new.update(changes)
	max_amount = flt(new.lc_amount) * (1 + flt(new.tolerance_plus) / 100)
	if flt(new.lc_amount) <= 0:
		frappe.throw(_("LC Amount must be more than zero."))
	if max_amount + 0.005 < sum(flt(s.amount) for s in lc.shipments):
		frappe.throw(_("Shipments already total more than the amended amount allows."))
	if new.latest_shipment_date and new.expiry_date and getdate(new.latest_shipment_date) > getdate(new.expiry_date):
		frappe.throw(_("The latest shipment date cannot be after the expiry date."))
	if "usance_days" in changes:
		from avinashgroup_app.lc.doctype.letter_of_credit.letter_of_credit import check_usance_limit
		check_usance_limit(lc.firm_type, lc.drafts_at, cint(new.usance_days))

	number = max([cint(a.amendment_no) for a in lc.amendments] or [0]) + 1
	je = None
	added = []
	if flt(charge) > 0:
		bank_account = _bank_account(lc, bank_account)
		je = accounting.post_charge(lc, posting_date, flt(charge, 2), bank_account, _("Amendment {0} charge").format(number))
		added.append(lc.append("charges", {
			"charge_type": "Amendment Charge", "charge_date": posting_date, "amount": flt(charge, 2),
			"bank_account": bank_account, "journal_entry": je, "remarks": _("Amendment {0}").format(number),
		}))
	for field, value in changes.items():
		added.append(lc.append("amendments", {
			"amendment_no": number, "amendment_date": posting_date, "fieldname": field,
			"field_label": AMENDABLE_FIELDS[field], "old_value": str(lc.get(field) or ""), "new_value": str(value),
			"beneficiary_accepted": cint(beneficiary_accepted), "journal_entry": je, "remarks": remarks,
		}))
	record_event(lc, _("Amendment {0}").format(number), posting_date, changes, journal_entry=je,
		amount=flt(charge) or None, remarks=", ".join(AMENDABLE_FIELDS[f] for f in changes), added=added)


def _check_link(lc, doctype, docname, shipment=None):
	if not docname:
		return
	doc = frappe.db.get_value(doctype, docname, ["docstatus", "company", "supplier", "currency"], as_dict=True)
	if not doc or doc.docstatus != 1:
		frappe.throw(_("{0} {1} is not submitted.").format(_(doctype), docname))
	if doc.company != lc.company or doc.supplier != lc.supplier:
		frappe.throw(_("{0} {1} is not from {2} in {3}.").format(_(doctype), docname, lc.supplier, lc.company))
	if doc.currency != lc.currency:
		frappe.throw(_("{0} {1} is in {2}; the LC is in {3}.").format(_(doctype), docname, doc.currency, lc.currency))
	field = "purchase_receipt" if doctype == "Purchase Receipt" else "purchase_invoice"
	other = frappe.db.sql(
		f"""select l.name, s.shipment_no from `tabLC Shipment` s join `tabLetter of Credit` l on l.name = s.parent
		where s.{field} = %s and l.docstatus = 1 and s.name != %s""",
		(docname, shipment.name if shipment else ""),
	)
	if other:
		frappe.throw(_("{0} is already linked to shipment {1} of {2}.").format(docname, other[0][1], other[0][0]))


def add_shipment(lc, transport_doc_no=None, transport_doc_date=None, amount=0, invoice_no=None,
		invoice_date=None, purchase_receipt=None, purchase_invoice=None):
	"""The supplier shipped under the LC: one drawing, checked against the LC's terms."""
	_require(lc, ("Opened", "Partly Settled"))
	amount = _positive(amount, _("Shipment amount"))
	if not transport_doc_no or not transport_doc_date:
		frappe.throw(_("Give the B/L, AWB or consignment note number and date."))
	shipped_on = getdate(transport_doc_date)
	if lc.latest_shipment_date and shipped_on > getdate(lc.latest_shipment_date):
		frappe.throw(
			_("Shipped on {0}, after the latest shipment date {1}. Amend the LC first.").format(
				frappe.format(shipped_on, "Date"), frappe.format(lc.latest_shipment_date, "Date")),
			title=_("Late shipment"),
		)
	if shipped_on > getdate(lc.expiry_date):
		frappe.throw(_("The LC expired on {0}.").format(frappe.format(lc.expiry_date, "Date")), title=_("LC expired"))
	if lc.partial_shipment == "Not Allowed":
		if lc.shipments:
			frappe.throw(_("Partial shipment is not allowed on this LC: it takes one shipment only."))
		if amount < flt(lc.lc_amount) * (1 - flt(lc.tolerance_minus) / 100) - 0.005:
			frappe.throw(_("Partial shipment is not allowed: the shipment must cover the full LC amount."))
	shipped = sum(flt(s.amount) for s in lc.shipments)
	max_amount = flt(lc.lc_amount) * (1 + flt(lc.tolerance_plus) / 100)
	if shipped + amount > max_amount + 0.005:
		frappe.throw(
			_("This shipment takes the LC to {0} {1}; the most it allows, with tolerance, is {0} {2}.").format(
				lc.currency, flt(shipped + amount, 2), flt(max_amount, 2)),
			title=_("Over the LC amount"),
		)
	_check_link(lc, "Purchase Receipt", purchase_receipt)
	_check_link(lc, "Purchase Invoice", purchase_invoice)

	row = lc.append("shipments", {
		"shipment_no": max([cint(s.shipment_no) for s in lc.shipments] or [0]) + 1,
		"status": "Shipped", "transport_doc_no": transport_doc_no, "transport_doc_date": transport_doc_date,
		"amount": amount, "invoice_no": invoice_no, "invoice_date": invoice_date,
		"purchase_receipt": purchase_receipt, "purchase_invoice": purchase_invoice,
	})
	record_event(lc, "Shipped", transport_doc_date, amount=None,
		remarks=_("{0} {1} {2}").format(transport_doc_no, lc.currency, amount), added=[row])
	# record_event snapshots the shipment only when it already existed; tag the row now.
	lc.events[-1].db_set("shipment_no", row.shipment_no, update_modified=False)


def link_documents(lc, shipment_no=None, purchase_receipt=None, purchase_invoice=None):
	"""Attach the Purchase Receipt / Invoice once they are made. Not after settlement."""
	_require(lc, OPEN_STATUSES)
	shipment = _shipment(lc, shipment_no, ("Shipped", "Docs Received", "Accepted"))
	values = {}
	for doctype, field, value in (
		("Purchase Receipt", "purchase_receipt", purchase_receipt),
		("Purchase Invoice", "purchase_invoice", purchase_invoice),
	):
		if value and value != shipment.get(field):
			_check_link(lc, doctype, value, shipment)
			values[field] = value
	if not values:
		frappe.throw(_("Nothing new to link."))
	record_event(lc, "Documents Linked", nowdate(), shipment=shipment, shipment_values=values,
		remarks=", ".join(values.values()))


def docs_received(lc, shipment_no=None, posting_date=None, discrepancies=None):
	"""The bank received the shipping documents. Late presentation is noted as a discrepancy."""
	posting_date = posting_date or nowdate()
	_require(lc, OPEN_STATUSES)
	shipment = _shipment(lc, shipment_no, ("Shipped",))
	on = getdate(posting_date)
	if on < getdate(shipment.transport_doc_date):
		frappe.throw(_("Documents cannot reach the bank before the goods shipped."))
	if on > getdate(lc.expiry_date):
		frappe.throw(_("Documents presented after the LC expired on {0}. Amend the expiry first.").format(
			frappe.format(lc.expiry_date, "Date")), title=_("LC expired"))
	notes = [discrepancies] if discrepancies else []
	if cint(lc.presentation_days) and on > getdate(add_days(shipment.transport_doc_date, cint(lc.presentation_days))):
		notes.append(_("Presented late: more than {0} days after shipment.").format(lc.presentation_days))
	record_event(lc, "Documents Received", posting_date, shipment=shipment,
		shipment_values={"status": "Docs Received", "docs_received_date": posting_date, "discrepancies": "\n".join(notes) or None},
		remarks="\n".join(notes) or None)


def maturity_for(lc, shipment, acceptance_date):
	basis = {
		"B/L Date": shipment.transport_doc_date,
		"Acceptance Date": acceptance_date,
		"Invoice Date": shipment.invoice_date or shipment.transport_doc_date,
	}.get(lc.usance_basis or "B/L Date")
	return add_days(basis, cint(lc.usance_days))


def accept(lc, shipment_no=None, posting_date=None, maturity_date=None):
	"""Usance: the company accepts the documents; the bank pays at maturity."""
	posting_date = posting_date or nowdate()
	_require(lc, OPEN_STATUSES)
	if lc.drafts_at != "Usance":
		frappe.throw(_("Acceptance is for usance LCs. A sight LC is settled straight after the documents arrive."))
	shipment = _shipment(lc, shipment_no, ("Docs Received",))
	maturity_date = maturity_date or maturity_for(lc, shipment, posting_date)
	record_event(lc, "Accepted", posting_date, shipment=shipment,
		shipment_values={"status": "Accepted", "acceptance_date": posting_date, "maturity_date": maturity_date},
		remarks=_("Matures {0}").format(frappe.format(maturity_date, "Date")))


def default_margin_use(lc, shipment):
	"""Margin a settlement uses unless told otherwise: the shipment's share of what is held."""
	balance = flt(lc.margin_deposited) - flt(lc.margin_released) - sum(
		flt(s.margin_applied) for s in lc.shipments if s.status == "Settled")
	if balance <= 0:
		return 0
	unsettled = [s for s in lc.shipments if s.status != "Settled"]
	still_open = max(flt(lc.lc_amount) - sum(flt(s.amount) for s in lc.shipments if s.status == "Settled"), 0)
	if len(unsettled) == 1 and flt(lc.available_amount) <= flt(lc.lc_amount) * flt(lc.tolerance_minus) / 100 + 0.005:
		return flt(balance, 2)  # last drawing: use it all
	if still_open <= 0:
		return flt(balance, 2)
	return flt(min(balance, balance * flt(shipment.amount) / still_open), 2)


def settle(lc, shipment_no=None, posting_date=None, exchange_rate=0, bank_account=None, margin_applied=None):
	"""The bank paid the supplier for a shipment, at its own rate, partly out of margin."""
	posting_date = posting_date or nowdate()
	_require(lc, OPEN_STATUSES)
	statuses = ("Accepted",) if lc.drafts_at == "Usance" else ("Docs Received",)
	shipment = _shipment(lc, shipment_no, statuses)
	exchange_rate = _positive(exchange_rate, _("Bank rate"))
	if margin_applied in (None, ""):
		margin_applied = default_margin_use(lc, shipment)
	held = flt(lc.margin_balance)
	if flt(margin_applied) < 0 or flt(margin_applied) > held + 0.005:
		frappe.throw(_("Margin used must be between 0 and the margin held ({0}).").format(held))
	bank_account = _bank_account(lc, bank_account)

	je, v = accounting.post_settlement(lc, shipment, posting_date, exchange_rate, bank_account, margin_applied)
	days = cint(frappe.db.get_single_value("LC Settings", "customs_proof_days"))
	record_event(lc, "Settled", posting_date, journal_entry=je, amount=v.bank_total, shipment=shipment,
		shipment_values={
			"status": "Settled", "settlement_date": posting_date, "exchange_rate": exchange_rate,
			"amount_npr": v.bank_total, "margin_applied": v.margin_applied,
			"exchange_difference": v.exchange_difference, "settlement_journal_entry": je,
			"customs_proof_due": add_days(posting_date, days) if days else None,
		},
		remarks=_("{0} {1} at {2}").format(lc.currency, shipment.amount, exchange_rate))


def customs_proof(lc, shipment_no=None, customs_declaration_no=None, customs_date=None, submitted_on=None):
	"""The customs declaration (Pragyapan) for a shipment, and the day it went to the bank."""
	_require(lc, OPEN_STATUSES + ("Closed", "Expired"))
	shipment = _shipment(lc, shipment_no)
	if not customs_declaration_no or not customs_date:
		frappe.throw(_("Give the customs declaration number and date."))
	submitted_on = submitted_on or nowdate()
	record_event(lc, "Customs Proof", submitted_on, shipment=shipment,
		shipment_values={
			"customs_declaration_no": customs_declaration_no, "customs_date": customs_date,
			"customs_proof_submitted_on": submitted_on,
		},
		remarks=customs_declaration_no)


def close(lc, posting_date=None, bank_account=None, remarks=None):
	"""Close the LC: no unsettled shipment may remain; unused margin comes back."""
	posting_date = posting_date or nowdate()
	_require(lc, OPEN_STATUSES)
	pending = [s.shipment_no for s in lc.shipments if s.status != "Settled"]
	if pending:
		frappe.throw(_("Shipments {0} are not settled yet.").format(", ".join(str(p) for p in pending)))
	je = None
	release = flt(lc.margin_balance)
	values = {"closed_on": posting_date,
		"status": "Expired" if getdate(posting_date) > getdate(lc.expiry_date) else "Closed"}
	if release > 0.005:
		je = accounting.post_margin_release(lc, posting_date, release, _bank_account(lc, bank_account))
		values["margin_released"] = flt(lc.margin_released) + release
	record_event(lc, values["status"], posting_date, values, journal_entry=je, amount=release or None, remarks=remarks)


def undo_last_step(lc):
	_require(lc)
	if len(lc.events) <= 1:
		frappe.throw(_("Nothing to undo. Cancel the LC to withdraw the application."))
	last = lc.events[-1]
	before = json.loads(last.previous_values or "{}")

	accounting.cancel_journal_entry(last.journal_entry)
	for doctype, name in before.get("added") or []:
		frappe.db.delete(doctype, {"name": name})
	if before.get("shipment") and before.get("shipment_values"):
		frappe.db.set_value("LC Shipment", before["shipment"], before["shipment_values"], update_modified=False)
	lc.db_set({f: v for f, v in (before.get("lc") or {}).items() if f in SNAPSHOT_FIELDS}, notify=False)
	frappe.db.delete("LC Event", {"name": last.name})
	lc.add_comment("Info", _("Undid step: {0} ({1})").format(last.event, last.journal_entry or _("no entry")))
	lc.notify_update()


# ── Whitelisted entry points ──────────────────────────────────────────────────

ACTIONS = {
	"open": open_lc,
	"deposit_margin": deposit_margin,
	"add_charge": add_charge,
	"amend": amend,
	"add_shipment": add_shipment,
	"link_documents": link_documents,
	"docs_received": docs_received,
	"accept": accept,
	"settle": settle,
	"customs_proof": customs_proof,
	"close": close,
}


def _load(name):
	lc = frappe.get_doc("Letter of Credit", name, for_update=True)
	lc.check_permission("write")
	return lc


@frappe.whitelist()
def run_action(name, action, **kwargs):
	_check_role(STEP_ROLES)
	if action not in ACTIONS:
		frappe.throw(_("Unknown action {0}").format(action))
	kwargs.pop("cmd", None)
	ACTIONS[action](_load(name), **kwargs)
	return frappe.db.get_value("Letter of Credit", name, "status")


@frappe.whitelist()
def undo(name):
	_check_role(UNDO_ROLES)
	undo_last_step(_load(name))


@frappe.whitelist()
def settlement_preview(name, shipment_no, exchange_rate, margin_applied=None):
	"""What Settle would post, for the dialog to show before the user confirms."""
	lc = frappe.get_doc("Letter of Credit", name)
	lc.check_permission("read")
	shipment = _shipment(lc, shipment_no)
	if margin_applied in (None, ""):
		margin_applied = default_margin_use(lc, shipment)
	return accounting.settlement_values(lc, shipment, flt(exchange_rate), flt(margin_applied))


@frappe.whitelist()
def make_from_purchase_order(purchase_order):
	"""Draft LC for a submitted Purchase Order, its terms copied where the PO has them."""
	po = frappe.get_doc("Purchase Order", purchase_order)
	po.check_permission("read")
	if po.docstatus != 1:
		frappe.throw(_("Submit the Purchase Order first."))
	lc = frappe.new_doc("Letter of Credit")
	lc.update({
		"company": po.company, "supplier": po.supplier, "supplier_name": po.supplier_name,
		"currency": po.currency, "lc_amount": po.grand_total,
		"incoterm": po.get("incoterm"), "named_place": po.get("named_place"),
		"latest_shipment_date": po.schedule_date,
	})
	lc.append("purchase_orders", {
		"purchase_order": po.name, "transaction_date": po.transaction_date,
		"grand_total": po.grand_total, "amount": po.grand_total,
	})
	lc.set_missing_values()
	out = lc.as_dict()
	out.update({"name": None, "__islocal": 1, "__unsaved": 1, "docstatus": 0})
	for table in lc.meta.get_table_fields():
		for row in out.get(table.fieldname) or []:
			row.update({"name": None, "parent": None, "__islocal": 1, "docstatus": 0})
	return out


@frappe.whitelist()
def purchase_order_hint(purchase_order):
	"""One line for the Purchase Order: does NRB require (or does it already have) an LC?"""
	po = frappe.db.get_value("Purchase Order", purchase_order,
		["supplier", "currency", "grand_total", "conversion_rate", "docstatus"], as_dict=True)
	if not po:
		return None
	lcs = frappe.db.sql(
		"""select distinct l.name, l.status from `tabLetter of Credit` l
		join `tabLC Purchase Order` p on p.parent = l.name
		where p.purchase_order = %s and l.docstatus = 1""",
		purchase_order, as_dict=True,
	)
	if lcs:
		return {"lcs": lcs}
	company_currency = frappe.db.get_value("Purchase Order", purchase_order, "company")
	company_currency = frappe.get_cached_value("Company", company_currency, "default_currency")
	if po.currency == company_currency:
		return None
	settings = frappe.get_cached_doc("LC Settings")
	if po.currency == "INR" and flt(settings.india_lc_threshold_inr) and flt(po.grand_total) > flt(settings.india_lc_threshold_inr):
		return {"message": _("Above INR {0}: NRB requires imports from India to go through an LC.").format(
			frappe.format_value(settings.india_lc_threshold_inr, {"fieldtype": "Float", "precision": 0}))}
	if po.currency != "INR" and flt(settings.draft_tt_limit_usd):
		from erpnext.setup.utils import get_exchange_rate

		rate = 1 if po.currency == "USD" else flt(get_exchange_rate(po.currency, "USD"))
		if rate and flt(po.grand_total) * rate > flt(settings.draft_tt_limit_usd):
			return {"message": _("Above USD {0}: pay this import by LC or documentary collection, not draft / TT.").format(
				frappe.format_value(settings.draft_tt_limit_usd, {"fieldtype": "Float", "precision": 0}))}
	return None
