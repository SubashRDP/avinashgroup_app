import json

import frappe
from frappe import _
from frappe.utils import get_first_day, nowdate, formatdate

from avinashgroup_app.avinash_group_app.report.party_ledger.party_ledger import (
	execute as party_ledger_execute,
	download_pdf as party_ledger_download_pdf,
	_fmt_inr,
	_bal_str,
)

# Deposit / security accounts that must never appear on a customer-facing statement.
# Matched against Account.account_name (LIKE patterns) so every company's variant is
# excluded regardless of its number/abbr suffix.
EXCLUDE_ACCOUNT_PATTERNS = [
	"Deposit Customers Cylinders%",      # 313101 Deposit Customers Cylinders (I)
	"Record of Deposit Cylinders%",      # 313102 Record of Deposit Cylinders (1013)
	"%Security Deposit%Dealer%",         # 313201 Security Deposit from Dealers (live server)
]


def _get_portal_customers():
	"""Customers linked to the logged-in user via the Portal User child table"""
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


# Rendered HTML for a website page is cached by path and language only
# (frappe/website/utils.py: cache_html) — not by user. This page is built from
# frappe.session.user, so caching it would serve one customer their neighbour's
# page. Frappe skips the cache when developer_mode is on, which is why this never
# shows up locally.
no_cache = 1


def get_context(context):
	context.no_cache = 1
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	if "Customer" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only customers can access this page."), frappe.PermissionError)

	# NO sidebar here, deliberately. This page asks for the full window on
	# purpose -- see the `.container { max-width: 100% !important; padding: 0
	# 80px }` override in the template. Behind a col-sm-2 sidebar the filter row
	# loses about a sixth of its width and the col-sm-3 fields go narrower than
	# their own contents: the company reads "Nepal Gas Udhyc" and the customer
	# "Seed Fourth H...", with the labels wider than the inputs beneath them.
	portal_customers = _get_portal_customers()

	# Customer dropdown — only this user's linked customers, with their company tag
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
		# Non-portal user (e.g. staff with Customer role) — free-text search fallback
		context.customer_list = []
		context.company_list = [r.name for r in frappe.get_all("Company", fields=["name"], ignore_permissions=True)]

	# Single-select company defaults to the user's default company if it's one of theirs, else the first.
	user_default = frappe.defaults.get_user_default("Company")
	if user_default in context.company_list:
		context.default_company = user_default
	else:
		context.default_company = context.company_list[0] if context.company_list else ""

	context.today = nowdate()
	context.from_date = str(get_first_day(nowdate()))
	context.to_date = nowdate()


@frappe.whitelist()
def search_companies(txt=None):
	"""Company options restricted to the logged-in user's linked companies."""
	portal_customers = _get_portal_customers()
	if portal_customers:
		companies = _get_allowed_companies(portal_customers)
		if txt:
			companies = [c for c in companies if txt.lower() in (c or "").lower()]
		return [{"name": c} for c in companies]

	# Non-portal user — show all companies
	filters = {}
	if txt:
		filters["company_name"] = ["like", f"%{txt}%"]
	return frappe.get_list(
		"Company", filters=filters, fields=["name"], limit=10, ignore_permissions=True
	)


@frappe.whitelist()
def search_customers(txt=None, company=None):
	"""Customer options restricted to the logged-in user's linked customers."""
	portal_customers = _get_portal_customers()

	if portal_customers:
		values = {"customers": tuple(portal_customers), "txt": f"%{txt}%" if txt else "%"}
		company_condition = ""
		if company:
			company_condition = "AND custom_company = %(company)s"
			values["company"] = company
		return frappe.db.sql(
			f"""
			SELECT name, customer_name FROM `tabCustomer`
			WHERE disabled = 0
			  AND name IN %(customers)s
			  {company_condition}
			  AND (name LIKE %(txt)s OR customer_name LIKE %(txt)s)
			ORDER BY customer_name
			""",
			values,
			as_dict=True,
		)

	# Non-portal user — search all customers (optionally by company)
	values = {"txt": f"%{txt}%" if txt else "%"}
	company_condition = ""
	if company:
		company_condition = "AND custom_company = %(company)s"
		values["company"] = company
	return frappe.db.sql(
		f"""
		SELECT name, customer_name FROM `tabCustomer`
		WHERE disabled = 0
		  {company_condition}
		  AND (name LIKE %(txt)s OR customer_name LIKE %(txt)s)
		ORDER BY customer_name
		LIMIT 10
		""",
		values,
		as_dict=True,
	)


def _to_list(value):
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


def _format_row(d):
	"""Shape one Party Ledger data row for the portal table (simple format)."""
	raw_date = d.get("date")
	return {
		"sr_no": d.get("sr_no") or "",
		"date": formatdate(raw_date) if raw_date else "",
		"miti": d.get("miti") or "",
		"voucher_no": d.get("voucher_no") or "",
		"description": d.get("description") or "",
		"debit": _fmt_inr(d.get("debit")),
		"credit": _fmt_inr(d.get("credit")),
		"balance": str(_bal_str(d.get("balance"))),
		"is_summary": 1 if d.get("is_summary") else 0,
		"is_section": 1 if d.get("is_section") else 0,
		# Customer-wise grouping: header row (code + name/VAT) and total-row kind.
		"is_customer_header": 1 if d.get("is_customer_header") else 0,
		"cust_code": d.get("cust_code") or "",
		"cust_label": d.get("cust_label") or "",
		"kind": d.get("kind") or "",
		"bold": 1 if d.get("bold") else 0,
	}


def _my_customers_in_company(portal_customers, company):
	"""The logged-in user's customers that belong to the given company."""
	if not portal_customers:
		return []
	rows = frappe.get_all(
		"Customer",
		filters={"name": ("in", portal_customers), "custom_company": company},
		fields=["name"],
	)
	return [r.name for r in rows]


def _resolve_request(company, customers):
	"""Role check + ownership re-validation shared by get_statement and download_pdf.

	Returns (customers, is_portal_user). For a portal user the list is forced to their
	own customers and never falls back to "all parties" (empty party = ALL parties in
	the company, which would leak other customers' data). Raises on any violation.
	"""
	if "Customer" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only customers can access this page."), frappe.PermissionError)

	customers = _to_list(customers)
	portal_customers = _get_portal_customers()

	if portal_customers:
		# Hard restriction — company and every customer must be the user's own.
		if company not in _get_allowed_companies(portal_customers):
			frappe.throw(_("You are not allowed to view this company."), frappe.PermissionError)
		if any(c not in portal_customers for c in customers):
			frappe.throw(_("You are not allowed to view one of these customers."), frappe.PermissionError)
		if not customers:
			customers = _my_customers_in_company(portal_customers, company)

	return customers, bool(portal_customers)


@frappe.whitelist()
def get_statement(company=None, customers=None, from_date=None, to_date=None):
	"""Return one Party Ledger statement (simple format) for a single company.
	"""
	if not (company and from_date and to_date):
		frappe.throw(_("Company, From Date and To Date are required."))

	customers, is_portal = _resolve_request(company, customers)
	if is_portal and not customers:
		return _empty_result(company, from_date, to_date)

	filters = frappe._dict({
		"company": company,
		"party_type": "Customer",
		"party": customers,
		"from_date": from_date,
		"to_date": to_date,
		"detailed_mapping": 0,
		"show_remarks": 0,
		"exclude_account_patterns": EXCLUDE_ACCOUNT_PATTERNS,
	})
	_columns, data = party_ledger_execute(filters)

	# When exactly one customer is selected, show its Tax ID (PAN/VAT) under the name,
	# mirroring the PDF/print header.
	party_tax_id = None
	if len(customers) == 1:
		party_tax_id = frappe.db.get_value("Customer", customers[0], "tax_id")

	return {
		"company": company,
		"multi_customer": len(customers) != 1,
		"customer_names": _customer_names(customers),
		"party_tax_id": party_tax_id,
		"rows": [_format_row(d) for d in data],
		"from_date": from_date,
		"to_date": to_date,
		"from_date_disp": formatdate(from_date),
		"to_date_disp": formatdate(to_date),
	}


def _customer_names(customers):
	"""Display names for the chosen customers, in the given order."""
	if not customers:
		return []
	rows = frappe.get_all("Customer", filters={"name": ("in", customers)}, fields=["name", "customer_name"])
	name_map = {r.name: r.customer_name for r in rows}
	return [name_map.get(c, c) for c in customers]


def _empty_result(company, from_date, to_date):
	return {
		"company": company,
		"multi_customer": False,
		"customer_names": [],
		"party_tax_id": None,
		"rows": [],
		"from_date": from_date,
		"to_date": to_date,
		"from_date_disp": formatdate(from_date),
		"to_date_disp": formatdate(to_date),
	}


@frappe.whitelist()
def download_pdf(company=None, customers=None, from_date=None, to_date=None):
	"""Download the report part as a Portrait PDF (with page numbers).

	Reuses Party Ledger's PDF generator — same look, same in-body page numbering
	(manual pagination, so it works on plain/unpatched wkhtmltopdf).
	Security is re-validated server-side, exactly like get_statement: the browser
	cannot request a company/customer that isn't the logged-in user's.
	"""
	if not (company and from_date and to_date):
		frappe.throw(_("Company, From Date and To Date are required."))

	customers, is_portal = _resolve_request(company, customers)
	if is_portal and not customers:
		frappe.throw(_("No statement to download for the selected filters."))

	filters = frappe._dict({
		"company": company,
		"party_type": "Customer",
		"party": customers,
		"from_date": from_date,
		"to_date": to_date,
		"detailed_mapping": 0,
		"show_remarks": 0,
		"exclude_account_patterns": EXCLUDE_ACCOUNT_PATTERNS,
	})

	# Always Portrait for a customer-facing statement; page numbers are rendered in the
	# PDF body by the report's manual pagination (no patched-wkhtmltopdf footer needed).
	party_ledger_download_pdf(
		filters,
		orientation="Portrait",
		report_title="Customer Statement",
		filename="customer_statement.pdf",
		# Pack a few more rows per page than the Party Ledger report's default (64),
		# for the customer statement PDF only.
		capacity_override=76,
	)
