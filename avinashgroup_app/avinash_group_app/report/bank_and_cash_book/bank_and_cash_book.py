"""Bank and Cash Book.

A daybook-style running ledger, one section per cash/bank account (every leaf
account under the company's "Cash and Cash Equivalent" group). Each section runs
Opening Balance -> transactions in date order -> a Day Closing after each date ->
Closing Balance, with a running balance carried down the section.

Stage 1: the flat on-screen layout. The reference PDF layout (day-closings,
voucher subtotals, party/narration sub-lines) is rendered in a later stage; the
figures here are what that layout is built from.

Account discovery and the "Cash and Cash Equivalent" resolution are shared with
Net Position of Cash and Bank so the two reports always agree on the account set.
"""

import json
import os

import frappe
import nepali_datetime as nd
from frappe import _
from frappe.utils import flt, fmt_money, getdate

from avinashgroup_app.avinash_group_app.report.net_position_of_cash_and_bank.net_position_of_cash_and_bank import (
	_cash_and_bank_accounts,
	_opening_balances,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate(filters)
	return get_columns(filters), get_data(filters)


def _validate(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is required"))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are required"))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))


@frappe.whitelist()
def get_cash_bank_accounts(company, txt=None):
	"""Account-filter options: the leaf accounts under the company's
	"Cash and Cash Equivalent" group, for the report's Account MultiSelectList."""
	if not company:
		return []
	txt = (txt or "").lower().strip()
	accounts = _cash_and_bank_accounts(company, None)
	return [
		{"value": a.name, "description": a.account_number or ""}
		for a in accounts
		if not txt or txt in a.name.lower()
	]


def get_columns(filters=None):
	filters = filters or {}
	columns = [
		{"label": _("Voucher Date"), "fieldname": "voucher_date", "fieldtype": "Data", "width": 110},
		{"label": _("Voucher Number"), "fieldname": "voucher_no", "fieldtype": "Data", "width": 150},
		{"label": _("Particulars"), "fieldname": "particulars", "fieldtype": "Data", "width": 300, "align": "left"},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Data", "width": 220, "align": "left"},
		{"label": _("Receipt"), "fieldname": "receipt", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Payment"), "fieldname": "payment", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "options": "currency", "width": 150},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Data", "width": 1, "hidden": 1},
	]
	# Narration is a wide column, so it's shown last and only when asked for.
	if filters.get("show_narration"):
		columns.append(
			{"label": _("Narration"), "fieldname": "narration", "fieldtype": "Data", "width": 320, "align": "left"}
		)
	return columns


def build_sections(filters):
	"""Structured per-account daybook data, shared by the screen table and the
	PDF. Returns a list of account sections, each with its opening balance, its
	transactions grouped by date (each date group carrying a running Day Closing),
	and its closing balance."""
	company = filters.company
	from_date = getdate(filters.from_date)
	to_date = getdate(filters.to_date)

	accounts = _cash_and_bank_accounts(company, filters.get("account"))
	if not accounts:
		return []

	opening_map = _opening_balances([a.name for a in accounts], from_date, to_date, consider_pdc=False)
	txn_map = _transactions([a.name for a in accounts], from_date, to_date)

	sections = []
	for acc in accounts:
		balance = flt(opening_map.get(acc.name, 0.0))
		opening = balance
		date_groups = []
		current = None
		for t in txn_map.get(acc.name, []):
			if current is None or t["posting_date"] != current["posting_date"]:
				current = {"posting_date": t["posting_date"], "bs_date": _bs(t["posting_date"]), "txns": []}
				date_groups.append(current)
			balance += flt(t["debit"]) - flt(t["credit"])
			current["txns"].append({**t, "balance": balance})
		for g in date_groups:
			g["day_closing"] = g["txns"][-1]["balance"]

		sections.append({
			"account": acc.name,
			"account_name": acc.account_name,
			"account_type": acc.account_type,
			"code": acc.account_number or "",
			"opening": opening,
			"date_groups": date_groups,
			"closing": balance,
			"has_txns": bool(date_groups),
		})
	return sections


def get_data(filters):
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	sections = build_sections(filters)
	if not sections:
		return [{}]

	data = []
	for s in sections:
		data.append({
			"particulars": s["account_name"],
			"currency": currency, "is_account_header": 1, "bold": 1,
		})
		data.append({
			"particulars": _("Opening Balance"), "balance": s["opening"],
			"currency": currency, "is_opening": 1, "bold": 1,
		})
		if not s["has_txns"]:
			data.append({
				"particulars": _("No Transactions exist for the specified period."),
				"balance": s["opening"], "currency": currency,
			})
		for g in s["date_groups"]:
			for t in g["txns"]:
				data.append({
					"voucher_date": g["bs_date"], "voucher_no": t["voucher_no"],
					"particulars": t["against"] or "", "party": t["party_line"],
					"narration": t["narration"] or "",
					"receipt": flt(t["debit"]) or None, "payment": flt(t["credit"]) or None,
					"balance": t["balance"], "currency": currency,
				})
			data.append({"particulars": _("Day Closing"), "balance": g["day_closing"], "currency": currency, "bold": 1})
		data.append({
			"particulars": _("Closing Balance"), "balance": s["closing"],
			"currency": currency, "is_closing": 1, "bold": 1,
		})
	return data


@frappe.whitelist()
def download_pdf(filters, view=None):
	"""Portrait Cash Book / Bank Book PDF matching the reference layout: one
	account section per page (Cash Book for cash-type accounts, Bank Book for the
	rest), a running-balance daybook with Day Closings, and a parameters footer
	page. Print opens it inline (view=1); otherwise the file downloads."""
	from frappe.utils.pdf import get_pdf

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	_validate(filters)

	company = filters.company
	sections = build_sections(filters)
	for i, s in enumerate(sections, start=1):
		s["seq"] = i
		s["book"] = _("Cash Book") if s["account_type"] == "Cash" else _("Bank Book")

	company_doc = frappe.db.get_value(
		"Company", company, ["company_name", "default_currency"], as_dict=True
	)

	# Fiscal year covering the From Date — drives the "FY [..]" label next to the
	# company name and the "Accounting Period" (its BS start/end) on the right.
	fy = frappe.db.sql(
		"""SELECT year_start_date, year_end_date FROM `tabFiscal Year`
		   WHERE %(d)s BETWEEN year_start_date AND year_end_date
		   ORDER BY year_start_date DESC LIMIT 1""",
		{"d": getdate(filters.from_date)}, as_dict=True,
	)
	fy_label, accounting_period = "", ""
	if fy:
		bs_start = nd.date.from_datetime_date(getdate(fy[0].year_start_date))
		bs_end = nd.date.from_datetime_date(getdate(fy[0].year_end_date))
		fy_label = "{0}.{1}".format(bs_start.year, str(bs_end.year)[-3:])
		accounting_period = "{0} - {1}".format(_bs(fy[0].year_start_date), _bs(fy[0].year_end_date))

	context = {
		"company_name": company_doc.company_name,
		"fy_label": fy_label,
		"accounting_period": accounting_period,
		"currency": company_doc.default_currency,
		"sections": sections,
		"from_bs": _bs(filters.from_date),
		"to_bs": _bs(filters.to_date),
		"from_date": getdate(filters.from_date),
		"to_date": getdate(filters.to_date),
		"total_pages": len(sections) + 1,
		"show_narration": bool(frappe.utils.cint(filters.get("show_narration"))),
		"fmt": _fmt,
	}

	template_path = os.path.join(os.path.dirname(__file__), "bank_and_cash_book_pdf.html")
	with open(template_path) as f:
		html = frappe.render_template(f.read(), context)

	pdf_data = get_pdf(html, {
		"page-size": "A4", "orientation": "Portrait",
		"margin-top": "8mm", "margin-right": "8mm", "margin-bottom": "12mm", "margin-left": "8mm",
		"encoding": "UTF-8",
	})

	frappe.response.filename = "bank_and_cash_book.pdf"
	frappe.response.filecontent = pdf_data
	frappe.response.type = "pdf" if frappe.utils.cint(view) else "download"


def _fmt(amount):
	"""Nepali-grouped amount with 2 decimals; blank for None."""
	if amount is None:
		return ""
	return fmt_money(flt(amount), 2, format="#,##,###.##")


def _bs(posting_date):
	"""AD posting date -> Bikram Sambat string YYYY/MM/DD."""
	bs = nd.date.from_datetime_date(getdate(posting_date))
	return f"{bs.year}/{bs.month:02d}/{bs.day:02d}"


def _party_name_map(rows):
	"""{party_id: display name} so the report shows 'Ram Traders' instead of the
	Customer/Supplier/Employee ID. IDs appear in gle.party, and for the row on the
	cash/bank account itself (the one this report reads) in gle.against."""
	ids = set()
	for r in rows:
		if r.party:
			ids.add(r.party)
		if r.against:
			ids.update(p.strip() for p in r.against.split(",") if p.strip())
	if not ids:
		return {}

	out = {}
	for doctype, field in (
		("Customer", "customer_name"),
		("Supplier", "supplier_name"),
		("Employee", "employee_name"),
	):
		for d in frappe.get_all(doctype, filters={"name": ["in", list(ids)]}, fields=["name", field]):
			out[d.name] = d.get(field) or d.name
	return out


def _replace_party_ids(text, party_names):
	"""Swap any party IDs inside a comma-separated against/party string for names."""
	if not text:
		return text
	return ", ".join(party_names.get(p.strip(), p.strip()) for p in text.split(",") if p.strip())


def _transactions(account_names, from_date, to_date):
	"""{account: [txn dicts in date order]} for the period.

	Every voucher that hits the account is included (Journal Entry, Payment Entry,
	invoices, ...). The Paid/Recd party and narration come from the Journal Entry
	when the voucher is one, otherwise from the GL Entry's own party/remarks."""
	if not account_names:
		return {}

	rows = frappe.db.sql(
		"""
		SELECT
			gle.account, gle.posting_date, gle.voucher_type,
			COALESCE(je.custom_name, pe.custom_name, pi.custom_name, gle.voucher_no) AS voucher_no,
			gle.against, gle.debit, gle.credit, gle.party, gle.party_type,
			gle.remarks AS gl_remarks,
			je.custom_paid_to, je.user_remark, je.cheque_no, je.cheque_date
		FROM `tabGL Entry` gle
		LEFT JOIN `tabJournal Entry` je
			ON gle.voucher_type = 'Journal Entry' AND je.name = gle.voucher_no
		LEFT JOIN `tabPayment Entry` pe
			ON gle.voucher_type = 'Payment Entry' AND pe.name = gle.voucher_no
		LEFT JOIN `tabPurchase Invoice` pi
			ON gle.voucher_type = 'Purchase Invoice' AND pi.name = gle.voucher_no
		WHERE gle.account IN %(accounts)s
		  AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND gle.is_cancelled = 0
		  AND COALESCE(gle.is_opening, 'No') != 'Yes'
		ORDER BY gle.account, gle.posting_date, gle.creation
		""",
		{"accounts": tuple(account_names), "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)

	party_names = _party_name_map(rows)

	out = {}
	for r in rows:
		# Party name for the Paid:/Recd: line — the JE's "Paid to" when present,
		# else the GL Entry party (supplier/customer), else the contra account.
		against_display = _replace_party_ids(r.against, party_names)
		party_display = party_names.get(r.party, r.party)
		party_name = r.custom_paid_to or party_display or against_display or ""
		if party_name:
			is_receipt = bool(flt(r.debit))
			party_line = "{0} : {1}".format(_("Recd") if is_receipt else _("Paid"), party_name)
			if r.cheque_no:
				# Receipts reference the cheque they came in on ("To"), payments the
				# cheque they went out on ("By") — matching the reference wording.
				chq = "{0} Chq No {1}".format(_("To") if is_receipt else _("By"), r.cheque_no)
				if r.cheque_date:
					chq += " Dt {0}".format(getdate(r.cheque_date).strftime("%Y/%m/%d"))
				party_line += " " + chq
		else:
			party_line = ""

		out.setdefault(r.account, []).append({
			"posting_date": r.posting_date,
			"voucher_no": r.voucher_no,
			"against": against_display,
			"debit": r.debit,
			"credit": r.credit,
			"party_line": party_line,
			"narration": r.user_remark or r.gl_remarks,
			"cheque_no": r.cheque_no,
			"cheque_date": r.cheque_date,
		})
	return out
