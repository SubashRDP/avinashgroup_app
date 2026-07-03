from collections import defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpnext.accounts.report.financial_statements import (
	get_accounts,
	filter_accounts,
	get_fiscal_year_data,
)
from erpnext.accounts.report.utils import convert_to_presentation_currency
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
		# 1) Drop accounts not shared across the chosen reference set (folded into parent).
		#    "Common Accounts" scope decides that reference set:
		#      - Selected Companies (default): account must exist in every selected company.
		#      - All Companies: account must exist in every company in the system.
		scope = filters.get("common_accounts_scope") or "Selected Companies"
		if scope == "All Companies":
			compare_companies = frappe.get_all("Company", pluck="name", order_by="lft")
		else:
			compare_companies = selected

		shared_keys = get_shared_account_keys(compare_companies, report_type)
		data = filter_shared_accounts(data, shared_keys)

		# 2) Optionally cap the (remaining) hierarchy at a chosen level.
		account_level = get_account_level(filters)
		if account_level:
			company_keys = [col.get("fieldname") for col in columns[2:] if col.get("fieldname")]
			data = apply_account_level_filter(data, account_level, company_keys)

	# add a "Total" column = sum of all the company columns in each row
	add_row_total_column(columns, data)

	return columns, data, message, chart, report_summary


def add_row_total_column(columns, data):
	"""Add a separate 'Total' column = sum of every company column in each row.

	The consolidated report renders one column per selected company; this adds a
	final Total column holding the row-wise sum across those companies. Rows that
	were blanked (e.g. by the account-level filter) keep an empty Total.
	"""
	# company columns are everything after `account` (0) and hidden `currency` (1)
	company_keys = [col.get("fieldname") for col in columns[2:] if col.get("fieldname")]

	for row in data:
		if not row:
			# blank separator rows
			continue

		values = [row.get(key) for key in company_keys if key in row]
		if values and all(v is None for v in values):
			# row intentionally blanked -> keep Total empty too
			row["total"] = None
		else:
			row["total"] = flt(sum(flt(v) for v in values if v is not None), 3)

	# append the Total column once, at the end
	if not any(col.get("fieldname") == "total" for col in columns):
		columns.append(
			{
				"fieldname": "total",
				"label": _("Total"),
				"fieldtype": "Currency",
				"options": "currency",
				"width": 150,
			}
		)


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

	The GL fetch itself is replaced with a single aggregated query per report
	run: erpnext's ``calculate_values`` only ever reduces the raw GL rows to
	two numbers per account/company (balance up to the end date, and the
	opening part before the period start), so we let SQL compute those sums
	and feed ``calculate_values`` two synthetic entries per account/company
	instead of every ledger row.
	"""
	orig_get_companies = cfs.get_companies
	orig_set_gl = cfs.set_gl_entries_by_account
	orig_account_type_gl = cfs.get_account_type_based_gl_data
	orig_get_accounts = cfs.get_accounts

	# one aggregated fetch per (from_date, to_date, ignore_closing_entries);
	# erpnext calls set_gl_entries_by_account once per root account (one root
	# per company per root type) — all those calls share this cache.
	agg_cache: dict = {}
	# Cash Flow: sums per (company, account_type), one grouped query instead of
	# erpnext's one query per company per account type.
	account_type_cache: dict = {}

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
		cache_key = (str(from_date), str(to_date), bool(ignore_closing_entries))
		if cache_key not in agg_cache:
			agg_cache[cache_key] = fetch_aggregated_gl_entries(
				_filters, selected, from_date, to_date, ignore_closing_entries
			)

		# dispatch the pre-aggregated entries that belong to this root subtree
		for entry in agg_cache[cache_key]:
			if entry.acc_lft < root_lft or entry.acc_rgt > root_rgt:
				continue
			if root_type and entry.root_type != root_type:
				continue

			if entry.account_number:
				account_name = entry.account_number + " - " + entry.account_name
			else:
				account_name = entry.account_name

			cfs.validate_entries(account_name, entry, accounts_by_name, accounts)
			gl_entries_by_account.setdefault(account_name, []).append(entry)

		return gl_entries_by_account

	def patched_get_accounts(root_type, companies):
		# erpnext queries Account once per company; fetch all companies in one
		# query. Company order must be preserved: on duplicate account keys,
		# filter_accounts() keeps the first occurrence (earlier company wins).
		accounts = frappe.get_all(
			"Account",
			fields=[
				"name",
				"is_group",
				"company",
				"parent_account",
				"lft",
				"rgt",
				"root_type",
				"report_type",
				"account_name",
				"account_number",
			],
			filters={"company": ("in", list(companies)), "root_type": root_type},
		)
		precedence = {c: i for i, c in enumerate(companies)}
		accounts.sort(key=lambda a: (precedence.get(a.company, len(precedence)), a.name))
		return accounts

	def patched_account_type_gl(company, _filters=None):
		_filters = frappe._dict(_filters or {})
		if _filters.get("cost_center"):
			# cost-center path mutates filters (children lookup) — rare here,
			# keep erpnext's own implementation for it.
			return orig_account_type_gl(company, _filters)

		cache_key = (
			str(_filters.get("start_date")),
			str(_filters.get("end_date")),
			str(_filters.get("finance_book")),
			bool(_filters.get("include_default_book_entries")),
		)
		if cache_key not in account_type_cache:
			account_type_cache[cache_key] = fetch_account_type_sums(_filters, selected)

		return account_type_cache[cache_key].get((company, _filters.get("account_type"))) or 0

	try:
		cfs.get_companies = patched_get_companies
		cfs.set_gl_entries_by_account = patched_set_gl
		cfs.get_account_type_based_gl_data = patched_account_type_gl
		cfs.get_accounts = patched_get_accounts
		return cfs.execute(filters)
	finally:
		cfs.get_companies = orig_get_companies
		cfs.set_gl_entries_by_account = orig_set_gl
		cfs.get_account_type_based_gl_data = orig_account_type_gl
		cfs.get_accounts = orig_get_accounts


def _opening_split_date(filters):
	"""The date erpnext's calculate_values() splits opening vs period on."""
	if filters.get("filter_based_on") == "Fiscal Year":
		fiscal_year = get_fiscal_year_data(
			filters.get("from_fiscal_year"), filters.get("to_fiscal_year")
		)
		return getdate(fiscal_year.year_start_date)
	return getdate(filters.get("period_start_date"))


def fetch_aggregated_gl_entries(
	filters, selected: list[str], from_date, to_date, ignore_closing_entries: bool
):
	"""Fetch GL balances pre-aggregated in SQL as synthetic GL entries.

	Returns up to two frappe._dict "entries" per account/company:
	  - an *opening* entry (posting_date just before the period start) with the
	    summed debit/credit of everything before the period, and
	  - a *period* entry (posting_date = to_date) with the period sums.
	calculate_values() consumes these exactly like raw GL rows — the math is
	identical because it only adds debits/credits per company bucketed by
	"before period start" vs "within period".

	Mirrors the WHERE clause of erpnext's set_gl_entries_by_account +
	get_additional_conditions (is_cancelled, date range, closing entries,
	finance books). Extra fields acc_lft/acc_rgt/root_type let the caller
	dispatch entries to the right root subtree without re-querying.
	"""
	split_date = _opening_split_date(filters)

	conditions = [
		"gle.is_cancelled = 0",
		"gle.posting_date <= %(to_date)s",
	]
	params: dict = {
		"to_date": to_date,
		"split_date": split_date,
	}

	if from_date:
		conditions.append("gle.posting_date >= %(from_date)s")
		params["from_date"] = from_date

	if ignore_closing_entries:
		conditions.append("gle.voucher_type != 'Period Closing Voucher'")

	# finance-book scoping, same as erpnext's get_additional_conditions().
	# The allowed set can differ per company (default_finance_book), so group
	# companies by their allowed finance-book list.
	base_books = [""]
	if filters.get("finance_book"):
		base_books.append(filters.get("finance_book"))

	books_to_companies: dict[tuple, list[str]] = defaultdict(list)
	for company in selected:
		books = list(base_books)
		if filters.get("include_default_book_entries"):
			company_fb = frappe.get_cached_value("Company", company, "default_finance_book")
			if company_fb:
				books.append(company_fb)
		books_to_companies[tuple(sorted(set(books)))].append(company)

	fb_clauses = []
	for i, (books, companies) in enumerate(books_to_companies.items()):
		params[f"fb_companies_{i}"] = tuple(companies)
		params[f"fb_books_{i}"] = books
		fb_clauses.append(
			f"(gle.company IN %(fb_companies_{i})s"
			f" AND (gle.finance_book IN %(fb_books_{i})s OR gle.finance_book IS NULL))"
		)
	conditions.append("(" + " OR ".join(fb_clauses) + ")")

	# When every selected company's currency equals the presentation currency,
	# erpnext never converts, so the in-account-currency sums and the
	# account_currency grouping are dead weight — skip them (4 fewer SUMs
	# evaluated per GL row).
	presentation_currency = filters.get("presentation_currency")
	needs_conversion = any(
		presentation_currency != frappe.get_cached_value("Company", c, "default_currency")
		for c in selected
	)

	currency_cols = (
		"""gle.account_currency,
			SUM(CASE WHEN gle.posting_date < %(split_date)s THEN gle.debit_in_account_currency ELSE 0 END) AS opening_debit_ac,
			SUM(CASE WHEN gle.posting_date < %(split_date)s THEN gle.credit_in_account_currency ELSE 0 END) AS opening_credit_ac,
			SUM(CASE WHEN gle.posting_date >= %(split_date)s THEN gle.debit_in_account_currency ELSE 0 END) AS period_debit_ac,
			SUM(CASE WHEN gle.posting_date >= %(split_date)s THEN gle.credit_in_account_currency ELSE 0 END) AS period_credit_ac,"""
		if needs_conversion
		else ""
	)
	group_by = "gle.company, gle.account" + (", gle.account_currency" if needs_conversion else "")

	# Pure GL aggregation — no join, so a covering index on GL Entry keeps this
	# an index-only scan. Account attributes are attached from a second, tiny
	# query over just the distinct accounts that have entries.
	rows = frappe.db.sql(
		f"""
		SELECT
			gle.company,
			gle.account,
			{currency_cols}
			SUM(CASE WHEN gle.posting_date < %(split_date)s THEN gle.debit ELSE 0 END) AS opening_debit,
			SUM(CASE WHEN gle.posting_date < %(split_date)s THEN gle.credit ELSE 0 END) AS opening_credit,
			SUM(CASE WHEN gle.posting_date >= %(split_date)s THEN gle.debit ELSE 0 END) AS period_debit,
			SUM(CASE WHEN gle.posting_date >= %(split_date)s THEN gle.credit ELSE 0 END) AS period_credit
		FROM `tabGL Entry` gle
		WHERE {" AND ".join(conditions)}
		GROUP BY {group_by}
		""",
		params,
		as_dict=True,
	)

	account_details = {
		a.name: a
		for a in frappe.get_all(
			"Account",
			filters={"name": ("in", sorted({r.account for r in rows}))},
			fields=["name", "account_name", "account_number", "lft", "rgt", "root_type"],
		)
	} if rows else {}

	opening_date = split_date - timedelta(days=1)
	period_date = getdate(to_date)

	entries = []
	for r in rows:
		acc = account_details.get(r.account)
		if not acc:
			# GL row pointing at a deleted/renamed account — nothing to report it under
			continue
		for prefix, posting_date in (("opening", opening_date), ("period", period_date)):
			debit = flt(r.get(f"{prefix}_debit"))
			credit = flt(r.get(f"{prefix}_credit"))
			debit_ac = flt(r.get(f"{prefix}_debit_ac"))
			credit_ac = flt(r.get(f"{prefix}_credit_ac"))
			if not (debit or credit or debit_ac or credit_ac):
				continue
			entries.append(
				frappe._dict(
					company=r.company,
					account=r.account,
					account_currency=r.account_currency,
					account_name=acc.account_name,
					account_number=acc.account_number,
					acc_lft=acc.lft,
					acc_rgt=acc.rgt,
					root_type=acc.root_type,
					posting_date=posting_date,
					debit=debit,
					credit=credit,
					debit_in_account_currency=debit_ac,
					credit_in_account_currency=credit_ac,
				)
			)

	# presentation-currency conversion, same trigger as erpnext (per company,
	# skipped when the presentation currency IS the company currency). The
	# conversion is linear (one report-date rate, or account-currency values),
	# so converting the sums equals summing converted rows.
	presentation_currency = filters.get("presentation_currency")
	for company in selected:
		default_currency = frappe.get_cached_value("Company", company, "default_currency")
		if presentation_currency == default_currency:
			continue
		company_entries = [e for e in entries if e.company == company]
		if company_entries:
			convert_to_presentation_currency(
				company_entries,
				frappe._dict(
					report_date=to_date,
					presentation_currency=presentation_currency,
					company=company,
					company_currency=default_currency,
				),
			)

	return entries


def fetch_account_type_sums(filters, selected: list[str]) -> dict:
	"""Cash-flow sums per (company, account_type), one grouped query.

	Replicates the WHERE clause of erpnext's cash_flow
	get_account_type_based_gl_data exactly (posting-date window, Period
	Closing Voucher exclusion, finance-book scoping, and — like erpnext —
	no is_cancelled filter), but grouped so all companies and account types
	come back in a single scan.
	"""
	conditions = [
		"gle.posting_date >= %(start_date)s",
		"gle.posting_date <= %(end_date)s",
		"gle.voucher_type != 'Period Closing Voucher'",
	]
	params: dict = {
		"start_date": filters.get("start_date"),
		"end_date": filters.get("end_date"),
	}

	books_to_companies: dict[tuple, list[str]] = defaultdict(list)
	for company in selected:
		books = {""}
		if filters.get("finance_book"):
			books.add(filters.get("finance_book"))
		if filters.get("include_default_book_entries"):
			company_fb = frappe.get_cached_value("Company", company, "default_finance_book")
			if company_fb:
				books.add(company_fb)
		books_to_companies[tuple(sorted(books))].append(company)

	fb_clauses = []
	for i, (books, companies) in enumerate(books_to_companies.items()):
		params[f"at_companies_{i}"] = tuple(companies)
		params[f"at_books_{i}"] = books
		fb_clauses.append(
			f"(gle.company IN %(at_companies_{i})s"
			f" AND (gle.finance_book IN %(at_books_{i})s OR gle.finance_book IS NULL))"
		)
	conditions.append("(" + " OR ".join(fb_clauses) + ")")

	rows = frappe.db.sql(
		f"""
		SELECT gle.company, gle.account,
			SUM(gle.credit) - SUM(gle.debit) AS total
		FROM `tabGL Entry` gle
		WHERE {" AND ".join(conditions)}
		GROUP BY gle.company, gle.account
		""",
		params,
		as_dict=True,
	)

	account_types = {
		a.name: a.account_type
		for a in frappe.get_all(
			"Account",
			filters={"company": ("in", selected), "account_type": ("is", "set")},
			fields=["name", "account_type"],
		)
	}

	sums: dict[tuple[str, str], float] = defaultdict(float)
	for r in rows:
		account_type = account_types.get(r.account)
		if account_type:
			sums[(r.company, account_type)] += flt(r.total)

	return dict(sums)


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

	rows = frappe.get_all(
		"Account",
		filters={"company": ("in", selected), "root_type": ("in", root_types)},
		fields=["company", "account_number", "account_name"],
	)

	coverage: dict[str, set[str]] = defaultdict(set)
	for a in rows:
		coverage[_account_key(a.account_number, a.account_name)].add(a.company)

	n = len(selected)
	return {key for key, companies in coverage.items() if len(companies) == n}


def filter_shared_accounts(data, shared_keys: set[str]):
	"""Keep only shared account rows; keep structural and synthetic/total rows.

	Non-shared accounts are dropped from the output. Their values are already
	included in their parent's totals via erpnext's parent accumulation, so the
	columns stay balanced.

	When a dropped account has *kept* descendants (a non-shared group whose
	children are shared), those descendants would dangle from a row that no
	longer exists — breaking the tree view and leaking through the account-level
	filter. So kept rows are re-parented to their nearest kept ancestor and
	their indent recomputed, keeping the hierarchy a proper tree.
	"""

	def is_synthetic(name: str) -> bool:
		return name.startswith("'") and name.endswith("'")

	# all account rows (kept or not) so parent chains can be walked through
	# dropped rows
	rows_by_account = {
		row.get("account"): row
		for row in data
		if row.get("account") and not is_synthetic(row.get("account_name") or "")
	}
	kept_accounts = {
		account
		for account, row in rows_by_account.items()
		if (row.get("account_name") or "") in shared_keys
	}

	out = []
	new_indent: dict[str, int] = {}
	for row in data:
		account = row.get("account")
		account_name = row.get("account_name") or ""

		# structural blank/separator rows (no account)
		if not account:
			out.append(row)
			continue

		# synthetic/total rows are quoted, e.g. "'Total Asset (Debit)'"
		if is_synthetic(account_name):
			out.append(row)
			continue

		if account not in kept_accounts:
			continue  # drop — folded into parent

		# walk up through dropped ancestors to the nearest kept one
		parent = row.get("parent_account") or None
		while parent and parent not in kept_accounts:
			parent_row = rows_by_account.get(parent)
			parent = (parent_row.get("parent_account") or None) if parent_row else None

		row["parent_account"] = parent
		# recompute depth from the (possibly re-parented) kept chain; data is in
		# tree order, so a kept parent's new indent is already known
		row["indent"] = (new_indent[parent] + 1) if parent in new_indent else 0
		new_indent[account] = row["indent"]

		out.append(row)

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

	visited: set[str] = set()

	def dfs(account, path):
		visited.add(account)
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

		# orphans whose parent row was removed are unreachable from any root —
		# they'd otherwise leak through as blank rows below the chosen level
		if account and account not in visited:
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
