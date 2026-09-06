"""Sales Order Analysis — customer portal.

A customer-facing cut of ERPNext's `Sales Order Analysis` query report
(erpnext/selling/report/sales_order_analysis). Same figures, but only the
columns the customer is meant to see, and hard-scoped to the Sales Orders of
the companies/customers the logged-in portal user is actually linked to.

Filters, and how they relate:
  Company        multi-select, required — the user's own companies
  Period         either a Fiscal Year (default: the current one) or an explicit
                 date range (default: this month). Only one is live at a time;
                 a fiscal year is resolved to its AD dates server-side.
  Customer       multi-select, scoped to the chosen companies
  Sales Order    multi-select, scoped to the chosen companies/customers/period
  Status         multi-select, a fixed Sales Order status list — not company-wise
"""

import json
import os

import frappe
from frappe import _
from frappe.utils import flt, formatdate, get_first_day, get_last_day, getdate, nowdate

# The Status column and filter report the Sales Order's *billing* status, not
# its workflow status — this is a billing-oriented report, so "Partly Billed"
# says more to the customer than "To Deliver and Bill".
# Options are Sales Order.billing_status verbatim.
SO_STATUSES = ["Not Billed", "Partly Billed", "Fully Billed", "Closed"]

# A customer with years of orders would otherwise render thousands of checkboxes.
MAX_SALES_ORDER_OPTIONS = 300

# Rendered HTML for a website page is cached by path and language only
# (frappe/website/utils.py: cache_html) — not by user. This page is built from
# frappe.session.user, so caching it would serve one customer their neighbour's
# page. Frappe skips the cache when developer_mode is on, which is why this
# never shows up locally.
no_cache = 1


# ── Miti ────────────────────────────────────────────────────────────────────
def _miti(custom_miti, date):
	"""The Miti shown in the first column.

	`Sales Order.custom_miti` is the field of record — a Data field already
	holding the BS date as a string, so it is printed exactly as entered.

	It is not populated on every order (orders created before the field existed,
	or through a path that does not set it, carry NULL), so an order with no
	stored miti falls back to converting its AD transaction_date — the same
	conversion the rest of the portal uses. Without the fallback those rows show
	a blank Miti column.
	"""
	if custom_miti:
		return str(custom_miti).strip()
	if not date:
		return ""
	try:
		from avinashgroup_app.custom_code.CBMS.utils import bs_date_str

		return bs_date_str(date) or ""
	except Exception:
		return ""


# ── Number formatting ───────────────────────────────────────────────────────
def _fmt_amount(v):
	"""Indian-style grouping with 2 decimals, zeros shown (not blanked)."""
	n = flt(v)
	neg = n < 0
	s = f"{abs(n):.2f}"
	int_part, dec = s.split(".")
	if len(int_part) > 3:
		out = int_part[-3:]
		int_part = int_part[:-3]
		while int_part:
			out = int_part[-2:] + "," + out
			int_part = int_part[:-2]
		int_part = out
	return ("-" if neg else "") + f"{int_part}.{dec}"


def _fmt_qty(v):
	"""Quantities read as whole numbers unless they genuinely are not."""
	n = flt(v)
	if n == int(n):
		return str(int(n))
	return f"{n:.3f}".rstrip("0").rstrip(".")


# ── Portal scoping ──────────────────────────────────────────────────────────
def _get_portal_customers():
	"""Customers linked to the logged-in user via the Portal User child table."""
	rows = frappe.db.sql(
		"""
		SELECT parent FROM `tabPortal User`
		WHERE user = %s AND parenttype = 'Customer'
		  AND parent IS NOT NULL AND parent != ''
		""",
		frappe.session.user,
		as_list=True,
	)
	return [r[0] for r in rows]


def _get_allowed_companies(portal_customers):
	"""Distinct companies (custom_company) for the given customers."""
	if not portal_customers:
		return []
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT custom_company AS name
		FROM `tabCustomer`
		WHERE disabled = 0
		  AND name IN %(customers)s
		  AND custom_company IS NOT NULL AND custom_company != ''
		ORDER BY custom_company
		""",
		{"customers": portal_customers},
		as_dict=True,
	)
	return [r.name for r in rows]


def _my_customers_in_companies(portal_customers, companies):
	"""The user's customers belonging to any of the given companies."""
	if not (portal_customers and companies):
		return []
	rows = frappe.get_all(
		"Customer",
		filters={"name": ("in", portal_customers), "custom_company": ("in", companies)},
		fields=["name"],
	)
	return [r.name for r in rows]


def _to_list(value):
	"""Normalise a MultiSelectList-ish value (JSON string / list / scalar)."""
	if not value:
		return []
	if isinstance(value, str):
		value = value.strip()
		if value.startswith("[") and value.endswith("]"):
			try:
				return [v for v in json.loads(value) if v]
			except Exception:
				pass
		return [value] if value else []
	if isinstance(value, (list, tuple, set)):
		return [v for v in value if v]
	return [value]


def _resolve_request(companies, customers):
	"""Role check + ownership re-validation shared by every whitelisted entry point.

	Returns (companies, customers, is_portal_user). For a portal user both lists
	are forced back to their own; an empty customer list is never allowed to mean
	"every customer in the company", which would leak the neighbours' orders.
	"""
	if "Customer" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only customers can access this page."), frappe.PermissionError)

	companies = _to_list(companies)
	customers = _to_list(customers)
	portal_customers = _get_portal_customers()

	if not companies:
		frappe.throw(_("Please select at least one Company."))

	if portal_customers:
		allowed = _get_allowed_companies(portal_customers)
		if any(c not in allowed for c in companies):
			frappe.throw(_("You are not allowed to view this company."), frappe.PermissionError)
		if any(c not in portal_customers for c in customers):
			frappe.throw(_("You are not allowed to view one of these customers."), frappe.PermissionError)
		if not customers:
			customers = _my_customers_in_companies(portal_customers, companies)

	return companies, customers, bool(portal_customers)


# ── Period ──────────────────────────────────────────────────────────────────
def _current_fiscal_year():
	from erpnext.accounts.utils import get_fiscal_year

	try:
		fy = get_fiscal_year(nowdate(), as_dict=True)
		return fy.name if fy else ""
	except Exception:
		return ""


def _fiscal_year_of(date):
	"""FY label a date falls in — used to fill the header in date-wise mode."""
	from erpnext.accounts.utils import get_fiscal_year

	try:
		fy = get_fiscal_year(date, as_dict=True)
		return fy.name if fy else ""
	except Exception:
		return ""


def _fiscal_year_list():
	rows = frappe.get_all(
		"Fiscal Year",
		filters={"disabled": 0},
		fields=["name"],
		order_by="year_start_date desc",
		ignore_permissions=True,
	)
	return [r.name for r in rows]


def _resolve_period(period_type, fiscal_year, from_date, to_date):
	"""Turn whichever period input is live into (from_date, to_date, fy_label).

	The query only ever runs on a date range — a chosen fiscal year is resolved
	to its AD start/end on the server, from the Fiscal Year record, never in the
	browser.
	"""
	if (period_type or "fiscal_year") == "fiscal_year":
		if not fiscal_year:
			frappe.throw(_("Please select a Fiscal Year."))
		from avinashgroup_app.custom_code.CBMS.utils import get_fiscal_year_dates

		dates = get_fiscal_year_dates(fiscal_year)
		if not dates:
			frappe.throw(_("Fiscal Year {0} does not exist.").format(fiscal_year))
		return dates["from_date"], dates["to_date"], fiscal_year

	if not (from_date and to_date):
		frappe.throw(_("From Date and To Date are required."))
	if getdate(to_date) < getdate(from_date):
		frappe.throw(_("To Date cannot be before From Date."))
	return str(from_date), str(to_date), _fiscal_year_of(to_date)


# ── Page ────────────────────────────────────────────────────────────────────
def get_context(context):
	context.no_cache = 1
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	if "Customer" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only customers can access this page."), frappe.PermissionError)

	portal_customers = _get_portal_customers()

	if portal_customers:
		context.customer_list = frappe.db.sql(
			"""
			SELECT name, customer_name, IFNULL(custom_company, '') AS company
			FROM `tabCustomer`
			WHERE disabled = 0 AND name IN %(customers)s
			ORDER BY customer_name
			""",
			{"customers": portal_customers},
			as_dict=True,
		)
		context.company_list = _get_allowed_companies(portal_customers)
	else:
		# Non-portal user (e.g. staff holding the Customer role) — no restriction.
		context.customer_list = []
		context.company_list = [
			r.name for r in frappe.get_all("Company", fields=["name"], ignore_permissions=True)
		]

	# Company is multi-select: default to the user's default company when it is
	# one of theirs, otherwise every company they can see.
	user_default = frappe.defaults.get_user_default("Company")
	if user_default in context.company_list:
		context.default_companies = [user_default]
	else:
		context.default_companies = list(context.company_list)

	context.status_list = SO_STATUSES
	context.fiscal_year_list = _fiscal_year_list()
	context.default_fiscal_year = _current_fiscal_year() or (
		context.fiscal_year_list[0] if context.fiscal_year_list else ""
	)
	# Date-wise mode opens on the current month.
	context.from_date = str(get_first_day(nowdate()))
	context.to_date = str(get_last_day(nowdate()))
	context.today = nowdate()


# ── Filter option feeds ─────────────────────────────────────────────────────
@frappe.whitelist()
def search_sales_orders(companies=None, customers=None, period_type=None, fiscal_year=None,
                        from_date=None, to_date=None, txt=None):
	"""Sales Order options for the filter — scoped to the rest of the filters.

	Company-wise by construction: an order can only be offered if it belongs to a
	company (and, for a portal user, a customer) the caller is entitled to see.
	"""
	companies, customers, is_portal = _resolve_request(companies, customers)
	if is_portal and not customers:
		return []

	from_date, to_date, _fy = _resolve_period(period_type, fiscal_year, from_date, to_date)

	values = {
		"companies": tuple(companies),
		"from_date": from_date,
		"to_date": to_date,
		"txt": f"%{txt}%" if txt else "%",
		"limit": MAX_SALES_ORDER_OPTIONS,
	}
	customer_condition = ""
	if customers:
		customer_condition = "AND so.customer IN %(customers)s"
		values["customers"] = tuple(customers)

	return frappe.db.sql(
		f"""
		SELECT so.name, so.customer, so.company
		FROM `tabSales Order` so
		WHERE so.docstatus = 1
		  AND so.status NOT IN ('Stopped', 'On Hold')
		  AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s
		  AND so.company IN %(companies)s
		  {customer_condition}
		  AND so.name LIKE %(txt)s
		ORDER BY so.transaction_date DESC, so.name DESC
		LIMIT %(limit)s
		""",
		values,
		as_dict=True,
	)


# ── Data ────────────────────────────────────────────────────────────────────
def _get_rows(companies, customers, sales_orders, statuses, from_date, to_date):
	"""One row per Sales Order Item.

	The query lives in the desk report (NG Sales Order Analysis) and is imported
	rather than repeated, so the portal and the desk can never report different
	figures for the same orders. Everything that scopes this page to the logged-in
	customer stays here — the shared query reads no session state of its own.
	"""
	from avinashgroup_app.avinash_group_app.report.ng_sales_order_analysis.ng_sales_order_analysis import (
		get_rows,
	)

	return get_rows(companies, customers, sales_orders, statuses, from_date, to_date)


def _build(companies, customers, sales_orders, statuses, from_date, to_date, fy_label):
	"""Shape the rows + totals both the screen table and the PDF render from."""
	raw = _get_rows(companies, customers, sales_orders, statuses, from_date, to_date)

	totals = {
		"qty": 0.0, "billed_qty": 0.0, "qty_to_bill": 0.0,
		"amount": 0.0, "billed_amount": 0.0, "pending_amount": 0.0,
	}
	rows = []
	for d in raw:
		qty_to_bill = flt(d.qty) - flt(d.billed_qty)
		totals["qty"] += flt(d.qty)
		totals["billed_qty"] += flt(d.billed_qty)
		totals["qty_to_bill"] += qty_to_bill
		totals["amount"] += flt(d.amount)
		totals["billed_amount"] += flt(d.billed_amount)
		totals["pending_amount"] += flt(d.pending_amount)

		rows.append({
			"miti": _miti(d.custom_miti, d.date),
			"date": formatdate(d.date) if d.date else "",
			"sales_order": d.sales_order or "",
			"status": d.status or "",
			"item_name": d.item_name or d.item_code or "",
			"qty": _fmt_qty(d.qty),
			"billed_qty": _fmt_qty(d.billed_qty),
			"qty_to_bill": _fmt_qty(qty_to_bill),
			"amount": _fmt_amount(d.amount),
			"billed_amount": _fmt_amount(d.billed_amount),
			"pending_amount": _fmt_amount(d.pending_amount),
			"delay": str(int(flt(d.delay))),
		})

	return {
		"companies": companies,
		"company_label": ", ".join(companies),
		"customer_names": _customer_names(customers),
		"customer_label": ", ".join(_customer_names(customers)),
		"fiscal_year": fy_label or "",
		"from_date": from_date,
		"to_date": to_date,
		"from_date_disp": formatdate(from_date),
		"to_date_disp": formatdate(to_date),
		"rows": rows,
		"totals": {
			"qty": _fmt_qty(totals["qty"]),
			"billed_qty": _fmt_qty(totals["billed_qty"]),
			"qty_to_bill": _fmt_qty(totals["qty_to_bill"]),
			"amount": _fmt_amount(totals["amount"]),
			"billed_amount": _fmt_amount(totals["billed_amount"]),
			"pending_amount": _fmt_amount(totals["pending_amount"]),
		},
		# Same split the standard report's donut shows.
		"chart": {
			"pending": flt(totals["pending_amount"]),
			"billed": flt(totals["billed_amount"]),
			"pending_disp": _fmt_amount(totals["pending_amount"]),
			"billed_disp": _fmt_amount(totals["billed_amount"]),
		},
	}


def _customer_names(customers):
	"""Display names for the chosen customers, in the given order."""
	if not customers:
		return []
	rows = frappe.get_all("Customer", filters={"name": ("in", customers)}, fields=["name", "customer_name"])
	name_map = {r.name: r.customer_name for r in rows}
	return [name_map.get(c, c) for c in customers]


def _empty(companies, customers, from_date, to_date, fy_label):
	zero_qty, zero_amt = _fmt_qty(0), _fmt_amount(0)
	return {
		"companies": companies,
		"company_label": ", ".join(companies),
		"customer_names": _customer_names(customers),
		"customer_label": ", ".join(_customer_names(customers)),
		"fiscal_year": fy_label or "",
		"from_date": from_date,
		"to_date": to_date,
		"from_date_disp": formatdate(from_date),
		"to_date_disp": formatdate(to_date),
		"rows": [],
		"totals": {
			"qty": zero_qty, "billed_qty": zero_qty, "qty_to_bill": zero_qty,
			"amount": zero_amt, "billed_amount": zero_amt, "pending_amount": zero_amt,
		},
		"chart": {"pending": 0.0, "billed": 0.0, "pending_disp": zero_amt, "billed_disp": zero_amt},
	}


def _prepare(companies, customers, sales_orders, statuses, period_type, fiscal_year,
             from_date, to_date):
	"""Validate + scope the request, then build the result. Shared by both endpoints."""
	companies, customers, is_portal = _resolve_request(companies, customers)
	from_date, to_date, fy_label = _resolve_period(period_type, fiscal_year, from_date, to_date)

	if is_portal and not customers:
		return _empty(companies, customers, from_date, to_date, fy_label)

	return _build(
		companies, customers, _to_list(sales_orders), _to_list(statuses),
		from_date, to_date, fy_label,
	)


@frappe.whitelist()
def get_report(companies=None, customers=None, sales_orders=None, statuses=None,
               period_type=None, fiscal_year=None, from_date=None, to_date=None):
	"""The table the page renders."""
	return _prepare(companies, customers, sales_orders, statuses, period_type,
	                fiscal_year, from_date, to_date)


@frappe.whitelist()
def download_pdf(companies=None, customers=None, sales_orders=None, statuses=None,
                 period_type=None, fiscal_year=None, from_date=None, to_date=None, view=None):
	"""The same report as a Landscape A4 PDF.

	Security is re-validated here exactly as in get_report — the browser cannot
	ask for a company or customer that is not the logged-in user's, whatever it
	puts in the query string.
	"""
	from frappe.utils.pdf import get_pdf

	res = _prepare(companies, customers, sales_orders, statuses, period_type,
	               fiscal_year, from_date, to_date)

	template_path = os.path.join(os.path.dirname(__file__), "sales_order_analysis_pdf.html")
	with open(template_path) as f:
		template_content = f.read()

	html = frappe.render_template(template_content, {"res": res})

	pdf_data = get_pdf(html, {
		"page-size": "A4",
		"orientation": "Landscape",
		"margin-top": "10mm",
		"margin-right": "10mm",
		"margin-bottom": "12mm",
		"margin-left": "10mm",
		"encoding": "UTF-8",
		"enable-local-file-access": None,
	})

	frappe.response.filename = "sales_order_analysis.pdf"
	frappe.response.filecontent = pdf_data
	# view=1 (Print) → open inline in the browser tab; otherwise download the file.
	frappe.response.type = "pdf" if frappe.utils.cint(view) else "download"
