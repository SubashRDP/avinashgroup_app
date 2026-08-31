# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""TDS Party Ledger Summary — a party-wise sub ledger of the TDS accounts.

Ported from the legacy "Normal Sub Ledger - Summary" (GL P03, Tax Deduction at
Source). Same arithmetic as ERPNext's "Trial Balance for Party":

    Opening / Closing  ->  netted to a single side
    Period  Dr / Cr    ->  left gross

The one thing the stock report cannot do is show Suppliers and Customers in the
same ledger — its ``party_type`` filter is single-select and required, and it
iterates the party master. This report drives off GL Entry instead, so every
party type lands in one list, and entries carrying no party at all are kept as
the legacy report's "No Subledger" line rather than being dropped.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

NO_SUBLEDGER = "__no_subledger__"

# Party doctype -> the field holding the display name
PARTY_NAME_FIELD = {
	"Customer": "customer_name",
	"Supplier": "supplier_name",
	"Employee": "employee_name",
	"Member": "member_name",
	"Shareholder": "title",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate(filters)

	accounts = _resolve_accounts(filters)
	if not accounts:
		frappe.msgprint(_("No TDS accounts found for {0}.").format(filters.company))
		return _get_columns(filters), []

	opening = _get_balances(filters, accounts, period="opening")
	within = _get_balances(filters, accounts, period="within")

	data = _build_rows(filters, accounts, opening, within)
	return _get_columns(filters), data


# ── filters ─────────────────────────────────────────────────────────────────────

def _validate(filters):
	if not filters.company:
		frappe.throw(_("Please select a Company."))
	if not (filters.from_date and filters.to_date):
		frappe.throw(_("Please select From Date and To Date."))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))


def _normalize_multiselect(value):
	"""Return a cleaned list for MultiSelectList inputs."""
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


def _resolve_accounts(filters):
	"""The TDS accounts in scope, as {name: account_number-and-label}.

	An explicit ``account`` filter wins (group accounts expand to their
	children). Otherwise every non-group account in the company whose name
	looks like a TDS account is used — the legacy report's single P03 ledger
	is split across 348101..348108 here.
	"""
	chosen = _normalize_multiselect(filters.get("account"))
	if chosen:
		from erpnext.accounts.report.general_ledger.general_ledger import get_accounts_with_children

		names = get_accounts_with_children(chosen)
		rows = frappe.get_all(
			"Account",
			filters={"name": ("in", names), "company": filters.company, "is_group": 0},
			fields=["name", "account_number", "account_name"],
			order_by="account_number, name",
		)
	else:
		rows = frappe.db.sql(
			"""
			SELECT name, account_number, account_name
			FROM `tabAccount`
			WHERE company = %(company)s
			  AND is_group = 0
			  AND (account_name LIKE '%%TDS%%' OR account_name LIKE '%%Tax Deduct%%')
			ORDER BY account_number, name
			""",
			{"company": filters.company},
			as_dict=True,
		)

	return {r.name: r for r in rows}


def _party_type_clause(filters, params):
	"""Restrict to the selected party types, keeping the no-party bucket."""
	party_types = _normalize_multiselect(filters.get("party_type"))
	if not party_types:
		return ""

	params["party_types"] = party_types
	clause = "AND g.party_type IN %(party_types)s"
	if cint(filters.get("include_no_subledger")):
		clause = "AND (g.party_type IN %(party_types)s OR IFNULL(g.party, '') = '')"
	return clause


# ── data ────────────────────────────────────────────────────────────────────────

def _get_balances(filters, accounts, period):
	"""Sum debit/credit per (account, party_type, party) for one period."""
	params = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"accounts": list(accounts),
	}

	if period == "opening":
		date_clause = """
			AND (g.posting_date < %(from_date)s
			     OR (g.is_opening = 'Yes' AND g.posting_date <= %(to_date)s))
		"""
	else:
		date_clause = """
			AND g.posting_date >= %(from_date)s
			AND g.posting_date <= %(to_date)s
			AND g.is_opening = 'No'
		"""

	rows = frappe.db.sql(
		"""
		SELECT
			g.account          AS account,
			IFNULL(g.party_type, '') AS party_type,
			IFNULL(g.party, '')      AS party,
			SUM(g.debit)  AS debit,
			SUM(g.credit) AS credit
		FROM `tabGL Entry` g
		WHERE g.company = %(company)s
		  AND g.is_cancelled = 0
		  AND g.account IN %(accounts)s
		  {date_clause}
		  {party_clause}
		GROUP BY g.account, g.party_type, g.party
		""".format(
			date_clause=date_clause,
			party_clause=_party_type_clause(filters, params),
		),
		params,
		as_dict=True,
	)

	out = {}
	for r in rows:
		key = (r.account, r.party_type or "", r.party or NO_SUBLEDGER)
		out[key] = [flt(r.debit), flt(r.credit)]
	return out


def _toggle_debit_credit(debit, credit):
	"""Net a Dr/Cr pair onto whichever side is larger."""
	if flt(debit) > flt(credit):
		return flt(debit) - flt(credit), 0.0
	return 0.0, flt(credit) - flt(debit)


def _get_party_names(keys):
	"""Batch-resolve display names for every (party_type, party) seen."""
	wanted = {}
	for _account, party_type, party in keys:
		if party == NO_SUBLEDGER or not party_type:
			continue
		wanted.setdefault(party_type, set()).add(party)

	names = {}
	for party_type, parties in wanted.items():
		name_field = PARTY_NAME_FIELD.get(party_type)
		if not name_field or not frappe.db.has_column(party_type, name_field):
			continue
		for row in frappe.get_all(
			party_type,
			filters={"name": ("in", list(parties))},
			fields=["name", "{0} as party_name".format(name_field)],
		):
			names[(party_type, row.name)] = row.party_name
	return names


def _build_rows(filters, accounts, opening, within):
	show_zero = cint(filters.get("show_zero_values"))

	keys = set(opening) | set(within)
	party_names = _get_party_names(keys)

	# bucket the keys per account so each account prints as its own section
	per_account = {}
	for key in keys:
		per_account.setdefault(key[0], []).append(key)

	data = []
	grand = frappe._dict(opening_debit=0.0, opening_credit=0.0, debit=0.0, credit=0.0)

	for account in sorted(
		per_account, key=lambda a: (accounts[a].account_number or "", a)
	):
		account_row = accounts[account]
		section_rows = []
		section = frappe._dict(opening_debit=0.0, opening_credit=0.0, debit=0.0, credit=0.0)

		for key in per_account[account]:
			_a, party_type, party = key

			opening_debit, opening_credit = _toggle_debit_credit(*opening.get(key, [0, 0]))
			debit, credit = within.get(key, [0, 0])
			closing_debit, closing_credit = _toggle_debit_credit(
				opening_debit + debit, opening_credit + credit
			)

			if not show_zero and not any(
				(opening_debit, opening_credit, debit, credit, closing_debit, closing_credit)
			):
				continue

			is_no_subledger = party == NO_SUBLEDGER
			section_rows.append(
				frappe._dict(
					party="" if is_no_subledger else party,
					party_type="" if is_no_subledger else party_type,
					party_name=_("No Subledger")
					if is_no_subledger
					else (party_names.get((party_type, party)) or party),
					opening_debit=opening_debit,
					opening_credit=opening_credit,
					debit=flt(debit),
					credit=flt(credit),
					closing_debit=closing_debit,
					closing_credit=closing_credit,
					_sort_key=(0 if is_no_subledger else 1,),
				)
			)

			# section/grand totals accumulate the GROSS movement and the NETTED
			# opening, then get netted once at the end — the way the legacy
			# report's "Balance" line foots.
			for bucket in (section, grand):
				bucket.opening_debit += opening_debit
				bucket.opening_credit += opening_credit
				bucket.debit += flt(debit)
				bucket.credit += flt(credit)

		if not section_rows:
			continue

		data.append(
			{
				"_section": 1,
				"party_name": "{0} {1}".format(
					account_row.account_number or "", account_row.account_name or account
				).strip(),
				"account": account,
			}
		)

		section_rows.sort(key=lambda r: (r._sort_key, (r.party_name or "").lower()))
		for row in section_rows:
			row.pop("_sort_key", None)
			row["account"] = account
			data.append(row)

		data.append(_total_row(_("Total ({0})").format(account_row.account_number or account), section))

	if data:
		data.append({})
		data.append(_total_row(_("Balance"), grand))

	return data


def _total_row(label, bucket):
	opening_debit, opening_credit = _toggle_debit_credit(
		bucket.opening_debit, bucket.opening_credit
	)
	closing_debit, closing_credit = _toggle_debit_credit(
		opening_debit + bucket.debit, opening_credit + bucket.credit
	)
	return {
		"party_name": label,
		"opening_debit": opening_debit,
		"opening_credit": opening_credit,
		"debit": bucket.debit,
		"credit": bucket.credit,
		"closing_debit": closing_debit,
		"closing_credit": closing_credit,
		"_bold": 1,
	}


# ── columns ─────────────────────────────────────────────────────────────────────

def _get_columns(filters):
	currency_col = lambda fieldname, label: {  # noqa: E731
		"fieldname": fieldname,
		"label": label,
		"fieldtype": "Currency",
		"options": "Company:company:default_currency",
		"width": 130,
	}

	return [
		{
			"fieldname": "party",
			"label": _("Sub Ledger Code"),
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 150,
		},
		{
			"fieldname": "party_type",
			"label": _("Type"),
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"fieldname": "party_name",
			"label": _("Sub Ledger Description"),
			"fieldtype": "Data",
			"width": 260,
		},
		currency_col("opening_debit", _("Opening (Dr)")),
		currency_col("opening_credit", _("Opening (Cr)")),
		currency_col("debit", _("Period (Dr)")),
		currency_col("credit", _("Period (Cr)")),
		currency_col("closing_debit", _("Closing (Dr)")),
		currency_col("closing_credit", _("Closing (Cr)")),
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 240,
			"hidden": 1,
		},
	]
