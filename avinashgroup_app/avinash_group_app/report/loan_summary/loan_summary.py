# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

# The two Chart of Accounts group accounts that drive the report. The loan-type
# rows are the immediate child accounts under each of these groups, and a cell
# value is the closing balance of that child (summed from its own sub-accounts).
SHORT_TERM_GROUP = "Short Term Borrowings"
LONG_TERM_GROUP = "Long Term Borrowings"


def execute(filters=None):
	filters = frappe._dict(filters or {})

	to_date = getdate(filters.to_date) if filters.to_date else getdate()
	companies = _get_companies(filters)

	if not companies:
		return _columns([]), []

	index = _get_account_index(companies)
	balances = _get_gl_balances(index.accounts, to_date)

	columns = _columns(companies)
	data = _build_rows(companies, index, balances, cint(filters.show_details))
	return columns, data


def _get_companies(filters):
	"""Selected companies (multi-select). Empty selection means all companies."""
	selected = _as_list(filters.company)
	company_filters = {"name": ["in", selected]} if selected else {}
	rows = frappe.get_all(
		"Company", filters=company_filters, fields=["name", "abbr"], order_by="name asc"
	)
	# Preserve the user's selection order when companies were explicitly chosen.
	if selected:
		order = {name: i for i, name in enumerate(selected)}
		rows.sort(key=lambda r: order.get(r.name, len(order)))
	return rows


def _normalize(label):
	"""Collapse label variants that mean the same loan type across companies.

	Only one company spells its short-term loan "Short Term Loan (STL)" while the
	others use "Short Term Loan" (same account number 341300), so the "(STL)"
	marker is stripped to keep them on a single row.
	"""
	label = re.sub(r"\(STL\)", "", label)
	return re.sub(r"\s+", " ", label).strip()


def _get_account_index(companies):
	"""Resolve every posting account under the borrowing groups, tagged with the
	loan-type it rolls up to.

	This touches only the (small) Account table -- the heavy GL Entry table is
	then queried with a plain indexed ``account IN (...)`` filter, which keeps the
	report well under Frappe's 15s "auto prepared report" threshold.
	"""
	placeholders = ", ".join(["%s"] * len(companies))
	rows = frappe.db.sql(
		"""
		SELECT a.name AS account, a.account_name AS account_label, a.lft AS lft,
			a.company AS company, lt.name AS lt_name,
			lt.account_name AS lt_label, lt.lft AS lt_lft,
			grp.account_name AS section
		FROM `tabAccount` a
		INNER JOIN `tabAccount` lt
			ON a.lft >= lt.lft AND a.rgt <= lt.rgt AND a.company = lt.company
		INNER JOIN `tabAccount` grp ON lt.parent_account = grp.name
		WHERE grp.account_name IN (%s, %s)
			AND a.company IN ({companies})
			AND a.is_group = 0
		""".format(companies=placeholders),
		(SHORT_TERM_GROUP, LONG_TERM_GROUP, *[c.name for c in companies]),
		as_dict=True,
	)

	account_map = {}
	short_lft, long_lft = {}, {}
	for r in rows:
		canon = _normalize(r.lt_label)
		account_map[r.account] = frappe._dict(
			company=r.company,
			canon=canon,
			label=r.account_label,
			lft=r.lft,
			# a posting account that is itself the loan type has nothing to expand
			is_head=r.account == r.lt_name,
		)
		bucket = short_lft if r.section == SHORT_TERM_GROUP else long_lft
		if canon not in bucket or r.lt_lft < bucket[canon]:
			bucket[canon] = r.lt_lft

	return frappe._dict(
		accounts=list(account_map.keys()),
		account_map=account_map,
		short=sorted(short_lft, key=short_lft.get),
		long=sorted(long_lft, key=long_lft.get),
	)


def _get_gl_balances(accounts, to_date):
	"""Closing balance (credit - debit) per posting account as of to_date."""
	if not accounts:
		return {}
	placeholders = ", ".join(["%s"] * len(accounts))
	rows = frappe.db.sql(
		"""
		SELECT account, SUM(credit - debit) AS balance
		FROM `tabGL Entry`
		WHERE account IN ({accounts})
			AND is_cancelled = 0
			AND posting_date <= %s
		GROUP BY account
		""".format(accounts=placeholders),
		(*accounts, to_date),
		as_dict=True,
	)
	return {r.account: flt(r.balance) for r in rows}


def _columns(companies):
	columns = [{"label": _("Loan Type"), "fieldname": "loan_type", "fieldtype": "Data", "width": 260}]
	for company in companies:
		columns.append(
			{
				"label": company.abbr or company.name,
				"fieldname": _field(company.name),
				"fieldtype": "Data",
				"align": "right",
				"width": 110,
			}
		)
	columns.append(
		{"label": _("Total"), "fieldname": "total", "fieldtype": "Data", "align": "right", "width": 130}
	)
	return columns


def _build_rows(companies, index, balances, show_details=False):
	fields = {c.name: _field(c.name) for c in companies}

	# (company, normalized loan type) -> rolled-up closing balance, plus the
	# per-account breakdown used when "Show Details" is on.
	matrix = {}
	detail_values = {}  # canon -> {account_label -> {company -> balance}}
	detail_lft = {}  # canon -> {account_label -> lowest lft (display order)}
	has_subaccounts = {}  # canon -> True if any company has a real sub-account
	for account, meta in index.account_map.items():
		balance = balances.get(account, 0.0)
		matrix[(meta.company, meta.canon)] = matrix.get((meta.company, meta.canon), 0.0) + balance

		# collect every posting account with a balance as a potential detail row.
		# a company that posts straight onto the loan-type account (is_head) is
		# kept too, so its amount is never dropped when the head is blanked; the
		# loan type only actually expands when some company has a real
		# sub-account (tracked by has_subaccounts).
		if show_details and account in balances:
			values = detail_values.setdefault(meta.canon, {}).setdefault(meta.label, {})
			values[meta.company] = values.get(meta.company, 0.0) + balance
			order = detail_lft.setdefault(meta.canon, {})
			if meta.label not in order or meta.lft < order[meta.label]:
				order[meta.label] = meta.lft
			if not meta.is_head:
				has_subaccounts[meta.canon] = True

	def loan_values(canon):
		return {c.name: matrix.get((c.name, canon), 0.0) for c in companies}

	def section_total(canons):
		return {
			c.name: sum(matrix.get((c.name, canon), 0.0) for canon in canons)
			for c in companies
		}

	def make_row(label, values, bold=False, ratio=False, detail=False):
		row = {"loan_type": label}
		if bold:
			row["_bold"] = 1
		if detail:
			row["_detail"] = 1
		running = 0.0
		for c in companies:
			value = flt(values.get(c.name, 0.0))
			running += value
			row[fields[c.name]] = _fmt_pct(value) if ratio else _fmt_amt(value)
		row["total"] = _fmt_pct(running) if ratio else _fmt_amt(running)
		return row

	def blank_head(label):
		# group-header row: keep the loan-type name, leave every amount cell empty
		row = {"loan_type": label}
		for c in companies:
			row[fields[c.name]] = ""
		row["total"] = ""
		return row

	def add_loan_type(data, canon):
		# expand only when the loan type genuinely has sub-accounts somewhere;
		# otherwise it is a direct posting account and stays a single inline row
		if not (show_details and has_subaccounts.get(canon)):
			data.append(make_row(canon, loan_values(canon)))
			return
		# details on: head carries no amount, the expanded accounts do
		data.append(blank_head(canon))
		details = detail_values.get(canon, {})
		for label in sorted(details, key=lambda l: detail_lft[canon][l]):
			data.append(make_row(label, details[label], detail=True))

	short_totals = section_total(index.short)
	long_totals = section_total(index.long)
	grand = {c.name: short_totals[c.name] + long_totals[c.name] for c in companies}

	grand_total_all = sum(grand.values())
	ratios = {
		c.name: (grand[c.name] / grand_total_all * 100) if grand_total_all else 0.0
		for c in companies
	}

	data = []
	for canon in index.short:
		add_loan_type(data, canon)
	data.append(make_row(_("Total Short-term Loan"), short_totals, bold=True))
	data.append({})
	for canon in index.long:
		add_loan_type(data, canon)
	data.append(make_row(_("Total Long Term Loan"), long_totals, bold=True))
	data.append({})
	data.append(make_row(_("Total Loan Amount"), grand, bold=True))
	data.append(make_row(_("Ratio"), ratios, bold=True, ratio=True))
	return data


def _field(company_name):
	return frappe.scrub(company_name)


def _fmt_amt(value):
	value = flt(value)
	# accounting-style dash for an exactly-zero cell keeps the grid readable
	if abs(value) < 0.005:
		return "-"
	# borrowings are liabilities: a net credit shows Cr, a net debit shows Dr,
	# instead of signing the number with a minus
	suffix = "Cr" if value > 0 else "Dr"
	return "{:,.2f} {}".format(abs(value), suffix)


def _fmt_pct(value):
	return "{:.2f}%".format(flt(value))


def _as_list(value):
	if not value:
		return []
	if isinstance(value, str):
		value = value.strip()
		if value.startswith("["):
			try:
				value = json.loads(value)
			except Exception:
				return [value]
		else:
			return [value]
	if isinstance(value, (list, tuple, set)):
		return [v for v in value if v]
	return [value]
