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
   contra account per pool fixed-asset account (111102 -> 111192, ...);
2. sets ``custom_tax_pool``, the four accounts, CWIP accounting and the
   non-depreciable flag on each category, matching on its name
   (``CATEGORY_RULES``).

It is idempotent: a second run changes nothing. ``dry_run=True`` (the default)
only reports.

Deliberately NOT done here:

- depreciation method / rate / finance book rows. Whether the books use
  written-down value at the tax rates or NFRS straight-line is the
  auditors' decision, which is still open;
- the tax computation itself (thirds rule, disposals, 7% repair cap,
  +1/3 for special industries). That is a report built on ``custom_tax_pool``;
- creating categories for a company that has none, or guessing the pool of a
  category whose name matches no rule. Both are reported for a person to fix;
- touching ``345109`` or renaming any existing account.

Run from ``bench --site <site> console``::

    from avinashgroup_app.fixed_assets.tax_pools import setup
    print("\\n".join(setup(dry_run=True)))

Rules and sources: ``docs/fixed-assets-tax-pools.md``.
"""

import frappe

TAX_POOL_FIELD = "custom_tax_pool"  # Custom Field fixture "Asset Category-custom_tax_pool"
NOT_DEPRECIABLE = "Not Depreciable"

PPE_GROUP_NUMBER = "111100"  # "Property, Plant and Equipment", parent of the pool accounts
ACCUMULATED_GROUP_NUMBER = "111190"
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
)

# GLMI has no separate cylinders account; its cylinders sit in Plant & Machinery.
FIXED_ASSET_FALLBACK = {"111106": "111105"}

# Pool fixed-asset account -> its depreciation expense account (existing chart).
DEPRECIATION_EXPENSE = {
	"111102": "555101",
	"111103": "555102",
	"111104": "555103",
	"111105": "555104",
	"111106": "555105",
}


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
		ppe_group = _account(company, PPE_GROUP_NUMBER, is_group=1)
		if not ppe_group:
			log.append(f"SKIP {company}: no {PPE_GROUP_NUMBER} group, not on the pool chart")
			continue
		_ensure_accumulated_accounts(company, ppe_group, log, dry_run)

	for name in frappe.get_all("Asset Category", pluck="name", order_by="name"):
		_wire_category(frappe.get_doc("Asset Category", name), log, dry_run)

	for company in frappe.get_all("Company", pluck="name", order_by="name"):
		if _account(company, PPE_GROUP_NUMBER, is_group=1) and not frappe.db.exists(
			"Asset Category Account", {"company_name": company, "parenttype": "Asset Category"}
		):
			log.append(f"TODO {company}: has the pool chart but no Asset Categories")

	if not dry_run:
		frappe.db.commit()
	return log


def _account(company: str, number: str, is_group: int = 0) -> str | None:
	return frappe.db.get_value(
		"Account", {"company": company, "account_number": number, "is_group": is_group}, "name"
	)


def _ensure_accumulated_accounts(company: str, ppe_group: str, log: list, dry_run: bool) -> None:
	"""Create 111190 and one contra account per existing pool fixed-asset account."""
	group = _account(company, ACCUMULATED_GROUP_NUMBER, is_group=1)
	if not group:
		log.append(f"CREATE {company}: group {ACCUMULATED_GROUP_NUMBER} Accumulated Depreciation")
		if not dry_run:
			group = _insert_account(company, "Accumulated Depreciation", ACCUMULATED_GROUP_NUMBER, ppe_group, is_group=1)

	for fa_number in DEPRECIATION_EXPENSE:
		fa_name = frappe.db.get_value(
			"Account", {"company": company, "account_number": fa_number, "is_group": 0}, "account_name"
		)
		number = _accumulated_number(fa_number)
		if not fa_name or _account(company, number):
			continue
		log.append(f"CREATE {company}: {number} Accumulated Depreciation - {fa_name}")
		if not dry_run:
			_insert_account(
				company,
				f"Accumulated Depreciation - {fa_name}",
				number,
				group,
				account_type="Accumulated Depreciation",
			)


def _accumulated_number(fa_number: str) -> str:
	"""111102 -> 111192: same last digit, inside the 111190 group."""
	return ACCUMULATED_GROUP_NUMBER[:-1] + fa_number[-1]


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
			wanted["depreciation_expense_account"] = _account(company, DEPRECIATION_EXPENSE[number])

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

	if not changes:
		return
	log.append(f"UPDATE {label}: " + "; ".join(f"{k} -> {v}" for k, v in changes.items()))
	if not dry_run:
		doc.set(TAX_POOL_FIELD, pool)
		doc.non_depreciable_category = non_depreciable
		doc.enable_cwip_accounting = enable_cwip
		doc.save()


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
