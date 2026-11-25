"""LC lifecycle — which step a Letter of Credit may take next, and what each step records.

    Draft ─submit (LC No., margin)→ Open ─depart date→ In Transit ─reach date→ Arrived
          ─transfer→ Transferred ─close→ Closed

    Any time while not closed:  Add Cost (bank charges, insurance, customs,
                                clearing, freight...), Deposit Margin
    Goods, sight LC:            Pay Goods (bank rate, margin used)
    Goods, usance LC:           Accept Bill → Pay at Maturity
    Arrived:                    Transfer to Stock / Fixed Asset (lc/transfer.py)

The shipment dates are plain fields that may be edited after submit; the status
follows them (`position()`). Everything that posts money is a step here.

Every step appends one row to the LC's History table (`LC Event`) carrying the
JE it posted and a JSON snapshot of what it changed: the LC's own totals, the
child rows it touched (their old values), the rows it added, and any document
it created elsewhere (Stock Entry, Asset). "Undo Last Step" is therefore
generic: cancel those, put the snapshot back, delete the added rows. Steps
write with `db_set` / `db_insert`, never a save of the submitted LC.

The LC's totals (cost by group, goods paid, margin held, status) are recomputed
from its rows after every step by `position()`, so no step keeps a running
total of its own.

Boundary: entries are built in `lc/accounting.py`, the transfer's documents in
`lc/transfer.py`; the LC's own submit / cancel live in its controller.

Landmine: steps run as whoever clicks but post JEs with ignore_permissions —
the gate is `_check_role`, not the JE's permissions.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from avinashgroup_app.lc import accounting

CLOSED_STATUSES = ("Closed", "Cancelled")

# Cost groups and the LC total each one adds up into (see LC Cost Type).
GROUP_FIELDS = {
	"Goods": "goods_cost",
	"Bank Charges": "bank_charges",
	"Insurance": "insurance_cost",
	"Customs": "customs_cost",
	"Clearing": "clearing_cost",
	"Freight": "freight_cost",
	"Other": "other_cost",
}

# Fields only the lifecycle writes: what an undo restores on the LC itself.
LIFECYCLE_FIELDS = tuple(GROUP_FIELDS.values()) + (
	"status", "total_cost", "vat_total", "goods_booked_fc", "goods_pending_fc", "acceptance_outstanding_fc",
	"transferred_cost", "margin_deposited", "margin_applied", "margin_released", "margin_balance",
	"exchange_difference", "transferred_on", "closed_on",
)

STEP_ROLES = ("Accounts User", "Accounts Manager", "System Manager")
UNDO_ROLES = ("Accounts Manager", "System Manager")


def _check_role(roles):
	if not set(roles) & set(frappe.get_roles()):
		frappe.throw(_("You need one of these roles: {0}").format(", ".join(roles)), frappe.PermissionError)


def _require_open(lc):
	if lc.docstatus != 1:
		frappe.throw(_("Submit the Letter of Credit first."))
	if lc.status in CLOSED_STATUSES:
		frappe.throw(_("{0} is {1}.").format(lc.name, _(lc.status)))


def _bank_account(lc, account):
	account = account or lc.bank_gl_account
	if not account:
		frappe.throw(_("Choose the bank account."))
	company, account_type, is_group = frappe.get_cached_value("Account", account, ["company", "account_type", "is_group"])
	if company != lc.company or is_group or account_type not in ("Bank", "Cash"):
		frappe.throw(_("{0} is not a bank or cash account of {1}.").format(account, lc.company))
	return account


def _positive(value, label):
	if flt(value) <= 0:
		frappe.throw(_("{0} must be more than zero.").format(label))
	return flt(value, 2)


def _date(value):
	return value or nowdate()


# ── Position ──────────────────────────────────────────────────────────────────


def max_amount(lc):
	return flt(flt(lc.lc_amount) * (1 + flt(lc.tolerance_plus) / 100), 2)


def position(lc):
	"""Totals and status from the LC's rows. Needs margin_deposited / released and the dates set."""
	totals = {field: 0.0 for field in GROUP_FIELDS.values()}
	vat = goods_fc = accepted_open_fc = margin_used = exchange = 0.0
	for c in lc.costs:
		if c.cost_group in GROUP_FIELDS:
			totals[GROUP_FIELDS[c.cost_group]] += flt(c.amount)
		vat += flt(c.vat_amount)
		if c.cost_group == "Goods":
			goods_fc += flt(c.fc_amount)
			if c.paid_via == "Acceptance" and not c.paid_on:
				accepted_open_fc += flt(c.fc_amount)
		margin_used += flt(c.margin_used) + flt(c.maturity_margin_used)
		exchange += flt(c.exchange_difference)

	if lc.docstatus == 2:
		status = "Cancelled"
	elif lc.closed_on:
		status = "Closed"
	elif lc.transferred_on:
		status = "Transferred"
	elif lc.arrival_date:
		status = "Arrived"
	elif lc.departure_date:
		status = "In Transit"
	else:
		status = "Open"

	out = {f: flt(v, 2) for f, v in totals.items()}
	out.update({
		"status": status,
		"total_cost": flt(sum(totals.values()), 2),
		"vat_total": flt(vat, 2),
		"goods_booked_fc": flt(goods_fc, 2),
		"goods_pending_fc": flt(max(flt(lc.lc_amount) - goods_fc, 0), 2),
		"acceptance_outstanding_fc": flt(accepted_open_fc, 2),
		"transferred_cost": flt(sum(flt(i.allocated_cost) for i in lc.items if i.stock_entry or i.asset_journal_entry), 2),
		"margin_applied": flt(margin_used, 2),
		"margin_balance": flt(flt(lc.margin_deposited) - margin_used - flt(lc.margin_released), 2),
		"exchange_difference": flt(exchange, 2),
	})
	return out


def refresh_position(lc):
	"""Recompute and store the totals (used after the shipment dates are edited)."""
	values = position(lc)
	lc.update(values)
	lc.db_set(values, notify=False, update_modified=False)


def record_event(lc, event, event_date, values=None, journal_entry=None, amount=None, remarks=None,
		touched=(), added=(), external=(), inserted=()):
	"""Apply one step and append its History row.

	`touched`  (row, {field: new value}) for child rows that already exist;
	           their old values go into the snapshot.
	`added`    child rows the step appended in memory (inserted here, so undo
	           deletes exactly them).
	`external` [doctype, name] of documents the step created elsewhere (Stock
	           Entry, Asset, an extra JE): undo cancels or deletes them.
	`inserted` child rows already saved by the form (a cost typed into the
	           grid); undo deletes them like `added`.
	"""
	before = {
		"lc": {f: lc.get(f) for f in LIFECYCLE_FIELDS},
		"touched": [],
		"added": [],
		"external": [list(x) for x in external],
	}
	for row, row_values in touched:
		before["touched"].append([row.doctype, row.name, {f: row.get(f) for f in row_values}])
		row.update(row_values)
		frappe.db.set_value(row.doctype, row.name, row_values, update_modified=False)
	for row in added:
		row.db_insert()
		before["added"].append([row.doctype, row.name])
	for row in inserted:
		before["added"].append([row.doctype, row.name])

	values = dict(values or {})
	lc.update(values)
	values.update(position(lc))
	lc.update(values)
	lc.db_set(values, notify=False)

	row = lc.append("events", {
		"event": event,
		"event_date": event_date,
		"status_after": values.get("status", lc.status),
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


def deposit_margin(lc, posting_date=None, amount=0, bank_account=None):
	"""Margin the bank blocks after opening, or a top-up."""
	posting_date = _date(posting_date)
	_require_open(lc)
	amount = _positive(amount, _("Margin"))
	je = accounting.post_margin(lc, posting_date, amount, _bank_account(lc, bank_account))
	record_event(lc, "Margin Deposited", posting_date, {"margin_deposited": flt(lc.margin_deposited) + amount},
		journal_entry=je, amount=amount)


# Cost row fields the user types; once posted they may not change (bill no. and remarks may).
COST_INPUT_FIELDS = ("posting_date", "cost_type", "amount", "vat_amount", "paid_via", "paid_from", "party")


def is_unposted_cost(row):
	return not row.journal_entry and row.cost_group != "Goods" and row.paid_via != "Acceptance"


def prepare_cost_row(lc, row):
	"""Check and complete one cost row before it is saved / posted (from the grid or add_cost)."""
	if not row.cost_type:
		frappe.throw(_("Costs row {0}: choose what the cost is.").format(row.idx))
	ctype = frappe.get_cached_doc("LC Cost Type", row.cost_type)
	if ctype.disabled:
		frappe.throw(_("Costs row {0}: {1} is disabled.").format(row.idx, row.cost_type))
	row.cost_group = ctype.cost_group
	row.posting_date = row.posting_date or nowdate()
	row.amount, row.vat_amount = flt(row.amount, 2), flt(row.vat_amount, 2)
	if ctype.cost_group == "VAT":
		# The whole amount is claimable VAT; none of it is cost.
		row.amount, row.vat_amount = 0, flt(row.amount + row.vat_amount, 2)
	if row.amount < 0 or row.vat_amount < 0 or row.amount + row.vat_amount <= 0:
		frappe.throw(_("Costs row {0}: give the amount of {1}.").format(row.idx, row.cost_type))
	if row.paid_via == "Party":
		if not row.party:
			frappe.throw(_("Costs row {0}: choose the party {1} is owed to.").format(row.idx, row.cost_type))
		row.paid_from = None
	else:
		row.paid_via = "Bank"
		row.party = None
		row.paid_from = _bank_account(lc, row.paid_from)
	row.description = row.remarks or ctype.cost_type_name


def post_cost_row(lc, row, inserted=True):
	"""Post the JE of one prepared cost row and record it. `inserted`: the row is already saved."""
	_require_open(lc)
	label = row.cost_type + (f" ({row.bill_no})" if row.bill_no else "")
	je = accounting.post_cost(lc, row.posting_date, label, row.amount, row.vat_amount, row.paid_from, row.party)
	row.journal_entry = je
	if inserted:
		row.db_update()
	record_event(lc, row.cost_type, row.posting_date, journal_entry=je, amount=flt(row.amount) + flt(row.vat_amount),
		remarks=row.remarks or row.bill_no, inserted=[row] if inserted else (), added=() if inserted else [row])


def _cost_value(row, field):
	value = row.get(field)
	if field in ("amount", "vat_amount"):
		return flt(value, 2)
	if field == "posting_date":
		return getdate(value) if value else None
	return value or None


def check_cost_edits(lc, before):
	"""Update of a submitted LC: posted cost rows may not change; which posted rows were deleted."""
	now = {r.name: r for r in lc.costs}
	removed = []
	for old in before.costs:
		if not old.journal_entry:
			continue
		new = now.get(old.name)
		if new is None:
			if old.cost_group == "Goods":
				frappe.throw(_("A goods payment cannot be deleted from the table. Use Undo Last Step."))
			if lc.transferred_on:
				frappe.throw(_("The goods are already transferred at their cost: undo the transfer before deleting a cost."))
			removed.append(old)
			continue
		changed = [f for f in COST_INPUT_FIELDS if _cost_value(old, f) != _cost_value(new, f)]
		if changed:
			frappe.throw(_("Costs row {0} ({1}) is already posted in {2}. Delete the row and add it again instead of changing it.").format(
				new.idx, old.cost_type or old.description, old.journal_entry))
	return removed


def remove_cost_row(lc, old):
	"""A posted cost row was deleted from the grid: cancel its JE and drop its History row."""
	accounting.cancel_journal_entry(old.journal_entry)
	for event in list(lc.events):
		added = (json.loads(event.previous_values or "{}").get("added") or [])
		if ["LC Cost", old.name] in added:
			frappe.db.delete("LC Event", {"name": event.name})
			lc.events.remove(event)
	lc.add_comment("Info", _("Cost removed: {0} {1} ({2} cancelled)").format(
		old.cost_type, frappe.format_value(flt(old.amount) + flt(old.vat_amount), {"fieldtype": "Currency"}), old.journal_entry))


def add_cost(lc, cost_type=None, posting_date=None, amount=0, vat_amount=0, paid_via="Bank",
		bank_account=None, party=None, bill_no=None, remarks=None):
	"""One cost of the import, booked by API (the form books costs through its Costs grid)."""
	_require_open(lc)
	row = lc.append("costs", {
		"cost_type": cost_type, "posting_date": posting_date or nowdate(), "amount": amount,
		"vat_amount": vat_amount, "paid_via": paid_via, "paid_from": bank_account, "party": party,
		"bill_no": bill_no, "remarks": remarks,
	})
	prepare_cost_row(lc, row)
	post_cost_row(lc, row, inserted=False)


def _check_goods_amount(lc, fc_amount):
	booked = sum(flt(c.fc_amount) for c in lc.costs if c.cost_group == "Goods")
	if booked + fc_amount > max_amount(lc) + 0.005:
		frappe.throw(
			_("This takes the goods paid / accepted to {0} {1}; the LC allows {0} {2}. Amend the LC amount first.").format(
				lc.currency, flt(booked + fc_amount, 2), max_amount(lc)),
			title=_("Over the LC amount"),
		)


def default_margin_use(lc, fc_amount):
	"""Margin a goods payment uses unless told otherwise: its share of what is held, all of it on the last."""
	position_now = position(lc)
	held = position_now["margin_balance"]
	if held <= 0:
		return 0
	unpaid_fc = position_now["goods_pending_fc"] + position_now["acceptance_outstanding_fc"]
	if unpaid_fc <= 0 or flt(fc_amount) >= unpaid_fc - 0.005:
		return flt(held, 2)
	return flt(held * flt(fc_amount) / unpaid_fc, 2)


def _check_margin(lc, margin_used):
	held = position(lc)["margin_balance"]
	if flt(margin_used) < 0 or flt(margin_used) > held + 0.005:
		frappe.throw(_("Margin used must be between 0 and the margin held ({0}).").format(held))


def pay_goods(lc, posting_date=None, fc_amount=0, exchange_rate=0, margin_used=None, bank_account=None, remarks=None):
	"""Sight LC: the bank paid the supplier (all or part of the LC) at its own rate."""
	posting_date = _date(posting_date)
	_require_open(lc)
	if lc.drafts_at == "Usance":
		frappe.throw(_("A usance LC is paid through Accept Bill, then Pay at Maturity."))
	fc_amount = _positive(fc_amount, _("Amount"))
	exchange_rate = _positive(exchange_rate, _("Bank rate"))
	_check_goods_amount(lc, fc_amount)
	if margin_used in (None, ""):
		margin_used = default_margin_use(lc, fc_amount)
	_check_margin(lc, margin_used)
	bank_account = _bank_account(lc, bank_account)

	je, total = accounting.post_goods_payment(lc, posting_date, fc_amount, exchange_rate, margin_used, bank_account)
	row = lc.append("costs", {
		"posting_date": posting_date, "cost_group": "Goods",
		"description": _("Goods: {0} {1} at {2}").format(lc.currency, fc_amount, exchange_rate),
		"amount": total, "paid_via": "Bank", "paid_from": bank_account, "party": lc.supplier,
		"fc_amount": fc_amount, "exchange_rate": exchange_rate, "margin_used": flt(margin_used, 2),
		"journal_entry": je, "remarks": remarks,
	})
	record_event(lc, "Goods Paid", posting_date, journal_entry=je, amount=total,
		remarks=_("{0} {1} at {2}").format(lc.currency, fc_amount, exchange_rate), added=[row])


def accept_bill(lc, posting_date=None, fc_amount=0, exchange_rate=0, maturity_date=None, remarks=None):
	"""Usance LC: the documents are accepted; the supplier is owed the bill until it matures."""
	posting_date = _date(posting_date)
	_require_open(lc)
	if lc.drafts_at != "Usance":
		frappe.throw(_("Acceptance is for usance LCs. Use Pay Goods on a sight LC."))
	fc_amount = _positive(fc_amount, _("Amount"))
	exchange_rate = _positive(exchange_rate, _("Rate"))
	_check_goods_amount(lc, fc_amount)
	maturity_date = maturity_date or lc.maturity_date
	if not maturity_date:
		frappe.throw(_("Give the maturity date."))
	if getdate(maturity_date) < getdate(posting_date):
		frappe.throw(_("The bill cannot mature before it is accepted."))

	je, total = accounting.post_acceptance(lc, posting_date, fc_amount, exchange_rate)
	row = lc.append("costs", {
		"posting_date": posting_date, "cost_group": "Goods",
		"description": _("Goods accepted: {0} {1} at {2}").format(lc.currency, fc_amount, exchange_rate),
		"amount": total, "paid_via": "Acceptance", "party": lc.supplier,
		"fc_amount": fc_amount, "exchange_rate": exchange_rate, "maturity_date": maturity_date,
		"journal_entry": je, "remarks": remarks,
	})
	record_event(lc, "Bill Accepted", posting_date, journal_entry=je, amount=total,
		remarks=_("Matures {0}").format(frappe.format(maturity_date, "Date")), added=[row])


def _acceptance(lc, cost_row):
	row = next((c for c in lc.costs if c.name == cost_row), None)
	if not row or row.paid_via != "Acceptance":
		frappe.throw(_("Choose an accepted bill of {0}.").format(lc.name))
	if row.paid_on:
		frappe.throw(_("That bill was paid on {0}.").format(frappe.format(row.paid_on, "Date")))
	return row


def pay_maturity(lc, cost_row=None, posting_date=None, exchange_rate=0, margin_used=None, bank_account=None):
	"""The bank paid an accepted bill on maturity, at its own rate."""
	posting_date = _date(posting_date)
	_require_open(lc)
	bill = _acceptance(lc, cost_row)
	exchange_rate = _positive(exchange_rate, _("Bank rate"))
	if margin_used in (None, ""):
		margin_used = default_margin_use(lc, bill.fc_amount)
	_check_margin(lc, margin_used)
	bank_account = _bank_account(lc, bank_account)

	je, v = accounting.post_maturity_payment(lc, bill, posting_date, exchange_rate, margin_used, bank_account)
	record_event(lc, "Bill Paid at Maturity", posting_date, journal_entry=je, amount=v.bank_total,
		remarks=_("{0} {1} at {2}").format(lc.currency, bill.fc_amount, exchange_rate),
		touched=[(bill, {
			"paid_on": posting_date, "maturity_rate": exchange_rate, "maturity_margin_used": v.margin_used,
			"exchange_difference": v.exchange_difference, "maturity_journal_entry": je,
		})])


def transfer(lc, posting_date=None):
	"""The goods arrived: move the landed cost into stock and fixed assets."""
	from avinashgroup_app.lc import transfer as lc_transfer

	posting_date = _date(posting_date)
	_require_open(lc)
	lc_transfer.transfer(lc, posting_date)


def close(lc, posting_date=None, bank_account=None, residual_account=None, remarks=None):
	"""Close the LC: no unpaid bill may remain; unused margin comes back; transit is cleared."""
	posting_date = _date(posting_date)
	_require_open(lc)
	open_bills = [c for c in lc.costs if c.paid_via == "Acceptance" and not c.paid_on]
	if open_bills:
		frappe.throw(_("{0} accepted bill(s) are not paid yet.").format(len(open_bills)))
	if lc.items and not lc.transferred_on:
		frappe.throw(_("Transfer the goods to stock or assets first."))

	external = []
	je = None
	values = {"closed_on": posting_date}
	release = position(lc)["margin_balance"]
	if release > 0.005:
		je = accounting.post_margin_release(lc, posting_date, release, _bank_account(lc, bank_account))
		values["margin_released"] = flt(lc.margin_released) + release
	residual = accounting.transit_balance(lc)
	if abs(residual) >= 0.01:
		if not residual_account:
			frappe.throw(
				_("LC Goods in Transit still holds {0} for this LC (a cost booked after the transfer, or rounding). Choose the account to clear it to.").format(
					frappe.format_value(residual, {"fieldtype": "Currency"})),
				title=_("Balance left in transit"),
			)
		residual_je = accounting.post_residual(lc, posting_date, residual, residual_account)
		external.append(["Journal Entry", residual_je])
	record_event(lc, "Closed", posting_date, values, journal_entry=je, amount=release or None,
		remarks=remarks, external=external)


def undo_last_step(lc):
	if lc.docstatus != 1:
		frappe.throw(_("Submit the Letter of Credit first."))
	if len(lc.events) <= 1:
		frappe.throw(_("Nothing to undo. Cancel the LC to withdraw it."))
	last = lc.events[-1]
	before = json.loads(last.previous_values or "{}")

	from avinashgroup_app.lc import transfer as lc_transfer

	# Rows first, so nothing on the LC still points at what is cancelled next.
	for doctype, name in before.get("added") or []:
		frappe.db.delete(doctype, {"name": name})
	for doctype, name, row_values in before.get("touched") or []:
		frappe.db.set_value(doctype, name, row_values, update_modified=False)
	for doctype, name in reversed(before.get("external") or []):
		lc_transfer.undo_document(doctype, name)
	accounting.cancel_journal_entry(last.journal_entry)
	lc.db_set({f: v for f, v in (before.get("lc") or {}).items() if f in LIFECYCLE_FIELDS}, notify=False)
	frappe.db.delete("LC Event", {"name": last.name})
	# Recompute rather than trust the snapshot's totals: a cost row deleted from
	# the grid since then changed them.
	refresh_position(frappe.get_doc("Letter of Credit", lc.name))
	lc.add_comment("Info", _("Undid step: {0} ({1})").format(last.event, last.journal_entry or _("no entry")))
	lc.notify_update()


# ── Whitelisted entry points ──────────────────────────────────────────────────

ACTIONS = {
	"deposit_margin": deposit_margin,
	"add_cost": add_cost,
	"pay_goods": pay_goods,
	"accept_bill": accept_bill,
	"pay_maturity": pay_maturity,
	"transfer": transfer,
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
def margin_suggestion(name, fc_amount):
	"""Margin a goods payment of `fc_amount` would use by default, for the dialog."""
	lc = frappe.get_doc("Letter of Credit", name)
	lc.check_permission("read")
	return default_margin_use(lc, flt(fc_amount))


@frappe.whitelist()
def maturity_preview(name, cost_row, exchange_rate, margin_used=None):
	"""What Pay at Maturity would post, for the dialog to show before the user confirms."""
	lc = frappe.get_doc("Letter of Credit", name)
	lc.check_permission("read")
	bill = _acceptance(lc, cost_row)
	if margin_used in (None, ""):
		margin_used = default_margin_use(lc, bill.fc_amount)
	return accounting.maturity_values(lc, bill, flt(exchange_rate), flt(margin_used))
