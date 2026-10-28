"""PDC setup — holding accounts for every company, a default JV Type, and the
workspace's number cards and charts.

`after_migrate` runs `after_migrate()`: it only ever *adds* what is missing
(dashboard records, a default JV Type) and never touches accounts — creating
ledger accounts on a live chart is the accountant's call, made with the
"Create Missing Accounts" button in PDC Settings (`ensure_company_accounts`).

Number Card and Dashboard Chart are not module-syncable doctypes in Frappe v15
(not in IMPORTABLE_DOCTYPES), so they are created here; the workspace JSON links
them by name and is synced with ignore_links.
"""

import frappe
from frappe import _

from avinashgroup_app.pdc.accounting import HOLDING_ACCOUNTS

# Used for custom_p_type on PDC Journal Entries when PDC Settings has none.
DEFAULT_JV_TYPE = "Bank Entry"


def after_migrate():
	try:
		if not frappe.db.exists("DocType", "PDC Settings"):
			return
		apply_settings_defaults()
		if not frappe.db.get_single_value("PDC Settings", "jv_type") and frappe.db.exists("JV Type", DEFAULT_JV_TYPE):
			frappe.db.set_single_value("PDC Settings", "jv_type", DEFAULT_JV_TYPE)
		ensure_dashboard()
	except Exception:
		frappe.log_error(title="PDC after_migrate setup failed", message=frappe.get_traceback())


def apply_settings_defaults():
	"""Write each PDC Settings default that has never been stored.

	A Single's JSON defaults only land when someone saves the form; until then
	get_single_value returns nothing, so "allow advances" read as off and the SMS
	templates as empty. Only fields with no tabSingles row are written, so a box
	someone unticked stays unticked.
	"""
	stored = set(frappe.db.sql_list("select field from `tabSingles` where doctype = 'PDC Settings'"))
	for df in frappe.get_meta("PDC Settings").fields:
		if df.default and df.fieldname not in stored:
			frappe.db.set_single_value("PDC Settings", df.fieldname, df.default)
	frappe.clear_document_cache("PDC Settings", "PDC Settings")


def _group_account(company, account_name, root_type):
	return frappe.db.get_value(
		"Account",
		{"company": company, "account_name": account_name, "is_group": 1, "root_type": root_type},
		"name",
	) or frappe.db.get_value(
		"Account", {"company": company, "is_group": 1, "root_type": root_type, "parent_account": ["is", "set"]}, "name",
		order_by="lft asc",
	)


def _ensure_account(company, account_name, parent_name, root_type):
	existing = frappe.db.get_value("Account", {"company": company, "account_name": account_name, "is_group": 0}, "name")
	if existing:
		return existing
	parent = _group_account(company, parent_name, root_type)
	if not parent:
		frappe.throw(_("No {0} group account found in {1}.").format(parent_name, company))
	account = frappe.get_doc({
		"doctype": "Account",
		"company": company,
		"account_name": account_name,
		"parent_account": parent,
		"root_type": root_type,
		"is_group": 0,
		"account_currency": frappe.get_cached_value("Company", company, "default_currency"),
	})
	account.flags.ignore_permissions = True
	account.insert()
	frappe.msgprint(_("Created {0}").format(account.name), alert=True)
	return account.name


def ensure_company_accounts(companies=None):
	"""Add a Company Accounts row (and its accounts) for each company lacking one."""
	settings = frappe.get_doc("PDC Settings")
	have = {r.company for r in settings.company_accounts}
	added = []
	for company in companies or frappe.get_all("Company", pluck="name", order_by="name"):
		if company in have:
			continue
		row = {"company": company}
		for field, name, parent, root_type in HOLDING_ACCOUNTS:
			row[field] = _ensure_account(company, name, parent, root_type)
		settings.append("company_accounts", row)
		added.append(company)
	if added:
		settings.flags.ignore_permissions = True
		settings.save()
	return added


# ── Workspace dashboard ──────────────────────────────────────────────────────

# The "this week" / "this month" windows are Timespan conditions in the static
# filters. Frappe evaluates dynamic_filters_json values as JavaScript, so a
# Timespan placed there fails with "Invalid expression set in filter".
NUMBER_CARDS = (
	("PDC Cheques in Hand", "Sum", "amount",
		[["PDC Cheque", "docstatus", "=", 1], ["PDC Cheque", "status", "in", ["In Hand", "Deposited"]],
			["PDC Cheque", "cheque_type", "=", "Received"]]),
	("PDC Due This Week", "Count", None,
		[["PDC Cheque", "docstatus", "=", 1], ["PDC Cheque", "status", "=", "In Hand"],
			["PDC Cheque", "cheque_type", "=", "Received"], ["PDC Cheque", "cheque_date", "Timespan", "this week"]]),
	("PDC Issued Outstanding", "Sum", "amount",
		[["PDC Cheque", "docstatus", "=", 1], ["PDC Cheque", "status", "=", "Issued"]]),
	("PDC Bounced This Month", "Count", None,
		[["PDC Cheque", "docstatus", "=", 1], ["PDC Cheque", "status", "=", "Bounced"],
			["PDC Cheque", "bounce_date", "Timespan", "this month"]]),
)


def ensure_dashboard():
	import json

	for name, function, field, filters in NUMBER_CARDS:
		if frappe.db.exists("Number Card", name):
			# Cards made by the first version carried the Timespan as a dynamic
			# filter; move it into the static filters once.
			if frappe.db.get_value("Number Card", name, "dynamic_filters_json") not in (None, "", "[]"):
				frappe.db.set_value("Number Card", name, {
					"filters_json": json.dumps(filters), "dynamic_filters_json": "[]",
				})
			continue
		frappe.get_doc({
			"doctype": "Number Card",
			"name": name,
			"label": name,
			"type": "Document Type",
			"document_type": "PDC Cheque",
			"function": function,
			"aggregate_function_based_on": field,
			"filters_json": json.dumps(filters),
			"dynamic_filters_json": "[]",
			"is_public": 1,
			"show_percentage_stats": 0,
			"module": "PDC",
			"is_standard": 0,
		}).insert(ignore_permissions=True)

	if not frappe.db.exists("Dashboard Chart", "PDC Open Cheques by Status"):
		frappe.get_doc({
			"doctype": "Dashboard Chart",
			"chart_name": "PDC Open Cheques by Status",
			"chart_type": "Group By",
			"document_type": "PDC Cheque",
			"group_by_type": "Sum",
			"group_by_based_on": "status",
			"aggregate_function_based_on": "amount",
			"type": "Donut",
			"filters_json": json.dumps([["PDC Cheque", "docstatus", "=", 1]]),
			"is_public": 1,
			"module": "PDC",
		}).insert(ignore_permissions=True)

	if not frappe.db.exists("Dashboard Chart", "PDC Cheques by Cheque Date"):
		frappe.get_doc({
			"doctype": "Dashboard Chart",
			"chart_name": "PDC Cheques by Cheque Date",
			"chart_type": "Sum",
			"document_type": "PDC Cheque",
			"based_on": "cheque_date",
			"value_based_on": "amount",
			"timespan": "Last Quarter",
			"time_interval": "Weekly",
			"timeseries": 1,
			"type": "Bar",
			"filters_json": json.dumps([["PDC Cheque", "docstatus", "=", 1], ["PDC Cheque", "cheque_type", "=", "Received"]]),
			"is_public": 1,
			"module": "PDC",
		}).insert(ignore_permissions=True)
