# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Ageing Report — bill-wise outstanding of customers or suppliers, aged by
posting date into the ranges the user types (like Accounts Receivable).

Why not just Accounts Receivable / Payable
------------------------------------------
On these sites most payments were booked without being allocated to the
bills they pay (Payment Entries left unallocated, receipts through Journal
Entries). ERPNext then shows every old bill as still unpaid and the payment
as a separate advance row: on mysite1 ~2.4 lakh of ~2.9 lakh submitted Sales
Invoices still carry an outstanding amount. The bills look overdue even when
the party owes nothing.

"Merged" fixes the picture without touching the books: for each party, the
advance rows (negative outstanding — unallocated payments, journal receipts,
credit notes) are knocked off the party's bills oldest first (FIFO). A bill
paid down to zero is not shown; a partly paid bill shows what is left, in the
range of its own age. If the advance is bigger than all the bills, what is
left of it shows as one advance row for the party.

Not merged: the bill-wise outstanding exactly as Accounts Receivable /
Payable has it, advance rows included.

Accounts
--------
Every account of type Receivable (Customer) / Payable (Supplier) counts unless
the Account filter narrows it. That matters here: on NGI the Receivable type
is also set on "Record of Deposit Cylinders" and "Other Long Term
Investment", so for Customer the filter starts on Debtors + Advance From
Customer (Party Ledger's default accounts) and deposits stay out.

Where the numbers come from
---------------------------
The bill-wise outstanding and the ageing are ERPNext's own
(accounts_receivable.ReceivablePayableReport, which reads the Payment Ledger),
run with: Receivable for Customer / Payable for Supplier, ageing on Posting
Date as on the report date. This report only reshapes those rows; it never
computes an outstanding amount itself, so Not-merged totals equal AR / AP.

Read-only.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from erpnext.accounts.report.accounts_receivable.accounts_receivable import ReceivablePayableReport

DEFAULT_RANGE = "30, 60, 90, 120"

# Amounts smaller than this are rounding left-overs, not money owed.
ZERO = 0.005

# Customer → Receivable side of ERPNext's AR / AP engine, Supplier → Payable;
# the second item is where the site keeps its "name parties by" setting.
SIDES = {
	"Customer": {"account_type": "Receivable", "naming_by": ["Selling Settings", "cust_master_name"]},
	"Supplier": {"account_type": "Payable", "naming_by": ["Buying Settings", "supp_master_name"]},
}

# The party's group: (filter fieldname, group doctype, field on the party).
GROUPS = {
	"Customer": ("customer_group", "Customer Group", "customer_group"),
	"Supplier": ("supplier_group", "Supplier Group", "supplier_group"),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	party_type = filters.get("party_type") if filters.get("party_type") in SIDES else "Customer"
	ranges = _ranges(filters.get("range"))
	merged = cint(filters.get("merged"))

	columns = _columns(party_type, ranges, merged)
	if not filters.get("company"):
		return columns, []

	rows = _ar_rows(filters, party_type, ranges)
	rows = _merge(rows, ranges) if merged else _not_merged(rows)
	return columns, _with_totals(rows, ranges, merged)


def _ranges(text):
	"""'30, 60, 90, 120' → ['30', '60', '90', '120'] (digits only, like AR)."""
	ranges = [n.strip() for n in (text or DEFAULT_RANGE).split(",") if n.strip().isdigit()]
	return ranges or [n.strip() for n in DEFAULT_RANGE.split(",")]


def _range_fields(ranges):
	return [f"range{i}" for i in range(1, len(ranges) + 2)]


def _columns(party_type, ranges, merged):
	columns = [
		{"label": _(party_type), "fieldname": "party", "fieldtype": "Link", "options": party_type, "width": 130},
		{"label": _("{0} Name").format(_(party_type)), "fieldname": "party_name", "fieldtype": "Data", "width": 200},
		# The group's name: group ids here are series codes (NGK-CGR-0008).
		{"label": _(GROUPS[party_type][1]), "fieldname": "party_group_name", "fieldtype": "Data", "width": 160},
		# Data, not Dynamic Link: the leftover-advance row has no voucher and
		# shows "Advance" here. The JS formatter links real vouchers by their
		# voucher_type, which stays in each row without its own column.
		{"label": _("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Data", "width": 170},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
	]
	# Range headings as AR writes them: 0-30, 31-60, …, 121-Above.
	low = 0
	for field, high in zip(_range_fields(ranges), [*ranges, _("Above")]):
		columns.append({"label": f"{low}-{high}", "fieldname": field, "fieldtype": "Currency", "width": 110})
		if str(high).isdigit():
			low = cint(high) + 1
	if merged:
		columns += [
			{"label": _("Total Due"), "fieldname": "total_due", "fieldtype": "Currency", "width": 120},
			{"label": _("Total Advance"), "fieldname": "total_advance", "fieldtype": "Currency", "width": 120},
		]
	columns.append({"label": _("Total Outstanding"), "fieldname": "outstanding", "fieldtype": "Currency", "width": 130})
	return columns


def _ar_rows(filters, party_type, ranges):
	"""ERPNext's bill-wise rows (one per voucher with something outstanding)."""
	ar_filters = frappe._dict(
		company=filters.company,
		report_date=getdate(filters.get("report_date") or nowdate()),
		party_type=party_type,
		party=_as_list(filters.get("party")),
		ageing_based_on="Posting Date",
		calculate_ageing_with="Report Date",
		range=", ".join(ranges),
	)
	# One account goes to ERPNext's engine (its party_account filter takes one);
	# several are filtered below on each row's account.
	accounts = set(_as_list(filters.get("account")))
	if len(accounts) == 1:
		ar_filters.party_account = next(iter(accounts))
	group_filter, group_doctype, group_field = GROUPS[party_type]
	groups = _as_list(filters.get(group_filter))
	if groups and party_type == "Customer":
		ar_filters.customer_group = groups  # ERPNext adds the sub-groups
	_columns_unused, data, *_rest = ReceivablePayableReport(ar_filters).run(SIDES[party_type])
	fields = _range_fields(ranges)
	rows = []
	for d in data:
		if not d.get("voucher_no"):
			continue  # AR's own total / party rows, if any
		if accounts and d.get("party_account") not in accounts:
			continue
		rows.append(
			frappe._dict(
				party=d.get("party"),
				party_name=d.get("party_name") or d.get("customer_name") or d.get("supplier_name") or d.get("party"),
				party_account=d.get("party_account"),
				voucher_type=d.get("voucher_type"),
				voucher_no=d.get("voucher_no"),
				posting_date=d.get("posting_date"),
				age=cint(d.get("age")),
				outstanding=flt(d.get("outstanding")),
				**{f: flt(d.get(f)) for f in fields},
			)
		)

	# Each row's party group, for the column (and the Supplier Group filter).
	party_groups = dict(
		frappe.get_all(party_type, filters={"name": ["in", list({r.party for r in rows})]}, fields=["name", group_field], as_list=True)
	) if rows else {}
	name_field = "customer_group_name" if party_type == "Customer" else "supplier_group_name"
	group_names = dict(
		frappe.get_all(group_doctype, filters={"name": ["in", list(set(party_groups.values()))]}, fields=["name", name_field], as_list=True)
	) if party_groups else {}
	for r in rows:
		r.party_group = party_groups.get(r.party)
		r.party_group_name = group_names.get(r.party_group) or r.party_group
	if groups and party_type == "Supplier":
		allowed = _with_sub_groups(group_doctype, groups)
		rows = [r for r in rows if r.party_group in allowed]
	return rows


def _with_sub_groups(doctype, groups):
	"""The chosen groups and every group under them (group trees use lft / rgt)."""
	allowed = set()
	for g in groups:
		lft, rgt = frappe.db.get_value(doctype, g, ["lft", "rgt"]) or (None, None)
		if lft is None:
			continue
		allowed.update(frappe.get_all(doctype, filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name"))
	return allowed


def _not_merged(rows):
	"""AR's rows as they are, party by party, oldest first."""
	return sorted(rows, key=lambda r: ((r.party_name or "").lower(), r.party, getdate(r.posting_date), r.voucher_no))


def _merge(rows, ranges):
	"""Knock each party's advance rows off its bills, oldest bill first.

	Per bill: Total Due = what AR says is outstanding on it, Total Advance =
	the part of the party's advance used on it, Total Outstanding = the rest,
	placed in the range of the bill's own age. Bills paid to zero are dropped.
	"""
	fields = _range_fields(ranges)
	by_party = {}
	for r in rows:
		by_party.setdefault(r.party, []).append(r)

	out = []
	for party in sorted(by_party, key=lambda p: ((by_party[p][0].party_name or "").lower(), p)):
		party_rows = by_party[party]
		bills = sorted((r for r in party_rows if r.outstanding > ZERO), key=lambda r: (getdate(r.posting_date), r.voucher_no))
		advance_left = -sum(r.outstanding for r in party_rows if r.outstanding < -ZERO)

		for bill in bills:
			used = min(advance_left, bill.outstanding)
			advance_left -= used
			left = flt(bill.outstanding - used, 2)
			if left <= ZERO:
				continue
			row = frappe._dict(bill, total_due=bill.outstanding, total_advance=used, outstanding=left)
			for f in fields:
				row[f] = 0.0
			row[_range_field_for_age(bill.age, ranges)] = left
			out.append(row)

		if advance_left > ZERO:
			# More advance than bills: what is left is owed back to / by the party.
			first = party_rows[0]
			out.append(
				frappe._dict(
					party=party,
					party_name=first.party_name,
					party_group=first.party_group,
					party_group_name=first.party_group_name,
					voucher_type=None,
					voucher_no=_("Advance"),
					posting_date=None,
					age=None,
					total_due=0.0,
					total_advance=advance_left,
					outstanding=-advance_left,
					**{f: 0.0 for f in fields},
				)
			)
	return out


def _range_field_for_age(age, ranges):
	"""The range column a bill of this age falls in (same rule as AR)."""
	for i, days in enumerate(ranges, start=1):
		if cint(age) <= cint(days):
			return f"range{i}"
	return f"range{len(ranges) + 1}"


def _with_totals(rows, ranges, merged):
	"""One total row per party (when it has more than one row) and a grand total."""
	fields = [*_range_fields(ranges), "outstanding"] + (["total_due", "total_advance"] if merged else [])
	out, grand = [], {f: 0.0 for f in fields}
	i = 0
	while i < len(rows):
		party = rows[i].party
		party_rows = []
		while i < len(rows) and rows[i].party == party:
			party_rows.append(rows[i])
			i += 1
		out.extend(party_rows)
		totals = {f: sum(flt(r.get(f)) for r in party_rows) for f in fields}
		for f in fields:
			grand[f] += totals[f]
		if len(party_rows) > 1:
			out.append(dict(totals, party_name=_("Total: {0}").format(party_rows[0].party_name), bold=1, is_total=1))
	if out:
		out.append(dict(grand, party_name=_("Grand Total"), bold=1, is_total=1))
	return out


def _as_list(value):
	if not value:
		return []
	if isinstance(value, str):
		value = value.strip()
		if value.startswith("["):
			return [v for v in frappe.parse_json(value) if v]
		return [value]
	return [v for v in value if v]


# ---------------------------------------------------------------------------
# Filter dropdowns (both Ageing reports)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_company_groups(party_type, company, txt=None):
	"""Customer / Supplier Groups of one company, for the group filter.

	Both group doctypes carry a Company field (custom_company), which decides.
	The group tree is not used for this: some groups sit under another
	company's branch (NGI's "Bulk 14.2 KG" … "Bulk 450 KG" under NGN's
	Bulk/Retail on mysite1). If the field is ever missing, the company
	abbreviation at the start of the group id (NGK-CGR-0008) is used instead.
	"""
	if party_type not in GROUPS or not company:
		return []
	_filter, doctype, _field = GROUPS[party_type]
	name_field = "customer_group_name" if party_type == "Customer" else "supplier_group_name"
	parent_field = "parent_customer_group" if party_type == "Customer" else "parent_supplier_group"
	filters = {}
	if frappe.db.has_column(doctype, "custom_company"):
		filters["custom_company"] = company
	else:
		abbr = frappe.get_cached_value("Company", company, "abbr")
		filters["name"] = ["like", f"{abbr}-%"]
	or_filters = None
	if txt:
		or_filters = {"name": ["like", f"%{txt}%"], name_field: ["like", f"%{txt}%"]}
	rows = frappe.get_all(
		doctype, filters=filters, or_filters=or_filters, fields=["name", name_field, parent_field], order_by="lft", limit=50
	)
	parents = dict(
		frappe.get_all(doctype, filters={"name": ["in", [r[parent_field] for r in rows if r[parent_field]]]}, fields=["name", name_field], as_list=True)
	) if rows else {}
	# The parent's name tells "Bulk 14.2 KG" under Bulk/Retail apart from a same-named group elsewhere.
	return [
		{"value": r.name, "label": r[name_field], "description": parents.get(r[parent_field]) or ""}
		for r in rows
	]


@frappe.whitelist()
def get_group_parties(party_type, company, groups=None, txt=None):
	"""Parties for the Party filter: the company's parties (same rule as Party
	Ledger's Party filter), narrowed to the chosen groups and their sub-groups."""
	from avinashgroup_app.avinash_group_app.report.party_ledger.party_ledger import get_company_parties

	groups = _as_list(groups)
	if not groups or party_type not in GROUPS:
		return get_company_parties(party_type, company, txt)
	_filter, doctype, field = GROUPS[party_type]
	allowed = _with_sub_groups(doctype, groups)
	name_field = "customer_name" if party_type == "Customer" else "supplier_name"
	filters = {field: ["in", list(allowed)], "disabled": 0}
	if frappe.db.has_column(party_type, "custom_company"):
		filters["custom_company"] = ["in", [company, ""]]
	or_filters = {"name": ["like", f"%{txt}%"], name_field: ["like", f"%{txt}%"]} if txt else None
	rows = frappe.get_all(party_type, filters=filters, or_filters=or_filters, fields=["name", name_field], order_by=name_field, limit=50)
	return [{"value": r.name, "label": r[name_field], "description": r.name} for r in rows]

