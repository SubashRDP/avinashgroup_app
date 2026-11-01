"""Creates one Process Payment Reconciliation (PPR) per party in a single step.

A PPR covers exactly one company + one party. "Auto Reconcile Payments" in
Accounts Settings only runs PPRs that someone has already created and
submitted, so matching advances to unpaid invoices for a whole company means
opening and submitting hundreds of PPRs one at a time.

This document holds Company + Party Type once at the top and one row per party
below. Choosing the company fills the rows with that company's parties (the
party's `custom_company`) and their accounts, the same accounts ERPNext would
pick on an invoice (party's Accounts row, then its group, then the Company
default). On submit, every row becomes a submitted PPR, status Queued, and the
row keeps the link to it.

Batches for the same company can follow one another: a party whose PPR is still
Queued / Running / Paused is left out when the table fills, and a row added by
hand for such a party blocks the save, so no party is ever queued twice.

Deliberately narrow: no matching happens here. ERPNext's own 15-minute job
(process_payment_reconciliation.trigger_reconciliation_for_queued_docs) does
it, oldest invoice first, and only while "Auto Reconcile Payments" is ticked.
Cancelling this document does not cancel the PPRs it made: by then they may
have already reconciled; cancel those on the PPR list if needed.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_link_to_form

from erpnext.accounts.party import get_party_account

# Customer and Supplier are the only party types with a `custom_company` field
# to find "the company's parties" by, and the only ones PPR's advance-account
# filter knows (Customer -> Liability, everything else -> Asset).
PARTY_TYPES = ("Customer", "Supplier")

# the readable-name field on each party doctype, shown beside the party ID
PARTY_NAME_FIELD = {"Customer": "customer_name", "Supplier": "supplier_name"}

# PPR statuses that mean "not finished yet": a party with one of these already
# has a reconciliation on its way, so a second batch must not queue it again.
PENDING_STATUSES = ("Queued", "Running", "Paused")

# Payment Ledger balances under this count as settled (rounding left-overs).
SETTLED_BELOW = 0.005


class BulkPaymentReconciliation(Document):
	def validate(self):
		validate_party_type(self.party_type)

		names = party_names(self.party_type, [row.party for row in self.parties])
		pending = pending_pprs(self.company, self.party_type)
		seen = set()
		for row in self.parties:
			row.party_type = self.party_type
			row.party_name = names.get(row.party)
			if row.party in seen:
				frappe.throw(_("Row {0}: {1} is listed twice").format(row.idx, frappe.bold(row.party)))
			seen.add(row.party)
			# skipped already when the table is filled; this catches rows added by hand
			if row.party in pending:
				ppr, status = pending[row.party]
				frappe.throw(
					_("Row {0}: {1} already has {2} {3}. Remove the row or wait for it to finish.").format(
						row.idx, frappe.bold(row.party), get_link_to_form("Process Payment Reconciliation", ppr), status
					)
				)

	def on_submit(self):
		"""Create and submit one PPR per row. One failing row fails the whole
		submit, so no half-made batch is left behind."""
		for row in self.parties:
			ppr = frappe.get_doc(
				{
					"doctype": "Process Payment Reconciliation",
					"company": self.company,
					"party_type": self.party_type,
					"party": row.party,
					"receivable_payable_account": row.receivable_payable_account,
					"default_advance_account": row.default_advance_account,
					"from_invoice_date": row.from_invoice_date,
					"to_invoice_date": row.to_invoice_date,
					"from_payment_date": row.from_payment_date,
					"to_payment_date": row.to_payment_date,
					"cost_center": row.cost_center,
					"bank_cash_account": row.bank_cash_account,
				}
			)
			ppr.insert()
			ppr.submit()
			row.db_set("process_payment_reconciliation", ppr.name)

		frappe.msgprint(
			_("{0} Process Payment Reconciliation entries created and queued").format(len(self.parties)),
			indicator="green",
			alert=True,
		)
		if not frappe.db.get_single_value("Accounts Settings", "auto_reconcile_payments"):
			frappe.msgprint(
				_(
					"'Auto Reconcile Payments' is off in Accounts Settings, so these entries will stay "
					"Queued until it is ticked (or each one is started with Start / Resume)."
				),
				indicator="orange",
			)


def validate_party_type(party_type):
	if party_type not in PARTY_TYPES:
		frappe.throw(_("Party Type must be one of: {0}").format(", ".join(PARTY_TYPES)))


@frappe.whitelist()
def get_parties(company, party_type, only_with_open_items=1):
	"""Rows for the Parties table: the company's enabled parties with their
	receivable/payable and advance accounts. With `only_with_open_items`, only
	parties that have both something unpaid and something unallocated, i.e.
	something a PPR can actually match."""
	validate_party_type(party_type)

	name_field = PARTY_NAME_FIELD[party_type]
	parties = frappe.get_all(
		party_type,
		filters={"custom_company": company, "disabled": 0},
		fields=["name", name_field],
		order_by="name",
	)
	if cint(only_with_open_items):
		open_parties = parties_with_open_items(company, party_type)
		parties = [p for p in parties if p.name in open_parties]
	pending = pending_pprs(company, party_type)
	parties = [p for p in parties if p.name not in pending]

	rows = []
	for party in parties:
		# [receivable/payable, advance] — the advance is dropped when none is set anywhere
		accounts = get_party_account(party_type, party.name, company, include_advance=True)
		rows.append(
			{
				"party": party.name,
				"party_name": party.get(name_field),
				"receivable_payable_account": accounts[0],
				"default_advance_account": accounts[1] if len(accounts) > 1 else None,
			}
		)
	return rows


def pending_pprs(company, party_type):
	"""{party: (PPR name, status)} for submitted PPRs of this company that have
	not finished yet (PENDING_STATUSES)."""
	rows = frappe.get_all(
		"Process Payment Reconciliation",
		filters={
			"company": company,
			"party_type": party_type,
			"docstatus": 1,
			"status": ("in", PENDING_STATUSES),
		},
		fields=["party", "name", "status"],
	)
	return {r.party: (r.name, r.status) for r in rows}


def party_names(party_type, parties):
	"""{party ID: readable name} for the given parties."""
	if not parties:
		return {}
	name_field = PARTY_NAME_FIELD[party_type]
	return dict(
		frappe.get_all(party_type, filters={"name": ("in", parties)}, fields=["name", name_field], as_list=True)
	)


def parties_with_open_items(company, party_type):
	"""Parties with at least one open positive item (an unpaid invoice) and one
	open negative item (an unallocated payment / credit) in the Payment Ledger,
	the same ledger the PPR job reads."""
	return set(
		frappe.db.sql_list(
			"""
			SELECT party FROM (
				SELECT party, SUM(amount) AS balance
				FROM `tabPayment Ledger Entry`
				WHERE company = %(company)s AND party_type = %(party_type)s AND delinked = 0
				GROUP BY party, account, against_voucher_type, against_voucher_no
			) item
			GROUP BY party
			HAVING SUM(balance > %(settled)s) > 0 AND SUM(balance < -%(settled)s) > 0
			""",
			{"company": company, "party_type": party_type, "settled": SETTLED_BELOW},
		)
	)
