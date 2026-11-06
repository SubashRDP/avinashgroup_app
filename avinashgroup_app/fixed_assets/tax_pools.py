"""Put every Asset Category in its Income Tax Act Schedule-2 pool and wire its accounts.

Nepal computes tax depreciation per *pool* (Income Tax Act 2058, Schedule-2
s.1: A buildings, B computers / furniture / office equipment, C vehicles,
D plant and everything not listed elsewhere, E intangibles). ERPNext only
knows per-asset categories. The group's chart of accounts already names the
pools (``111102 Pool A - Buildings``, ``555101 Depreciation on Pool A``), but
the Asset Categories that should point at them were wired by hand and drifted
apart company by company (seen on demo-nggroup, 2026-11-03):

- accumulated depreciation pointed at ``345109 Provision for Accumulated
  Depreciation``, a *liability* provision, or was blank;
- the depreciation expense account was blank on about half the rows;
- Land sat on the "Pool A" account and was depreciable, though land is not
  depreciable property (s.2(aak): it does not decline in value);
- WIP categories posted straight to the Pool A buildings account with CWIP
  accounting switched off.

What ``setup()`` does, for each company that has the pool chart (the
``111100`` Property, Plant and Equipment group):

1. creates the group ``111190 Accumulated Depreciation`` under 111100 and one
   contra account per pool fixed-asset account (111102 -> 111192, ...), and
   the same for intangibles: ``111290 Accumulated Amortization`` under
   ``111200 Intangible Assets`` (111201 -> 111291, ...);
2. creates the Pool E categories (``INTANGIBLE_CATEGORIES``) for a company
   that has the intangible accounts but no such category yet. No company had
   intangibles in 2026-11, but the chart already carries ``111201 Pool E
   -Capitalized Software``, so the category is ready when the first licence
   is bought;
3. sets ``custom_tax_pool``, the four accounts, CWIP accounting and the
   non-depreciable flag on each category, matching on its name
   (``CATEGORY_RULES``).

Pool E differs from A-D (Schedule-2 s.1(2)(b), s.3(1), s.3(2)): every
intangible is a class of its own, its rate is 100 / period of use rounded to
the nearest half year, so it is set per Asset from ``custom_useful_life_years``
(``nepal_wdv.fill_from_tax_pool``), not on the category, and it never gets the
+1/3 rate. The category's finance-book row only carries the method.

It is idempotent: a second run changes nothing. ``dry_run=True`` (the default)
only reports.

Deliberately NOT done here:

- depreciation method / rate / finance book rows. Whether the books use
  written-down value at the tax rates or NFRS straight-line is the
  auditors' decision, which is still open;
- the tax computation itself (thirds rule, disposals, 7% repair cap,
  +1/3 for special industries). That is a report built on ``custom_tax_pool``;
- creating A-D categories for a company that has none, or guessing the pool of a
  category whose name matches no rule. Both are reported for a person to fix;
- touching ``345109`` or renaming any existing account.

Run from ``bench --site <site> console``::

    from avinashgroup_app.fixed_assets.tax_pools import setup
    print("\\n".join(setup(dry_run=True)))

Rules and sources: ``docs/fixed-assets-tax-pools.md``.
"""

import frappe
from frappe.utils import flt

TAX_POOL_FIELD = "custom_tax_pool"  # Custom Field fixture "Asset Category-custom_tax_pool"
NOT_DEPRECIABLE = "Not Depreciable"

PPE_GROUP_NUMBER = "111100"  # "Property, Plant and Equipment", parent of the pool accounts
ACCUMULATED_GROUP_NUMBER = "111190"
INTANGIBLE_GROUP_NUMBER = "111200"  # "Intangible Assets", parent of the Pool E accounts
AMORTIZATION_GROUP_NUMBER = "111290"

# Fixed-asset account prefix -> (contra group number, its name, parent group number).
# The contra account takes the fixed-asset account's last digit: 111102 -> 111192, 111201 -> 111291.
ACCUMULATED_GROUPS = {
	"1111": (ACCUMULATED_GROUP_NUMBER, "Accumulated Depreciation", PPE_GROUP_NUMBER),
	"1112": (AMORTIZATION_GROUP_NUMBER, "Accumulated Amortization", INTANGIBLE_GROUP_NUMBER),
}
CWIP_GROUP_NUMBER = "111300"  # "Capital WIP- Assets"

# Category name keywords -> (tax pool, fixed asset account number, CWIP account name keyword).
# First match wins, so WIP rows come before the plain asset rows they contain
# ("WIP Filling Plant" must not match "plant"). Pools per Schedule-2 s.1(1).
CATEGORY_RULES = (
	(("wip", "civil"), "A", "111102", "civil work wip"),
	(("wip", "filling plant"), "D", "111105", "filling plant (wip)"),
	(("wip", "vehicle"), "C", "111104", "wip vehicle"),
	(("land",), NOT_DEPRECIABLE, "111101", None),
	(("building",), "A", "111102", None),
	(("computer",), "B", "111103", None),
	(("office equipment",), "B", "111103", None),
	(("furniture",), "B", "111103", None),
	(("vehicle",), "C", "111104", None),
	(("cylinder",), "D", "111106", None),
	(("plant",), "D", "111105", None),
	(("other fixed asset",), "D", "111105", None),
	(("software",), "E", "111201", None),
	(("trademark",), "E", "111203", None),
)

# Pool E categories created per company (name, fixed asset account). The names
# match the "software" / "trademark" rules above. Not 111202 Right of Use
# Assets (an NFRS 16 lease, not a tax intangible) and not 111204 Goodwill,
# whose tax treatment is for the tax adviser to confirm.
INTANGIBLE_CATEGORIES = (
	("Software (Pool E)", "111201"),
	("Brands, Trademarks & Copyrights (Pool E)", "111203"),
)

# GLMI has no separate cylinders account; its cylinders sit in Plant & Machinery.
FIXED_ASSET_FALLBACK = {"111106": "111105"}

# Schedule-2 s.3(1) rates, unchanged from 2058 through Finance Act 2083.
POOL_RATES = {"A": 5, "B": 25, "C": 20, "D": 15}

# ERPNext needs a finite number of WDV years and writes the remainder off in
# the last one. These are the years until under 1% of cost is left
# (ln 0.01 / ln(1 - rate)), so that final write-off is immaterial.
POOL_YEARS = {"A": 90, "B": 17, "C": 21, "D": 29}

# Schedule-2 s.3(2): +1/3 on the A-D rates for special (manufacturing) industries
# and some infrastructure. Compulsory once eligible (Supreme Court 074-RB-0345).
# Empty until Accounts / the tax adviser confirm which companies qualify.
EXTRA_THIRD_COMPANIES: tuple[str, ...] = ()

# Pool fixed-asset account -> its depreciation expense account (existing chart).
DEPRECIATION_EXPENSE = {
	"111102": "555101",
	"111103": "555102",
	"111104": "555103",
	"111105": "555104",
	"111106": "555105",
	"111201": "555200",  # Amortization A/c
	"111203": "555200",
}

# Pool E finance-book row on the category. Rate and number of years are per
# asset (nepal_wdv.fill_from_tax_pool fills them from the useful life); these are
# placeholders ERPNext's category validation needs (at least one year).
POOL_E_PLACEHOLDER = {"rate_of_depreciation": 0, "total_number_of_depreciations": 1}


def setup(dry_run: bool = True) -> list[str]:
	"""Apply (or with dry_run, describe) the pool setup on every company.

	Returns one line per change or problem. Raises if the custom field is
	missing, since every category write depends on it.
	"""
	log = []
	if not frappe.get_meta("Asset Category").has_field(TAX_POOL_FIELD):
		if not dry_run:
			frappe.throw(
				f"Asset Category has no {TAX_POOL_FIELD}; run bench migrate so the fixture installs it."
			)
		log.append(f"NOTE: {TAX_POOL_FIELD} not installed yet; bench migrate adds it before applying")

	for company in frappe.get_all("Company", pluck="name", order_by="name"):
		if not _account(company, PPE_GROUP_NUMBER, is_group=1):
			log.append(f"SKIP {company}: no {PPE_GROUP_NUMBER} group, not on the pool chart")
			continue
		_ensure_accumulated_accounts(company, log, dry_run)
		_ensure_depreciation_type(company, log, dry_run)
		_ensure_intangible_categories(company, log, dry_run)

	for name in frappe.get_all("Asset Category", pluck="name", order_by="name"):
		_wire_category(frappe.get_doc("Asset Category", name), log, dry_run)

	for company in frappe.get_all("Company", pluck="name", order_by="name"):
		# Pool E categories are created above, so they do not count as having categories.
		if _account(company, PPE_GROUP_NUMBER, is_group=1) and not frappe.db.exists(
			"Asset Category", {"custom_company": company, TAX_POOL_FIELD: ["!=", "E"]}
		):
			log.append(f"TODO {company}: has the pool chart but no Asset Categories for pools A-D or Land")

	if not dry_run:
		frappe.db.commit()
	return log


def _account(company: str, number: str, is_group: int = 0) -> str | None:
	return frappe.db.get_value(
		"Account", {"company": company, "account_number": number, "is_group": is_group}, "name"
	)


def _ensure_accumulated_accounts(company: str, log: list, dry_run: bool) -> None:
	"""Create 111190 / 111290 and one contra account per existing pool fixed-asset account.

	A contra group is only created when the company has at least one fixed-asset
	account that needs it, so a company without intangible accounts gets no 111290.
	"""
	groups = {}
	for fa_number in DEPRECIATION_EXPENSE:
		fa_name = frappe.db.get_value(
			"Account", {"company": company, "account_number": fa_number, "is_group": 0}, "account_name"
		)
		number = _accumulated_number(fa_number)
		if not fa_name or _account(company, number):
			continue
		group_number, group_name, parent_number = ACCUMULATED_GROUPS[fa_number[:4]]
		if group_number not in groups:
			groups[group_number] = _account(company, group_number, is_group=1)
			if not groups[group_number]:
				parent = _account(company, parent_number, is_group=1)
				if not parent:
					log.append(f"TODO {company}: no {parent_number} group for {group_number} {group_name}")
					continue
				log.append(f"CREATE {company}: group {group_number} {group_name}")
				if not dry_run:
					groups[group_number] = _insert_account(company, group_name, group_number, parent, is_group=1)
		label = f"{group_name} - {fa_name}"
		log.append(f"CREATE {company}: {number} {label}")
		if not dry_run:
			_insert_account(company, label, number, groups[group_number], account_type="Accumulated Depreciation")


def _accumulated_number(fa_number: str) -> str:
	"""111102 -> 111192, 111201 -> 111291: same last digit, inside the prefix's contra group."""
	return ACCUMULATED_GROUPS[fa_number[:4]][0][:-1] + fa_number[-1]


def _ensure_depreciation_type(company: str, log: list, dry_run: bool) -> None:
	"""Asset Category only accepts an expense account typed Depreciation.

	555200 Amortization A/c was created as a plain expense (or untyped) on every
	company. Its type is fixed only while it has no GL entries; otherwise a
	person decides.
	"""
	for number in sorted(set(DEPRECIATION_EXPENSE.values())):
		account = frappe.db.get_value(
			"Account", {"company": company, "account_number": number, "is_group": 0}, ["name", "account_type"], as_dict=True
		)
		if not account or account.account_type == "Depreciation":
			continue
		if frappe.db.exists("GL Entry", {"account": account.name, "is_cancelled": 0}):
			log.append(f"TODO {account.name}: typed {account.account_type or 'blank'} and has GL entries")
			continue
		log.append(f"FIX {account.name}: account type {account.account_type or 'blank'} -> Depreciation")
		if not dry_run:
			frappe.db.set_value("Account", account.name, "account_type", "Depreciation")


def _ensure_intangible_categories(company: str, log: list, dry_run: bool) -> None:
	"""Create each INTANGIBLE_CATEGORIES row the company has the account for but no category.

	Only the company and its fixed-asset account are set here; _wire_category,
	which runs over every category next, fills the pool, contra, expense account
	and finance-book row like any other category.
	"""
	existing = {
		name.strip().lower()
		for name in frappe.get_all(
			"Asset Category", filters={"custom_company": company}, pluck="asset_category_name"
		)
	}
	for category_name, fa_number in INTANGIBLE_CATEGORIES:
		fa_account = _account(company, fa_number)
		if not fa_account or category_name.lower() in existing:
			continue
		log.append(f"CREATE {company}: Asset Category {category_name} on {fa_account}")
		if dry_run:
			continue
		frappe.get_doc(
			{
				"doctype": "Asset Category",
				"asset_category_name": category_name,
				"custom_company": company,
				"custom_tax_pool": "E",
				"accounts": [{"company_name": company, "fixed_asset_account": fa_account}],
			}
		).insert()


def _insert_account(company, account_name, number, parent, is_group=0, account_type=None) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Account",
				"company": company,
				"account_name": account_name,
				"account_number": number,
				"parent_account": parent,
				"is_group": is_group,
				"account_type": account_type,
			}
		)
		.insert()
		.name
	)


def _match_rule(category_name: str):
	text = category_name.lower()
	for keywords, pool, fa_number, cwip_keyword in CATEGORY_RULES:
		if all(k in text for k in keywords):
			return pool, fa_number, cwip_keyword
	return None


def _wire_category(doc, log: list, dry_run: bool) -> None:
	label = f"{doc.name} ({doc.asset_category_name.strip()})"
	rule = _match_rule(doc.asset_category_name)
	if not rule:
		log.append(f"TODO {label}: name matches no pool rule, set the pool and accounts by hand")
		return
	pool, fa_number, cwip_keyword = rule

	changes = {}
	if doc.get(TAX_POOL_FIELD) != pool:
		changes[TAX_POOL_FIELD] = pool
	non_depreciable = int(pool == NOT_DEPRECIABLE)
	if doc.non_depreciable_category != non_depreciable:
		changes["non_depreciable_category"] = non_depreciable

	# Only ever switched on (when a CWIP account is found), never off.
	enable_cwip = doc.enable_cwip_accounting
	for row in doc.accounts:
		company = row.company_name
		number = fa_number if _account(company, fa_number) else FIXED_ASSET_FALLBACK.get(fa_number)
		wanted = {"fixed_asset_account": _account(company, number) if number else None}
		if not wanted["fixed_asset_account"]:
			log.append(f"TODO {label}: {company} has no account {fa_number}")
			continue

		if non_depreciable:
			wanted["accumulated_depreciation_account"] = None
			wanted["depreciation_expense_account"] = None
		else:
			# In a dry run the 1111 9x account may not exist yet; name what it will be.
			wanted["accumulated_depreciation_account"] = _account(
				company, _accumulated_number(number)
			) or ("(new) " + _accumulated_number(number) if dry_run else None)
			wanted["depreciation_expense_account"] = _account(company, DEPRECIATION_EXPENSE.get(number))

		if cwip_keyword:
			# No match -> keep whatever is there; the TODO line asks a person to decide.
			cwip = _cwip_account(company, cwip_keyword, label, log, dry_run)
			if cwip:
				wanted["capital_work_in_progress_account"] = cwip
				enable_cwip = 1

		for field, value in wanted.items():
			if (row.get(field) or None) != value:
				changes[f"{company}: {field}"] = value
				if not dry_run:
					row.set(field, value)

	if doc.enable_cwip_accounting != enable_cwip:
		changes["enable_cwip_accounting"] = enable_cwip

	if pool in POOL_RATES or pool == "E":
		_wire_finance_book(doc, pool, label, changes, log, dry_run)

	if not changes:
		return
	log.append(f"UPDATE {label}: " + "; ".join(f"{k} -> {v}" for k, v in changes.items()))
	if not dry_run:
		doc.set(TAX_POOL_FIELD, pool)
		doc.non_depreciable_category = non_depreciable
		doc.enable_cwip_accounting = enable_cwip
		doc.save()


def _wire_finance_book(doc, pool: str, label: str, changes: dict, log: list, dry_run: bool) -> None:
	"""One default-book row: yearly WDV at the pool rate (+1/3 where the company qualifies).

	Pool E gets the same method with placeholder rate and years, because both
	depend on each asset's useful life (nepal_wdv.fill_from_tax_pool). The thirds
	rule for the first year is applied at schedule time by
	fixed_assets/nepal_wdv.py, not stored here. Rows for a named Finance Book
	are left alone.
	"""
	if pool == "E":
		years_and_rate = POOL_E_PLACEHOLDER
	else:
		companies = {row.company_name for row in doc.accounts}
		extra = {c in EXTRA_THIRD_COMPANIES for c in companies}
		if len(extra) > 1:
			log.append(f"TODO {label}: shared by companies with and without the +1/3 rate")
			return
		rate = POOL_RATES[pool] * (4 / 3 if extra == {True} else 1)
		years_and_rate = {
			"rate_of_depreciation": round(rate, 2),
			"total_number_of_depreciations": POOL_YEARS[pool],
		}

	wanted = {
		"depreciation_method": "Written Down Value",
		"frequency_of_depreciation": 12,
		**years_and_rate,
		"daily_prorata_based": 0,
	}
	row = next((r for r in doc.finance_books if not r.finance_book), None)
	current = {k: (row.get(k) if row else None) for k in wanted}
	if row and all(
		flt(current[k]) == flt(v) if k != "depreciation_method" else current[k] == v
		for k, v in wanted.items()
	):
		return
	changes["finance book"] = (
		"WDV yearly, rate and years per asset from its useful life"
		if pool == "E"
		else f"WDV {wanted['rate_of_depreciation']}% yearly, {POOL_YEARS[pool]} years"
	)
	if not dry_run:
		if not row:
			row = doc.append("finance_books", {})
		row.update(wanted)


def _cwip_account(company: str, keyword: str, label: str, log: list, dry_run: bool) -> str | None:
	"""Find the company's CWIP leaf under 111300 by name, fixing its type if it has no GL entries."""
	group = _account(company, CWIP_GROUP_NUMBER, is_group=1)
	candidates = frappe.get_all(
		"Account",
		filters={"company": company, "parent_account": group, "is_group": 0},
		fields=["name", "account_name", "account_type"],
	)
	match = next((a for a in candidates if keyword in a.account_name.lower()), None)
	if not match:
		log.append(f"TODO {label}: {company} has no CWIP account named like '{keyword}'")
		return None
	if match.account_type != "Capital Work in Progress":
		if frappe.db.exists("GL Entry", {"account": match.name, "is_cancelled": 0}):
			log.append(f"TODO {label}: {match.name} is typed {match.account_type} and has GL entries")
			return None
		log.append(f"FIX {match.name}: account type {match.account_type} -> Capital Work in Progress")
		if not dry_run:
			frappe.db.set_value("Account", match.name, "account_type", "Capital Work in Progress")
	return match.name


# Tax Pool -> the fixed-asset accounts (by number) that hold that pool's cost.
# The accumulated and expense accounts follow from the fixed-asset account
# (_accumulated_number, DEPRECIATION_EXPENSE), so one table decides all three.
POOL_FIXED_ASSET_ACCOUNTS = {
	"A": ("111102",),
	"B": ("111103",),
	"C": ("111104",),
	"D": ("111105", "111106"),  # plant & machinery, cylinders
	"E": ("111201", "111203"),  # software, trademarks
}


def validate_pool_accounts(doc, method=None) -> None:
	"""Asset Category validate: every account must belong to the category's Tax Pool.

	The pool accounts differ only by "Pool A" / "Pool B" deep in a long name, so
	picking a neighbour from the dropdown is easy and silent: depreciation would
	then credit one pool while the cost sits in another, and both pools (and the
	tax report) would be wrong. Found when a Generator category was saved with
	Pool A's accumulated depreciation (demo-nggroup, 2026-11-06).

	Rows of a company not on the numbered pool chart are skipped. Throws with
	the wrong account and the one expected.
	"""
	pool = doc.get(TAX_POOL_FIELD)
	allowed = POOL_FIXED_ASSET_ACCOUNTS.get(pool)
	if not allowed:
		return
	problems = []
	for row in doc.get("accounts") or []:
		fa = frappe.db.get_value("Account", row.fixed_asset_account, "account_number") if row.fixed_asset_account else None
		if not fa:
			continue
		if fa not in allowed:
			problems.append(
				frappe._("{0}: Fixed Asset Account {1} is not a Pool {2} account (use {3})").format(
					row.company_name, row.fixed_asset_account, pool, " / ".join(
						_account(row.company_name, n) or n for n in allowed
					)
				)
			)
			continue
		expected = {
			"accumulated_depreciation_account": _accumulated_number(fa),
			"depreciation_expense_account": DEPRECIATION_EXPENSE[fa],
		}
		for field, number in expected.items():
			want = _account(row.company_name, number)
			if want and row.get(field) != want:
				problems.append(
					frappe._("{0}: {1} is {2}, should be {3}").format(
						row.company_name, row.meta.get_label(field), row.get(field) or frappe._("empty"), want
					)
				)
	if problems:
		frappe.throw(
			"<br>".join(problems),
			title=frappe._("Accounts do not match Tax Pool {0}").format(pool),
		)


def years_for_pool(pool: str | None) -> int | None:
	"""Yearly rows ERPNext should build for a pool; None when the pool gives none.

	Nepali law has no "number of years": A-D run at their rate until the pool
	is used up, E until the right expires. ERPNext still needs a count, so A-D
	get POOL_YEARS and E the placeholder (each Pool E asset replaces it, see
	nepal_wdv.fill_from_tax_pool).
	"""
	if pool in POOL_YEARS:
		return POOL_YEARS[pool]
	if pool == "E":
		return POOL_E_PLACEHOLDER["total_number_of_depreciations"]
	return None


def fill_category_years(doc, method=None) -> None:
	"""Asset Category before_validate: Total Number of Depreciations from the Tax Pool.

	The field is hidden and not mandatory on screen (Property Setter fixtures
	on Asset Finance Book), so a category made or edited in the desk would
	otherwise reach ERPNext's "cannot be less than 1" check with nothing a
	person can fix. Throws only when a depreciating row is left with no count
	and the category has no pool to take one from.
	"""
	years = years_for_pool(doc.get(TAX_POOL_FIELD))
	for row in doc.get("finance_books") or []:
		if years:
			row.total_number_of_depreciations = years
		elif not row.total_number_of_depreciations:
			frappe.throw(
				frappe._("Set the Tax Pool of {0}: the number of depreciation years comes from it.").format(
					doc.name or doc.asset_category_name
				),
				title=frappe._("Tax Pool needed"),
			)
