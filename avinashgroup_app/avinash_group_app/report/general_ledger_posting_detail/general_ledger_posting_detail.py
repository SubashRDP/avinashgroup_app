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

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

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
	"""Company names the current user may see, from Company User Permissions.

	None means unrestricted -- the Administrator, or a user with no Company
	user permission at all (Frappe's "no user permission == see everything"
	rule). Same shape as the helper in Invoice Activity Report.
	"""
	if frappe.session.user == "Administrator":
		return None
	from frappe.core.doctype.user_permission.user_permission import get_user_permissions

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
	suffix = " - {0}".format(frappe.get_cached_value("Company", company, "abbr")) if company else ""
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
		if suffix and part.endswith(suffix):
			part = part[: -len(suffix)]
		# drop a leading account number ("549301 - R & M ..." -> "R & M ...")
		head, sep, tail = part.partition(" - ")
		if sep and head.strip().isdigit():
			part = tail
		out.append(part.strip())
	return ", ".join(out)


def _decorate(postings, filters_company=None):
	"""Add the BS miti, the printed voucher number as a link, and party names."""
	from avinashgroup_app.custom_code.CBMS.utils import bs_date_str
	from avinashgroup_app.utils.voucher_numbers import link, resolve

	numbers = resolve((r.voucher_type, r.voucher_no) for r in postings)

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
	if category == "Party":
		return sample.party_name or _("No Party")
	if category == "Both":
		return "{0}  —  {1}".format(sample.account, sample.party_name or _("No Party"))
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


def _opening_balances(filters, postings):
	"""Balance carried into the period, keyed the same way the sections are.

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
			       SUM(g.debit) - SUM(g.credit) AS balance
			FROM `tabGL Entry` g
			WHERE g.company = %(company)s
			  AND g.is_cancelled = 0
			  AND g.account IN %(accounts)s
			  AND g.posting_date < %(from_date)s
			  {since_clause}
			  {narrowing}
			GROUP BY g.account, g.party_type, g.party
			""".format(since_clause=since_clause, narrowing=" ".join(narrowing)),
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
		if category == "Party":
			key = (r.party_type or "", r.party or "")
		elif category == "Both":
			key = (r.account, r.party_type or "", r.party or "")
		else:
			key = (r.account,)
		opening[key] = opening.get(key, 0.0) + flt(r.balance)
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


def _build_rows(filters, postings, with_narration=False, columns=None, always_narration=False):
	# The grid always receives narration rows and shows or hides them in the
	# browser -- a checkbox toggle should not cost a five-second re-query. The
	# print-out honours the setting server-side, since it has no browser.
	show_remarks = with_narration and (always_narration or cint(filters.get("remarks", 1)))
	columns = columns or _get_columns(filters)

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

	for key in sorted(sections, key=lambda k: tuple(str(part) for part in k)):
		rows = sections[key]
		data.append({"_section": 1, "party_name": _section_label(filters, key, rows)})

		# what this account/party carried into the period
		balance = flt(opening.get(key, 0.0))
		grand_opening += balance
		data.append(_balance_band(_("Opening Balance"), balance))

		# Kept so the closing balance is derived, not accumulated -- see below.
		section_opening = balance
		section_debit = section_credit = 0.0
		# A date that has not changed is not restated -- Receipt Register does
		# the same. A column of the same date repeated down twenty rows says
		# nothing, and the eye wants the point where it moves.
		last_date = None

		for posting in rows:
			balance += flt(posting.debit) - flt(posting.credit)
			section_debit += flt(posting.debit)
			section_credit += flt(posting.credit)
			same_day = posting.posting_date == last_date
			last_date = posting.posting_date

			data.append(
				{
					"date": "" if same_day else posting.posting_date,
					"miti": "" if same_day else posting.miti,
					"voucher_type": posting.voucher_type,
					"voucher_no": posting.voucher_link,
					"voucher_number": posting.number,
					"party_name": posting.party_name or "",
					"debit": flt(posting.debit),
					"credit": flt(posting.credit),
					# a posting whose running balance happens to hit zero leaves
					# the cell blank; only the Opening/Period/Closing lines are
					# obliged to state a figure
					"balance": _balance_text(balance),
					"balance_value": balance,
				}
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

		# Balance on this line is the period's own net movement, not the running
		# total -- the legacy print states it the same way, so that
		#   opening + period movement = closing
		# reads straight down the Balance column.
		data.append(
			{
				"party_name": _("Period Total"),
				"debit": section_debit,
				"credit": section_credit,
				"balance": _balance_text(section_debit - section_credit, always=True),
				"balance_value": section_debit - section_credit,
				"_bold": 1,
				"_band": 1,
			}
		)
		# Derived from the opening and the period totals, not from the running
		# accumulator. Adding `debit - credit` once per posting compounds float
		# error: on one Gandaki account the accumulator reached
		# 106195401.19999996 where opening + period gives 106195401.2, so the
		# section and grand closing balances disagreed by 4.5e-08 while both
		# displayed as 10,61,95,401.20. A closing balance that does not equal
		# opening plus movement is the first thing an accountant checks.
		data.append(
			_balance_band(
				_("Closing Balance"), section_opening + section_debit - section_credit
			)
		)
		# blank line between sections -- flagged so the formatter empties it.
		# An unflagged {} renders every Currency column as "Rs 0.00", which
		# reads as a real zero on a row that means nothing at all.
		data.append({"_spacer": 1})
		grand_debit += section_debit
		grand_credit += section_credit

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
			data.append(
				{
					"party_name": _("Grand Total"),
					"debit": grand_debit,
					"credit": grand_credit,
					"balance": _balance_text(grand_debit - grand_credit, always=True),
					"balance_value": grand_debit - grand_credit,
					"_bold": 1,
					"_band": 1,
				}
			)
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

@frappe.whitelist()
def download_pdf(filters, orientation="Landscape"):
	"""The ledger as a print-out, with the narration under each posting.

	This is where narration lives: a page has the width to carry a sentence,
	where a datatable cell can only clip it. "Show Narration" is the setting
	that decides whether it is included here.
	"""
	import os

	from frappe.utils.pdf import get_pdf

	from avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger import _fmt_npr, _bs

	filters = frappe._dict(json.loads(filters) if isinstance(filters, str) else filters)
	_validate(filters)

	postings = _get_postings(filters)
	if not postings:
		frappe.throw(_("Nothing to print for these filters."))
	_decorate(postings, filters.company)

	rows = _build_rows(filters, postings, with_narration=True)

	printable = []
	for row in rows:
		if not row or row.get("_spacer"):
			continue

		# The balance is printed exactly as the screen states it -- the figure
		# followed by the side it falls on -- so a number can be checked
		# against the other view without translating between two layouts.
		# _balance_text already produced that string for every row, including
		# the "0.00" the Opening/Period/Closing lines state and the blank a
		# posting leaves when its running balance happens to hit zero.
		printable.append(
			frappe._dict(
				date=row.get("date") or "",
				miti=row.get("miti") or "",
				voucher_type=row.get("voucher_type") or "",
				# the anchor is for the desk; print wants the bare number
				voucher_no=row.get("voucher_number") or _strip_tags(row.get("voucher_no")),
				# a narration row's text is split across cells for the grid; the
				# print-out spans it with colspan, so it wants the whole string
				description=row.get("narration") or row.get("party_name") or "",
				debit=_fmt_npr(row.get("debit")),
				credit=_fmt_npr(row.get("credit")),
				balance=row.get("balance") or "",
				css=(
					"section"
					if row.get("_section")
					else "narration"
					if row.get("_narration")
					else "band"
					if row.get("_band")
					else "total"
					if row.get("_bold")
					else ""
				),
			)
		)

	template_path = os.path.join(os.path.dirname(__file__), "general_ledger_posting_detail_pdf.html")
	with open(template_path) as handle:
		template = handle.read()

	html = frappe.render_template(
		template,
		{
			"company": filters.company,
			"from_bs": _bs(filters.from_date),
			"to_bs": _bs(filters.to_date),
			"grouped_by": filters.get("categorized_by") or "Account",
			"rows": printable,
			"printed_on": _bs(frappe.utils.nowdate()),
			"printed_by": frappe.utils.get_fullname(frappe.session.user),
			"fiscal_year": filters.get("fiscal_year") or "",
			"scope": _print_scope(filters),
		},
	)

	frappe.local.response.filename = "General Ledger Posting Detail - {0}.pdf".format(filters.company)
	frappe.local.response.filecontent = get_pdf(
		html,
		{
			"orientation": orientation if orientation in ("Portrait", "Landscape") else "Landscape",
			"margin-top": "10mm",
			"margin-bottom": "12mm",
			"margin-left": "8mm",
			"margin-right": "8mm",
		},
	)
	frappe.local.response.type = "download"


def _print_scope(filters):
	"""The filters that actually narrowed this print, for the footer."""
	parts = []
	for label, key in (
		("Voucher Type", "voucher_type"),
		("Subtype", "voucher_subtype"),
		("Party Type", "party_type"),
		("Party", "party"),
		("Account", "account"),
	):
		chosen = _normalize(filters.get(key))
		if chosen:
			parts.append("{0}: {1}".format(label, ", ".join(chosen[:4]) + ("…" if len(chosen) > 4 else "")))
	if filters.get("voucher_no"):
		parts.append("Voucher No: {0}".format(filters.voucher_no))
	return parts or ["All vouchers, all parties, all accounts"]


def _strip_tags(value):
	"""The visible text of a cell that may carry an anchor."""
	import re

	return re.sub(r"<[^>]+>", "", str(value or ""))
