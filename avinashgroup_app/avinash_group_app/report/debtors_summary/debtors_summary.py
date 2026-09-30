# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Debtors Summary — customer receivables, in two shapes.

Customer Wise: one company's customers on a single date, largest balance first.

Monthly: every company's closing balance for each day of a Bikram Sambat month,
split into gas and cylinder columns with a group total. Advances from customers
are a separate balance and are deliberately excluded. Below the days, a
"For Comparison" block sets two BS dates side by side — each date's balances,
the change between them and ▲ / ▼ / – per column — like the reference sheet.
"""

import datetime
import json
import os

import frappe
import nepali_datetime as nd
from frappe import _
from frappe.utils import flt, nowdate

CUSTOMER_WISE = "Customer Wise"
MONTHLY = "Monthly"

# Party Ledger Summary needs a period. Closing balance is opening + debit - credit,
# so any From Date earlier than the first GL entry yields the same closing figure.
EARLIEST_FROM_DATE = "1900-01-01"

# Account numbers are identical across all seven companies, so the monthly buckets
# are keyed on the number rather than the (company-suffixed) account name.
GAS_ACCOUNT_NUMBERS = ["143101"]                 # Debtors A/c - Domestic
CYLINDER_ACCOUNT_NUMBERS = ["313101", "313102"]  # Deposit Customers Cylinders

# Left-to-right company order in the Monthly view, following the reference report.
COMPANY_ORDER = ["NGI", "NGN", "NGG", "NGK", "GEPL", "GLMI", "SGU"]

# Up/Down marks in the comparison block.
UP, DOWN, SAME = "▲", "▼", "–"

BS_MONTH_NAMES = [
	"Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
	"Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
]


def execute(filters=None):
	filters = filters or {}
	if (filters.get("view") or CUSTOMER_WISE) == MONTHLY:
		return _execute_monthly(filters)
	return _execute_customer_wise(filters)


# ── Customer Wise ────────────────────────────────────────────────────────────
#
# Reproduces the reference sheet: one company's debtors laid out in side-by-side
# blocks — Bulk, Dealer, Others (from the debtors account, split by Customer
# Group) and Cylinder (from the cylinder-deposit accounts). Each block is its own
# list sorted largest-first; the blocks share row numbers the way spreadsheet
# columns do, so row N holds the Nth-largest of each block, unrelated across
# blocks. A final Total row carries each block's total.

# Debtor blocks in left-to-right order. A customer lands in the first block whose
# keyword its Customer Group name contains; anything left over falls to Others.
DEBTOR_BLOCKS = [
	("bulk",   _("Bulk Customer"),   "Bulk"),
	("dealer", _("Dealer Customer"), "Dealer"),
	("others", _("Others"),          None),
]


def _execute_customer_wise(filters):
	columns = get_customer_wise_columns()
	if not filters.get("company"):
		return columns, []
	return columns, get_customer_wise_data(filters)


def get_customer_wise_columns():
	"""Like the Monthly view, each column carries its block as `group` and its own
	name as `sub_label`, drawn as a two-row heading on screen and in the PDF."""
	columns = [{"label": _("SN"), "fieldname": "sn", "fieldtype": "Data", "width": 50}]

	for key, title, _keyword in DEBTOR_BLOCKS:
		columns += [
			{"label": f"{title} — Code",   "fieldname": f"{key}_code",   "fieldtype": "Data",     "width": 110, "group": title, "sub_label": _("Code")},
			{"label": f"{title} — Name",   "fieldname": f"{key}_name",   "fieldtype": "Data",     "width": 240, "align": "left", "group": title, "sub_label": _("Name")},
			{"label": f"{title} — Amount", "fieldname": f"{key}_amount", "fieldtype": "Currency", "width": 140, "group": title, "sub_label": _("Amount")},
			{"label": f"{title} — Rmk",    "fieldname": f"{key}_rmk",    "fieldtype": "Data",     "width": 55,  "group": title, "sub_label": _("Rmk")},
		]

	cylinder = _("Cylinder")
	columns += [
		{"label": cylinder + " — Name",   "fieldname": "cyl_name",   "fieldtype": "Data",     "width": 240, "align": "left", "group": cylinder, "sub_label": _("Name")},
		{"label": cylinder + " — Amount", "fieldname": "cyl_amount", "fieldtype": "Currency", "width": 140, "group": cylinder, "sub_label": _("Amount")},
		{"label": cylinder + " — Rmk",    "fieldname": "cyl_rmk",    "fieldtype": "Data",     "width": 55,  "group": cylinder, "sub_label": _("Rmk")},
	]
	return columns


def get_customer_wise_data(filters):
	company = filters.get("company")
	as_on = filters.get("as_on_date") or nowdate()

	debtor_rows = _customer_account_balances(company, as_on, GAS_ACCOUNT_NUMBERS, with_group=True)
	cyl_rows = _customer_account_balances(company, as_on, CYLINDER_ACCOUNT_NUMBERS, with_group=False)

	# Bucket the debtors by Customer Group into the blocks. Debit balances fill
	# the main blocks; credit balances are customer advances and fill the same
	# blocks in the Advance section below, as positive figures.
	blocks = {key: [] for key, _title, _kw in DEBTOR_BLOCKS}
	adv_blocks = {key: [] for key, _title, _kw in DEBTOR_BLOCKS}
	for row in debtor_rows:
		key = _block_for_group(row["group"])
		if row["balance"] <= 0:
			adv_blocks[key].append({**row, "balance": -row["balance"]})
		else:
			blocks[key].append(row)

	cyl = [r for r in cyl_rows if r["balance"] > 0]

	for rows in blocks.values():
		rows.sort(key=lambda r: r["balance"], reverse=True)
	cyl.sort(key=lambda r: r["balance"], reverse=True)

	# Lay the blocks out side by side, one list per set of columns.
	n = max([len(rows) for rows in blocks.values()] + [len(cyl)] + [0])
	data = []
	for i in range(n):
		out = {"sn": i + 1}
		for key, _title, _kw in DEBTOR_BLOCKS:
			if i < len(blocks[key]):
				r = blocks[key][i]
				out[f"{key}_code"] = r["code"]
				out[f"{key}_name"] = r["name"]
				out[f"{key}_amount"] = r["balance"]
				out[f"{key}_rmk"] = "DB"
		if i < len(cyl):
			out["cyl_name"] = cyl[i]["name"]
			out["cyl_amount"] = cyl[i]["balance"]
			out["cyl_rmk"] = "DB"
		data.append(out)

	# Totals row — each block totalled under its own Amount column.
	total = {"sn": "", "bold": 1, "bulk_name": _("TOTAL")}
	for key, _title, _kw in DEBTOR_BLOCKS:
		total[f"{key}_amount"] = round(sum(r["balance"] for r in blocks[key]), 2)
	total["cyl_amount"] = round(sum(r["balance"] for r in cyl), 2)
	data.append(total)

	# Advance section — the credit balances the blocks above skipped, split into
	# the same Bulk / Dealer / Others blocks and laid out side by side under the
	# same columns, largest first, as positive figures with a CR remark.
	if any(adv_blocks.values()):
		for rows in adv_blocks.values():
			rows.sort(key=lambda r: r["balance"], reverse=True)

		data.append({})
		header = {"bold": 1}
		for key, title, _kw in DEBTOR_BLOCKS:
			if adv_blocks[key]:
				header[f"{key}_name"] = _("Advance from {0}").format(title)
		data.append(header)

		n_adv = max(len(rows) for rows in adv_blocks.values())
		for i in range(n_adv):
			out = {"sn": i + 1}
			for key, _title, _kw in DEBTOR_BLOCKS:
				if i < len(adv_blocks[key]):
					r = adv_blocks[key][i]
					out[f"{key}_code"] = r["code"]
					out[f"{key}_name"] = r["name"]
					out[f"{key}_amount"] = r["balance"]
					out[f"{key}_rmk"] = "CR"
			data.append(out)

		adv_total = {"sn": "", "bold": 1, "bulk_name": _("TOTAL")}
		for key, _title, _kw in DEBTOR_BLOCKS:
			if adv_blocks[key]:
				adv_total[f"{key}_amount"] = round(sum(r["balance"] for r in adv_blocks[key]), 2)
		data.append(adv_total)

	return data


def _block_for_group(group_name):
	"""First block whose keyword the group name contains; Others otherwise."""
	name = (group_name or "").lower()
	for key, _title, keyword in DEBTOR_BLOCKS:
		if keyword and keyword.lower() in name:
			return key
	return "others"


def _customer_account_balances(company, as_on, account_numbers, with_group):
	"""Per-customer net balance on the given accounts, as on a date.

	Returns dicts with code (customer id), name, balance and — when with_group —
	the Customer Group name used to bucket debtors into blocks.
	"""
	# LEFT join so a customer with no Customer Group still appears — it falls into
	# the Others block rather than being dropped.
	group_select = ", cg.customer_group_name AS grp" if with_group else ""
	group_join = "LEFT JOIN `tabCustomer Group` cg ON cg.name = c.customer_group" if with_group else ""

	rows = frappe.db.sql(f"""
		SELECT gle.party AS code,
		       COALESCE(c.customer_name, gle.party) AS name{group_select},
		       SUM(gle.debit - gle.credit) AS balance
		FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON acc.name = gle.account
		JOIN `tabCustomer` c ON c.name = gle.party
		{group_join}
		WHERE gle.is_cancelled = 0
		  AND gle.party_type = 'Customer'
		  AND acc.account_number IN %(account_numbers)s
		  AND gle.company = %(company)s
		  AND gle.posting_date <= %(as_on)s
		GROUP BY gle.party, name{', grp' if with_group else ''}
		HAVING ROUND(balance, 2) <> 0
	""", {
		"account_numbers": tuple(account_numbers),
		"company": company,
		"as_on": as_on,
	}, as_dict=True)

	for row in rows:
		row["balance"] = round(flt(row["balance"]), 2)
		if with_group:
			row["group"] = row.pop("grp")
	return rows


# ── Monthly ────────────────────────────────────────────────────────────────────

def _execute_monthly(filters):
	bs_year = int(filters.get("bs_year") or 0)
	bs_month = _parse_bs_month(filters.get("bs_month"))

	companies = _companies()
	columns = get_monthly_columns(companies)

	if not bs_year or not bs_month:
		return columns, []

	data, movements = get_monthly_data(bs_year, bs_month, companies)
	if data:
		data += get_comparison_rows(filters, data, companies, movements)
	return columns, data


def _parse_bs_month(value):
	"""The filter sends '03 - Ashadh'; the leading number is the month."""
	if not value:
		return 0
	return int(str(value).split("-")[0].strip())


def _companies():
	"""Companies to show, in COMPANY_ORDER; any not listed there go last."""
	rows = frappe.get_all("Company", fields=["name", "abbr"])
	known = [r for r in rows if r.abbr in COMPANY_ORDER]
	rest = [r for r in rows if r.abbr not in COMPANY_ORDER]
	known.sort(key=lambda r: COMPANY_ORDER.index(r.abbr))
	rest.sort(key=lambda r: r.abbr)
	return known + rest


def get_monthly_columns(companies):
	"""Labels stay fully qualified ("NGI Gas Customers") for Excel export and print.
	On screen the JS draws `group` as a merged row above the header and shows only
	`sub_label` beneath it, like the reference sheet's two-row heading."""
	columns = [{"label": _("Date"), "fieldname": "date", "fieldtype": "Data", "width": 110}]

	for company in companies:
		for suffix, title in (("gas", _("Gas Customers")), ("cyl", _("Cylinder")), ("total", _("Total"))):
			columns.append({
				"label": f"{company.abbr} {title}",
				"fieldname": f"{company.abbr}_{suffix}",
				"fieldtype": "Currency",
				"width": 150,
				"group": company.abbr,
				"sub_label": title,
			})

	consolidated = _("Consolidated Total")
	columns += [
		{"label": _("Total of Gas"),      "fieldname": "total_gas",   "fieldtype": "Currency", "width": 165, "group": consolidated, "sub_label": _("Total of Gas")},
		{"label": _("Total of Cylinder"), "fieldname": "total_cyl",   "fieldtype": "Currency", "width": 165, "group": consolidated, "sub_label": _("Total of Cylinder")},
		{"label": _("Grand Total"),       "fieldname": "grand_total", "fieldtype": "Currency", "width": 175, "group": consolidated, "sub_label": _("Grand Total")},
	]
	return columns


def get_monthly_data(bs_year, bs_month, companies):
	"""The month's daily rows, plus the GL movements they were built from (reused by
	the comparison block for any earlier date)."""
	days = _bs_month_days(bs_year, bs_month)
	if not days:
		return [], {}

	# The reference report opens with the previous month's last day, so balances
	# can be read against a starting point rather than from zero.
	all_days = [_previous_bs_day(days[0][0])] + days

	# Days that haven't happened yet have no balance to report.
	today = datetime.date.today()
	all_days = [entry for entry in all_days if entry[1] <= today]
	if not all_days:
		return [], {}

	first_ad = all_days[0][1]
	last_ad = all_days[-1][1]
	movements = _daily_movements(last_ad)

	# Running balance per (company, bucket), carried forward across days that have
	# no entries of their own.
	balances = {}
	for company in companies:
		for bucket in ("gas", "cyl"):
			balances[(company.name, bucket)] = _opening_balance(movements, company.name, bucket, first_ad)

	data = []
	for bs_date, ad_date in all_days:
		for company in companies:
			for bucket in ("gas", "cyl"):
				balances[(company.name, bucket)] += movements.get((company.name, bucket, ad_date), 0.0)

		row = {"date": _format_bs(bs_date)}
		total_gas = 0.0
		total_cyl = 0.0

		for company in companies:
			gas = round(balances[(company.name, "gas")], 2)
			cyl = round(balances[(company.name, "cyl")], 2)
			row[f"{company.abbr}_gas"] = gas
			row[f"{company.abbr}_cyl"] = cyl
			row[f"{company.abbr}_total"] = round(gas + cyl, 2)
			total_gas += gas
			total_cyl += cyl

		row["total_gas"] = round(total_gas, 2)
		row["total_cyl"] = round(total_cyl, 2)
		row["grand_total"] = round(total_gas + total_cyl, 2)
		data.append(row)

	return data, movements


# ── Monthly comparison block ───────────────────────────────────────────────────

def get_comparison_rows(filters, month_rows, companies, movements):
	"""The "For Comparison" block under the month: a blank spacer, a heading, the
	Compare Date's balances, the With Date's balances, Changes in Value
	(compare − with) and Up/Down (▲ / ▼ / – per column).

	Both dates are typed as BS dates ("2083.03.11") and may fall in any month.
	Left blank, Compare Date is the month's latest reported day and With Date the
	day before Compare Date. Every row carries compare_block so the PDF can keep
	the block together as a table of its own.
	"""
	compare_bs = _parse_bs_date(filters.get("compare_date"), _("Compare Date"))
	if not compare_bs:
		compare_bs = _parse_bs_date(month_rows[-1]["date"], _("Compare Date"))
	with_bs = _parse_bs_date(filters.get("with_date"), _("With Date"))
	if not with_bs:
		with_bs = _previous_bs_day(compare_bs)[0]

	today = datetime.date.today()
	for label, bs_date in ((_("Compare Date"), compare_bs), (_("With Date"), with_bs)):
		if bs_date.to_datetime_date() > today:
			frappe.throw(_("{0} {1} is in the future.").format(label, _format_bs(bs_date)))

	compare_row = _balances_row(compare_bs, companies, month_rows, movements)
	with_row = _balances_row(with_bs, companies, month_rows, movements)

	change_row = {"date": _("Changes in Value"), "bold": 1}
	updown_row = {"date": _("Up/Down"), "up_down": 1}
	for fieldname, value in compare_row.items():
		if fieldname == "date":
			continue
		change = round(value - with_row[fieldname], 2)
		change_row[fieldname] = change
		updown_row[fieldname] = UP if change > 0 else (DOWN if change < 0 else SAME)

	heading = {"date": _("For Comparison"), "bold": 1}
	rows = [{}, heading, compare_row, with_row, change_row, updown_row]
	for row in rows:
		row["compare_block"] = 1
	return rows


def _parse_bs_date(value, label):
	"""A typed BS date — "2083.03.11", "2083-3-11" or "2083/03/11" — as a
	nepali_datetime.date, or None when blank."""
	text = (value or "").strip()
	if not text:
		return None
	parts = text.replace("-", ".").replace("/", ".").split(".")
	try:
		year, month, day = (int(p) for p in parts)
		return nd.date(year, month, day)
	except (ValueError, TypeError):
		frappe.throw(_("{0} \"{1}\" is not a valid BS date. Type it like 2083.03.11.").format(label, text))


def _balances_row(bs_date, companies, month_rows, month_movements):
	"""One Monthly-shaped row of closing balances on a BS date.

	A date inside the reported month is copied from its daily row. An earlier
	date is summed from the movements the month was built from, which run up to
	the month's last reported day. Only a later date costs another pass over the GL.
	"""
	label = _format_bs(bs_date)
	for row in month_rows:
		if row.get("date") == label:
			return dict(row)

	ad_date = bs_date.to_datetime_date()
	covered_to = max((d for (_c, _b, d) in month_movements), default=None)
	if covered_to and ad_date <= covered_to:
		movements = {k: v for k, v in month_movements.items() if k[2] <= ad_date}
	else:
		movements = _daily_movements(ad_date)
	row = {"date": label}
	total_gas = 0.0
	total_cyl = 0.0
	for company in companies:
		gas = round(sum(v for (c, b, _d), v in movements.items() if c == company.name and b == "gas"), 2)
		cyl = round(sum(v for (c, b, _d), v in movements.items() if c == company.name and b == "cyl"), 2)
		row[f"{company.abbr}_gas"] = gas
		row[f"{company.abbr}_cyl"] = cyl
		row[f"{company.abbr}_total"] = round(gas + cyl, 2)
		total_gas += gas
		total_cyl += cyl
	row["total_gas"] = round(total_gas, 2)
	row["total_cyl"] = round(total_cyl, 2)
	row["grand_total"] = round(total_gas + total_cyl, 2)
	return row


def _daily_movements(last_ad):
	"""{(company, bucket, posting_date): net debit} for every day up to last_ad.

	One query for the whole report; the per-day balances are accumulated in
	Python rather than by re-querying for each date.
	"""
	account_numbers = GAS_ACCOUNT_NUMBERS + CYLINDER_ACCOUNT_NUMBERS

	rows = frappe.db.sql("""
		SELECT gle.company, acc.account_number, gle.posting_date,
		       SUM(gle.debit - gle.credit) AS amount
		FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0
		  AND acc.account_number IN %(account_numbers)s
		  AND gle.posting_date <= %(last_ad)s
		GROUP BY gle.company, acc.account_number, gle.posting_date
	""", {"account_numbers": tuple(account_numbers), "last_ad": last_ad}, as_dict=True)

	movements = {}
	for row in rows:
		bucket = "gas" if row.account_number in GAS_ACCOUNT_NUMBERS else "cyl"
		key = (row.company, bucket, row.posting_date)
		movements[key] = movements.get(key, 0.0) + flt(row.amount)
	return movements


def _opening_balance(movements, company, bucket, first_ad):
	"""Everything posted before the report's first day."""
	return sum(
		amount for (comp, buck, date), amount in movements.items()
		if comp == company and buck == bucket and date < first_ad
	)


def _bs_month_days(bs_year, bs_month):
	"""[(bs_date, ad_date)] for every day of a BS month.

	Month lengths vary year to year, so days are probed until one is invalid
	rather than read from a length table.
	"""
	days = []
	for day in range(1, 33):
		try:
			bs_date = nd.date(bs_year, bs_month, day)
		except ValueError:
			break
		days.append((bs_date, bs_date.to_datetime_date()))
	return days


def _previous_bs_day(bs_date):
	"""The BS date one day before the given one."""
	ad_date = bs_date.to_datetime_date() - datetime.timedelta(days=1)
	return (nd.date.from_datetime_date(ad_date), ad_date)


def _format_bs(bs_date):
	return f"{bs_date.year}.{bs_date.month:02d}.{bs_date.day:02d}"


# ── PDF (Download PDF + Print) ────────────────────────────────────────────────
#
# Both buttons open the same wkhtmltopdf PDF. Page numbers are printed in the
# body because the server's wkhtmltopdf is unpatched and ignores footer HTML, so
# rows are chunked into pages here and every page repeats its heading.

# Monthly has 25 columns — too wide for one A4 sheet. Like the reference
# workbook, it prints in parts of at most this many column groups, each part a
# full-width table of its own with the Date column repeated.
MONTHLY_GROUPS_PER_PART = 4

# Body rows per printed page, by view and orientation. Measured against the
# real template through wkhtmltopdf, then set a few rows under capacity.
PDF_ROW_LIMIT = {
	(MONTHLY, "Landscape"): 34,
	(MONTHLY, "Portrait"): 76,  # both 33-row parts stacked on one page
	(CUSTOMER_WISE, "Landscape"): 38,  # overflows at 40
	(CUSTOMER_WISE, "Portrait"): 76,
}

# Page space one table's two-row heading and the gap above it take, in body rows.
PDF_TABLE_HEADING_ROWS = 4


def _fmt_inr(v):
	if not v:
		return ''
	import locale
	try:
		locale.setlocale(locale.LC_ALL, 'en_IN.UTF-8')
		return locale.format_string('%.2f', v, grouping=True)
	except Exception:
		return '{:,.2f}'.format(v)


@frappe.whitelist()
def download_pdf(filters, orientation=None, view=None):
	from frappe.utils.pdf import get_pdf

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	orientation = orientation if orientation in ("Portrait", "Landscape") else "Landscape"

	template_path = os.path.join(os.path.dirname(__file__), "debtors_summary_pdf.html")
	with open(template_path) as f:
		template = f.read()

	html = frappe.render_template(template, _pdf_context(filters, orientation))
	frappe.response.filename = "debtors_summary.pdf"
	frappe.response.filecontent = get_pdf(html, {
		"page-size": "A4",
		"orientation": orientation,
		"margin-top": "10mm",
		"margin-right": "8mm",
		"margin-bottom": "10mm",
		"margin-left": "8mm",
		"encoding": "UTF-8",
	})
	# view=1 (Print) → open inline in the browser tab; otherwise download the file.
	frappe.response.type = "pdf" if frappe.utils.cint(view) else "download"


def _pdf_context(filters, orientation):
	"""Everything the template needs, pre-arranged into pages.

	Returns {"orientation", "pages"}; each page has its heading lines and one or
	more tables, each with the column groups for its two-row heading, its
	columns, and its body rows as display strings.
	"""
	view = filters.get("view") or CUSTOMER_WISE
	columns, data = execute(filters)

	if view == MONTHLY:
		bs_year = int(filters.get("bs_year") or 0)
		bs_month = _parse_bs_month(filters.get("bs_month"))
		title = _("Debtors Summary Report")
		subtitle = f"{BS_MONTH_NAMES[bs_month - 1].upper()} {bs_year}" if bs_month else ""
		# Split into parts of whole column groups, each led by the Date column.
		date_col, rest = columns[0], columns[1:]
		groups = _group_runs(rest)
		parts = [
			[date_col] + [col for run in groups[i:i + MONTHLY_GROUPS_PER_PART] for col in run["columns"]]
			for i in range(0, len(groups), MONTHLY_GROUPS_PER_PART)
		]
	else:
		title = filters.get("company") or ""
		as_on = filters.get("as_on_date") or nowdate()
		subtitle = _("Debtors as on {0}").format(
			_format_bs(nd.date.from_datetime_date(frappe.utils.getdate(as_on)))
		)
		parts = [columns]

	# Cut each part into tables of at most row_limit rows, then fill pages: a
	# table joins the current page while the page's rows — counting each table's
	# heading as PDF_TABLE_HEADING_ROWS — stay within row_limit. So a portrait
	# Monthly stacks both parts on one page, and anything longer runs on.
	#
	# Monthly's comparison block is kept out of that cutting: after all the daily
	# tables, each part's comparison follows as one small table of its own, so it
	# never splits across pages and the parts' comparisons print together. Its
	# blank spacer row is dropped — the gap between tables already separates it.
	row_limit = PDF_ROW_LIMIT[(view, orientation)]
	main_rows = [row for row in data if not row.get("compare_block")]
	compare_rows = [row for row in data if row.get("compare_block") and row.get("date")]
	pages = []
	used = row_limit  # forces a new page for the first table

	def place(table):
		nonlocal used
		cost = len(table["rows"]) + PDF_TABLE_HEADING_ROWS
		if used + cost > row_limit:
			pages.append({"title": title, "subtitle": subtitle, "tables": []})
			used = 0
		pages[-1]["tables"].append(table)
		used += cost

	for part_columns in parts:
		body = [_pdf_row(row, part_columns) for row in main_rows] or [None]
		for start in range(0, len(body), row_limit):
			rows = [row for row in body[start:start + row_limit] if row]
			place({"groups": _group_runs(part_columns), "columns": part_columns, "rows": rows})
	if compare_rows:
		for part_columns in parts:
			rows = [_pdf_row(row, part_columns) for row in compare_rows]
			place({"groups": _group_runs(part_columns), "columns": part_columns, "rows": rows})

	return {"orientation": orientation, "pages": pages}


def _group_runs(columns):
	"""Consecutive columns sharing a `group`, as [{"label", "columns"}]."""
	runs = []
	for col in columns:
		group = col.get("group") or ""
		if runs and runs[-1]["label"] == group:
			runs[-1]["columns"].append(col)
		else:
			runs.append({"label": group, "columns": [col]})
	return runs


def _pdf_row(row, columns):
	"""One body row as display strings, plus whether it prints bold."""
	cells = []
	for col in columns:
		value = row.get(col["fieldname"])
		if row.get("up_down"):
			# ▲ / ▼ / – marks sit in the money columns; print them as they are.
			cells.append("" if value is None else str(value))
		elif col["fieldtype"] == "Currency":
			cells.append(_fmt_inr(value) if value is not None else "")
		else:
			cells.append("" if value is None else str(value))
	return {"cells": cells, "bold": bool(row.get("bold"))}


@frappe.whitelist()
def get_current_bs_period():
	"""Current BS year and month, for the Monthly view's default filter values."""
	today = nd.date.today()
	return {"bs_year": today.year, "bs_month": today.month}
