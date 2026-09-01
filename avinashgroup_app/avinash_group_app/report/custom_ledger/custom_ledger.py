# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Custom Ledger — the legacy DevExpress ledger reports as one parameterised report.

The old system printed what looked like four different reports:

    General Ledger - Summary            Normal Sub Ledger - Summary
    General Ledger - Posting Detail     Normal Sub Ledger - Detail

They are not four reports. Comparing the print-outs shows one engine with two
axes and everything else a filter — "TDS Formet.pdf" and the vehicle-expense
sub ledger print are the same layout with a different GL selected, and the
"VAT Ledger" and "Gas Purchases (K03)" prints are the same report twice. So
this is one report with a Format dropdown, mirroring the legacy footer's own
"General Ledgers : 19 of 225" account picker.

    LEVEL   account            -> one row per GL account
            subledger          -> GL account, then its sub ledgers beneath it
    DEPTH   summary            -> Opening / Period / Closing, each split Dr-Cr
            detail             -> transactions, with opening/period/closing bands

Summary arithmetic follows ERPNext's "Trial Balance for Party", which already
matches the legacy print: opening and closing are netted onto a single side,
the period columns are left gross.

Sub ledgers are not one thing, which is the only genuinely hard part of the
port. Two resolvers cover what is in the books today:

    party    - the sub ledger is GL Entry.party (TDS, debtors, creditors).
    vehicle  - the sub ledger is a vehicle. An Account declares which vehicles
               belong to it via the custom_sub_type_list child table, and the
               vehicle itself is stamped on the voucher line as custom_subtype.

The vehicle resolver cannot read GL Entry: custom_subtype lives on Journal
Entry Account / Purchase Invoice Item, and GL Entry.voucher_detail_no is empty
on every one of these rows, so there is no link back to the child line. It
therefore aggregates the child tables directly, the same way the existing
Avinas Vehicle Expense report does.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

# Format label -> (level, depth)
FORMATS = {
	"General Ledger - Summary": ("account", "summary"),
	"Normal Sub Ledger - Summary": ("subledger", "summary"),
	"General Ledger - Posting Detail": ("account", "detail"),
	"Normal Sub Ledger - Detail": ("subledger", "detail"),
}

DEFAULT_FORMAT = "Normal Sub Ledger - Summary"

# "General Ledger Type" on the legacy parameter screen: Both / Profit & Loss /
# Balance Sheet. Selecting one is how the legacy operator picks a whole class of
# accounts at once instead of ticking them one by one.
LEDGER_TYPE_ROOTS = {
	"Profit & Loss": ("Income", "Expense"),
	"Balance Sheet": ("Asset", "Liability", "Equity"),
}

NO_SUBLEDGER = "__none__"

PARTY_NAME_FIELD = {
	"Customer": "customer_name",
	"Supplier": "supplier_name",
	"Employee": "employee_name",
	"Member": "member_name",
	"Shareholder": "title",
}

# Voucher number and BS date are both resolved generically, never per-doctype:
#
#   number  Numbering Configuration.target_field names the field a doctype
#           stores its voucher number in — custom_branch_name on Sales
#           Invoice, custom_name on the rest. Reading the rule means a new
#           doctype (or a changed target) needs no edit here.
#   miti    converted from posting_date with the CBMS converter, rather than
#           read from one of the thirteen per-doctype miti fields. The ledger
#           wants the posting date in BS, which is exactly what that yields.


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate(filters)

	level, depth = FORMATS[filters.report_format]

	accounts = _resolve_accounts(filters)
	if not accounts:
		frappe.msgprint(_("No accounts match the current filters."))
		return _get_columns(depth), []

	if depth == "summary":
		data = _build_summary(filters, accounts, level)
	else:
		data = _build_detail(filters, accounts, level)

	return _get_columns(depth), data


# ── filters ─────────────────────────────────────────────────────────────────────

def _validate(filters):
	if not filters.company:
		frappe.throw(_("Please select a Company."))
	if not (filters.from_date and filters.to_date):
		frappe.throw(_("Please select From Date and To Date."))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))

	filters.report_format = filters.get("report_format") or DEFAULT_FORMAT
	if filters.report_format not in FORMATS:
		frappe.throw(_("Unknown Format {0}.").format(filters.report_format))


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
	"""The GL accounts in scope, as {name: row}. Mirrors "General Ledgers : N of M"."""
	chosen = _normalize_multiselect(filters.get("general_ledger"))

	conditions = ["company = %(company)s", "is_group = 0"]
	params = {"company": filters.company}

	if chosen:
		from erpnext.accounts.report.general_ledger.general_ledger import get_accounts_with_children

		params["names"] = get_accounts_with_children(chosen)
		conditions.append("name IN %(names)s")

	roots = LEDGER_TYPE_ROOTS.get(filters.get("ledger_type"))
	if roots:
		params["roots"] = roots
		conditions.append("root_type IN %(roots)s")

	if not cint(filters.get("include_cash_bank")):
		conditions.append("account_type NOT IN ('Cash', 'Bank') OR account_type IS NULL")

	rows = frappe.db.sql(
		"""
		SELECT name, account_number, account_name, account_type
		FROM `tabAccount`
		WHERE {0}
		ORDER BY account_number, name
		""".format(" AND ".join("({0})".format(c) for c in conditions)),
		params,
		as_dict=True,
	)
	return {r.name: r for r in rows}


def _vehicle_accounts(accounts):
	"""Accounts that declare vehicles as their sub ledger, via custom_sub_type_list."""
	if not accounts:
		return set()
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT parent
		FROM `tabVehicle List`
		WHERE parenttype = 'Account'
		  AND parentfield = 'custom_sub_type_list'
		  AND parent IN %(accounts)s
		""",
		{"accounts": list(accounts)},
		as_dict=True,
	)
	return {r.parent for r in rows}


# ── balances ────────────────────────────────────────────────────────────────────

def _gl_balances(filters, accounts, period, by_party=False):
	"""Sum debit/credit from GL Entry, keyed by account (and party when asked)."""
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

	party_select = "IFNULL(g.party_type,'') AS party_type, IFNULL(g.party,'') AS party," if by_party else ""
	party_group = ", g.party_type, g.party" if by_party else ""

	rows = frappe.db.sql(
		"""
		SELECT g.account AS account, {party_select}
			SUM(g.debit) AS debit, SUM(g.credit) AS credit
		FROM `tabGL Entry` g
		WHERE g.company = %(company)s
		  AND g.is_cancelled = 0
		  AND g.account IN %(accounts)s
		  {date_clause}
		GROUP BY g.account{party_group}
		""".format(party_select=party_select, date_clause=date_clause, party_group=party_group),
		params,
		as_dict=True,
	)

	out = {}
	for r in rows:
		key = (r.account, r.party_type or "", r.party or NO_SUBLEDGER) if by_party else r.account
		out[key] = [flt(r.debit), flt(r.credit)]
	return out


def _vehicle_balances(filters, accounts, period):
	"""Sum per (account, vehicle) straight off the voucher child tables.

	GL Entry cannot answer this — see the module docstring.
	"""
	params = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"accounts": list(accounts),
	}

	if period == "opening":
		pi_date = "AND pi.posting_date < %(from_date)s"
		je_date = "AND je.posting_date < %(from_date)s"
	else:
		pi_date = "AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s"
		je_date = "AND je.posting_date BETWEEN %(from_date)s AND %(to_date)s"

	rows = frappe.db.sql(
		"""
		SELECT account, vehicle, SUM(debit) AS debit, SUM(credit) AS credit
		FROM (
			SELECT pii.expense_account AS account, pii.custom_subtype AS vehicle,
			       SUM(pii.amount) AS debit, 0 AS credit
			FROM `tabPurchase Invoice` pi
			JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
			WHERE pi.docstatus = 1 AND pi.company = %(company)s
			  AND pii.expense_account IN %(accounts)s
			  AND IFNULL(pii.custom_subtype, '') != ''
			  {pi_date}
			GROUP BY pii.expense_account, pii.custom_subtype

			UNION ALL

			SELECT jea.account, jea.custom_subtype,
			       SUM(jea.debit), SUM(jea.credit)
			FROM `tabJournal Entry` je
			JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
			WHERE je.docstatus = 1 AND je.company = %(company)s
			  AND jea.account IN %(accounts)s
			  AND IFNULL(jea.custom_subtype, '') != ''
			  {je_date}
			GROUP BY jea.account, jea.custom_subtype
		) AS combined
		GROUP BY account, vehicle
		""".format(pi_date=pi_date, je_date=je_date),
		params,
		as_dict=True,
	)

	return {(r.account, "Vehicle", r.vehicle): [flt(r.debit), flt(r.credit)] for r in rows}


def _toggle_debit_credit(debit, credit):
	"""Net a Dr/Cr pair onto whichever side is larger."""
	if flt(debit) > flt(credit):
		return flt(debit) - flt(credit), 0.0
	return 0.0, flt(credit) - flt(debit)


# ── sub ledger descriptions ─────────────────────────────────────────────────────

def _subledger_names(keys):
	"""Display names for every (kind, code) sub ledger seen."""
	wanted = {}
	for _acc, kind, code in keys:
		if code == NO_SUBLEDGER or not kind:
			continue
		wanted.setdefault(kind, set()).add(code)

	names = {}
	for kind, codes in wanted.items():
		codes = list(codes)
		if kind == "Vehicle":
			for row in frappe.get_all(
				"Vehicle",
				filters={"name": ("in", codes)},
				fields=["name", "license_plate"],
			):
				names[(kind, row.name)] = row.license_plate or row.name
			continue

		name_field = PARTY_NAME_FIELD.get(kind)
		if not name_field or not frappe.db.has_column(kind, name_field):
			continue
		for row in frappe.get_all(
			kind,
			filters={"name": ("in", codes)},
			fields=["name", "{0} as label".format(name_field)],
		):
			names[(kind, row.name)] = row.label
	return names


# ── summary ─────────────────────────────────────────────────────────────────────

def _build_summary(filters, accounts, level):
	show_zero = cint(filters.get("show_zero_values"))

	if level == "account":
		return _account_summary(filters, accounts, show_zero)
	return _subledger_summary(filters, accounts, show_zero)


def _account_summary(filters, accounts, show_zero):
	opening = _gl_balances(filters, accounts, "opening")
	within = _gl_balances(filters, accounts, "within")

	data = []
	grand = frappe._dict(opening_debit=0.0, opening_credit=0.0, debit=0.0, credit=0.0)

	for name, account in accounts.items():
		row = _balance_row(opening.get(name, [0, 0]), within.get(name, [0, 0]))
		if not show_zero and not any(row.values()):
			continue

		data.append(
			dict(
				row,
				code=account.account_number or "",
				description=account.account_name or name,
				account=name,
			)
		)
		_accumulate(grand, row)

	if data:
		data.sort(key=lambda r: (r["code"], r["description"]))
		data.append(_total_row(_("Grand Total"), grand))
	return data


def _subledger_summary(filters, accounts, show_zero):
	vehicle_accounts = _vehicle_accounts(accounts)
	party_accounts = {a: accounts[a] for a in accounts if a not in vehicle_accounts}

	opening, within = {}, {}
	if party_accounts:
		opening.update(_gl_balances(filters, party_accounts, "opening", by_party=True))
		within.update(_gl_balances(filters, party_accounts, "within", by_party=True))
	if vehicle_accounts:
		opening.update(_vehicle_balances(filters, vehicle_accounts, "opening"))
		within.update(_vehicle_balances(filters, vehicle_accounts, "within"))

	keys = set(opening) | set(within)
	labels = _subledger_names(keys)

	per_account = {}
	for key in keys:
		per_account.setdefault(key[0], []).append(key)

	data = []
	grand = frappe._dict(opening_debit=0.0, opening_credit=0.0, debit=0.0, credit=0.0)

	for name in sorted(per_account, key=lambda a: (accounts[a].account_number or "", a)):
		account = accounts[name]
		section, section_rows = frappe._dict(
			opening_debit=0.0, opening_credit=0.0, debit=0.0, credit=0.0
		), []

		for key in per_account[name]:
			_acc, kind, code = key
			row = _balance_row(opening.get(key, [0, 0]), within.get(key, [0, 0]))
			if not show_zero and not any(row.values()):
				continue

			blank = code == NO_SUBLEDGER
			section_rows.append(
				dict(
					row,
					code="" if blank else code,
					kind="" if blank else kind,
					description=_("No Subledger") if blank else (labels.get((kind, code)) or code),
					account=name,
					_blank=blank,
				)
			)
			_accumulate(section, row)
			_accumulate(grand, row)

		if not section_rows:
			continue

		data.append(
			{
				"_section": 1,
				"code": account.account_number or "",
				"description": account.account_name or name,
				"account": name,
			}
		)
		section_rows.sort(key=lambda r: (not r["_blank"], (r["description"] or "").lower()))
		for row in section_rows:
			row.pop("_blank", None)
			data.append(row)
		data.append(_total_row(_("Total ({0})").format(account.account_number or name), section))

	if data:
		data.append({})
		data.append(_total_row(_("Grand Total"), grand))
	return data


def _balance_row(opening_pair, within_pair):
	opening_debit, opening_credit = _toggle_debit_credit(*opening_pair)
	debit, credit = flt(within_pair[0]), flt(within_pair[1])
	closing_debit, closing_credit = _toggle_debit_credit(
		opening_debit + debit, opening_credit + credit
	)
	return {
		"opening_debit": opening_debit,
		"opening_credit": opening_credit,
		"debit": debit,
		"credit": credit,
		"closing_debit": closing_debit,
		"closing_credit": closing_credit,
	}


def _accumulate(bucket, row):
	bucket.opening_debit += row["opening_debit"]
	bucket.opening_credit += row["opening_credit"]
	bucket.debit += row["debit"]
	bucket.credit += row["credit"]


def _total_row(label, bucket):
	opening_debit, opening_credit = _toggle_debit_credit(bucket.opening_debit, bucket.opening_credit)
	closing_debit, closing_credit = _toggle_debit_credit(
		opening_debit + bucket.debit, opening_credit + bucket.credit
	)
	return {
		"description": label,
		"opening_debit": opening_debit,
		"opening_credit": opening_credit,
		"debit": bucket.debit,
		"credit": bucket.credit,
		"closing_debit": closing_debit,
		"closing_credit": closing_credit,
		"_bold": 1,
	}


# ── detail ──────────────────────────────────────────────────────────────────────

def _gl_transactions(filters, accounts, by_party):
	params = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"accounts": list(accounts),
	}
	rows = frappe.db.sql(
		"""
		SELECT g.posting_date, g.account, IFNULL(g.party_type,'') AS party_type,
		       IFNULL(g.party,'') AS party, g.voucher_type, g.voucher_no,
		       g.debit, g.credit, g.remarks
		FROM `tabGL Entry` g
		WHERE g.company = %(company)s
		  AND g.is_cancelled = 0
		  AND g.account IN %(accounts)s
		  AND g.posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND g.is_opening = 'No'
		ORDER BY g.posting_date, g.creation
		""",
		params,
		as_dict=True,
	)
	for r in rows:
		r["group"] = (
			(r.account, r.party_type or "", r.party or NO_SUBLEDGER) if by_party else r.account
		)
	return rows


def _vehicle_transactions(filters, accounts):
	params = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"accounts": list(accounts),
	}
	rows = frappe.db.sql(
		"""
		SELECT pi.posting_date, pii.expense_account AS account,
		       pii.custom_subtype AS vehicle, 'Purchase Invoice' AS voucher_type,
		       pi.name AS voucher_no, pii.amount AS debit, 0 AS credit,
		       pii.description AS remarks
		FROM `tabPurchase Invoice` pi
		JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		WHERE pi.docstatus = 1 AND pi.company = %(company)s
		  AND pii.expense_account IN %(accounts)s
		  AND IFNULL(pii.custom_subtype, '') != ''
		  AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s

		UNION ALL

		SELECT je.posting_date, jea.account, jea.custom_subtype, 'Journal Entry',
		       je.name, jea.debit, jea.credit, je.user_remark
		FROM `tabJournal Entry` je
		JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		WHERE je.docstatus = 1 AND je.company = %(company)s
		  AND jea.account IN %(accounts)s
		  AND IFNULL(jea.custom_subtype, '') != ''
		  AND je.posting_date BETWEEN %(from_date)s AND %(to_date)s

		ORDER BY posting_date
		""",
		params,
		as_dict=True,
	)
	for r in rows:
		r["party_type"], r["party"] = "Vehicle", r.vehicle
		r["group"] = (r.account, "Vehicle", r.vehicle)
	return rows


def _build_detail(filters, accounts, level):
	by_party = level == "subledger"

	if by_party:
		vehicle_accounts = _vehicle_accounts(accounts)
		party_accounts = {a: accounts[a] for a in accounts if a not in vehicle_accounts}
		opening = {}
		transactions = []
		if party_accounts:
			opening.update(_gl_balances(filters, party_accounts, "opening", by_party=True))
			transactions += _gl_transactions(filters, party_accounts, True)
		if vehicle_accounts:
			opening.update(_vehicle_balances(filters, vehicle_accounts, "opening"))
			transactions += _vehicle_transactions(filters, vehicle_accounts)
	else:
		opening = _gl_balances(filters, accounts, "opening")
		transactions = _gl_transactions(filters, accounts, False)

	_apply_voucher_numbers(transactions)

	grouped = {}
	for txn in transactions:
		grouped.setdefault(txn["group"], []).append(txn)

	labels = _subledger_names(grouped) if by_party else {}

	# a group with an opening balance but no movement still prints
	for key in opening:
		grouped.setdefault(key, [])

	per_account = {}
	for key in grouped:
		per_account.setdefault(key[0] if by_party else key, []).append(key)

	data = []
	for name in sorted(per_account, key=lambda a: (accounts[a].account_number or "", a)):
		account = accounts[name]
		data.append(
			{
				"_section": 1,
				"voucher_no": account.account_number or "",
				"description": account.account_name or name,
			}
		)

		for key in sorted(
			per_account[name],
			key=lambda k: (labels.get((k[1], k[2]), k[2]) if by_party else "").lower(),
		):
			rows = grouped[key]
			opening_debit, opening_credit = _toggle_debit_credit(*opening.get(key, [0, 0]))
			balance = opening_debit - opening_credit

			if by_party:
				_acc, kind, code = key
				blank = code == NO_SUBLEDGER
				data.append(
					{
						"_subsection": 1,
						"voucher_no": "" if blank else code,
						"description": _("No Subledger")
						if blank
						else (labels.get((kind, code)) or code),
					}
				)

			data.append(
				{"description": _("Opening Balance"), "balance": balance, "_bold": 1}
			)

			period_debit = period_credit = 0.0
			for txn in rows:
				balance += flt(txn.debit) - flt(txn.credit)
				period_debit += flt(txn.debit)
				period_credit += flt(txn.credit)
				data.append(
					{
						"date": txn.posting_date,
						"miti": txn.get("miti") or "",
						"voucher_no": txn.voucher_no,
						"description": (txn.remarks or txn.voucher_type or "").strip()[:180],
						"debit": flt(txn.debit),
						"credit": flt(txn.credit),
						"balance": balance,
					}
				)

			data.append(
				{
					"description": _("Period Total"),
					"debit": period_debit,
					"credit": period_credit,
					"_bold": 1,
				}
			)
			data.append({"description": _("Closing Balance"), "balance": balance, "_bold": 1})
			data.append({})

	return data


def _voucher_number_fields():
	"""DocType -> the field holding its voucher number, per Numbering Configuration.

	This is the number written on the document the customer is given
	(NGI-CS-000002-83/84), not the internal Frappe name (NGI-JE-83/84-00334),
	and it is what the legacy ledger prints in its Voucher No column.
	"""
	fields = {}
	for row in frappe.get_all(
		"Numbering Configuration",
		filters={"enabled": 1},
		fields=["document_type", "target_field"],
	):
		if row.target_field and row.document_type not in fields:
			fields[row.document_type] = row.target_field
	return fields


def _apply_voucher_numbers(rows):
	"""Swap each row's internal name for its voucher number, and add BS miti."""
	if not rows:
		return

	targets = _voucher_number_fields()

	by_type = {}
	for r in rows:
		if r.get("voucher_type") and r.get("voucher_no"):
			by_type.setdefault(r["voucher_type"], set()).add(r["voucher_no"])

	numbers = {}
	for voucher_type, names in by_type.items():
		field = targets.get(voucher_type)
		if not field or not frappe.db.has_column(voucher_type, field):
			continue
		names = list(names)
		for i in range(0, len(names), 500):
			for row in frappe.get_all(
				voucher_type,
				filters={"name": ("in", names[i : i + 500])},
				fields=["name", "{0} as number".format(field)],
			):
				if row.number:
					numbers[(voucher_type, row.name)] = row.number

	for r in rows:
		# keep the internal name so the row can still be traced back
		r["voucher_name"] = r.get("voucher_no")
		r["voucher_no"] = numbers.get(
			(r.get("voucher_type"), r.get("voucher_no")), r.get("voucher_no")
		)
		r["miti"] = _bs(r.get("posting_date"))


def _bs(ad_date):
	"""posting_date as a BS string, blank if it cannot be converted."""
	if not ad_date:
		return ""
	try:
		from avinashgroup_app.custom_code.CBMS.utils import bs_date_str

		return bs_date_str(ad_date)
	except Exception:
		return ""


# ── columns ─────────────────────────────────────────────────────────────────────

def _currency(fieldname, label, width=130):
	return {
		"fieldname": fieldname,
		"label": label,
		"fieldtype": "Currency",
		"options": "Company:company:default_currency",
		"width": width,
	}


def _get_columns(depth):
	if depth == "summary":
		return [
			{"fieldname": "code", "label": _("Code"), "fieldtype": "Data", "width": 110},
			{"fieldname": "kind", "label": _("Type"), "fieldtype": "Data", "width": 80},
			{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 280},
			_currency("opening_debit", _("Opening (Dr)")),
			_currency("opening_credit", _("Opening (Cr)")),
			_currency("debit", _("Period (Dr)")),
			_currency("credit", _("Period (Cr)")),
			_currency("closing_debit", _("Closing (Dr)")),
			_currency("closing_credit", _("Closing (Cr)")),
			{
				"fieldname": "account",
				"label": _("Account"),
				"fieldtype": "Link",
				"options": "Account",
				"width": 240,
				"hidden": 1,
			},
		]

	return [
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "miti", "label": _("Miti (BS)"), "fieldtype": "Data", "width": 110},
		{"fieldname": "voucher_no", "label": _("Voucher No"), "fieldtype": "Data", "width": 190},
		{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 340},
		_currency("debit", _("Debit")),
		_currency("credit", _("Credit")),
		_currency("balance", _("Balance"), 150),
	]


# ── filter options ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_general_ledgers(company, txt=None, ledger_type=None):
	"""Every account in the company, for the General Ledgers picker.

	frappe.db.get_link_options caps at ten results, which is unusable against
	the 395 accounts a company carries here — the legacy picker offers all of
	them ("General Ledgers : 19 of 225"). This returns the full list, narrowed
	by the typed text and the selected ledger type.
	"""
	if not company:
		return []

	conditions = ["company = %(company)s", "is_group = 0"]
	params = {"company": company, "txt": "%{0}%".format((txt or "").strip())}

	if txt:
		conditions.append("(name LIKE %(txt)s OR account_name LIKE %(txt)s OR account_number LIKE %(txt)s)")

	roots = LEDGER_TYPE_ROOTS.get(ledger_type)
	if roots:
		params["roots"] = roots
		conditions.append("root_type IN %(roots)s")

	return frappe.db.sql(
		"""
		SELECT name AS value,
		       TRIM(CONCAT(IFNULL(account_number, ''), ' ', account_name)) AS description
		FROM `tabAccount`
		WHERE {0}
		ORDER BY account_number, account_name
		LIMIT 1000
		""".format(" AND ".join(conditions)),
		params,
		as_dict=True,
	)
