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
	if not postings:
		return _get_columns(filters), []

	_decorate(postings, filters.company)
	columns = _get_columns(filters)
	return columns, _build_rows(filters, postings, with_narration=True, columns=columns)


def _validate(filters):
	if not filters.company:
		frappe.throw(_("Please select a Company."))
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


def _section_label(filters, key, postings):
	category = filters.get("categorized_by") or "Account"
	sample = postings[0]
	if category == "Party":
		return sample.party_name or _("No Party")
	if category == "Both":
		return "{0}  —  {1}".format(sample.account, sample.party_name or _("No Party"))
	return sample.account


# ERPNext writes this placeholder when a voucher carries no narration at all --
# 778,865 of avinas1's 954,582 GL rows, so printing it would put a noise line
# under four postings in five.
EMPTY_REMARKS = {"no remarks", "no remark", "none", "-"}


def _clean_narration(remarks):
	"""A one-line narration, or "" when there is nothing worth printing.

	Remarks arrive with newlines (reference lines, multi-line notes) and with
	_x000D_ left behind by the spreadsheet imports; both would break the row.
	"""
	if not remarks:
		return ""
	text = " ".join(str(remarks).replace("_x000D_", " ").split())
	return "" if text.lower().strip(" .") in EMPTY_REMARKS else text


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
	accounts = sorted({p.account for p in postings})
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
			GROUP BY g.account, g.party_type, g.party
			""".format(since_clause=since_clause),
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


def _build_rows(filters, postings, with_narration=False, columns=None):
	show_remarks = with_narration and cint(filters.get("remarks", 1))
	columns = columns or _get_columns(filters)

	sections = {}
	for posting in postings:
		sections.setdefault(_section_key(filters, posting), []).append(posting)

	opening = _opening_balances(filters, postings)

	data = []
	grand_opening = grand_debit = grand_credit = 0.0

	for key in sorted(sections, key=lambda k: tuple(str(part) for part in k)):
		rows = sections[key]
		data.append({"_section": 1, "party_name": _section_label(filters, key, rows)})

		# what this account/party carried into the period
		balance = flt(opening.get(key, 0.0))
		grand_opening += balance
		data.append(
			{"party_name": _("Opening Balance"), "balance": balance, "_bold": 1, "_band": 1}
		)

		section_debit = section_credit = 0.0
		for posting in rows:
			balance += flt(posting.debit) - flt(posting.credit)
			section_debit += flt(posting.debit)
			section_credit += flt(posting.credit)
			data.append(
				{
					"miti": posting.miti,
					"voucher_type": posting.voucher_type,
					"voucher_no": posting.voucher_link,
					"voucher_number": posting.number,
					"party_name": posting.party_name or "",
					"debit": flt(posting.debit),
					"credit": flt(posting.credit),
					"balance": balance,
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
					data.append(
						{
							"party_name": "Narr: {0}".format(narration[:400]),
							"narration": narration,
							"_narration": 1,
						}
					)

		data.append(
			{
				"party_name": _("Period Total"),
				"debit": section_debit,
				"credit": section_credit,
				"_bold": 1,
				"_band": 1,
			}
		)
		data.append(
			{"party_name": _("Closing Balance"), "balance": balance, "_bold": 1, "_band": 1}
		)
		data.append({})
		grand_debit += section_debit
		grand_credit += section_credit

	if data:
		data.append(
			{"party_name": _("Opening Balance"), "balance": grand_opening, "_bold": 1, "_band": 1}
		)
		data.append(
			{
				"party_name": _("Grand Total"),
				"debit": grand_debit,
				"credit": grand_credit,
				"_bold": 1,
				"_band": 1,
			}
		)
		data.append(
			{
				"party_name": _("Closing Balance"),
				"balance": grand_opening + grand_debit - grand_credit,
				"_bold": 1,
				"_band": 1,
			}
		)
	return data


def _get_columns(filters=None):
	filters = filters or {}
	return [
		{"fieldname": "miti", "label": _("Posting Miti"), "fieldtype": "Data", "width": 110},
		{"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Data", "width": 140},
		{"fieldname": "voucher_no", "label": _("Voucher No."), "fieldtype": "Data", "width": 210},
		{
			"fieldname": "party_name",
			"label": _("Party Name/Description"),
			"fieldtype": "Data",
			"width": 320,
		},
		{"fieldname": "debit", "label": _("Debit"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "credit", "label": _("Credit"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "balance", "label": _("Balance"), "fieldtype": "Currency", "width": 150},
	]


# ── filter options ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_subtypes(voucher_types=None, txt=None):
	"""Subtypes available for the selected voucher types.

	Each doctype keeps its subtype in its own field pointing at its own doctype,
	so the options are the union of whichever ones are in play. With no voucher
	type selected, everything is offered.
	"""
	selected = _normalize(voucher_types) or list(SUBTYPE_SOURCE)
	needle = (txt or "").strip().lower()

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
		for row in frappe.get_all(linked, fields=["name"], order_by="name", limit=200):
			add(row.name, doctype)

	return options


@frappe.whitelist()
def get_parties(party_types=None, txt=None):
	"""Parties of the selected types, matched on id or name."""
	selected = [p for p in (_normalize(party_types) or list(PARTY_TYPES)) if p in PARTY_TYPES]
	needle = "%{0}%".format((txt or "").strip())

	options = []
	for party_type in selected:
		field = PARTY_NAME_FIELD[party_type]
		rows = frappe.db.sql(
			"""
			SELECT name AS value, `{0}` AS label FROM `tab{1}`
			WHERE name LIKE %(txt)s OR `{0}` LIKE %(txt)s
			ORDER BY `{0}` LIMIT 200
			""".format(field, party_type),
			{"txt": needle},
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
		if not row:
			continue
		printable.append(
			frappe._dict(
				miti=row.get("miti") or "",
				voucher_type=row.get("voucher_type") or "",
				# the anchor is for the desk; print wants the bare number
				voucher_no=row.get("voucher_number") or _strip_tags(row.get("voucher_no")),
				# a narration row's text is split across cells for the grid; the
				# print-out spans it with colspan, so it wants the whole string
				description=row.get("narration") or row.get("party_name") or "",
				debit=_fmt_npr(row.get("debit")),
				credit=_fmt_npr(row.get("credit")),
				balance=_fmt_npr(row.get("balance")),
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


def _strip_tags(value):
	"""The visible text of a cell that may carry an anchor."""
	import re

	return re.sub(r"<[^>]+>", "", str(value or ""))
