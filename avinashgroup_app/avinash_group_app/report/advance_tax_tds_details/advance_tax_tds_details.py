# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.utils import flt, getdate

# Tax Withholding Category names encode everything, e.g.
#   "2.5% -11124 TDS-Other Entities"  ->  rate 2.5, khata 11124, title "TDS-Other Entities"
CATEGORY_RE = re.compile(r"^\s*([\d.]+)\s*%\s*-?\s*(\d+)\s+(.+?)\s*$")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		frappe.throw(_("Please select a Company."))

	from_date, to_date = _resolve_period(filters)

	rows = _get_tds_rows(filters.company, from_date, to_date)
	rows += _get_partyless_je_rows(filters.company, from_date, to_date)
	columns = _get_columns()
	data = _build_rows(rows)
	return columns, data


def _resolve_period(filters):
	"""Return (from_date, to_date) from the From/To Date filters.

	The dates may be picked in AD or BS (the rdp Nepali-date widget writes the AD
	value back to from_date/to_date).
	"""
	if not (filters.get("from_date") and filters.get("to_date")):
		frappe.throw(_("Select From Date and To Date."))

	return getdate(filters.from_date), getdate(filters.to_date)


def _get_tds_rows(company, from_date, to_date):
	"""One aggregated row per (supplier, withholding category) for the period.

	karobar = sum of item amounts that have Apply TDS ticked (un-ticked items
	          are excluded, i.e. invoice total minus the un-ticked lines).
	tds     = the invoice's own Total TDS Amount field, added up across the invoices in
	          the group — NOT re-summed from the item lines. The items are pre-aggregated
	          to one row per invoice so this header figure is counted once per invoice
	          rather than once per item line.
	"""
	return frappe.db.sql(
		"""
		SELECT
			pi.supplier_name AS supplier_name,
			sup.tax_id AS pan,
			pi.custom_tax_withholding_category_custom AS category,
			SUM(it.turnover) AS turnover,
			SUM(pi.custom_total_tds_amount) AS tds_amount,
			MAX(it.amount_based) AS amount_based
		FROM `tabPurchase Invoice` pi
		INNER JOIN (
			SELECT
				parent,
				SUM(CASE WHEN apply_tds = 1 THEN amount ELSE 0 END) AS turnover,
				MAX(CASE WHEN custom_tds_apply_on = 'Amount' THEN 1 ELSE 0 END) AS amount_based
			FROM `tabPurchase Invoice Item`
			GROUP BY parent
		) it ON it.parent = pi.name
		LEFT JOIN `tabSupplier` sup ON sup.name = pi.supplier
		WHERE pi.company = %(company)s
			AND pi.docstatus = 1
			AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND pi.custom_tax_withholding_category_custom IS NOT NULL
			AND pi.custom_tax_withholding_category_custom != ''
		GROUP BY pi.supplier_name, pi.custom_tax_withholding_category_custom, sup.tax_id
		HAVING tds_amount != 0 OR turnover != 0
		ORDER BY pi.supplier_name
		""",
		{"company": company, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)


NO_SUBLEDGER = "No Subledger"


def _tds_accounts(company):
	"""TDS account names for the company: the ones the Tax Withholding Categories post to,
	plus any other account named as TDS (the SST accounts are not on a category)."""
	mapped = frappe.get_all(
		"Tax Withholding Account", filters={"company": company}, pluck="account"
	)
	named = frappe.get_all(
		"Account",
		filters={"company": company, "account_name": ("like", "%TDS%")},
		pluck="name",
	)
	return sorted(set(mapped) | set(named))


def _strip_account_name(account, abbr):
	"""'348101 - 11111 TDS-Individual or Proprietorship - NGK' -> '11111 TDS-Individual or
	Proprietorship', i.e. drop the leading account number and the trailing company abbr."""
	name = account or ""
	if abbr and name.endswith(f" - {abbr}"):
		name = name[: -len(f" - {abbr}")]
	return re.sub(r"^\s*\d+\s*-\s*", "", name).strip()


def _fmt_rate(rate):
	"""2.5 -> '2.5', 15.0 -> '15' so the rate column reads like the invoice-based rows."""
	return ("%f" % rate).rstrip("0").rstrip(".")


def _split_account(account, abbr):
	"""(khata, title) for the account a journal entry posted its TDS to, e.g.
	'348101 - 11111 TDS-Individual or Proprietorship - NGK' -> ('11111', 'TDS-Individual
	or Proprietorship'). An account with no khata in its name gives ('', title), which is
	the same empty-khata section the invoice rows use."""
	name = _strip_account_name(account, abbr)
	match = re.match(r"^(\d+)\s+(.+?)$", name)
	if match:
		return match.group(1), match.group(2).strip()
	return "", name


def _get_partyless_je_rows(company, from_date, to_date):
	"""Journal Entry TDS postings where the line carries no party.

	These never reach the Purchase Invoice query above, so without this they are missing
	from the report entirely. They are reported under "No Subledger" in the नाम column,
	inside the section of the account they were posted to.

	कारोबार रकम is the expense side of the same journal entry — for a salary JE of
	47,400 with 474 deducted, the turnover is 47,400 and the rate 1%. A voucher carrying
	several TDS lines has that expense split across them in proportion to each deduction.
	"""
	accounts = _tds_accounts(company)
	if not accounts:
		return []

	abbr = frappe.get_cached_value("Company", company, "abbr")

	lines = frappe.db.sql(
		"""
		SELECT gle.voucher_no, gle.account, (gle.credit - gle.debit) AS tds_amount
		FROM `tabGL Entry` gle
		WHERE gle.company = %(company)s
			AND gle.is_cancelled = 0
			AND gle.voucher_type = 'Journal Entry'
			AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND gle.account IN %(accounts)s
			AND COALESCE(gle.party, '') = ''
			AND (gle.credit - gle.debit) > 0
		""",
		{
			"company": company,
			"from_date": from_date,
			"to_date": to_date,
			"accounts": tuple(accounts),
		},
		as_dict=True,
	)
	if not lines:
		return []

	# The expense (debit) side of each voucher, excluding the TDS lines themselves.
	turnovers = dict(
		frappe.db.sql(
			"""
			SELECT gle.voucher_no, SUM(gle.debit)
			FROM `tabGL Entry` gle
			WHERE gle.company = %(company)s
				AND gle.is_cancelled = 0
				AND gle.voucher_no IN %(vouchers)s
				AND gle.account NOT IN %(accounts)s
			GROUP BY gle.voucher_no
			""",
			{
				"company": company,
				"vouchers": tuple({line.voucher_no for line in lines}),
				"accounts": tuple(accounts),
			},
		)
	)

	# A voucher with several TDS lines shares its expense across them by deduction size.
	tds_per_voucher = {}
	for line in lines:
		tds_per_voucher[line.voucher_no] = tds_per_voucher.get(line.voucher_no, 0) + flt(line.tds_amount)

	rows = []
	for line in lines:
		tds_amount = flt(line.tds_amount)
		voucher_tds = tds_per_voucher.get(line.voucher_no) or 0
		voucher_turnover = flt(turnovers.get(line.voucher_no))
		turnover = voucher_turnover * (tds_amount / voucher_tds) if voucher_tds else 0.0

		# The account tells us which section the row belongs in; the rate is what was
		# actually deducted, since one account serves several rates (15%, 2.5%, 1.5%).
		khata, title = _split_account(line.account, abbr)
		rows.append(
			frappe._dict(
				supplier_name=NO_SUBLEDGER,
				pan=None,
				category=None,
				khata=khata,
				title=title,
				rate=round(tds_amount / turnover * 100, 2) if turnover else 0,
				turnover=turnover,
				tds_amount=tds_amount,
				amount_based=0,
			)
		)

	return _merge_partyless(rows)


def _merge_partyless(rows):
	"""One "No Subledger" line per section, rather than one per journal entry.

	The rate is only shown when every journal entry merged into the line deducted at the
	same rate. Salary/SST vouchers bundle several expenses behind one deduction, so their
	implied rates differ line by line and no single rate describes the merged row.
	"""
	merged = {}
	for row in rows:
		entry = merged.get((row.khata, row.title))
		if entry is None:
			merged[(row.khata, row.title)] = row
			continue
		entry.turnover += row.turnover
		entry.tds_amount += row.tds_amount
		if entry.rate != row.rate:
			entry.rate = 0
	return list(merged.values())


def _parse_category(name):
	"""Return (rate_str, khata, title) parsed from a withholding category name."""
	name = (name or "").strip()
	# with account no: "2.5% -11124 TDS-Other Entities"
	match = CATEGORY_RE.match(name)
	if match:
		return match.group(1), match.group(2), match.group(3).strip()
	# without account no: "1.5% - TDS Payable" -> rate 1.5, no khata, title "TDS Payable"
	match = re.match(r"^([\d.]+)\s*%\s*-?\s*(.+?)$", name)
	if match:
		return match.group(1), "", match.group(2).strip()
	return "", "", name


def _get_columns():
	return [
		{"label": _("क्र.सं."), "fieldname": "sn", "fieldtype": "Data", "width": 55, "align": "center"},
		{"label": _("नाम"), "fieldname": "party", "fieldtype": "Data", "width": 260},
		{"label": _("कारोबार रकम"), "fieldname": "turnover", "fieldtype": "Float", "precision": 2, "width": 140},
		{"label": _("खाता नं"), "fieldname": "account_no", "fieldtype": "Data", "width": 90, "align": "center"},
		{"label": _("अग्रिम कर रकम"), "fieldname": "tds_amount", "fieldtype": "Float", "precision": 2, "width": 140},
		{"label": _("पान नम्बर"), "fieldname": "pan", "fieldtype": "Data", "width": 120},
		{"label": _("रेट"), "fieldname": "rate", "fieldtype": "Data", "width": 80, "align": "right"},
	]


def _build_rows(rows):
	# group (supplier, category) rows into sections keyed by khata (account no)
	sections = {}
	for r in rows:
		if r.get("khata") is not None:
			# Journal Entry rows already know their section and rate (see _split_account).
			rate = _fmt_rate(r.rate) if r.rate else ""
			khata, title = r.khata, r.title
		else:
			rate, khata, title = _parse_category(r.category)
		section = sections.setdefault(khata, {"title": title, "khata": khata, "rows": []})
		# keep the first non-empty title seen for the account
		if not section["title"] and title:
			section["title"] = title
		section["rows"].append(
			frappe._dict(
				supplier_name=r.supplier_name,
				pan=r.pan or "",
				turnover=flt(r.turnover),
				tds_amount=flt(r.tds_amount),
				rate="amount" if r.amount_based else ("{0}%".format(rate) if rate else ""),
			)
		)

	data = []
	serial = 0
	grand_turnover = grand_tds = 0.0

	# order sections by khata (numeric where possible)
	for khata in sorted(sections, key=lambda k: (int(k) if k.isdigit() else 9999999, k)):
		section = sections[khata]

		# section header: category title goes in the कारोबार रकम (turnover) column,
		# account no in खाता नं; the JS formatter blanks the other cells (no 0.00)
		data.append(
			{"_section": 1, "section_title": section["title"], "account_no": section["khata"]}
		)

		sec_turnover = sec_tds = 0.0
		for row in sorted(section["rows"], key=lambda x: (x.supplier_name or "")):
			serial += 1
			sec_turnover += row.turnover
			sec_tds += row.tds_amount
			data.append(
				{
					"sn": serial,
					"party": row.supplier_name,
					"turnover": row.turnover,
					"tds_amount": row.tds_amount,
					"pan": row.pan,
					"rate": row.rate,
				}
			)

		# section total (English label; Nepali stays in the column headers only)
		data.append(
			{
				"party": "TOTAL ({0})".format(section["khata"] or section["title"]),
				"turnover": sec_turnover,
				"tds_amount": sec_tds,
				"_bold": 1,
			}
		)
		data.append({})  # spacer between sections
		grand_turnover += sec_turnover
		grand_tds += sec_tds

	if data:
		data.append(
			{
				"party": "GRAND TOTAL",
				"turnover": grand_turnover,
				"tds_amount": grand_tds,
				"_bold": 1,
			}
		)
	return data


