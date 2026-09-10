# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""General Ledger Posting Detail — postings, filtered the way the books are kept.

Built to the spec in "General ledger posting date.xlsx": a posting-level ledger
whose filters are the ones an operator actually reaches for — voucher type and
its subtype, the party, the period, and a voucher number — with the rows
grouped by account, by party, or by both.

    Posting Miti | Voucher Type | Voucher No. | Party Name/Description
                                  Narr:(remarks)
                 | Debit | Credit | Balance

Two things are deliberate:

*Subtype* is per-doctype, not one field. A Journal Entry's is custom_p_type
(JV Type), a Purchase Invoice's is custom_purchase_type, and a Sales Invoice
has none at all -- "Sales" and "Sales Return" are the is_return flag. Rather
than force one column onto all of them, SUBTYPE_SOURCE names where each lives
and the filter builds an EXISTS per doctype.

*The narration is its own row*, printed under the posting rather than beside
it. Remarks run long, and the spec's layout puts them on a second line.
"""

import json
import os

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate
from frappe.core.doctype.user_permission.user_permission import get_user_permissions

# The doctypes worth ledgering, and where each keeps its subtype.
#   doctype -> (field on the document, the doctype that field links to)
# A None field means the subtype comes from somewhere else, or nowhere.
SUBTYPE_SOURCE = {
	"Sales Invoice": (None, None),
	"Purchase Invoice": ("custom_purchase_type", "Purchase Type"),
	"Payment Entry": ("custom_p_type", "Payment - Receipt Type"),
	"Journal Entry": ("custom_p_type", "JV Type"),
	"Purchase Receipt": ("custom_receipt_type", "Receipt type"),
	"Stock Entry": (None, None),
	"Stock Reconciliation": (None, None),
}

# Sales Invoice has no subtype doctype; the split is the return flag.
SALES_SUBTYPES = {"Sales": 0, "Sales Return": 1}

PARTY_TYPES = ("Supplier", "Customer", "Employee")

PARTY_NAME_FIELD = {
	"Customer": "customer_name",
	"Supplier": "supplier_name",
	"Employee": "employee_name",
}

CATEGORIES = ("Account", "Party", "Both")

# A cheque number typed to fill the field rather than to record a cheque. 17,505
# of 27,421 Payment Entries carry "1", and 37 Journal Entries do. It matters
# because custom_chequereference_miti is written on every one of those 27,421
# rows: without this, two payments in three would state a cheque date for a
# cheque that does not exist.
CHEQUE_PLACEHOLDERS = {"", "1"}

# What a JV Type is *called* where it stands in for a description. The legacy
# Posting Detail heads a plain journal "Journal", and so does the voucher; the JV
# Type record is named "Journal Entry". Only the printed label differs -- the
# record is left alone, 108 vouchers point at it.
JV_TYPE_LABEL = {"Journal Entry": "Journal"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate(filters)

	postings = _get_postings(filters)
	# No early return on an empty period: an account can carry a balance into a
	# window in which nothing moved, and that balance is the answer to the
	# question being asked. Returning nothing meant splitting a year in two
	# gave a first half closing at 8,50,63,74,498.62 and a second half showing
	# an empty report.
	_decorate(postings, filters.company)
	columns = _get_columns(filters)
	return columns, _build_rows(
		filters, postings, with_narration=True, columns=columns, always_narration=True
	)


def _allowed_companies():

	if frappe.session.user == "Administrator":
		return None
	

	companies = [p.get("doc") for p in (get_user_permissions().get("Company") or []) if p.get("doc")]
	return companies or None


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def company_query(doctype, txt, searchfield, start, page_len, filters):
	"""Companies for the report's Company picker.

	Deliberately not the stock Link search: this offers only the companies the
	user actually has a Company User Permission for, and offers all of them --
	no page limit, because the whole point is to choose from the full set
	rather than page through it.
	"""
	allowed = _allowed_companies()
	conditions = ["name LIKE %(txt)s"]
	params = {"txt": "%{0}%".format(txt or "")}
	if allowed is not None:
		conditions.append("name IN %(allowed)s")
		params["allowed"] = tuple(allowed)

	return frappe.db.sql(
		"SELECT name FROM `tabCompany` WHERE {0} ORDER BY name".format(" AND ".join(conditions)),
		params,
	)


def _validate(filters):
	if not filters.company:
		frappe.throw(_("Please select a Company."))
	# The picker only offers permitted companies, but the report is whitelisted
	# and its filters arrive from the client, so the scope is enforced here too
	# rather than trusted.
	allowed = _allowed_companies()
	if allowed is not None and filters.company not in allowed:
		frappe.throw(_("You are not permitted to view {0}.").format(frappe.bold(filters.company)))
	if not (filters.from_date and filters.to_date):
		frappe.throw(_("Please select From Date and To Date."))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))


def _normalize(value):
	"""Return a cleaned list for MultiSelectList / Select inputs."""
	if not value:
		return []
	if isinstance(value, str):
		value = value.strip()
		if not value:
			return []
		if value.startswith("[") and value.endswith("]"):
			try:
				parsed = json.loads(value)
				return [v for v in parsed if v] if isinstance(parsed, list) else []
			except ValueError:
				return []
		return [value]
	if isinstance(value, (list, tuple)):
		return [v for v in value if v]
	return []


def _subtype_clause(filters, params):
	"""Restrict to the chosen subtypes, per doctype.

	Subtype lives on the document, not on GL Entry, and in a different field for
	each doctype -- so this is an EXISTS per doctype rather than one join. A
	doctype with no subtype selected is left unrestricted.
	"""
	subtypes = _normalize(filters.get("voucher_subtype"))
	if not subtypes:
		return ""

	clauses = []
	for index, doctype in enumerate(sorted(SUBTYPE_SOURCE)):
		field, _linked = SUBTYPE_SOURCE[doctype]

		if doctype == "Sales Invoice":
			flags = [SALES_SUBTYPES[s] for s in subtypes if s in SALES_SUBTYPES]
			if not flags:
				continue
			key = "si_returns_{0}".format(index)
			params[key] = flags
			clauses.append(
				"(g.voucher_type = 'Sales Invoice' AND EXISTS ("
				"SELECT 1 FROM `tabSales Invoice` d WHERE d.name = g.voucher_no"
				" AND d.is_return IN %({0})s))".format(key)
			)
			continue

		if not field or not frappe.db.has_column(doctype, field):
			continue

		key = "subtypes_{0}".format(index)
		params[key] = subtypes
		clauses.append(
			"(g.voucher_type = %(vt_{0})s AND EXISTS ("
			"SELECT 1 FROM `tab{1}` d WHERE d.name = g.voucher_no"
			" AND d.`{2}` IN %({3})s))".format(index, doctype, field, key)
		)
		params["vt_{0}".format(index)] = doctype

	if not clauses:
		return ""
	return "AND ({0})".format(" OR ".join(clauses))


def _get_postings(filters):
	"""GL Entry rows in the period, narrowed by every filter that applies."""
	params = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
	}
	conditions = [
		"g.company = %(company)s",
		"g.is_cancelled = 0",
		"g.posting_date BETWEEN %(from_date)s AND %(to_date)s",
	]

	# An entry flagged is_opening carries a balance forward; it is not something
	# that happened in the period. It belongs in the Opening Balance, and is
	# taken there by _opening_balances -- so it must not also be counted here,
	# or the same row lands in both and the section stops footing. ERPNext makes
	# the same split, as an if/elif so a row can only ever be in one place
	# (general_ledger.py:527). "Show Opening Entries" moves them back into the
	# period instead, and _opening_balances then leaves them alone.
	if not cint(filters.get("show_opening_entries")):
		conditions.append("g.is_opening = 'No'")

	accounts = _normalize(filters.get("account"))
	if accounts:
		from erpnext.accounts.report.general_ledger.general_ledger import get_accounts_with_children

		params["accounts"] = get_accounts_with_children(accounts)
		conditions.append("g.account IN %(accounts)s")

	voucher_types = _normalize(filters.get("voucher_type"))
	if voucher_types:
		params["voucher_types"] = voucher_types
		conditions.append("g.voucher_type IN %(voucher_types)s")

	party_types = _normalize(filters.get("party_type"))
	if party_types:
		params["party_types"] = party_types
		conditions.append("g.party_type IN %(party_types)s")

	parties = _normalize(filters.get("party"))
	if parties:
		params["parties"] = parties
		conditions.append("g.party IN %(parties)s")

	subtype_clause = _subtype_clause(filters, params)

	rows = frappe.db.sql(
		"""
		SELECT g.name, g.posting_date, g.account, g.voucher_type, g.voucher_no,
		       IFNULL(g.party_type, '') AS party_type, IFNULL(g.party, '') AS party,
		       g.debit, g.credit, g.remarks, g.against
		FROM `tabGL Entry` g
		WHERE {conditions}
		  {subtype_clause}
		ORDER BY g.posting_date, g.creation
		""".format(conditions=" AND ".join(conditions), subtype_clause=subtype_clause),
		params,
		as_dict=True,
	)

	# Voucher number is filtered after the fact: it lives in a different field
	# per doctype (Numbering Configuration), so it cannot be a SQL condition
	# without joining every doctype in play.
	wanted_number = (filters.get("voucher_no") or "").strip().lower()
	if wanted_number:
		from avinashgroup_app.utils.voucher_numbers import resolve

		numbers = resolve((r.voucher_type, r.voucher_no) for r in rows)
		rows = [
			r
			for r in rows
			if wanted_number in str(numbers.get((r.voucher_type, r.voucher_no), r.voucher_no)).lower()
		]

	return rows


def _describe_against(against, company, names=None):
	"""What a party-less posting was posted against, in readable form.

	`against` holds two quite different things. Usually it is contra accounts,
	which arrive as "549301 - R & M - Vehicles O/O - NGI, 544121 - Office
	Expenses - NGI" -- the account number and company abbreviation repeat on
	every one and carry nothing here. But on a party-side posting it holds the
	party id instead, so those are resolved to a name rather than printed raw.
	"""
	if not against:
		return ""
	suffix = _company_suffix(company)
	names = names or {}
	out = []
	for part in str(against).split(","):
		part = part.strip()
		if not part:
			continue
		# a party id rather than an account
		resolved = names.get(("", part))
		if resolved:
			out.append(resolved)
			continue
		out.append(_trim_account(part, suffix))
	return ", ".join(out)


def _trim_account(account, suffix):
	"""An account as a ledger prints it: no leading number, no company suffix.

	"145201 - Global IME Bank A/c 10101010000310 - NGI" reads
	"Global IME Bank A/c 10101010000310", which is what the legacy Posting Detail
	puts in its Bank/Cash/Journal Description column.
	"""
	part = str(account or "").strip()
	if suffix and part.endswith(suffix):
		part = part[: -len(suffix)]
	head, sep, tail = part.partition(" - ")
	if sep and head.strip().isdigit():
		part = tail
	return part.strip()


def _company_suffix(company):
	return " - {0}".format(frappe.get_cached_value("Company", company, "abbr")) if company else ""


def _journal_descriptions(postings):
	"""Per Journal Entry in view: its JV Type, its cash/bank legs, its cheque.

	Every Journal Entry, whatever its JV Type. The type is not a gate -- it is only
	what the description falls back to when the entry moved through no cash or
	bank account. See _journal_description().
	"""
	vouchers = sorted(
		{p.voucher_no for p in postings if p.voucher_type == "Journal Entry" and p.voucher_no}
	)
	if not vouchers:
		return {}

	entries = {}
	for start in range(0, len(vouchers), 500):
		for row in frappe.db.sql(
			"""SELECT name, custom_p_type, custom_paid_to, cheque_no, custom_reference_miti
			   FROM `tabJournal Entry` WHERE name IN %(names)s""",
			{"names": vouchers[start : start + 500]},
			as_dict=True,
		):
			row.cash_bank = []
			entries[row.name] = row

	if not entries:
		return {}

	names = sorted(entries)
	for start in range(0, len(names), 500):
		for row in frappe.db.sql(
			"""SELECT ja.parent, ja.account FROM `tabJournal Entry Account` ja
			   JOIN `tabAccount` a ON a.name = ja.account
			   WHERE ja.parent IN %(names)s AND a.account_type IN ('Cash', 'Bank')
			   ORDER BY ja.idx""",
			{"names": names[start : start + 500]},
			as_dict=True,
		):
			entries[row.parent].cash_bank.append(row.account)

	return entries


def _journal_description(entry, own_account, suffix):
	"""The Bank/Cash/Journal Description for one posting.

	Two rules, and the JV Type gates neither of them:

	  1. the entry moved through cash or a bank -> that account
	  2. it did not                             -> its JV Type

	Which is what the legacy print does -- "Prabhu Bank Ltd A/C 0010101244800011"
	against "Journal" -- and the ledger reads the same whether the voucher was
	keyed as a Bank Entry, a Contra or a plain journal.

	A cash/bank leg other than the row's own is preferred, so on a bank-to-bank
	contra each bank's row names the other bank. When the row's own account is the
	only cash/bank leg, it is named all the same -- the JV Type is for entries that
	touched no cash or bank at all. Falling back to it there printed "Cash/ Bank or
	Contra Voucher" on the bank's own ledger where the bank's name belongs.
	"""
	for account in entry.cash_bank:
		if account != own_account:
			return _trim_account(account, suffix)
	if entry.cash_bank:
		return _trim_account(entry.cash_bank[0], suffix)
	p_type = entry.custom_p_type or ""
	return JV_TYPE_LABEL.get(p_type, p_type)


def _cheque(number):
	"""A cheque number, or "" when the field holds a placeholder instead."""
	number = str(number or "").strip()
	return "" if number in CHEQUE_PLACEHOLDERS else number


def _paid_line(who, ref_no, miti):
	"""The sub-line: "Paid To/Receive From: <who>  Ref: <no>  Dt: <miti>".

	Printed only when the voucher's own Paid To / Receive From field holds
	something, and that field is the only source of the name. Two earlier forms
	were wrong in ways worth remembering:

	  - A fixed "Paid:" read every receipt backwards -- 8,614 Payment Entry
	    receipts and 136 journals were printing "Paid:" for money that came in.
	    The field's own label says both directions, so the line uses it.
	  - Falling back to the party misfired on a leg with no party of its own,
	    where the "party" is its contra accounts: "Paid: Global IME Bank A/c ...",
	    a bank standing where a payee belongs.

	Ref and Dt follow the cheque rule -- a placeholder number has no date worth
	printing, so both go together or not at all.
	"""
	who = str(who or "").strip()
	if not who:
		return ""
	out = "Paid To/Receive From: {0}".format(who)
	ref = _cheque(ref_no)
	if ref:
		out += "  Ref: {0}".format(ref)
		miti = str(miti or "").strip().split(" ")[0]
		if miti:
			out += "  Dt: {0}".format(miti)
	return out


def _payment_details(postings):
	"""Per Payment Entry in view: its payee and its cheque.

	Only the sub-line is loaded. A Payment Entry's description column is left as
	it is -- it already reads correctly through its contra accounts.
	"""
	vouchers = sorted(
		{p.voucher_no for p in postings if p.voucher_type == "Payment Entry" and p.voucher_no}
	)
	if not vouchers:
		return {}
	out = {}
	for start in range(0, len(vouchers), 500):
		for row in frappe.db.sql(
			"""SELECT name, custom_paid_to_from, reference_no, custom_chequereference_miti
			   FROM `tabPayment Entry` WHERE name IN %(names)s""",
			{"names": vouchers[start : start + 500]},
			as_dict=True,
		):
			out[row.name] = row
	return out


def _decorate(postings, filters_company=None):
	"""Add the BS miti, the printed voucher number as a link, and party names."""
	from avinashgroup_app.custom_code.CBMS.utils import bs_date_str
	from avinashgroup_app.utils.voucher_numbers import link, resolve

	numbers = resolve((r.voucher_type, r.voucher_no) for r in postings)
	journals = _journal_descriptions(postings)
	payments = _payment_details(postings)
	suffix = _company_suffix(filters_company)

	# Some rows carry a party with no party_type -- 343 in a fortnight on NGI.
	# Those still have a name to show, so they are looked up against every party
	# doctype rather than skipped, which would print the raw id.
	wanted = {}
	untyped = set()
	for r in postings:
		if not r.party:
			continue
		if r.party_type:
			wanted.setdefault(r.party_type, set()).add(r.party)
		else:
			untyped.add(r.party)
	# `against` can hold a party id too, so those go through the same lookup
	for r in postings:
		if not r.party and r.against:
			for part in str(r.against).split(","):
				part = part.strip()
				if part and " - " not in part:
					untyped.add(part)

	for party_type in PARTY_TYPES:
		if untyped:
			wanted.setdefault(party_type, set()).update(untyped)

	party_names = {}
	for party_type, names in wanted.items():
		field = PARTY_NAME_FIELD.get(party_type)
		if not field or not frappe.db.has_column(party_type, field):
			continue
		names = list(names)
		for start in range(0, len(names), 500):
			for row in frappe.get_all(
				party_type,
				filters={"name": ("in", names[start : start + 500])},
				fields=["name", "{0} as label".format(field)],
			):
				party_names[(party_type, row.name)] = row.label
				# so an untyped party can be found without knowing its type
				party_names.setdefault(("", row.name), row.label)

	for r in postings:
		try:
			r.miti = bs_date_str(r.posting_date)
		except Exception:
			r.miti = ""
		r.number = numbers.get((r.voucher_type, r.voucher_no)) or r.voucher_no
		r.voucher_link = link(r.voucher_type, r.voucher_no, r.number)
		r.party_name = (
			party_names.get((r.party_type, r.party))
			or (r.party if r.party else "")
			or _describe_against(r.against, filters_company, party_names)
		)

		# The legacy Posting Detail's Bank/Cash/Journal Description column. Kept
		# beside party_name rather than replacing it: the party name is what a
		# Party or Both block is headed by, and a block titled "Journal" would be
		# the same defect 47c8774 fixed at the other end.
		entry = journals.get(r.voucher_no) if r.voucher_type == "Journal Entry" else None
		# Every Journal Entry, whatever its JV Type: the JV Type is only what the
		# description falls back to when the entry touched no cash or bank account.
		r.description = _journal_description(entry, r.account, suffix) if entry else ""

		# The Paid To / Receive From sub-line: only where the voucher's own field
		# says who. Journal Entry keeps it in custom_paid_to, Payment Entry in
		# custom_paid_to_from; each has its own reference number and miti.
		payment = payments.get(r.voucher_no) if r.voucher_type == "Payment Entry" else None
		if entry:
			r.paid = _paid_line(entry.custom_paid_to, entry.cheque_no, entry.custom_reference_miti)
		elif payment:
			r.paid = _paid_line(
				payment.custom_paid_to_from, payment.reference_no, payment.custom_chequereference_miti
			)
		else:
			r.paid = ""


def _section_key(filters, posting):
	"""What this posting is grouped under, per "Categorized by"."""
	category = filters.get("categorized_by") or "Account"
	if category == "Party":
		return (posting.party_type or "", posting.party or "")
	if category == "Both":
		return (posting.account, posting.party_type or "", posting.party or "")
	return (posting.account,)


def _party_label(party_type, party):
	"""A party's display name, for a section with no postings to read it from."""
	if not (party_type and party):
		return ""
	field = PARTY_NAME_FIELD.get(party_type)
	if not field or not frappe.db.has_column(party_type, field):
		return ""
	return frappe.db.get_value(party_type, party, field) or ""


def _section_label(filters, key, postings):
	category = filters.get("categorized_by") or "Account"
	if not postings:
		# a section that carries a balance but saw no movement -- the key is all
		# there is to name it by
		if category == "Party":
			return _party_label(key[0], key[1]) or key[1] or _("No Party")
		if category == "Both":
			return "{0}  —  {1}".format(key[0], _party_label(key[1], key[2]) or key[2] or _("No Party"))
		return key[0]
	sample = postings[0]
	# Named from the key, not from the first posting in it. A posting with no party
	# still carries a Party Name -- for those, _describe_against() fills the column
	# with whoever the entry was posted against, so the expense and VAT legs of a
	# purchase read "Bhat-Bhateni Super Market". Useful on the line, wrong on the
	# heading: every party-less posting in the period shares the one ("", "") key,
	# so the block holding all of them was titled after whichever sorted first and
	# claimed the other suppliers' expense legs as its own.
	if category == "Party":
		return (sample.party_name or _("No Party")) if key[1] else _("No Party")
	if category == "Both":
		party = (sample.party_name or _("No Party")) if key[2] else _("No Party")
		return "{0}  —  {1}".format(sample.account, party)
	return sample.account


# ERPNext writes this placeholder when a voucher carries no narration at all --
# 778,865 of avinas1's 954,582 GL rows, so printing it would put a noise line
# under four postings in five.
EMPTY_REMARKS = {"no remarks", "no remark", "none", "-", "n/a", "na", "nil", "-do-"}

# Labels that introduce a narration but carry none themselves. Stripped before
# the emptiness test, so "Note:" and "Narration :-" are recognised as empty
# rather than printed as a row that says nothing.
NARRATION_LABELS = ("note", "narration", "narr", "remarks", "remark", "ref")


def _clean_narration(remarks):
	"""A one-line narration, or "" when there is nothing worth printing.

	Remarks arrive with newlines (reference lines, multi-line notes) and with
	_x000D_ left behind by the spreadsheet imports; both would break the row.

	A narration row exists to say something. Whitespace says nothing, and
	neither does a bare label -- "Note:", "Narration :-", "N/A" -- so those are
	treated as empty and no row is emitted at all.
	"""
	if not remarks:
		return ""

	text = " ".join(str(remarks).replace("_x000D_", " ").split())
	if not text:
		return ""

	# what is left once the label and its punctuation are taken off
	body = text
	lowered = body.lower()
	for label in NARRATION_LABELS:
		if lowered.startswith(label):
			body = body[len(label) :]
			break
	body = body.strip(" .:;-–—_*()[]/\\")

	if not body or body.lower() in EMPTY_REMARKS:
		return ""
	return text


def _opening_balances(filters, postings, totals_out=None):
	"""Balance carried into the period, keyed the same way the sections are.

	`totals_out`, when given, is filled with key -> [debit, credit]: the gross
	totals behind each balance, which the printed ledger states beside it.

	Income and Expense accounts do not carry a balance across a year end -- a
	Period Closing Voucher sweeps them into retained earnings, and this site
	runs none -- so their history stops at the fiscal year start. When the
	report begins on that date they carry nothing at all and are skipped.

	The two classes are split in Python rather than joined to tabAccount in the
	query: the join costs the optimiser the fin_stmt_agg_index and turned this
	into a 14.8s scan, which alone tripped Frappe's 15s prepared-report timer.
	"""
	# Accounts come from the postings in the period, plus any the user asked
	# for explicitly. Without the second half, an account picked by name that
	# happened to have no movement in the window reported no opening balance at
	# all -- a filtered month showed 0.00 where the account plainly carried a
	# balance into it.
	accounts = set(p.account for p in postings)
	chosen = _normalize(filters.get("account"))
	if chosen:
		from erpnext.accounts.report.general_ledger.general_ledger import get_accounts_with_children

		accounts.update(get_accounts_with_children(chosen))

	# Categorised by party, a party's block is its whole position -- every account
	# it has used, not only those that moved in the window. Taking accounts from
	# the postings alone dropped a customer's cylinder deposit from its opening
	# whenever nobody touched the deposit account that month: 135 of 1,123 NGI
	# parties opened wrong against ERPNext's party-wise General Ledger, all of it
	# on 313101 / 313102 / 313201-style deposit accounts. The extra accounts are
	# read for the listed parties only, so no new opening-only parties appear.
	extra, in_scope = set(), set()
	if not chosen and (filters.get("categorized_by") or "Account") == "Party":
		in_scope = {p.party for p in postings if p.party} | set(_normalize(filters.get("party")))
		if in_scope:
			extra = (
				set(
					frappe.db.sql_list(
						"""SELECT DISTINCT account FROM `tabGL Entry`
						   WHERE company = %(company)s AND is_cancelled = 0 AND party IN %(parties)s
						     AND (posting_date < %(from_date)s
						          OR (is_opening = 'Yes' AND posting_date <= %(to_date)s))""",
						{
							"company": filters.company,
							"parties": tuple(sorted(in_scope)),
							"from_date": filters.from_date,
							"to_date": filters.to_date,
						},
					)
				)
				- accounts
			)
			accounts.update(extra)
	accounts = sorted(accounts)
	if not accounts:
		return {}

	pl = set(
		frappe.db.sql_list(
			"""SELECT name FROM `tabAccount`
			   WHERE name IN %(accounts)s AND root_type IN ('Income', 'Expense')""",
			{"accounts": accounts},
		)
	)
	balance_sheet = [a for a in accounts if a not in pl]

	floor = frappe.db.sql(
		"""
		SELECT year_start_date FROM `tabFiscal Year`
		WHERE %(from_date)s BETWEEN year_start_date AND year_end_date
		ORDER BY year_start_date DESC LIMIT 1
		""",
		{"from_date": filters.from_date},
	)
	floor = floor[0][0] if floor else None

	def totals(account_list, since=None):
		if not account_list:
			return []
		params = {
			"company": filters.company,
			"from_date": filters.from_date,
			"accounts": account_list,
		}
		since_clause = ""
		if since:
			params["since"] = since
			since_clause = "AND g.posting_date >= %(since)s"

		# On this data 1,139 opening entries sit on 2025-07-17 alongside 625
		# ordinary ones -- the same day the fiscal year starts. Running from
		# that date, the opening entries belong above the ledger and the 625
		# below it, whatever order they were keyed in. Intra-day sequence does
		# not matter: an opening entry states the position at the start of the
		# period, not a movement within it.
		params["to_date"] = filters.to_date
		opening_dates = """
			(
				g.posting_date < %(from_date)s
				OR (
					g.is_opening = 'Yes'
					AND g.posting_date BETWEEN %(from_date)s AND %(to_date)s
				)
			)
		"""
		if cint(filters.get("show_opening_entries")):
			opening_dates = "g.posting_date < %(from_date)s"

		# The opening must be narrowed by exactly what narrows the postings
		# below it, or the two describe different ledgers. Filtering to one
		# customer's Sales Invoices while opening on the whole account gave a
		# month closing higher than the year that contains it.
		narrowing = []

		voucher_types = _normalize(filters.get("voucher_type"))
		if voucher_types:
			params["voucher_types"] = voucher_types
			narrowing.append("AND g.voucher_type IN %(voucher_types)s")

		party_types = _normalize(filters.get("party_type"))
		if party_types:
			params["party_types"] = party_types
			narrowing.append("AND g.party_type IN %(party_types)s")

		parties = _normalize(filters.get("party"))
		if parties:
			params["parties"] = parties
			narrowing.append("AND g.party IN %(parties)s")

		narrowing.append(_subtype_clause(filters, params))

		return frappe.db.sql(
			"""
			SELECT g.account, IFNULL(g.party_type, '') AS party_type,
			       IFNULL(g.party, '') AS party,
			       SUM(g.debit) - SUM(g.credit) AS balance,
			       SUM(g.debit) AS dr, SUM(g.credit) AS cr
			FROM `tabGL Entry` g
			WHERE g.company = %(company)s
			  AND g.is_cancelled = 0
			  AND g.account IN %(accounts)s
			  AND {opening_dates}
			  {since_clause}
			  {narrowing}
			GROUP BY g.account, g.party_type, g.party
			""".format(
				opening_dates=opening_dates,
				since_clause=since_clause,
				narrowing=" ".join(narrowing),
			),
			params,
			as_dict=True,
		)

	rows = totals(balance_sheet)
	# a P&L account opening on its own year start carries nothing in
	if pl and (not floor or getdate(floor) < getdate(filters.from_date)):
		rows += totals(sorted(pl), since=floor)

	category = filters.get("categorized_by") or "Account"
	opening = {}
	for r in rows:
		if r.account in extra and (r.party or "") not in in_scope:
			continue
		if category == "Party":
			key = (r.party_type or "", r.party or "")
		elif category == "Both":
			key = (r.account, r.party_type or "", r.party or "")
		else:
			key = (r.account,)
		opening[key] = opening.get(key, 0.0) + flt(r.balance)
		if totals_out is not None:
			pair = totals_out.setdefault(key, [0.0, 0.0])
			pair[0] += flt(r.dr)
			pair[1] += flt(r.cr)
	return opening


def _balance_text(balance, always=False):
	"""A balance as a ledger states it: the figure, then the side it falls on.

	Built here rather than in the client formatter. A Currency column renders a
	bare number with nowhere to put the side, so the indicator had to be
	appended in JS -- and that quietly did nothing whenever the framework
	handed the formatter something other than a native number.

	`always` is for the Opening / Period Total / Closing lines, which state a
	figure even when it is zero: a squared account has a balance of 0.00, and
	an empty cell there reads as though the balance were unknown. It carries no
	Dr or Cr, because zero falls on neither side.
	"""
	from avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger import _fmt_npr

	balance = flt(balance)
	if not balance:
		return "0.00" if always else ""
	return "{0} {1}".format(_fmt_npr(abs(balance)), "Dr" if balance > 0 else "Cr")


def _balance_band(label, balance):
	"""An Opening/Closing line, with the balance on the side it belongs to.

	A debit balance is a figure in the Debit column, a credit balance one in
	Credit -- the sign alone is not how a ledger states it. The signed value is
	kept on `balance` so the running column and any export stay arithmetic.
	"""
	balance = flt(balance)
	# Both sides are stated, one of them as 0.00. A balance line with one cell
	# filled and the other blank reads as though the empty side were unknown;
	# an explicit zero says the account owes nothing on that side.
	return {
		"party_name": label,
		"balance": _balance_text(balance, always=True),
		# the signed number stays on the row for the print path and any export
		"balance_value": balance,
		"debit": balance if balance > 0 else 0.0,
		"credit": -balance if balance < 0 else 0.0,
		"_bold": 1,
		"_band": 1,
	}


def _row_description(posting, category):
	"""What a posting's Party Name / Description cell says -- on screen and in print.

	The Bank/Cash/Journal Description stands in for the party only where the
	party is already on the page: a posting with none of its own, or a Party /
	Both block headed by it. In Account mode this column is the only place a
	party is named -- 2,628 of 2,733 journal rows in one NGI month would
	otherwise read "Opening Entry" where a customer was.
	"""
	if posting.description and (not posting.party or category in ("Party", "Both")):
		return posting.description
	return posting.party_name or ""


def _party_section_label(key, postings):
	"""The party heading a nested sub-block carries.

	"Both" names the account once, in the heading above, so the sub-block is
	headed by the party alone. Repeating the account on every one of its forty
	customers is exactly what the nesting removes.
	"""
	# key[2] is the party itself -- empty for the block of party-less postings,
	# whose Party Name column names what they were posted against rather than a
	# party of their own. See _section_label().
	if postings and key[2]:
		return postings[0].party_name or _("No Party")
	return _party_label(key[1], key[2]) or key[2] or _("No Party")


def _period_total(debit, credit, label=None):
	"""The movement line that closes a block.

	Balance on this line is the block's own net movement, not the running
	total -- the legacy print states it the same way, so that
	    opening + period movement = closing
	reads straight down the Balance column.
	"""
	return {
		"party_name": label or _("Period Total"),
		"debit": debit,
		"credit": credit,
		"balance": _balance_text(debit - credit, always=True),
		"balance_value": debit - credit,
		"_bold": 1,
		"_band": 1,
	}


def _build_rows(filters, postings, with_narration=False, columns=None, always_narration=False):
	# The grid always receives narration rows and shows or hides them in the
	# browser -- a checkbox toggle should not cost a five-second re-query. The
	# print-out honours the setting server-side, since it has no browser.
	show_remarks = with_narration and (always_narration or cint(filters.get("remarks", 1)))
	columns = columns or _get_columns(filters)

	category = filters.get("categorized_by") or "Account"

	# A posting with no party is kept, and blocks under "No Party".
	#
	# ERPNext writes the party onto the receivable / payable side only, so the
	# expense, VAT and bank legs of every voucher carry none -- 8,130 such rows on
	# NGI's purchase invoices alone. Dropping them was tried, and it cost the
	# report the one thing a ledger is checked for: on NGI for Bhadra 2083 it took
	# 134 accounts -- every bank, cash, stock and expense account -- off the page
	# and left the movement footing to 3,05,75,41,768.72 against the general
	# ledger's 17,93,48,95,822.53. A general ledger that does not foot to the
	# general ledger is not one.
	#
	# What was actually wrong is fixed in _section_label(): the block took its
	# heading from the first posting in it, and a party-less row still carries a
	# Party Name -- _describe_against() fills that column with whoever the entry was
	# posted against -- so the block holding every supplier's expense legs was
	# titled "ABC Electrical Works". Named from the key instead, it reads
	# "No Party", which is what it holds.

	sections = {}
	for posting in postings:
		sections.setdefault(_section_key(filters, posting), []).append(posting)

	opening = _opening_balances(filters, postings)

	# A balance carried into the period is worth reporting even when nothing
	# moved. Sections are built from postings, so a window with no activity
	# produced an empty report -- splitting a year in two gave a first half
	# closing at 8,50,63,74,498.62 and a second half showing nothing at all,
	# rather than opening and closing on that same figure.
	for key in opening:
		if opening[key]:
			sections.setdefault(key, [])

	data = []
	grand_opening = grand_debit = grand_credit = 0.0

	def emit_block(key, rows, heading, heading_flag):
		"""One ledger block: heading, opening, postings, period total, closing.

		Returns the block's (opening, debit, credit), so a caller nesting these
		can total them into a block of its own.
		"""
		data.append({heading_flag: 1, "party_name": heading})

		# what this account/party carried into the period
		balance = flt(opening.get(key, 0.0))
		data.append(_balance_band(_("Opening Balance"), balance))

		# Kept so the closing balance is derived, not accumulated -- see below.
		block_opening = balance
		block_debit = block_credit = 0.0
		# A date that has not changed is not restated -- Receipt Register does
		# the same. A column of the same date repeated down twenty rows says
		# nothing, and the eye wants the point where it moves.
		last_date = None

		for posting in rows:
			balance += flt(posting.debit) - flt(posting.credit)
			block_debit += flt(posting.debit)
			block_credit += flt(posting.credit)
			same_day = posting.posting_date == last_date
			last_date = posting.posting_date

			data.append(
				{
					"date": "" if same_day else posting.posting_date,
					"miti": "" if same_day else posting.miti,
					"voucher_type": posting.voucher_type,
					"voucher_no": posting.voucher_link,
					"voucher_number": posting.number,
					"party_name": _row_description(posting, category),
					"debit": flt(posting.debit),
					"credit": flt(posting.credit),
					# a posting whose running balance happens to hit zero leaves
					# the cell blank; only the Opening/Period/Closing lines are
					# obliged to state a figure
					"balance": _balance_text(balance),
					"balance_value": balance,
				}
			)

			# "Paid: <who> by chq no <no> dt <miti>", between the posting and its
			# narration, exactly where the legacy print puts it. Not gated on
			# Show Narration: it describes the payment, it is not a remark.
			if posting.paid:
				data.append(
					{"voucher_type": posting.paid, "narration": posting.paid, "_subline": 1}
				)

			# the narration sits on its own line under the posting, as the
			# spec's layout has it -- remarks run long beside a number
			if show_remarks:
				narration = _clean_narration(posting.remarks)
				if narration:
					# The whole narration goes in the first cell; the JS then
					# lets that cell spill across the row (Receipt Register does
					# the same for its remarks sub-line). The datatable has no
					# colspan, so overflow is the only way to a full-width row.
					# The narration starts at Voucher Type, not Party Name.
					# Fit Columns sizes a column to its widest cell, and a
					# narration in Party Name made that the widest cell in the
					# table -- it stretched to 600px and pushed Balance off the
					# right edge. Voucher Type holds short values ("Journal
					# Entry"), so its own width is set by the header and the
					# narration is free to overflow rightwards across Voucher
					# No. and Party Name, which are empty on this row.
					data.append(
						{
							"voucher_type": "Narr: {0}".format(narration[:400]),
							"narration": narration,
							"_narration": 1,
						}
					)

		data.append(_period_total(block_debit, block_credit))
		# Derived from the opening and the period totals, not from the running
		# accumulator. Adding `debit - credit` once per posting compounds float
		# error: on one Gandaki account the accumulator reached
		# 106195401.19999996 where opening + period gives 106195401.2, so the
		# section and grand closing balances disagreed by 4.5e-08 while both
		# displayed as 10,61,95,401.20. A closing balance that does not equal
		# opening plus movement is the first thing an accountant checks.
		data.append(_balance_band(_("Closing Balance"), block_opening + block_debit - block_credit))
		return block_opening, block_debit, block_credit

	ordered = sorted(sections, key=lambda k: tuple(str(part) for part in k))

	if category == "Both":
		# The account is written once and its parties nest under it. Flat, the
		# heading read "411101 - LP Gas Sales  —  ABC Traders" and restated the
		# account for every party it trades with; nested, the account is named
		# once and gains an opening and a closing of its own, which the flat
		# layout had nowhere to put.
		by_account = {}
		for key in ordered:
			by_account.setdefault(key[0], []).append(key)

		for account in sorted(by_account):
			party_keys = by_account[account]
			# The account's own opening is every party's, including any whose
			# balance is zero and so never became a block of its own.
			account_opening = flt(sum(v for k, v in opening.items() if k[0] == account))

			# Every account totals itself, including one holding a single party
			# -- where the account's figures are that party's, restated. The
			# alternative was to drop them there, and it reads worse: an account
			# with a total sits above one without, and nothing on the page says
			# why. A reader who finds the closing balance under one account
			# expects to find it under the next.
			data.append({"_section": 1, "party_name": account})
			data.append(_balance_band(_("Opening Balance"), account_opening))

			account_debit = account_credit = 0.0
			for key in party_keys:
				_block_opening, debit, credit = emit_block(
					key, sections[key], _party_section_label(key, sections[key]), "_subsection"
				)
				account_debit += debit
				account_credit += credit
				# blank line between parties -- flagged so the formatter empties
				# it. An unflagged {} renders every Currency column as
				# "Rs 0.00", which reads as a real zero on a row that means
				# nothing at all.
				data.append({"_spacer": 1})

			data.append(_period_total(account_debit, account_credit))
			data.append(
				_balance_band(_("Closing Balance"), account_opening + account_debit - account_credit)
			)

			grand_opening += account_opening
			grand_debit += account_debit
			grand_credit += account_credit
			data.append({"_spacer": 1})
	else:
		for key in ordered:
			block_opening, debit, credit = emit_block(
				key, sections[key], _section_label(filters, key, sections[key]), "_section"
			)
			grand_opening += block_opening
			grand_debit += debit
			grand_credit += credit
			# blank line between sections -- flagged so the formatter empties it.
			# An unflagged {} renders every Currency column as "Rs 0.00", which
			# reads as a real zero on a row that means nothing at all.
			data.append({"_spacer": 1})

	if data:
		# The opening balance heads the ledger, it does not close it -- appended
		# with the Grand Total block it put the figure the reader needs first at
		# the very bottom, past every section and on the last page of a print.
		# It is summed during the section loop, so it can only be built here.
		#
		# The rest of the grand block is skipped when there is only one section:
		# it restates that section's own Period Total and Closing Balance line
		# for line, so on a single-account run the same figure appeared four
		# times over.
		sections = sum(1 for row in data if row and row.get("_section"))

		data.insert(0, _balance_band(_("Opening Balance"), grand_opening))
		data.insert(1, {"_spacer": 1})

		if sections > 1:
			data.append({"_spacer": 1})
			data.append(_period_total(grand_debit, grand_credit, _("Grand Total")))
			data.append(
				_balance_band(_("Closing Balance"), grand_opening + grand_debit - grand_credit)
			)

	# Every section ends with a spacer, so the grand block adds a second one and
	# a run without it ends on a trailing blank. Collapse both.
	while data and data[-1] and data[-1].get("_spacer"):
		data.pop()
	collapsed = []
	for row in data:
		if row and row.get("_spacer") and collapsed and collapsed[-1] and collapsed[-1].get("_spacer"):
			continue
		collapsed.append(row)
	return collapsed


def _get_columns(filters=None):
	filters = filters or {}
	# Widths are budgeted to ~1230px so Balance -- the column a ledger is read
	# for -- lands on screen without scrolling. At 1330 it fell off the right
	# edge and looked missing entirely. Dates and voucher fields are sized to
	# their actual content (a BS miti is 10 characters, not 110px of one);
	# Party Name/Description keeps the slack because the narration overflows
	# from it, and Balance keeps room for its Dr/Cr suffix.
	return [
		{"fieldname": "date", "label": _("Posting Date"), "fieldtype": "Date", "width": 92},
		{"fieldname": "miti", "label": _("Posting Miti"), "fieldtype": "Data", "width": 88},
		{"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Data", "width": 108},
		{"fieldname": "voucher_no", "label": _("Voucher No."), "fieldtype": "Data", "width": 168},
		{
			"fieldname": "party_name",
			"label": _("Party Name/Description"),
			"fieldtype": "Data",
			"width": 280,
		},
		{"fieldname": "debit", "label": _("Debit"), "fieldtype": "Currency", "width": 118},
		{"fieldname": "credit", "label": _("Credit"), "fieldtype": "Currency", "width": 118},
		# Data, not Currency: the value is built as "1,09,45,494.08 Cr" server
		# side. A Currency column formats a bare number and there is nowhere to
		# put the side, so it was being appended in the client formatter --
		# which silently did nothing whenever the framework handed the
		# formatter something other than a native number.
		{"fieldname": "balance", "label": _("Balance"), "fieldtype": "Data", "width": 160, "align": "right"},
	]


# ── filter options ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_subtypes(voucher_types=None, txt=None, company=None, from_date=None, to_date=None):
	"""Subtypes available for the selected voucher types.

	Each doctype keeps its subtype in its own field pointing at its own doctype,
	so the options are the union of whichever ones are in play. With no voucher
	type selected, everything is offered.

	Narrowed to the subtypes actually used by the chosen company in the chosen
	period, for the same reason as the party picker: a subtype nobody used
	returns an empty report. This reads each voucher table directly rather than
	GL Entry -- those tables are small and carry both company and posting_date,
	so it costs a fraction of the party lookup. Falls back to the full list
	when the company or the dates are not known yet.
	"""
	selected = _normalize(voucher_types) or list(SUBTYPE_SOURCE)
	needle = (txt or "").strip().lower()
	scoped = bool(company and from_date and to_date)

	options = []
	seen = set()

	def add(value, source):
		key = value.lower()
		if key in seen or (needle and needle not in key):
			return
		seen.add(key)
		options.append({"value": value, "description": source})

	for doctype in selected:
		field, linked = SUBTYPE_SOURCE.get(doctype, (None, None))

		if doctype == "Sales Invoice":
			for value in SALES_SUBTYPES:
				add(value, "Sales Invoice")
			continue

		if not linked or not frappe.db.exists("DocType", linked):
			continue

		if scoped and frappe.db.has_column(doctype, field):
			used = frappe.db.sql(
				"""
				SELECT DISTINCT `{0}` FROM `tab{1}`
				WHERE company = %(company)s
				  AND posting_date BETWEEN %(from_date)s AND %(to_date)s
				  AND docstatus < 2
				  AND `{0}` IS NOT NULL AND `{0}` <> ''
				""".format(field, doctype),
				{"company": company, "from_date": from_date, "to_date": to_date},
				pluck=field,
			)
			for value in sorted(used):
				add(value, doctype)
			continue

		for row in frappe.get_all(linked, fields=["name"], order_by="name", limit=200):
			add(row.name, doctype)

	return options


def _parties_in_scope(company, from_date, to_date, party_type):
	"""Parties of one type that actually posted to this company in the period.

	A Customer or Supplier is not owned by a company in ERPNext, so "this
	company's parties" can only mean the ones that transacted with it. That is
	a DISTINCT over GL Entry, and the period is what makes it affordable:
	filtered by company alone it takes ~41s on this site's 938k rows, because
	no index leads with company+party. Adding the report's own date range lets
	it use posting_date_company_index -- measured 124ms, returning 1,114 of the
	1,151 customers the unscoped query finds.

	Returns None when the scope is not known yet (no company or no dates), so
	the caller falls back to offering everything rather than an empty picker.
	"""
	if not (company and from_date and to_date):
		return None
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT party FROM `tabGL Entry`
		WHERE company = %(company)s
		  AND posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND party_type = %(party_type)s
		  AND ifnull(is_cancelled, 0) = 0
		  AND party IS NOT NULL AND party <> ''
		""",
		{"company": company, "from_date": from_date, "to_date": to_date, "party_type": party_type},
		pluck="party",
	)
	return rows


@frappe.whitelist()
def get_parties(party_types=None, txt=None, company=None, from_date=None, to_date=None):
	"""Parties of the selected types, narrowed to the company and period.

	Offering a party that cannot appear in the report is a dead end: you pick
	it, and the report comes back empty. So the list is the parties that
	actually posted to the chosen company inside the chosen dates.
	"""
	selected = [p for p in (_normalize(party_types) or list(PARTY_TYPES)) if p in PARTY_TYPES]
	needle = "%{0}%".format((txt or "").strip())

	options = []
	for party_type in selected:
		field = PARTY_NAME_FIELD[party_type]
		in_scope = _parties_in_scope(company, from_date, to_date, party_type)
		if in_scope is not None and not in_scope:
			continue

		conditions = ["(name LIKE %(txt)s OR `{0}` LIKE %(txt)s)".format(field)]
		params = {"txt": needle}
		if in_scope is not None:
			conditions.append("name IN %(in_scope)s")
			params["in_scope"] = tuple(in_scope)

		# Once the scope is known the IN-list already bounds the result, so the
		# picker offers every party that can appear rather than a truncated
		# slice of them. The cap only applies before a company and period are
		# chosen, where the alternative is dumping every customer on the site.
		rows = frappe.db.sql(
			"""
			SELECT name AS value, `{0}` AS label FROM `tab{1}`
			WHERE {2}
			ORDER BY `{0}` {3}
			""".format(
				field,
				party_type,
				" AND ".join(conditions),
				"" if in_scope is not None else "LIMIT 500",
			),
			params,
			as_dict=True,
		)
		options.extend(
			{"value": r.value, "description": "{0} · {1}".format(r.label or r.value, party_type)}
			for r in rows
		)
	return options


# ── print / PDF ─────────────────────────────────────────────────────────────────

# ---------------------------------------------------------------------------
# The printed ledger -- the legacy "Normal Sub Ledger - Detail - Posting Detail"
# ---------------------------------------------------------------------------
#
# Drawn the way DevExpress drew it: every line of text placed at a measured point
# on the page. The coordinates below were read off the legacy PDF itself
# ("Ledger of supplier.pdf", DXperience v13.2.6, via pdftotext -bbox and its
# vector rules). The font is Carlito -- metric-identical to the Calibri that
# report embeds, bundled under public/fonts/carlito (SIL OFL) -- and text is
# wrapped here by the font's own advance widths, never by the browser. So the
# page breaks are known before anything is rendered, every page can say
# "Page 3/7", and Chrome and wkhtmltopdf put every word at the same point.

PRINT_PAGE_W = 595.28  # A4, points
PRINT_PAGE_H = 841.89
PRINT_BODY_TOP = 147.9  # first line under the column box
PRINT_BODY_BOTTOM = 792.0  # the last line may start here; the footer is at 813.4
PRINT_PITCH = 13.65  # one field's first line to the next field's
PRINT_WRAP_PITCH = 11.0  # a wrapped line inside the same field
PRINT_RULE_GAP = 2.05  # extra drop for a line with a rule above it
PRINT_TEXT_W = 207.5  # Description field, x 188.4 -> 395.9: where narration wraps
PRINT_VOUCHER_W = 84.0  # Voucher Number field, x 101.3 -> 185.3
PRINT_NARRATION_MAX = 8  # a longer narration is cut, so no posting outgrows a page
PRINT_GREY_RULE = "#d3d3d3"  # the legacy's 82.7% grey, above Period Total and Balance
PRINT_GREY_TEXT = "#808080"  # parameter values

# x positions in points: left edges, or right edges for amounts
PRINT_X = frappe._dict(
	code=23.0,  # General Ledger / Sub Ledger code, band labels
	desc=110.3,  # General Ledger / Sub Ledger description
	date=50.2,
	voucher=101.3,
	text=188.4,  # description, Paid To line, narration
	net=197.7,  # right edge of a band's figure
	side=201.4,  # DEBIT / CREDIT
	debit=486.7,
	credit=578.3,
	params=(23.0, 196.4, 361.6),
)

_CARLITO = {}


def _carlito():
	"""Carlito's advance widths and the fonts themselves, loaded once."""
	if not _CARLITO:
		import base64

		folder = frappe.get_app_path("avinashgroup_app", "public", "fonts", "carlito")
		with open(os.path.join(folder, "metrics.json")) as handle:
			_CARLITO.update(json.load(handle))
		for weight in ("Regular", "Bold"):
			with open(os.path.join(folder, "Carlito-{0}.ttf".format(weight)), "rb") as handle:
				_CARLITO["font_" + weight.lower()] = base64.b64encode(handle.read()).decode()
	return _CARLITO


def _text_pt(text, size=9.0, bold=False):
	"""Printed width of `text`, in points."""
	metrics = _carlito()
	widths = metrics["bold" if bold else "regular"]
	fallback = metrics["avg_bold" if bold else "avg_regular"]
	return sum(widths.get(str(ord(ch)), fallback) for ch in str(text)) * size / metrics["upm"]


def _wrap_pt(text, width=PRINT_TEXT_W, size=9.0, bold=False):
	"""Greedy word wrap to a printed width; a word wider than the line is cut."""
	lines, current = [], ""
	for word in str(text or "").split():
		trial = "{0} {1}".format(current, word) if current else word
		if _text_pt(trial, size, bold) <= width:
			current = trial
			continue
		if current:
			lines.append(current)
		while _text_pt(word, size, bold) > width:
			cut = len(word)
			while cut > 1 and _text_pt(word[:cut], size, bold) > width:
				cut -= 1
			lines.append(word[:cut])
			word = word[cut:]
		current = word
	if current:
		lines.append(current)
	return lines or [""]


def _pt(x, text, size=9.0, bold=False, align="l", grey=False, italic=False, colour=None):
	"""One run of text at x; its y is set when its line is placed."""
	return {
		"kind": "text",
		"x": x,
		"size": size,
		"bold": bold,
		"align": align,
		"grey": grey,
		"italic": italic,
		"colour": colour,
		"text": text,
	}


def _set_y(item, y):
	"""Fix a text run's top from the y its glyph box should start at.

	pdftotext reports the top of the glyph box, one em tall with the baseline at
	0.75 em. In CSS with line-height 1, Carlito's baseline sits at 0.8418 em below
	the box top (hhea ascent 1950 and descent 550 of 2048 units), so the box goes
	0.0918 em above that point.
	"""
	placed = dict(item)
	placed["top"] = round(y - 0.0918 * item["size"], 2)
	placed["text"] = frappe.utils.escape_html(item["text"])
	return placed


def _print_frame(head, page_no, total_pages):
	"""What every page carries: masthead, rules, the boxed column heads, the foot."""
	X = PRINT_X
	right = PRINT_PAGE_W - 16.0  # the masthead's right edge, x 579.3
	items = [
		{"kind": "rule", "y": 14.4, "w": 1.5, "colour": "#000"},
		_set_y(_pt(X.code, "{0}{1}".format(head.company, " FY [{0}]".format(head.fy) if head.fy else ""), bold=True), 17.3),
		_set_y(_pt(right, "Normal Sub Ledger - Detail - Posting Detail", size=14.0, bold=True, align="r"), 18.2),
		_set_y(_pt(right, "Accounting Period : {0}".format(head.period) if head.period else "", bold=True, align="r"), 36.6),
		_set_y(_pt(right, "Page {0}/{1}".format(page_no, total_pages), bold=True, align="r"), 75.4),
		_set_y(_pt(X.code, "From {0} To {1}".format(head.from_bs, head.to_bs)), 88.2),
		_set_y(_pt(151.2, "(All parameters listed at end of report)"), 88.2),
		_set_y(_pt(right, "Amount in Nepalese Rupee ( NPR )", align="r"), 88.2),
		{"kind": "rule", "y": 99.9, "w": 0.75, "colour": "#000"},
		{"kind": "box", "top": 102.8, "height": 43.3, "w": 0.8},
		_set_y(_pt(X.code, "General Ledger Code", bold=True), 107.1),
		_set_y(_pt(X.desc, "General Ledger Description", bold=True), 107.1),
		_set_y(_pt(X.code, "Sub Ledger Code", bold=True), 120.7),
		_set_y(_pt(X.desc, "Sub Ledger Description", bold=True), 120.7),
		_set_y(_pt(X.date, "Date", bold=True), 134.5),
		_set_y(_pt(X.voucher, "Voucher Number", bold=True), 134.5),
		_set_y(_pt(X.text, "Bank/Cash/Journal Description", bold=True), 134.5),
		_set_y(_pt(324.7, "Document Amount", bold=True), 134.5),
		_set_y(_pt(X.debit, "Debit", bold=True, align="r"), 134.5),
		_set_y(_pt(578.0, "Credit", bold=True, align="r"), 134.5),
	]
	label = "Design Name : "
	items.append(_set_y(_pt(X.code, label, size=6.0, bold=True), 813.4))
	items.append(
		_set_y(
			_pt(X.code + _text_pt(label, 6.0, True), "Posting Detail [DEFAULT] in Version 7.0.5", size=6.0), 813.4
		)
	)
	return items


def _place(items, cursor, field):
	"""Draw one field at `cursor` into `items`; return the cursor after it."""
	first = cursor
	if field.get("rule"):
		items.append({"kind": "rule", "y": cursor - 1.25, "w": 0.75, "colour": field["rule"]})
		first = cursor + PRINT_RULE_GAP
	for index, line in enumerate(field["lines"]):
		y = first + index * PRINT_WRAP_PITCH
		items.extend(_set_y(run, y) for run in line)
	last = first + (len(field["lines"]) - 1) * PRINT_WRAP_PITCH
	if field.get("rule_after"):
		rule_y = last + 12.6
		items.append({"kind": "rule", "y": rule_y, "w": 0.75, "colour": "#000"})
		return rule_y + 4.6
	return last + PRINT_PITCH


def _measure(cursor, fields):
	"""Where the cursor would end after `fields`, without drawing anything."""
	for field in fields:
		cursor = _place([], cursor, field)
	return cursor


def _print_pages(filters, postings):
	"""The ledger as the legacy print lays it out, cut into pages of placed items.

	A heading travels with its Opening Balance, a posting with its sub-lines, a
	block's totals with each other; a page that opens in the middle of a block
	repeats that block's heading lines first, so no page of postings is left
	without saying whose they are.
	"""
	from avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger import _fmt_npr

	X = PRINT_X
	category = filters.get("categorized_by") or "Account"
	show_remarks = cint(filters.get("remarks", 1))
	totals = {}
	opening = _opening_balances(filters, postings, totals_out=totals)

	sections = {}
	for posting in postings:
		sections.setdefault(_section_key(filters, posting), []).append(posting)
	for key, value in opening.items():
		if value:
			sections.setdefault(key, [])
	if not sections:
		return []

	meta = {}
	if category in ("Account", "Both"):
		for row in frappe.get_all(
			"Account",
			filters={"name": ("in", sorted({key[0] for key in sections}))},
			fields=["name", "account_number", "account_name"],
		):
			meta[row.name] = row

	def heading(code, desc):
		return {"lines": [[_pt(X.code, code, bold=True), _pt(X.desc, desc, bold=True)]]}

	def gl(account):
		m = meta.get(account) or frappe._dict()
		return heading(m.account_number or "", m.account_name or account)

	def sub(party_type, party, rows):
		if not party:
			return heading("", _("No Party"))
		name = next((r.party_name for r in rows if r.party == party and r.party_name), "")
		return heading(party, name or _party_label(party_type, party) or party)

	def band(label, net, dr, cr, rule=None, rule_after=False):
		net = flt(net, 2)
		runs = [_pt(X.code, label, bold=True), _pt(X.net, _fmt_npr(abs(net)) or "0.00", bold=True, align="r")]
		if net:
			runs.append(_pt(X.side, "DEBIT" if net > 0 else "CREDIT", bold=True))
		if flt(dr, 2):
			runs.append(_pt(X.debit, _fmt_npr(dr), align="r"))
		if flt(cr, 2):
			runs.append(_pt(X.credit, _fmt_npr(cr), align="r"))
		return {"lines": [runs], "rule": rule, "rule_after": rule_after}

	def text_field(lines):
		return {"lines": [[_pt(X.text, line)] for line in lines]}

	def posting_fields(posting):
		desc = _wrap_pt(_row_description(posting, category))
		voucher = posting.number or posting.voucher_no or ""
		# Our voucher numbers run longer than the legacy's "JV/00001/82-83"; one
		# that would reach into the description is set a touch smaller instead.
		size = min(9.0, round(9.0 * PRINT_VOUCHER_W / max(_text_pt(voucher), 1), 2))
		first = [
			_pt(X.date, (posting.miti or "").replace("-", "/")),
			_pt(X.voucher, voucher, size=size),
			_pt(X.text, desc[0]),
		]
		if flt(posting.debit):
			first.append(_pt(X.debit, _fmt_npr(posting.debit), align="r"))
		if flt(posting.credit):
			first.append(_pt(X.credit, _fmt_npr(posting.credit), align="r"))
		fields = [{"lines": [first] + [[_pt(X.text, line)] for line in desc[1:]]}]
		if posting.paid:
			fields.append(text_field(_wrap_pt(posting.paid)))
		if show_remarks:
			narration = _clean_narration(posting.remarks)
			if narration:
				lines = _wrap_pt("Narration : {0}".format(narration))
				if len(lines) > PRINT_NARRATION_MAX:
					lines = lines[:PRINT_NARRATION_MAX]
					lines[-1] = lines[-1].rstrip(". ") + " …"
				fields.append(text_field(lines))
		return fields

	units = []

	def block(key, rows, head_fields, context):
		opening_net = flt(opening.get(key, 0.0))
		dr0, cr0 = totals.get(key, (0.0, 0.0))
		units.append(
			{"fields": head_fields + [band(_("Opening Balance"), opening_net, dr0, cr0)], "ctx": context, "head": True}
		)
		moved_dr = moved_cr = 0.0
		for posting in rows:
			units.append({"fields": posting_fields(posting), "ctx": context, "head": False})
			moved_dr += flt(posting.debit)
			moved_cr += flt(posting.credit)
		units.append(
			{
				"fields": [
					band(_("Period Total"), moved_dr - moved_cr, moved_dr, moved_cr, rule=PRINT_GREY_RULE),
					band(_("Closing Balance"), opening_net + moved_dr - moved_cr, dr0 + moved_dr, cr0 + moved_cr),
				],
				"ctx": context,
				"head": False,
			}
		)
		return [opening_net, dr0, cr0, moved_dr, moved_cr]

	ordered = sorted(sections, key=lambda k: tuple(str(part) for part in k))
	if category == "Both":
		# General Ledger once, each Sub Ledger under it, and a Balance line for the
		# ledger as a whole -- the legacy layout.
		by_account = {}
		for key in ordered:
			by_account.setdefault(key[0], []).append(key)
		for account in sorted(by_account):
			ledger = [0.0] * 5
			for index, key in enumerate(by_account[account]):
				rows = sections[key]
				party_line = sub(key[1], key[2], rows)
				head_fields = ([gl(account)] if index == 0 else []) + [party_line]
				figures = block(key, rows, head_fields, [gl(account), party_line])
				ledger = [a + b for a, b in zip(ledger, figures)]
			net, dr0, cr0, moved_dr, moved_cr = ledger
			units.append(
				{
					"fields": [
						band(
							_("Balance"),
							net + moved_dr - moved_cr,
							dr0 + moved_dr,
							cr0 + moved_cr,
							rule=PRINT_GREY_RULE,
							rule_after=True,
						)
					],
					"ctx": [gl(account)],
					"head": False,
				}
			)
	elif category == "Party":
		for key in ordered:
			party_line = sub(key[0], key[1], sections[key])
			block(key, sections[key], [party_line], [party_line])
	else:
		for key in ordered:
			ledger_line = gl(key[0])
			block(key, sections[key], [ledger_line], [ledger_line])

	pages = [[]]
	cursor = PRINT_BODY_TOP
	after_rule = False
	for unit in units:
		end = _measure(cursor, unit["fields"])
		if end - PRINT_PITCH > PRINT_BODY_BOTTOM and cursor > PRINT_BODY_TOP:
			pages.append([])
			cursor = PRINT_BODY_TOP
			if not unit["head"] and unit["ctx"]:
				for field in unit["ctx"]:
					cursor = _place(pages[-1], cursor, field)
		for field in unit["fields"]:
			cursor = _place(pages[-1], cursor, field)
			after_rule = bool(field.get("rule_after"))

	# Report Parameters: under the Balance line's rule, or under a rule of its own
	params = _print_parameters(filters)
	height = (0 if after_rule else 4.6) + 13.0 + 12.2 * (len(params) - 1) + 11.9
	if cursor + height > PRINT_BODY_BOTTOM + PRINT_PITCH:
		pages.append([])
		cursor = PRINT_BODY_TOP
		after_rule = True
	if not after_rule:
		pages[-1].append({"kind": "rule", "y": cursor - 1.25, "w": 0.75, "colour": "#000"})
		cursor += 3.35
	pages[-1].append(_set_y(_pt(X.code, "Report Parameters", size=8.5, bold=True), cursor))
	for row, line in enumerate(params):
		y = cursor + 13.0 + 12.2 * row
		for column, cell in enumerate(line):
			if not cell:
				continue
			label = "{0} : ".format(cell[0])
			x = X.params[column]
			pages[-1].append(_set_y(_pt(x, label, size=8.5), y))
			pages[-1].append(_set_y(_pt(x + _text_pt(label, 8.5), cell[1], size=8.5, grey=True), y))
	pages[-1].append(
		{"kind": "rule", "y": cursor + 13.0 + 12.2 * (len(params) - 1) + 11.9, "w": 0.75, "colour": "#000"}
	)
	return pages


def _print_masthead(filters):
	"""Company, fiscal year and dates for the page head, in BS with slashes."""
	from avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger import _bs

	def bs(date):
		return (_bs(date) or "").replace("-", "/")

	fy = frappe.db.sql(
		"""SELECT name, year_start_date, year_end_date FROM `tabFiscal Year`
		   WHERE %(d)s BETWEEN year_start_date AND year_end_date
		   ORDER BY year_start_date DESC LIMIT 1""",
		{"d": filters.from_date},
		as_dict=True,
	)
	fy = fy[0] if fy else frappe._dict()
	name = str(fy.get("name") or filters.get("fiscal_year") or "")
	# "83/84" prints as the legacy "2083.084"
	parts = name.split("/")
	if len(parts) == 2 and all(part.isdigit() and len(part) == 2 for part in parts):
		name = "20{0}.0{1}".format(*parts)
	return frappe._dict(
		company=filters.company,
		fy=name,
		period="{0} - {1}".format(bs(fy.year_start_date), bs(fy.year_end_date)) if fy else "",
		from_bs=bs(filters.from_date),
		to_bs=bs(filters.to_date),
	)


def _print_parameters(filters):
	"""The legacy "Report Parameters" block, three to a line.

	Four settings the old report had -- Month Total, Month Total Exclusive, Include
	Cash / Bank Code, Closing Narration -- have no counterpart here and print as its
	default, No, which is also true of this report: it does none of them.
	"""
	from avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger import _bs

	def listed(values, limit=3):
		if not values:
			return "All"
		return ", ".join(values[:limit]) + ("…" if len(values) > limit else "")

	accounts = _normalize(filters.get("account"))
	numbers = (
		[n for n in frappe.get_all("Account", filters={"name": ("in", accounts)}, pluck="account_number") if n]
		if accounts
		else []
	)
	narrowing = []
	for label, key in (("Voucher Type", "voucher_type"), ("Subtype", "voucher_subtype"), ("Party Type", "party_type")):
		chosen = _normalize(filters.get(key))
		if chosen:
			narrowing.append("{0}: {1}".format(label, listed(chosen, 2)))
	if filters.get("voucher_no"):
		narrowing.append("Voucher No: {0}".format(filters.voucher_no))

	date_range = "From {0} To {1}".format(
		(_bs(filters.from_date) or "").replace("-", "/"), (_bs(filters.to_date) or "").replace("-", "/")
	)
	return [
		[("Date Range", date_range), ("General Ledgers", listed(numbers or accounts)), ("Month Total", "No")],
		[
			("Month Total Exclusive", "No"),
			("Include Cash / Bank Code", "No"),
			("Remarks", "Yes" if cint(filters.get("remarks", 1)) else "No"),
		],
		[
			("Closing Narration", "No"),
			("Show Grand Total", "No"),
			("Class Segment Wise", listed(_normalize(filters.get("party")))),
		],
		[("Filter", "; ".join(narrowing) or "All"), None, None],
	]


# ---------------------------------------------------------------------------
# The standard print -- the same ledger, laid out for reading
# ---------------------------------------------------------------------------
#
# The legacy print above reproduces the old DevExpress page point for point. This
# one keeps everything that page carries -- account and party blocks, opening and
# closing with their gross Dr / Cr, the Paid To line, narration -- and takes what
# the Cash Book print does well: a running balance on every posting and a Day
# closing line. On top of that:
#
#   - opening and closing say which date they stand "as at"
#   - a ledger that crosses a page break is "Carried forward" at the foot of one
#     page and "Brought forward" at the head of the next
#   - dates read BS first with the AD date beneath, as the screen shows both
#   - the voucher type sits under the voucher number
#   - a block with no postings says so, instead of a Period Total of 0.00
#   - the filters open the first page, a summary closes the last, and every page
#     says "Page n of N" and who printed it
#
# Same machinery as the legacy print: Carlito, text wrapped by the font's own
# widths, every line placed at a computed point, pages decided before rendering.

STD = frappe._dict(
	left=28.0,
	right=PRINT_PAGE_W - 28.0,
	date=31.0,
	voucher=84.0,
	voucher_w=90.0,
	text=178.0,
	text_w=170.0,
	debit=418.0,
	credit=484.0,
	amount_w=62.0,
	balance=PRINT_PAGE_W - 31.0,
	balance_w=78.0,
	body_bottom=798.0,
	first_body_top=130.0,
	body_top=86.0,
	ink="#111827",
	muted="#6b7280",
	faint="#9ca3af",
	hair="#e5e7eb",
	band="#eef1f5",
	subband="#f7f8fa",
	accent="#1f2937",
)
STD_LINE = 11.0  # the first line of a posting
STD_SUBLINE = 9.4  # each further line of it
STD_GAP = 3.0  # air under a posting, above its hairline
STD_CF = 12.0  # a Carried / Brought forward line


def _fit(text, width, size, bold=False, floor=6.0):
	"""The largest size, up to `size`, at which `text` fits `width`."""
	w = _text_pt(text, size, bold)
	return size if w <= width else max(floor, round(size * width / w, 2))


def _std_place(items, y, line):
	"""Draw one line of the standard print at y; return the y under it."""
	S = STD
	h = line["h"]
	if line.get("fill"):
		items.append({"kind": "fill", "x": S.left, "w": S.right - S.left, "top": y, "h": h, "colour": line["fill"]})
	if line.get("rule_top"):
		colour, weight = line["rule_top"]
		items.append({"kind": "rule", "x": S.left, "width": S.right - S.left, "y": y, "w": weight, "colour": colour})
	for run in line["runs"]:
		items.append(_set_y(run, y + (h - run["size"]) / 2.0))
	if line.get("rule_bottom"):
		colour, weight = line["rule_bottom"]
		items.append({"kind": "rule", "x": S.left, "width": S.right - S.left, "y": y + h, "w": weight, "colour": colour})
	return y + h


def _std_context(filters):
	"""Everything the page frame says, worked out once for the whole document."""
	from avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger import _bs

	def bs(date):
		return (_bs(date) or "").replace("-", "/")

	fy = frappe.db.sql(
		"""SELECT name FROM `tabFiscal Year`
		   WHERE %(d)s BETWEEN year_start_date AND year_end_date
		   ORDER BY year_start_date DESC LIMIT 1""",
		{"d": filters.from_date},
	)
	fy = str((fy[0][0] if fy else "") or filters.get("fiscal_year") or "")
	parts = fy.split("/")
	if len(parts) == 2 and all(part.isdigit() and len(part) == 2 for part in parts):
		fy = "20{0}/{1}".format(*parts)

	def listed(values, limit=3):
		if not values:
			return _("All")
		return ", ".join(values[:limit]) + ("…" if len(values) > limit else "")

	accounts = _normalize(filters.get("account"))
	numbers = (
		[n for n in frappe.get_all("Account", filters={"name": ("in", accounts)}, pluck="account_number") if n]
		if accounts
		else []
	)
	category = filters.get("categorized_by") or "Account"
	pairs = [
		(_("Categorised by"), {"Account": _("Account"), "Party": _("Party"), "Both": _("Account & Party")}[category]),
		(_("Accounts"), listed(numbers or accounts)),
		(_("Voucher type"), listed(_normalize(filters.get("voucher_type")))),
		(_("Party type"), listed(_normalize(filters.get("party_type")))),
		(_("Parties"), listed(_normalize(filters.get("party")))),
		(_("Voucher subtype"), listed(_normalize(filters.get("voucher_subtype")))),
		(_("Voucher No."), filters.get("voucher_no") or _("All")),
		(
			_("Opening entries"),
			_("Shown as postings") if cint(filters.get("show_opening_entries")) else _("In the opening balance"),
		),
		(_("Narration"), _("Shown") if cint(filters.get("remarks", 1)) else _("Hidden")),
	]
	now = frappe.utils.now_datetime()
	return frappe._dict(
		company=filters.company,
		left="{0}   ·   {1}".format(
			_("Fiscal Year {0}").format(fy) if fy else "", _("Amounts in Nepalese Rupee (NPR)")
		).strip(" ·"),
		period="{0} – {1} BS   ·   {2} – {3} AD".format(
			bs(filters.from_date), bs(filters.to_date), getdate(filters.from_date), getdate(filters.to_date)
		),
		printed=_("Printed {0} {1} by {2}").format(
			bs(now.date()), now.strftime("%H:%M"), frappe.utils.get_fullname(frappe.session.user)
		),
		filters=[pairs[i : i + 3] for i in range(0, len(pairs), 3)],
		as_at_open=bs(filters.from_date),
		as_at_close=bs(filters.to_date),
	)


def _std_frame(ctx, page_no, total_pages):
	"""Masthead, the first page's filters, the column heads and the foot."""
	S = STD
	items = [
		_set_y(_pt(S.left, ctx.company, size=12.5, bold=True, colour=S.ink), 28.0),
		_set_y(_pt(S.right, _("General Ledger Posting Detail"), size=15.0, bold=True, align="r", colour=S.ink), 26.5),
		_set_y(_pt(S.left, ctx.left, size=7.5, colour=S.muted), 47.0),
		_set_y(_pt(S.right, ctx.period, size=7.5, align="r", colour=S.muted), 47.0),
		{"kind": "rule", "x": S.left, "width": S.right - S.left, "y": 59.0, "w": 1.0, "colour": S.accent},
	]
	head_y = 66.0
	if page_no == 1:
		column_w = (S.right - S.left) / 3.0
		for row, pairs in enumerate(ctx.filters):
			y = 66.0 + 10.0 * row
			for column, (label, value) in enumerate(pairs):
				x = S.left + column * column_w
				items.append(_set_y(_pt(x, label, size=7.0, colour=S.muted), y))
				value_x = x + 62.0
				items.append(_set_y(_pt(value_x, value, size=_fit(value, column_w - 66.0, 7.0), colour=S.ink), y))
		items.append(
			_set_y(
				_pt(
					S.left,
					_("Figures in grey on opening and closing lines are the gross debits and credits behind the balance."),
					size=6.8,
					italic=True,
					colour=S.faint,
				),
				96.0,
			)
		)
		head_y = 110.0
	items.append({"kind": "fill", "x": S.left, "w": S.right - S.left, "top": head_y, "h": 16.0, "colour": S.band})
	for x, label, align in (
		(S.date, _("Date"), "l"),
		(S.voucher, _("Voucher"), "l"),
		(S.text, _("Particulars"), "l"),
		(S.debit, _("Debit"), "r"),
		(S.credit, _("Credit"), "r"),
		(S.balance, _("Balance"), "r"),
	):
		items.append(_set_y(_pt(x, label, size=7.5, bold=True, align=align, colour=S.ink), head_y + 4.25))
	items.append(
		{"kind": "rule", "x": S.left, "width": S.right - S.left, "y": head_y + 16.0, "w": 0.6, "colour": S.faint}
	)
	items.append({"kind": "rule", "x": S.left, "width": S.right - S.left, "y": 810.0, "w": 0.4, "colour": S.hair})
	items.append(_set_y(_pt(S.left, ctx.printed, size=6.5, colour=S.muted), 815.0))
	items.append(
		_set_y(_pt(S.right, _("Page {0} of {1}").format(page_no, total_pages), size=6.5, bold=True, align="r", colour=S.muted), 815.0)
	)
	return items


def _std_pages(filters, postings, ctx):
	"""The standard print, cut into pages of placed items."""
	from collections import Counter

	from avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger import _fmt_npr

	S = STD
	category = filters.get("categorized_by") or "Account"
	show_remarks = cint(filters.get("remarks", 1))
	totals = {}
	opening = _opening_balances(filters, postings, totals_out=totals)

	sections = {}
	for posting in postings:
		sections.setdefault(_section_key(filters, posting), []).append(posting)
	for key, value in opening.items():
		if value:
			sections.setdefault(key, [])
	if not sections:
		return []

	meta = {}
	if category in ("Account", "Both"):
		for row in frappe.get_all(
			"Account",
			filters={"name": ("in", sorted({key[0] for key in sections}))},
			fields=["name", "account_number", "account_name"],
		):
			meta[row.name] = row

	def runs(*items):
		return [item for item in items if item]

	def amt(value, x, bold=False, colour=None):
		text = _fmt_npr(value)
		if not text:
			return None
		return _pt(x, text, size=_fit(text, S.amount_w, 8.0, bold), bold=bold, align="r", colour=colour or S.ink)

	def bal(value, bold=False, colour=None, size=8.0):
		value = flt(value, 2)
		text = "0.00" if not value else "{0} {1}".format(_fmt_npr(abs(value)), "Dr" if value > 0 else "Cr")
		return _pt(S.balance, text, size=_fit(text, S.balance_w, size, bold), bold=bold, align="r", colour=colour or S.ink)

	def labelled(label, note, size=8.0, bold=True, colour=None):
		"""A label with a quieter note after it, as two runs."""
		out = [_pt(S.text, label, size=size, bold=bold, colour=colour or S.ink)]
		if note:
			out.append(_pt(S.text + _text_pt(label + "   ", size, bold), note, size=7.0, colour=S.muted))
		return out

	def account_band(account, cont=False):
		m = meta.get(account) or frappe._dict()
		label = "{0}   {1}".format(m.account_number or "", m.account_name or account).strip()
		return {
			"h": 16.0,
			"fill": S.band,
			"runs": [
				_pt(S.left + 6.0, label, size=9.0, bold=True, colour=S.ink),
				_pt(S.right - 6.0, _("continued") if cont else _("Account"), size=7.0, italic=cont, align="r", colour=S.muted),
			],
		}

	def party_band(party_type, party, rows, cont=False, nested=True):
		if party:
			name = next((r.party_name for r in rows if r.party == party and r.party_name), "")
			label = "{0}   {1}".format(party, name or _party_label(party_type, party) or "")
		else:
			label = _("No Party")
		return {
			"h": 14.0 if nested else 16.0,
			"fill": S.subband if nested else S.band,
			"runs": [
				_pt(S.left + (14.0 if nested else 6.0), label, size=8.5 if nested else 9.0, bold=True, colour=S.ink),
				_pt(S.right - 6.0, _("continued") if cont else (party_type or ""), size=7.0, italic=cont, align="r", colour=S.muted),
			],
		}

	def opening_line(value, dr0, cr0):
		return {
			"h": 14.0,
			"runs": labelled(_("Opening balance"), _("as at {0}").format(ctx.as_at_open))
			+ runs(amt(dr0, S.debit, colour=S.faint), amt(cr0, S.credit, colour=S.faint), bal(value, bold=True)),
			"rule_bottom": (S.hair, 0.4),
		}

	def posting_lines(posting, balance):
		stream = [(line, 8.0, False, S.ink) for line in _wrap_pt(_row_description(posting, category), S.text_w, 8.0)]
		if posting.paid:
			stream += [(line, 7.2, False, S.muted) for line in _wrap_pt(posting.paid, S.text_w, 7.2)]
		if show_remarks:
			narration = _clean_narration(posting.remarks)
			if narration:
				lines = _wrap_pt(narration, S.text_w, 7.2)
				if len(lines) > PRINT_NARRATION_MAX:
					lines = lines[:PRINT_NARRATION_MAX]
					lines[-1] = lines[-1].rstrip(". ") + " …"
				stream += [(line, 7.2, True, S.muted) for line in lines]
		voucher = posting.number or posting.voucher_no or ""
		out = []
		for index in range(max(len(stream), 2)):
			line_runs = []
			if index == 0:
				line_runs += runs(
					_pt(S.date, (posting.miti or "").replace("-", "/"), size=8.0, colour=S.ink),
					_pt(S.voucher, voucher, size=_fit(voucher, S.voucher_w, 8.0), colour=S.ink),
					amt(posting.debit, S.debit),
					amt(posting.credit, S.credit),
					bal(balance),
				)
			elif index == 1:
				line_runs += runs(
					_pt(S.date, str(getdate(posting.posting_date)) if posting.posting_date else "", size=6.8, colour=S.faint),
					_pt(S.voucher, posting.voucher_type or "", size=_fit(posting.voucher_type or "", S.voucher_w, 6.8), colour=S.faint),
				)
			if index < len(stream):
				text, size, italic, colour = stream[index]
				line_runs.append(_pt(S.text, text, size=size, italic=italic, colour=colour))
			out.append({"h": STD_LINE if index == 0 else STD_SUBLINE, "runs": line_runs})
		out[-1]["h"] += STD_GAP
		out[-1]["rule_bottom"] = (S.hair, 0.4)
		return out

	def day_closing(miti, balance):
		return {
			"h": 12.0,
			"runs": labelled(_("Day closing"), (miti or "").replace("-", "/"), size=7.4, colour=S.muted)
			+ [bal(balance, bold=True, colour=S.muted, size=7.4)],
			"rule_bottom": (S.hair, 0.4),
		}

	def period_total(dr, cr):
		return {
			"h": 13.0,
			"runs": labelled(_("Total for the period"), _("net change"))
			+ runs(amt(dr, S.debit, bold=True), amt(cr, S.credit, bold=True), bal(dr - cr, colour=S.muted)),
			"rule_top": (S.faint, 0.6),
		}

	def closing_line(value, drc, crc):
		return {
			"h": 14.0,
			"runs": labelled(_("Closing balance"), _("as at {0}").format(ctx.as_at_close))
			+ runs(amt(drc, S.debit, colour=S.faint), amt(crc, S.credit, colour=S.faint), bal(value, bold=True)),
			"rule_bottom": (S.accent, 0.9),
		}

	def forward(label, balance):
		return {"h": STD_CF, "runs": [_pt(S.text, label, size=7.2, italic=True, colour=S.muted), bal(balance, colour=S.muted, size=7.6)]}

	units = []
	grand = [0.0, 0.0, 0.0]
	vouchers = set()

	def unchanged_line(value, dr0, cr0):
		"""A ledger that did not move, as one line: its balance, opening and closing alike."""
		return {
			"h": 14.0,
			"runs": labelled(_("Balance"), _("no transactions from {0} to {1}").format(ctx.as_at_open, ctx.as_at_close))
			+ runs(amt(dr0, S.debit, colour=S.faint), amt(cr0, S.credit, colour=S.faint), bal(value, bold=True)),
			"rule_bottom": (S.accent, 0.9),
		}

	def block(key, rows, bands, context):
		opening_net = flt(opening.get(key, 0.0))
		dr0, cr0 = totals.get(key, (0.0, 0.0))
		grand[0] += opening_net
		if not rows:
			# An opening, a "no transactions" line and a closing that repeats the
			# opening say one thing three times. One line says it once, and it
			# cannot be split across a page.
			units.append({"lines": bands + [unchanged_line(opening_net, dr0, cr0)], "head": True})
			return opening_net, 0.0, 0.0
		head = bands + [opening_line(opening_net, dr0, cr0)]
		balance = opening_net
		moved_dr = moved_cr = 0.0
		per_day = Counter(posting.posting_date for posting in rows)
		for index, posting in enumerate(rows):
			brought = balance
			balance += flt(posting.debit) - flt(posting.credit)
			moved_dr += flt(posting.debit)
			moved_cr += flt(posting.credit)
			vouchers.add((posting.voucher_type, posting.voucher_no))
			lines = posting_lines(posting, balance)
			following = rows[index + 1].posting_date if index + 1 < len(rows) else None
			if per_day[posting.posting_date] > 1 and following != posting.posting_date:
				lines.append(day_closing(posting.miti, balance))
			if index == 0:
				# the heading and opening travel with the first posting, so a page
				# never ends on a heading with nothing under it
				units.append({"lines": head + lines, "head": True})
			else:
				units.append({"lines": lines, "ctx": context, "bf": brought, "head": False})
		units.append(
			{
				"lines": [
					period_total(moved_dr, moved_cr),
					closing_line(opening_net + moved_dr - moved_cr, dr0 + moved_dr, cr0 + moved_cr),
				],
				"ctx": context,
				"bf": balance,
				"head": False,
			}
		)
		grand[1] += moved_dr
		grand[2] += moved_cr
		return opening_net, moved_dr, moved_cr

	ordered = sorted(sections, key=lambda k: tuple(str(part) for part in k))
	parties = set()
	if category == "Both":
		by_account = {}
		for key in ordered:
			by_account.setdefault(key[0], []).append(key)
		for account in sorted(by_account):
			ledger = [0.0, 0.0, 0.0]
			for index, key in enumerate(by_account[account]):
				rows = sections[key]
				parties.add((key[1], key[2]))
				bands = ([account_band(account)] if index == 0 else []) + [party_band(key[1], key[2], rows)]
				context = [account_band(account, True), party_band(key[1], key[2], rows, True)]
				ledger = [a + b for a, b in zip(ledger, block(key, rows, bands, context))]
			m = meta.get(account) or frappe._dict()
			opening_net, moved_dr, moved_cr = ledger
			units.append(
				{
					"lines": [
						{
							"h": 15.0,
							"fill": S.band,
							"rule_top": (S.accent, 0.6),
							"runs": labelled(_("Total for {0}").format(m.account_number or account), m.account_name or "")
							+ runs(
								amt(moved_dr, S.debit, bold=True),
								amt(moved_cr, S.credit, bold=True),
								bal(opening_net + moved_dr - moved_cr, bold=True),
							),
						}
					],
					"ctx": [account_band(account, True)],
					"head": False,
				}
			)
		accounts = set(by_account)
	elif category == "Party":
		for key in ordered:
			parties.add(key)
			band = party_band(key[0], key[1], sections[key], nested=False)
			block(key, sections[key], [band], [party_band(key[0], key[1], sections[key], True, nested=False)])
		accounts = {p.account for p in postings}
	else:
		for key in ordered:
			block(key, sections[key], [account_band(key[0])], [account_band(key[0], True)])
		accounts = {key[0] for key in sections}
		parties = {(p.party_type, p.party) for p in postings if p.party}

	# the summary that closes the document
	width = (S.right - S.left) / 4.0
	close_net = grand[0] + grand[1] - grand[2]
	labels, values = [], []
	for column, (label, text) in enumerate(
		(
			(_("Opening balance"), bal(grand[0])["text"]),
			(_("Total debit"), _fmt_npr(grand[1]) or "0.00"),
			(_("Total credit"), _fmt_npr(grand[2]) or "0.00"),
			(_("Closing balance"), bal(close_net)["text"]),
		)
	):
		x = S.left + column * width + 8.0
		labels.append(_pt(x, label.upper(), size=6.5, bold=True, colour=S.muted))
		values.append(_pt(x, text, size=_fit(text, width - 16.0, 11.0, True), bold=True, colour=S.ink))
	def counted(n, one, many):
		return "{0} {1}".format(n, one if n == 1 else many)

	party_count = len({p for p in parties if p and p[-1]})
	counts = "   ·   ".join(
		part
		for part in (
			counted(len(accounts), _("account"), _("accounts")),
			counted(party_count, _("party"), _("parties")) if party_count else "",
			counted(len(vouchers), _("voucher"), _("vouchers")),
			counted(len(postings), _("posting"), _("postings")),
		)
		if part
	)
	units.append(
		{
			"lines": [
				{"h": 10.0, "runs": []},
				{"h": 16.0, "runs": [_pt(S.left, _("Summary"), size=9.0, bold=True, colour=S.ink)], "rule_bottom": (S.accent, 0.9)},
				{"h": 16.0, "fill": S.subband, "runs": labels},
				{"h": 20.0, "fill": S.subband, "runs": values, "rule_bottom": (S.hair, 0.4)},
				{"h": 14.0, "runs": [_pt(S.left, counts, size=7.2, colour=S.muted)]},
			],
			"head": True,
		}
	)

	pages = [[]]
	y = S.first_body_top
	for unit in units:
		need = sum(line["h"] for line in unit["lines"])
		mid = not unit["head"] and unit.get("ctx")
		room = S.body_bottom - (STD_CF if mid and unit.get("bf") is not None else 0.0)
		top = S.first_body_top if len(pages) == 1 else S.body_top
		if y + need > room and y > top + 0.5:
			if mid and unit.get("bf") is not None:
				y = _std_place(pages[-1], y, forward(_("Carried forward"), unit["bf"]))
			pages.append([])
			y = S.body_top
			if mid:
				for line in unit["ctx"]:
					y = _std_place(pages[-1], y, line)
				if unit.get("bf") is not None:
					y = _std_place(pages[-1], y, forward(_("Brought forward"), unit["bf"]))
		for line in unit["lines"]:
			y = _std_place(pages[-1], y, line)
	return pages


@frappe.whitelist()
def download_pdf(filters, orientation="Portrait", style="legacy"):
	"""The ledger printed exactly the way the legacy system printed it.

	See the note above PRINT_PAGE_W. Always A4 portrait -- every coordinate is
	measured for it; `orientation` is accepted only so an old link still works.
	"""
	from frappe.utils.pdf import get_pdf

	from avinashgroup_app.custom_code.printing.chrome_pdf import render as chrome_render

	filters = frappe._dict(json.loads(filters) if isinstance(filters, str) else filters)
	_validate(filters)

	postings = _get_postings(filters)
	_decorate(postings, filters.company)
	# "standard" prints the same ledger laid out for reading (see the note above
	# STD); anything else is the legacy Posting Detail page.
	if style == "standard":
		ctx = _std_context(filters)
		pages = _std_pages(filters, postings, ctx)

		def frame(index, total):
			return _std_frame(ctx, index + 1, total)

	else:
		pages = _print_pages(filters, postings)
		head = _print_masthead(filters)

		def frame(index, total):
			return _print_frame(head, index + 1, total)

	if not pages:
		frappe.throw(_("Nothing to print for these filters."))
	sheets = [frame(index, len(pages)) + body for index, body in enumerate(pages)]
	metrics = _carlito()

	template_path = os.path.join(os.path.dirname(__file__), "general_ledger_posting_detail_pdf.html")
	with open(template_path) as handle:
		template = handle.read()
	html = frappe.render_template(
		template,
		{
			"sheets": sheets,
			"page_w": PRINT_PAGE_W,
			"page_h": PRINT_PAGE_H,
			"grey": PRINT_GREY_TEXT,
			"font_regular": metrics["font_regular"],
			"font_bold": metrics["font_bold"],
		},
	)

	# Chrome first, as every print format in this app is rendered: a bench set up
	# that way may have no wkhtmltopdf at all, and get_pdf would raise before
	# anything was tried. get_pdf stays as the fallback for a bench without Chrome.
	pdf = chrome_render(html=html, pdf_generator="chrome")
	if not pdf:
		pdf = get_pdf(
			html,
			{
				"page-size": "A4",
				"orientation": "Portrait",
				"margin-top": "0mm",
				"margin-bottom": "0mm",
				"margin-left": "0mm",
				"margin-right": "0mm",
			},
		)

	frappe.local.response.filename = "General Ledger Posting Detail - {0}.pdf".format(filters.company)
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "download"


def _strip_tags(value):
	"""The visible text of a cell that may carry an anchor."""
	import re

	return re.sub(r"<[^>]+>", "", str(value or ""))
