from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.financial_statements import (
	get_accounts,
	filter_accounts,
)
import erpnext.accounts.report.consolidated_financial_statement.consolidated_financial_statement as cfs


def execute(filters=None):
	filters = frappe._dict(filters or {})

	# Resolve the set of companies to consolidate. Multiple companies may be
	# selected explicitly; if none are chosen we fall back to ALL companies.
	# This report does not rely on a group/parent company tree.
	selected = resolve_companies(filters)

	# erpnext's consolidated report needs a single `company` for currency
	# look-ups and a few labels. Use the default company when it is part of
	# the selection, otherwise the first selected company.
	default_company = frappe.defaults.get_user_default("Company")
	representative = default_company if default_company in selected else (
		selected[0] if selected else default_company
	)
	filters.company = representative

	columns, data, message, chart, report_summary = run_consolidated(filters, selected)

	# Collapses only apply to account-tree reports (P&L / Balance Sheet), not Cash Flow.
	report_type = filters.get("report", "Balance Sheet")
	if report_type != "Cash Flow":
		# 1) Drop accounts not shared by every selected company (folded into parent).
		shared_keys = get_shared_account_keys(selected, report_type)
		data = filter_shared_accounts(data, shared_keys)

		# 2) Optionally cap the (remaining) hierarchy at a chosen level.
		account_level = get_account_level(filters)
		if account_level:
			company_keys = [col.get("fieldname") for col in columns[2:] if col.get("fieldname")]
			data = apply_account_level_filter(data, account_level, company_keys)

	return columns, data, message, chart, report_summary


def resolve_companies(filters) -> list[str]:
	"""Return the ordered, de-duplicated list of companies to consolidate.

	Reads the ``companies`` multi-select filter (falls back to ``company``).
	Empty selection means "all companies".
	"""
	raw = filters.get("companies") or filters.get("company")

	selected: list[str] = []
	if isinstance(raw, str):
		selected = [c.strip() for c in raw.split(",") if c.strip()]
	elif isinstance(raw, (list, tuple)):
		selected = [c for c in raw if c]

	# de-duplicate, preserve order
	seen: set[str] = set()
	selected = [c for c in selected if not (c in seen or seen.add(c))]

	if not selected:
		# nothing chosen -> all companies (tree order for stable column order)
		selected = frappe.get_all("Company", pluck="name", order_by="lft")

	return selected


def run_consolidated(filters, selected: list[str]):
	"""Run erpnext's consolidated report against an explicit company list.

	erpnext derives the company set (and the GL-entry scope) from the
	``filters.company`` group-company tree. Since this report consolidates an
	arbitrary set of companies with no shared parent, we temporarily patch the
	two functions that read that tree so they use ``selected`` instead. All the
	rest of erpnext's tested consolidation logic (account-key merging,
	per-company columns, totals) is reused as-is.
	"""
	orig_get_companies = cfs.get_companies
	orig_set_gl = cfs.set_gl_entries_by_account

	def patched_get_companies(_filters):
		# all_companies (column order) and {company: [its own]} accumulation map.
		return list(selected), {c: [c] for c in selected}

	def patched_set_gl(
		from_date,
		to_date,
		root_lft,
		root_rgt,
		_filters,
		gl_entries_by_account,
		accounts_by_name,
		accounts,
		ignore_closing_entries=False,
		root_type=None,
	):
		# Reuse the original GL fetch once per company. With no group tree each
		# company's subtree is just itself, so this collects GL for every
		# selected company into the shared gl_entries_by_account dict.
		saved = _filters.company
		try:
			for company in selected:
				_filters.company = company
				orig_set_gl(
					from_date,
					to_date,
					root_lft,
					root_rgt,
					_filters,
					gl_entries_by_account,
					accounts_by_name,
					accounts,
					ignore_closing_entries=ignore_closing_entries,
					root_type=root_type,
				)
		finally:
			_filters.company = saved

	try:
		cfs.get_companies = patched_get_companies
		cfs.set_gl_entries_by_account = patched_set_gl
		return cfs.execute(filters)
	finally:
		cfs.get_companies = orig_get_companies
		cfs.set_gl_entries_by_account = orig_set_gl


# ---------------------------------------------------------------------------
# Shared-account collapse (drop accounts not common to every selected company)
# ---------------------------------------------------------------------------

def _root_types_for_report(report_type: str) -> tuple[str, ...]:
	if report_type == "Profit and Loss Statement":
		return ("Income", "Expense")
	# Balance Sheet
	return ("Asset", "Liability", "Equity")


def _account_key(account_number, account_name) -> str:
	"""Build the same display key prepare_data() uses for a row's account_name."""
	if account_number:
		return f"{_(account_number)} - {_(account_name)}"
	return _(account_name)


def get_shared_account_keys(selected: list[str], report_type: str) -> set[str]:
	"""Return account keys (``number - name``) that exist in EVERY selected company.

	An account is "shared" only when each selected company has an account with
	the same number+name. Accounts missing from any company are not shared; their
	rows are dropped on display and their amounts remain rolled up into the
	parent (erpnext already accumulates every child into its parent).
	"""
	root_types = _root_types_for_report(report_type)

	coverage: dict[str, set[str]] = defaultdict(set)
	for company in selected:
		rows = frappe.get_all(
			"Account",
			filters={"company": company, "root_type": ("in", root_types)},
			fields=["account_number", "account_name"],
		)
		for a in rows:
			coverage[_account_key(a.account_number, a.account_name)].add(company)

	n = len(selected)
	return {key for key, companies in coverage.items() if len(companies) == n}


def filter_shared_accounts(data, shared_keys: set[str]):
	"""Keep only shared account rows; keep structural and synthetic/total rows.

	Non-shared accounts are dropped from the output. Their values are already
	included in their parent's totals via erpnext's parent accumulation, so the
	columns stay balanced.
	"""
	out = []
	for row in data:
		account = row.get("account")
		account_name = row.get("account_name") or ""

		# structural blank/separator rows (no account)
		if not account:
			out.append(row)
			continue

		# synthetic/total rows are quoted, e.g. "'Total Asset (Debit)'"
		if account_name.startswith("'") and account_name.endswith("'"):
			out.append(row)
			continue

		if account_name in shared_keys:
			out.append(row)
		# else: drop — folded into parent

	return out


# ---------------------------------------------------------------------------
# Account-level cap (same behaviour as the Balance Sheet Hierarchy report)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_max_account_depth(company: str | None = None, report: str = "Balance Sheet") -> int:
	"""Return maximum depth of accounts for the given company and report type."""
	if not company:
		company = frappe.defaults.get_user_default("Company")

	if not company:
		return 1

	root_types = _root_types_for_report(report)

	max_indent = 0
	for root_type in root_types:
		accounts = get_accounts(company, root_type)
		if not accounts:
			continue
		filtered_accounts, _by_name, _pcm = filter_accounts(accounts)
		for acc in filtered_accounts:
			indent = int(flt(getattr(acc, "indent", 0)))
			if indent > max_indent:
				max_indent = indent

	return int(max_indent) + 1 if max_indent >= 0 else 1


def get_account_level(filters) -> int | None:
	level = filters.get("account_level")
	if not level:
		return None
	try:
		level_int = int(level)
	except (TypeError, ValueError):
		return None
	if level_int < 1:
		return None
	return min(level_int, 20)


def apply_account_level_filter(data, level: int, company_keys: list[str]):
	"""Show values only at the chosen level per branch; keep structure.

	- For each root→leaf path, if depth >= level keep only node at level N.
	- If branch shorter than level, keep last leaf node's values.
	- Ancestors shown as structural rows with empty values.
	- Descendants below kept node are hidden.
	- Synthetic/total rows (quoted account_name) are always kept intact.
	"""
	rows_by_account: dict[str, dict] = {}
	parent_children: dict[str | None, list[str]] = {}

	for row in data:
		account = row.get("account")
		if not account:
			continue
		account_name = row.get("account_name") or ""
		if account_name.startswith("'") and account_name.endswith("'"):
			continue
		rows_by_account[account] = row
		parent = row.get("parent_account") or None
		parent_children.setdefault(parent, []).append(account)

	roots = [
		acc for acc in rows_by_account
		if rows_by_account[acc].get("parent_account") in (None, "")
	]

	keep_value_accounts: set[str] = set()
	hide_accounts: set[str] = set()

	def process_path(path):
		depth = len(path)
		idx_keep = (level - 1) if depth >= level else (depth - 1)
		keep_value_accounts.add(path[idx_keep])
		for acc in path[idx_keep + 1:]:
			hide_accounts.add(acc)

	def dfs(account, path):
		path.append(account)
		children = parent_children.get(account) or []
		if not children:
			process_path(path)
		else:
			for child in children:
				dfs(child, path)
		path.pop()

	for root in roots:
		dfs(root, [])

	new_data = []
	for row in data:
		account = row.get("account")
		account_name = row.get("account_name") or ""

		# always keep synthetic/total rows
		if account_name.startswith("'") and account_name.endswith("'"):
			new_data.append(row)
			continue

		if account in hide_accounts:
			continue

		if account and account not in keep_value_accounts:
			for key in company_keys:
				if key in row:
					row[key] = None
			if "total" in row:
				row["total"] = None
			if "opening_balance" in row:
				row["opening_balance"] = None
			row["has_value"] = False

		new_data.append(row)

	return new_data
