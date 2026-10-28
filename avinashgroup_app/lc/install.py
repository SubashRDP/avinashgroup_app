"""LC setup — settings defaults, a default JV Type, the Miti mapping, and the
per-company accounts.

`after_migrate` runs `after_migrate()`: it only ever *adds* what is missing
(settings defaults, a JV Type, a Bs Conversion record for the LC's dates) and
never touches accounts — creating ledger accounts on a live chart is the
accountant's call, made with the "Create Missing Accounts" button in LC
Settings (`ensure_company_accounts`).
"""

import frappe
from frappe import _

from avinashgroup_app.lc.accounting import LC_ACCOUNTS

# Used for custom_p_type on LC Journal Entries when LC Settings has none: LC
# entries all move money through a bank, like PDC's.
DEFAULT_JV_TYPE = "Bank Entry"

# AD date → Miti field on the Letter of Credit, filled by utils/bs_miti.py.
MITI_FIELDS = (
	("posting_date", "posting_miti"),
	("expiry_date", "expiry_miti"),
	("latest_shipment_date", "latest_shipment_miti"),
)


def after_migrate():
	try:
		if not frappe.db.exists("DocType", "LC Settings"):
			return
		apply_settings_defaults()
		if not frappe.db.get_single_value("LC Settings", "jv_type") and frappe.db.exists("JV Type", DEFAULT_JV_TYPE):
			frappe.db.set_single_value("LC Settings", "jv_type", DEFAULT_JV_TYPE)
		ensure_miti_mapping()
	except Exception:
		frappe.log_error(title="LC after_migrate setup failed", message=frappe.get_traceback())


def apply_settings_defaults():
	"""Write each LC Settings default that has never been stored (see pdc/install.py for why)."""
	stored = set(frappe.db.sql_list("select field from `tabSingles` where doctype = 'LC Settings'"))
	for df in frappe.get_meta("LC Settings").fields:
		if df.default and df.fieldname not in stored:
			frappe.db.set_single_value("LC Settings", df.fieldname, df.default)
	frappe.clear_document_cache("LC Settings", "LC Settings")


def ensure_miti_mapping():
	if not frappe.db.exists("DocType", "Bs Conversion") or frappe.db.exists("Bs Conversion", "Letter of Credit"):
		return
	doc = frappe.get_doc({
		"doctype": "Bs Conversion",
		"doctype_names": "Letter of Credit",
		"ad_bs": [{"ad_date": ad, "bs_date": bs, "enabled": 1} for ad, bs in MITI_FIELDS],
	})
	doc.insert(ignore_permissions=True)


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
	settings = frappe.get_doc("LC Settings")
	have = {r.company for r in settings.company_accounts}
	added = []
	for company in companies or frappe.get_all("Company", pluck="name", order_by="name"):
		if company in have:
			continue
		row = {"company": company, "firm_type": "Industry"}
		for field, name, parent, root_type in LC_ACCOUNTS:
			row[field] = _ensure_account(company, name, parent, root_type)
		settings.append("company_accounts", row)
		added.append(company)
	if added:
		settings.flags.ignore_permissions = True
		settings.save()
	return added
