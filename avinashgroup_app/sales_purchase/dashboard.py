"""Data behind the Selling and Buying dashboards.

The two dashboards sit at the top of the stock Selling and Buying workspaces
(public/js/trade_workspace.js mounts public/js/trade_dashboard.js). They are the
same page with a different "mode": selling reads Sales Invoices / customers,
buying reads Purchase Invoices / suppliers.

Who sees what
-------------
Every figure is read through `frappe.get_list`, never raw SQL, so the dashboard
shows exactly what the user's list views show:

- role permission on the doctype (a block whose doctype the user cannot read
  is left out),
- User Permissions on Company and Branch (strict user permissions is off on
  these sites, so a branch-restricted user also sees documents with no branch,
  the same as in the Sales Invoice list),
- the fiscal-year access rule from custom_code/fiscal_year_filter.py (a
  permission_query_conditions hook, which get_list applies).

Periods are BS months or fiscal years. Both are resolved here in the backend;
the browser only sends "month 2083/7" or "fiscal year 83/84".

Read-only: nothing in this module writes.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from rdp_common_app.utils.bs_boundaries import (
	ad_to_bs,
	get_bs_month_name,
	get_bs_month_range,
)

# Branch dropdown value for "documents with the branch left empty".
NO_BRANCH = "__none__"

# How many rows the "top customers / suppliers / items" cards show.
TOP_N = 8

# The "Waiting for next step" card (open quotations, orders, receipts, draft
# invoices) is hidden to keep the dashboard simple (2026-11-04). Set True to
# bring it back; PIPELINE below is unchanged.
SHOW_PIPELINE = False

# How long one user's dashboard answer is reused before it is read again. The
# year view reads ~70k invoices plus the year before (a cold read took ~30s on
# mysite1 with a 128 MB InnoDB buffer pool), and a year's totals barely move
# minute to minute, so it is kept longer.
CACHE_SECONDS = {"month": 300, "year": 1800}

# No receivable / payable card on purpose (2026-11-03, mysite1): 239,722 of
# 292,376 submitted Sales Invoices still carry an outstanding_amount (payments
# went through Journal Entries without being matched), so invoice ageing is
# wrong; and the GL balance of the Debtors accounts takes ~40s on 5.6M GL rows.
# The menu links to Debtors Summary / Accounts Receivable / Accounts Payable.

MODES = {
	"selling": {
		"title": "Selling",
		"roles": ("Sales User", "Sales Manager", "Accounts User", "Accounts Manager", "System Manager"),
		"invoice": "Sales Invoice",
		"item_table": "Sales Invoice Item",
		"party_field": "customer",
		"party_name_field": "customer_name",
		"party_doctype": "Customer",
		# Payment Entry rows that count as "money in/out" for this side.
		"payment_type": "Receive",
		"payment_amount": "base_received_amount",
	},
	"buying": {
		"title": "Buying",
		"roles": ("Purchase User", "Purchase Manager", "Accounts User", "Accounts Manager", "System Manager"),
		"invoice": "Purchase Invoice",
		"item_table": "Purchase Invoice Item",
		"party_field": "supplier",
		"party_name_field": "supplier_name",
		"party_doctype": "Supplier",
		"payment_type": "Pay",
		"payment_amount": "base_paid_amount",
	},
}


def _mode(mode):
	if mode not in MODES:
		frappe.throw(_("Unknown dashboard {0}").format(mode))
	cfg = MODES[mode]
	frappe.only_for(cfg["roles"])
	return cfg


@frappe.whitelist()
def get_dashboard(mode, company=None, branch=None, period="month", bs_year=None, bs_month=None, fiscal_year=None, force=0):
	"""Every figure on one dashboard for one period.

	period="month" uses bs_year/bs_month (default: the current BS month);
	period="year" uses fiscal_year (default: the fiscal year of today).
	Raises PermissionError for a company or branch the user may not see.

	The answer is cached per user and per filter for CACHE_SECONDS, because
	the year view and the payment total are slow on a cold database.
	force=1 (the refresh button) skips the cache.
	"""
	_mode(mode)
	key = "trade_dashboard:v2:" + frappe.as_json(
		[frappe.session.user, mode, company, branch, period, bs_year, bs_month, fiscal_year], indent=None
	)
	if not frappe.utils.cint(force):
		cached = frappe.cache.get_value(key)
		if cached:
			return cached
	out = _build(mode, company, branch, period, bs_year, bs_month, fiscal_year)
	out["generated_at"] = frappe.utils.now()
	frappe.cache.set_value(key, out, expires_in_sec=CACHE_SECONDS.get(period, CACHE_SECONDS["month"]))
	return out


def _build(mode, company, branch, period, bs_year, bs_month, fiscal_year):
	cfg = _mode(mode)
	scope = _scope(company, branch)
	window = _period(period, bs_year, bs_month, fiscal_year)

	can_read_invoice = frappe.has_permission(cfg["invoice"], "read")
	out = {
		"mode": mode,
		"title": _(cfg["title"]),
		"today": _today_label(),
		"period": window["public"],
		"companies": scope["all_companies"],
		"branches": scope["all_branches"],
		"company": company or "",
		"branch": branch or "",
		"can_read_invoice": can_read_invoice,
	}
	if not scope["companies"]:
		return out

	if can_read_invoice:
		out["totals"] = _totals(cfg, scope, window)
		out["trend"] = _trend(cfg, scope, window)
		out["top_parties"] = _top_parties(cfg, scope, window)
		out["top_items"] = _top_items(cfg, scope, window)
		out["by_branch"] = _by_branch(cfg, scope, window)
		out["by_company"] = _by_company(cfg, scope, window)
	out["paid"] = _payments(cfg, scope, window)
	out["pipeline"] = _pipeline(mode, scope, window) if SHOW_PIPELINE else []
	return out


# ---------------------------------------------------------------------------
# Scope: which companies and branches this user may look at
# ---------------------------------------------------------------------------

def _scope(company, branch):
	"""Companies and branches the user may see, narrowed to the chosen ones.

	Both lists come from get_list, so they already obey User Permissions.
	"""
	all_companies = frappe.get_list("Company", pluck="name", order_by="name")
	if company and company not in all_companies:
		frappe.throw(_("Not permitted for company {0}").format(company), frappe.PermissionError)
	companies = [company] if company else all_companies

	abbr = dict(frappe.get_all("Company", fields=["name", "abbr"], as_list=True))
	branches = []
	if companies:
		branches = frappe.get_list(
			"Branch",
			filters={"custom_company": ["in", companies]},
			fields=["name", "branch", "custom_company"],
			order_by="custom_company, branch",
		)
	all_branches = [
		{
			"name": b.name,
			"label": b.branch or b.name,
			"company": b.custom_company,
			"abbr": abbr.get(b.custom_company, ""),
		}
		for b in branches
	]
	if branch and branch != NO_BRANCH and branch not in {b["name"] for b in all_branches}:
		frappe.throw(_("Not permitted for branch {0}").format(branch), frappe.PermissionError)

	return {
		"companies": companies,
		"branch": branch or None,
		"abbr": abbr,
		"branch_labels": {b["name"]: b for b in all_branches},
		"all_companies": [{"name": c, "abbr": abbr.get(c, c)} for c in all_companies],
		"all_branches": all_branches,
	}


def _has_branch(doctype):
	return frappe.get_meta(doctype).has_field("custom_branch")


def _base_filters(doctype, scope, docstatus=1):
	"""Company + branch + docstatus filters for one doctype.

	The branch filter is skipped for doctypes without a branch field
	(Purchase Order, Material Request); the card says so.
	"""
	filters = [[doctype, "company", "in", scope["companies"]]]
	if docstatus is not None:
		filters.append([doctype, "docstatus", "=", docstatus])
	branch = scope["branch"]
	if branch and _has_branch(doctype):
		if branch == NO_BRANCH:
			filters.append([doctype, "custom_branch", "is", "not set"])
		else:
			filters.append([doctype, "custom_branch", "=", branch])
	return filters


def _between(doctype, start, end, field="posting_date"):
	return [doctype, field, "between", [str(start), str(end)]]


# ---------------------------------------------------------------------------
# Period
# ---------------------------------------------------------------------------

def _step_month(year, month, delta):
	index = year * 12 + (month - 1) + delta
	return index // 12, index % 12 + 1


def _period(period, bs_year, bs_month, fiscal_year):
	"""The chosen window, the window before it, and how they line up.

	`compare` is the slice of the previous window that matches how far into
	the current window we are: on 10 Kartik, Kartik 1–10 is compared with
	Ashwin 1–10, not with the whole of Ashwin.
	"""
	date_today = getdate(today())
	if period == "year":
		fy = _fiscal_year(fiscal_year, date_today)
		start, end = getdate(fy.year_start_date), getdate(fy.year_end_date)
		prev = _fiscal_year_containing(add_days(start, -1))
		nxt = _fiscal_year_containing(add_days(end, 1))
		prev_start = getdate(prev.year_start_date) if prev else start.replace(year=start.year - 1)
		prev_end = getdate(prev.year_end_date) if prev else add_days(start, -1)
		label = _("FY {0}").format(fy.name)
		prev_label = _("FY {0}").format(prev.name) if prev else _("previous year")
		public = {
			"kind": "year",
			"fiscal_year": fy.name,
			"prev": {"fiscal_year": prev.name, "label": prev_label} if prev else None,
			"next": {"fiscal_year": nxt.name, "label": _("FY {0}").format(nxt.name)}
			if nxt and getdate(nxt.year_start_date) <= date_today
			else None,
		}
	else:
		if bs_year and bs_month:
			year, month = int(bs_year), int(bs_month)
		else:
			bs = ad_to_bs(date_today)
			year, month = bs.year, bs.month
		start, end = get_bs_month_range(year, month)
		py, pm = _step_month(year, month, -1)
		ny, nm = _step_month(year, month, 1)
		prev_start, prev_end = get_bs_month_range(py, pm)
		label = f"{get_bs_month_name(month)} {year}"
		prev_label = f"{get_bs_month_name(pm)} {py}"
		next_start, _next_end = get_bs_month_range(ny, nm)
		public = {
			"kind": "month",
			"bs_year": year,
			"bs_month": month,
			"prev": {"bs_year": py, "bs_month": pm, "label": prev_label},
			"next": {"bs_year": ny, "bs_month": nm, "label": f"{get_bs_month_name(nm)} {ny}"}
			if next_start <= date_today
			else None,
		}

	# How far into the window we are, capped at its end.
	upto = min(end, date_today) if start <= date_today else end
	elapsed = (upto - start).days + 1
	compare_end = min(prev_end, add_days(prev_start, elapsed - 1))
	in_progress = start <= date_today < end

	public.update(
		{
			"label": label,
			"start": str(start),
			"end": str(end),
			"days": (end - start).days + 1,
			"elapsed": elapsed,
			"in_progress": in_progress,
			"compare_label": (
				_("same days of {0}").format(prev_label) if in_progress else prev_label
			),
		}
	)
	return {
		"start": start,
		"end": end,
		"prev_start": prev_start,
		"prev_end": prev_end,
		"compare_end": getdate(compare_end),
		"kind": public["kind"],
		"public": public,
	}


def _fiscal_year(name, date_today):
	if name:
		if not frappe.db.exists("Fiscal Year", name):
			frappe.throw(_("Fiscal Year {0} not found").format(name))
		return frappe.db.get_value("Fiscal Year", name, ["name", "year_start_date", "year_end_date"], as_dict=True)
	fy = _fiscal_year_containing(date_today)
	if not fy:
		frappe.throw(_("No Fiscal Year covers today"))
	return fy


def _fiscal_year_containing(date):
	rows = frappe.get_all(
		"Fiscal Year",
		filters={"year_start_date": ["<=", date], "year_end_date": [">=", date], "disabled": 0},
		fields=["name", "year_start_date", "year_end_date"],
		limit=1,
	)
	return rows[0] if rows else None


def _today_label():
	date = getdate(today())
	bs = ad_to_bs(date)
	return {
		"date": str(date),
		"bs_label": f"{bs.day} {get_bs_month_name(bs.month)} {bs.year}",
		"weekday": date.strftime("%A"),
	}


# ---------------------------------------------------------------------------
# Invoice figures
# ---------------------------------------------------------------------------

def _invoice_sums(cfg, scope, start, end):
	"""Sale (or purchase) and return totals between two dates, excl. VAT."""
	doctype = cfg["invoice"]
	rows = frappe.get_list(
		doctype,
		filters=_base_filters(doctype, scope) + [_between(doctype, start, end)],
		fields=[
			"is_return",
			"sum(base_net_total) as net",
			"sum(base_grand_total) as grand",
			"count(name) as bills",
			f"count(distinct {cfg['party_field']}) as parties",
		],
		group_by="is_return",
		order_by=None,
	)
	out = {"gross": 0.0, "returns": 0.0, "net": 0.0, "grand": 0.0, "bills": 0, "return_bills": 0, "parties": 0}
	for r in rows:
		if r.is_return:
			out["returns"] = flt(r.net)  # negative on a return
			out["return_bills"] = r.bills
		else:
			out["gross"] = flt(r.net)
			out["bills"] = r.bills
			out["parties"] = r.parties
		out["grand"] += flt(r.grand)
	out["net"] = out["gross"] + out["returns"]
	out["avg_bill"] = out["gross"] / out["bills"] if out["bills"] else 0
	return out


def _totals(cfg, scope, window):
	now = _invoice_sums(cfg, scope, window["start"], window["end"])
	before = _invoice_sums(cfg, scope, window["prev_start"], window["compare_end"])
	return {"now": now, "before": before}


def _daily(cfg, scope, start, end):
	doctype = cfg["invoice"]
	rows = frappe.get_list(
		doctype,
		filters=_base_filters(doctype, scope) + [_between(doctype, start, end)],
		fields=["posting_date", "sum(base_net_total) as net", "count(name) as bills"],
		group_by="posting_date",
		order_by=None,
	)
	return {str(r.posting_date): (flt(r.net), r.bills) for r in rows}


def _trend(cfg, scope, window):
	"""Net amount per BS day (month view) or per BS month (year view).

	`before` is the previous window laid on the same buckets — day 5 of last
	month under day 5 of this month — so the two read against each other.
	"""
	now = _daily(cfg, scope, window["start"], window["end"])
	before = _daily(cfg, scope, window["prev_start"], window["prev_end"])
	date_today = getdate(today())

	if window["kind"] == "month":
		buckets = []
		day = window["start"]
		i = 0
		while day <= window["end"]:
			prev_day = add_days(window["prev_start"], i)
			value, bills = now.get(str(day), (0.0, 0))
			buckets.append(
				{
					"label": str(i + 1),
					"date": str(day),
					"weekday": day.strftime("%a"),
					"value": value,
					"bills": bills,
					"before": before.get(str(prev_day), (0.0, 0))[0] if getdate(prev_day) <= window["prev_end"] else None,
					"future": day > date_today,
				}
			)
			day = add_days(day, 1)
			i += 1
		return {"unit": "day", "buckets": buckets}

	# Year view: twelve BS months starting at the fiscal year's first month.
	def by_month(daily, start):
		months = {}
		for date_str, (value, bills) in daily.items():
			bs = ad_to_bs(getdate(date_str))
			key = (bs.year, bs.month)
			v, b = months.get(key, (0.0, 0))
			months[key] = (v + value, b + bills)
		first = ad_to_bs(getdate(start))
		return months, (first.year, first.month)

	now_months, (y, m) = by_month(now, window["start"])
	before_months, (py, pm) = by_month(before, window["prev_start"])
	buckets = []
	for i in range(12):
		ky, km = _step_month(y, m, i)
		kpy, kpm = _step_month(py, pm, i)
		month_start, _month_end = get_bs_month_range(ky, km)
		value, bills = now_months.get((ky, km), (0.0, 0))
		buckets.append(
			{
				"label": get_bs_month_name(km)[:3],
				"full_label": f"{get_bs_month_name(km)} {ky}",
				"value": value,
				"bills": bills,
				"before": before_months.get((kpy, kpm), (0.0, 0))[0],
				"future": month_start > date_today,
			}
		)
	return {"unit": "month", "buckets": buckets}


def _top_parties(cfg, scope, window):
	doctype = cfg["invoice"]
	party = cfg["party_field"]
	rows = frappe.get_list(
		doctype,
		filters=_base_filters(doctype, scope) + [_between(doctype, window["start"], window["end"])],
		fields=[party + " as party", f"max({cfg['party_name_field']}) as party_name", "sum(base_net_total) as net", "count(name) as bills"],
		group_by=party,
		order_by="net desc",
		limit_page_length=TOP_N,
	)
	return [
		{"party": r.party, "label": r.party_name or r.party, "value": flt(r.net), "bills": r.bills}
		for r in rows
		if flt(r.net) > 0
	]


def _top_items(cfg, scope, window):
	"""Best items by amount, grouped by item name and stock UOM.

	Each company keeps its own item codes for the same product (LP Gas is
	GEPL-ITEM-00066 in one company and another code in the next), so grouping
	by code lists "LP Gas" once per company. The name + UOM pair adds them up.
	"""
	doctype, child = cfg["invoice"], cfg["item_table"]
	col = lambda f: f"`tab{child}`.{f}"  # noqa: E731 — a child-table column for get_list
	rows = frappe.get_list(
		doctype,
		filters=_base_filters(doctype, scope) + [_between(doctype, window["start"], window["end"])],
		fields=[
			col("item_name"),
			col("stock_uom"),
			f"count(distinct {col('item_code')}) as codes",
			f"sum({col('stock_qty')}) as qty",
			f"sum({col('base_net_amount')}) as amount",
		],
		group_by=f"{col('item_name')}, {col('stock_uom')}",
		order_by="amount desc",
		limit_page_length=TOP_N,
	)
	return [
		{"label": r.item_name, "uom": r.stock_uom, "qty": flt(r.qty), "value": flt(r.amount)}
		for r in rows
		if flt(r.amount) > 0
	]


def _by_branch(cfg, scope, window):
	"""Net amount per branch; None when splitting by branch tells nothing."""
	doctype = cfg["invoice"]
	if scope["branch"] or not _has_branch(doctype):
		return None
	rows = frappe.get_list(
		doctype,
		filters=_base_filters(doctype, scope) + [_between(doctype, window["start"], window["end"])],
		fields=["custom_branch as branch", "sum(base_net_total) as net"],
		group_by="custom_branch",
		order_by="net desc",
	)
	labels = scope["branch_labels"]
	parts = []
	for r in rows:
		if not flt(r.net):
			continue
		info = labels.get(r.branch)
		if r.branch and info:
			label = info["label"] if len(scope["companies"]) == 1 else f"{info['label']} · {info['abbr']}"
		else:
			label = _("No branch")
		parts.append({"branch": r.branch or NO_BRANCH, "label": label, "value": flt(r.net)})
	return parts if len(parts) > 1 else None


def _by_company(cfg, scope, window):
	doctype = cfg["invoice"]
	if len(scope["companies"]) < 2:
		return None
	rows = frappe.get_list(
		doctype,
		filters=_base_filters(doctype, scope) + [_between(doctype, window["start"], window["end"])],
		fields=["company", "sum(base_net_total) as net", "count(name) as bills"],
		group_by="company",
		order_by="net desc",
	)
	parts = [
		{"company": r.company, "label": scope["abbr"].get(r.company, r.company), "title": r.company, "value": flt(r.net), "bills": r.bills}
		for r in rows
		if flt(r.net)
	]
	return parts if len(parts) > 1 else None


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

def _payments(cfg, scope, window):
	"""Money received from customers (or paid to suppliers) through Payment Entry.

	Journal Entry receipts are not counted; the card says "via Payment Entry".
	"""
	if not frappe.has_permission("Payment Entry", "read"):
		return None

	def total(start, end):
		row = frappe.get_list(
			"Payment Entry",
			filters=_base_filters("Payment Entry", scope)
			+ [
				["Payment Entry", "payment_type", "=", cfg["payment_type"]],
				["Payment Entry", "party_type", "=", cfg["party_doctype"]],
				_between("Payment Entry", start, end),
			],
			fields=[f"sum({cfg['payment_amount']}) as amount", "count(name) as entries"],
			order_by=None,
		)
		return {"amount": flt(row[0].amount) if row else 0.0, "entries": row[0].entries if row else 0}

	return {"now": total(window["start"], window["end"]), "before": total(window["prev_start"], window["compare_end"])}


# ---------------------------------------------------------------------------
# Pipeline: documents waiting for the next step
# ---------------------------------------------------------------------------

# (doctype, label, extra filters, docstatus, amount field or None, in period only)
# Open documents are counted whatever their date — an order from last month
# that is still not billed is still work. Draft invoices are the exception:
# they are counted in the chosen period only, because a draft count over all of
# tabSales Invoice is a full scan of 290k rows (~17s on mysite1).
PIPELINE = {
	"selling": [
		("Quotation", "Open quotations", [["status", "=", "Open"]], 1, "base_net_total", False),
		("Sales Order", "Orders to deliver", [["status", "in", ["To Deliver and Bill", "To Deliver"]]], 1, "base_net_total", False),
		("Sales Order", "Orders to bill", [["status", "in", ["To Deliver and Bill", "To Bill"]]], 1, "base_net_total", False),
		("Delivery Note", "Deliveries to bill", [["status", "=", "To Bill"]], 1, "base_net_total", False),
		("Sales Invoice", "Draft invoices", [], 0, "base_net_total", True),
	],
	"buying": [
		("Material Request", "Material requests", [["material_request_type", "=", "Purchase"], ["status", "in", ["Pending", "Partially Ordered"]]], 1, None, False),
		("Purchase Order", "Orders to receive", [["status", "in", ["To Receive and Bill", "To Receive"]]], 1, "base_net_total", False),
		("Purchase Order", "Orders to bill", [["status", "in", ["To Receive and Bill", "To Bill"]]], 1, "base_net_total", False),
		("Purchase Receipt", "Receipts to bill", [["status", "=", "To Bill"]], 1, "base_net_total", False),
		("Purchase Invoice", "Draft invoices", [], 0, "base_net_total", True),
	],
}


def _pipeline(mode, scope, window):
	out = []
	for doctype, label, extra, docstatus, amount_field, in_period in PIPELINE[mode]:
		if not frappe.has_permission(doctype, "read"):
			continue
		filters = _base_filters(doctype, scope, docstatus=docstatus) + [[doctype] + f for f in extra]
		if in_period:
			filters.append(_between(doctype, window["start"], window["end"]))
		fields = ["count(name) as n"] + ([f"sum({amount_field}) as amount"] if amount_field else [])
		row = frappe.get_list(doctype, filters=filters, fields=fields, order_by=None)[0]
		# Route options for the list view: the same filters, as the list expects them.
		route = {f[1]: [f[2], f[3]] for f in filters if f[1] != "docstatus"}
		route["docstatus"] = docstatus
		out.append(
			{
				"doctype": doctype,
				"label": _(label),
				"count": row.n or 0,
				"amount": flt(row.get("amount")) if amount_field else None,
				"route": route,
				"in_period": in_period,
				# Purchase Order / Material Request have no branch field.
				"all_branches": bool(scope["branch"]) and not _has_branch(doctype),
			}
		)
	return out


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

# (label, icon, [(type, name, label)]) — type is doctype, report or new.
MENU = {
	"selling": [
		("Transactions", "cart", [
			("new", "Sales Invoice", "New Sales Invoice"),
			("doctype", "Sales Invoice", "Sales Invoices"),
			("doctype", "Sales Order", "Sales Orders"),
			("doctype", "Quotation", "Quotations"),
			("doctype", "Delivery Note", "Delivery Notes"),
			("doctype", "Payment Entry", "Payment Entries"),
		]),
		("Sales reports", "chart", [
			("report", "Sales Register Report", "Sales Register"),
			("report", "Sales Report Summary", "Sales Report Summary"),
			("report", "Sales Analysis Customer wise Summary", "Customer-wise Summary"),
			("report", "Sales Analysis Customer wise Details", "Customer-wise Details"),
			("report", "Sales Analysis Product wise Invoice Details", "Product-wise Details"),
			("report", "Sales Bill Details", "Sales Bill Details"),
			("report", "Sales Stock Ledger", "Sales Stock Ledger"),
			("report", "Gas Dispatch (Quota)", "Gas Dispatch (Quota)"),
			("report", "Invoice Activity Report", "Invoice Activity"),
		]),
		("Orders", "box", [
			("report", "NG Sales Order Analysis", "Sales Order Analysis"),
			("report", "Sales Order Billing Capacity", "Order Billing Capacity"),
		]),
		("Receivables", "wallet", [
			("report", "Debtors Summary", "Debtors Summary"),
			("report", "Party Ledger", "Party Ledger"),
			("report", "Party Ledger Summary", "Party Ledger Summary"),
			("report", "Receipt Register", "Receipt Register"),
			("report", "Accounts Receivable", "Accounts Receivable"),
			("report", "PDC Register", "PDC Register"),
			("report", "PDC Maturity", "PDC Maturity"),
		]),
		("Masters", "gear", [
			("doctype", "Customer", "Customers"),
			("doctype", "Customer Group", "Customer Groups"),
			("doctype", "Item", "Items"),
			("doctype", "Item Price", "Item Prices"),
			("doctype", "Price List", "Price Lists"),
			("doctype", "Branch", "Branches"),
		]),
	],
	"buying": [
		("Transactions", "cart", [
			("new", "Purchase Invoice", "New Purchase Invoice"),
			("doctype", "Purchase Invoice", "Purchase Invoices"),
			("doctype", "Purchase Order", "Purchase Orders"),
			("doctype", "Purchase Receipt", "Purchase Receipts"),
			("doctype", "Material Request", "Material Requests"),
			("doctype", "Supplier Quotation", "Supplier Quotations"),
			("doctype", "Payment Entry", "Payment Entries"),
		]),
		("Purchase reports", "chart", [
			("report", "Purchase Register Report", "Purchase Register"),
			("report", "Gas Purchase Report", "Gas Purchase"),
			("report", "Custom Supplier Quotation Comparison", "Supplier Quotation Comparison"),
			("report", "Avinas Vehicle Expense", "Vehicle Expense"),
		]),
		("Payables & tax", "wallet", [
			("report", "Party Ledger", "Party Ledger"),
			("report", "Party Ledger Summary", "Party Ledger Summary"),
			("report", "Accounts Payable", "Accounts Payable"),
			("report", "TDS Party Ledger Summary", "TDS Party Ledger Summary"),
			("report", "Advance Tax TDS Details", "Advance Tax TDS Details"),
		]),
		("LC", "bank", [
			("doctype", "Letter of Credit", "Letters of Credit"),
			("report", "LC Register", "LC Register"),
			("report", "LC Maturity", "LC Maturity"),
			("report", "LC Cost Sheet", "LC Cost Sheet"),
			("report", "LC Margin and Charges", "LC Margin & Charges"),
		]),
		("Masters", "gear", [
			("doctype", "Supplier", "Suppliers"),
			("doctype", "Supplier Group", "Supplier Groups"),
			("doctype", "Item", "Items"),
			("doctype", "Item Price", "Item Prices"),
			("doctype", "Transporter", "Transporters"),
		]),
	],
}


# Menu groups kept in MENU but not shown, to keep the dashboard simple
# (2026-11-04). To bring one back, take its label out of this set.
HIDDEN_MENU_GROUPS = {"Transactions", "Masters"}

# The menu shows reports only, for now: document lists ("doctype") and
# new-document links ("new") inside the remaining groups — e.g. "Letters of
# Credit" in LC — are left out. Set True to show them again.
SHOW_DOCUMENT_LINKS = False


@frappe.whitelist()
def get_menu(mode):
	"""The menu for one dashboard, minus hidden groups and anything the user cannot open or that is not installed."""
	_mode(mode)
	groups = []
	for label, icon, items in MENU[mode]:
		if label in HIDDEN_MENU_GROUPS:
			continue
		visible = []
		for kind, name, item_label in items:
			if kind != "report" and not SHOW_DOCUMENT_LINKS:
				continue
			if kind == "report":
				if not frappe.db.exists("Report", name):
					continue
				report = frappe.get_cached_doc("Report", name)
				if report.disabled or not report.is_permitted():
					continue
			else:
				if not frappe.db.exists("DocType", name):
					continue
				if not frappe.has_permission(name, "create" if kind == "new" else "read"):
					continue
			visible.append({"type": kind, "name": name, "label": _(item_label)})
		if visible:
			groups.append({"label": _(label), "icon": icon, "items": visible})
	return groups
