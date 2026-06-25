import json

import frappe
from frappe import _
from frappe.utils import get_first_day, nowdate, formatdate, cint

# Reuse the report's row builder + number formatters (no query duplication).
from avinashgroup_app.avinash_group_app.report.sales_analysis_product_wise_invoice_details.sales_analysis_product_wise_invoice_details import (
	build_rows,
	_fmt_inr,
	_fmt_qty,
)
# Reuse the Customer Statement security/scoping helpers — same portal-user guard.
from avinashgroup_app.templates.pages.customer_statement import (
	_get_portal_customers,
	_get_allowed_companies,
	_to_list,
)


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	if "Customer" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only customers can access this page."), frappe.PermissionError)

	portal_customers = _get_portal_customers()

	if portal_customers:
		context.company_list = _get_allowed_companies(portal_customers)
		# Customer dropdown — only this user's linked customers, each tagged with its company
		# so the front-end can filter the list by the selected company.
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
	else:
		# Non-portal user (e.g. staff with Customer role) — all companies, no scoped list.
		context.company_list = [r.name for r in frappe.get_all("Company", fields=["name"], ignore_permissions=True)]
		context.customer_list = []

	# Prefer Nepal Gas Karnali as the default when it's available to this user;
	# otherwise fall back to the user's default company, then the first allowed one.
	preferred = "Nepal Gas Udhyog (Karnali) Pvt. Ltd."
	user_default = frappe.defaults.get_user_default("Company")
	if preferred in context.company_list:
		context.default_company = preferred
	elif user_default in context.company_list:
		context.default_company = user_default
	else:
		context.default_company = context.company_list[0] if context.company_list else ""

	context.from_date = str(get_first_day(nowdate()))
	context.to_date = nowdate()


def _shape(r):
	"""Map one report row into a flat, display-ready dict for the portal table."""
	if r.get("is_product_header"):
		return {"type": "product", "code": r.get("product_code") or "", "name": r.get("label") or ""}
	if r.get("is_customer_header"):
		return {"type": "customer", "code": r.get("label") or "", "name": r.get("miti") or ""}
	if r.get("is_section"):
		return {"type": "section", "text": r.get("miti") or ""}
	if r.get("is_invoice"):
		return {
			"type": "invoice",
			"miti": r.get("miti") or "",
			"invoice_no": r.get("invoice_no") or "",
			"qty": _fmt_qty(r.get("qty")),
			"value": _fmt_inr(r.get("value")),
			"vat": _fmt_inr(r.get("vat")),
			"total": _fmt_inr(r.get("total_incl_vat")),
		}
	if "summary_kind" in r:
		return {
			"type": "summary",
			"kind": r.get("summary_kind") or "",
			"label": r.get("invoice_no") or "",
			"qty": _fmt_qty(r.get("qty")),
			"value": _fmt_inr(r.get("value")),
			"vat": _fmt_inr(r.get("vat")),
			"total": _fmt_inr(r.get("total_incl_vat")),
			"bold": 1 if r.get("bold") else 0,
		}
	return {"type": "other"}


def _my_customers_in_companies(portal_customers, companies):
	"""The logged-in user's customers that belong to any of the given companies."""
	if not portal_customers or not companies:
		return []
	rows = frappe.get_all(
		"Customer",
		filters={"name": ("in", portal_customers), "custom_company": ("in", companies)},
		fields=["name"],
	)
	return [r.name for r in rows]


def _resolve_request(companies, customers):
	"""Role + ownership re-validation for the multi-company request.

	A portal user may only request their own companies and customers; an empty customer
	list is filled with their customers across the selected companies (never "all").
	"""
	if "Customer" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only customers can access this page."), frappe.PermissionError)

	companies = _to_list(companies)
	customers = _to_list(customers)
	portal_customers = _get_portal_customers()

	if portal_customers:
		allowed = _get_allowed_companies(portal_customers)
		if any(c not in allowed for c in companies):
			frappe.throw(_("You are not allowed to view one of these companies."), frappe.PermissionError)
		if any(c not in portal_customers for c in customers):
			frappe.throw(_("You are not allowed to view one of these customers."), frappe.PermissionError)
		if not customers:
			customers = _my_customers_in_companies(portal_customers, companies)

	return companies, customers, bool(portal_customers)


@frappe.whitelist()
def get_data(company=None, customers=None, from_date=None, to_date=None, include_return=1):
	"""Product-wise invoice details for the logged-in customer (no Agent rows).

	`company` may be a single value or a JSON list (multi-company select).
	"""
	if not (from_date and to_date):
		frappe.throw(_("From Date and To Date are required."))

	companies, customers, is_portal = _resolve_request(company, customers)
	if not companies:
		frappe.throw(_("Select at least one company."))
	if is_portal and not customers:
		return _empty(companies, from_date, to_date)

	inc = cint(include_return)
	filters = frappe._dict({
		"company": companies,
		"customer": customers,
		"from_date": from_date,
		"to_date": to_date,
		"include_return": inc,
	})
	# include_agent=False → drop the No Agent / Agent Sales/Returns/Net rows.
	data = build_rows(filters, inc, include_agent=False)

	return {
		"company": ", ".join(companies),
		"include_return": inc,
		"rows": [_shape(r) for r in data],
		"from_date": from_date,
		"to_date": to_date,
		"from_date_disp": formatdate(from_date),
		"to_date_disp": formatdate(to_date),
	}


def _empty(companies, from_date, to_date):
	return {
		"company": ", ".join(companies),
		"include_return": 1,
		"rows": [],
		"from_date": from_date,
		"to_date": to_date,
		"from_date_disp": formatdate(from_date),
		"to_date_disp": formatdate(to_date),
	}
