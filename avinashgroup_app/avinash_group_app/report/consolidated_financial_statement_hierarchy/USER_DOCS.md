# Consolidated Financial Statement Hierarchy — User Documentation

## What This Report Does

Generates a consolidated Balance Sheet, Profit & Loss Statement, or Cash Flow report across any set of companies — **without** requiring a parent group company in ERPNext.

ERPNext's built-in "Consolidated Financial Statement" report requires all selected companies to share a common parent company in the Company master. This report removes that requirement: you pick any combination of companies and it consolidates them directly.

---

## Filters

| Filter | Type | Required | Description |
|---|---|---|---|
| **Companies** | MultiSelect | No | Companies to consolidate. Leave empty to include **all** companies. |
| **Filter Based On** | Select | Yes | Choose **Fiscal Year** or **Date Range**. |
| **Start Year / End Year** | Fiscal Year Link | Yes (if Fiscal Year) | Fiscal year range to report on. |
| **Start Date / End Date** | Date | Yes (if Date Range) | Explicit date range. |
| **Finance Book** | Link | No | Restrict GL entries to a specific Finance Book. |
| **Report** | Select | Yes | One of: **Balance Sheet**, **Profit and Loss Statement**, **Cash Flow**. |
| **Currency** | Select | No | Presentation currency for all amounts. |
| **Accumulated Values in Group Company** | Check | No | Standard ERPNext option — accumulates child amounts into group account rows. |
| **Include Default FB Entries** | Check | No | Include GL entries that have no Finance Book assigned (always-on by default). |
| **Show Zero Values** | Check | No | Show account rows even when all amounts are zero. |
| **Account Hierarchy Level** | Select | No | Collapse the account tree to a chosen depth. See below. |

### Companies Filter Behaviour

- **One or more selected** → only those companies are consolidated.
- **None selected (blank)** → every Company in the system is included, ordered by the company tree's left-right position for stable column ordering.
- The filter defaults to your user's default company on load.

### Filter Based On

Switching between Fiscal Year and Date Range shows/hides the relevant date filters automatically. Selecting a fiscal year auto-fills the corresponding start/end dates.

---

## How Consolidation Works

### Step 1 — Company Resolution (`resolve_companies`)

The report reads the **Companies** multi-select. If it is empty, it fetches all companies from the database. The result is a de-duplicated, ordered list of companies.

### Step 2 — Representative Company

ERPNext's consolidation engine needs one "anchor" company for currency lookups and a few labels. The report picks:

1. Your user default company, **if** it is in the selected list; otherwise
2. The first company in the selected list.

This company is set as `filters.company` purely for ERPNext's internal plumbing — it does **not** limit which GL entries are fetched.

### Step 3 — Monkey-patching ERPNext (`run_consolidated`)

ERPNext's `consolidated_financial_statement.execute()` has two internal functions that read the group-company tree:

- `get_companies(filters)` — returns the set of companies and their GL accumulation map.
- `set_gl_entries_by_account(...)` — fetches GL entries for each company.

This report temporarily replaces these functions with patched versions:

- **Patched `get_companies`** → returns the explicitly selected list; maps each company to itself (no parent accumulation).
- **Patched `set_gl_entries_by_account`** → instead of fetching every raw GL Entry row (hundreds of thousands of rows shipped to Python), it runs **one aggregated SQL query per report run** that sums debit/credit per account × company × opening/period bucket, then feeds ERPNext's unchanged maths two synthetic "entries" per account/company. Numerically identical, orders of magnitude faster.
- **Patched `get_account_type_based_gl_data`** (Cash Flow) → one grouped query for all companies and account types instead of one query per company per account type. This also fixes an ERPNext bug where every company column of the consolidated Cash Flow showed the *representative* company's values (ERPNext's SQL reads `%(company)s` from filters, ignoring the function's `company` argument).
- **Patched `get_accounts`** → fetches the account heads of all selected companies in one query instead of one per company.

After ERPNext's `execute()` returns, the original functions are restored (even if an exception occurs). All of ERPNext's account-key merging, column generation, and total row logic runs unchanged.

**Performance:** for full speed the site needs the `fin_stmt_agg_index` covering index on `tabGL Entry` (created by patch `avinashgroup_app.patches.add_gl_entry_fin_stmt_agg_index` on `bench migrate`). Without it the aggregation falls back to a full-table scan (~2–3 s on ~500k GL rows); with it the report returns in well under a second.

### Step 4 — Shared Account Filtering (Balance Sheet / P&L only)

ERPNext builds one column per company. When a leaf account exists in company A but not company B, ERPNext still shows the row — it just shows zero for company B. This report **hides** those non-universal accounts instead.

**Logic (`get_shared_account_keys` + `filter_shared_accounts`):**

1. For each selected company, fetch all accounts with the relevant root types (Asset/Liability/Equity for Balance Sheet; Income/Expense for P&L).
2. Build a coverage map: `account_key → {set of companies that have it}`.
3. An account is "shared" only when its coverage set equals all selected companies.
4. Any account row whose `account_name` is **not** in the shared set is dropped from the output.

**What happens to the dropped amounts?**
ERPNext already rolls every child's amounts up into its parent during data preparation. Dropping a non-shared leaf row does **not** distort any totals — the parent's column values already contain that child's contribution.

**Orphan repair:** when a dropped account is a *group* whose children **are** shared, the surviving children are re-parented to their nearest kept ancestor (with indentation recomputed) so the tree never contains rows pointing at removed parents.

**What is never dropped:**
- Blank separator rows (no `account` field).
- Synthetic total rows — identified by `account_name` starting and ending with a single quote (e.g., `'Total Asset (Debit)'`).

Cash Flow reports are **excluded** from this filter because their rows are predefined (not driven by the company's account master).

### Step 5 — Account Hierarchy Level (optional)

When an **Account Hierarchy Level** is chosen (e.g., level 2), the report collapses the tree so that:

- Each root-to-leaf path shows values only at the chosen depth.
- If a branch is **shallower** than the chosen level, values appear on its deepest node.
- Nodes **above** the value node are shown as structural rows (no amounts).
- Nodes **below** the value node are hidden entirely.
- Synthetic/total rows are always kept intact.

**Example — level 2 on a 4-deep tree:**

```
Assets                       ← structural (no value)
  Current Assets             ← VALUE shown here (depth 2)
    Cash and Equivalents     ← hidden
      Petty Cash             ← hidden
  Fixed Assets               ← VALUE shown here (depth 2)
    Machinery                ← hidden
```

Note: company-specific (non-shared) accounts are dropped in Step 4 with their sums rolled into the nearest shared ancestor. In a level view that ancestor may be structural (blank), so the visible rows at the chosen level can sum to less than the section total — the difference is the rolled-up company-specific amounts. The synthetic Total rows are always complete.

The level dropdown is populated dynamically: when the page loads (and whenever the **Report** type changes), the frontend calls `get_max_account_depth` to find the deepest account in the representative company and builds options 1 through max-depth.

---

## Columns

Columns are generated by ERPNext's standard consolidation engine:

| Column | Description |
|---|---|
| **Account** | Account name, rendered as a tree (bold for root accounts). Clicking opens the General Ledger for that account. |
| **[Company Name]** | One column per selected company, showing that company's amount in the presentation currency. |
| **Total** | Sum across all company columns for that row. |

---

## Access Control

The report is visible to users with any of these roles:

- Accounts User
- Accounts Manager
- Auditor

---

## Key Differences from ERPNext's Built-in Report

| Feature | ERPNext Built-in | This Report |
|---|---|---|
| Requires group company | Yes | No |
| Company selection | Children of one parent | Any arbitrary set |
| Non-universal accounts | Shown as zero | Hidden (rolled into parent) |
| Account depth cap | No | Yes (Account Hierarchy Level) |

---

## Common Usage Scenarios

**1. Compare two independent subsidiaries side by side**
Select both companies in the Companies filter. Each gets its own column; totals appear in the last column. Only accounts that both companies share are shown.

**2. Organisation-wide Balance Sheet with no group setup**
Leave Companies blank. Every company in the system is included. Use Account Hierarchy Level = 2 or 3 to get a high-level summary without drilling into every leaf account.

**3. Executive summary P&L**
Set Report = "Profit and Loss Statement", select the desired fiscal year, and set Account Hierarchy Level = 1 to see only root-level Income and Expense totals per company.

**4. Cash flow across entities**
Set Report = "Cash Flow". The shared-account filter and hierarchy level filter are both bypassed; you see the standard ERPNext cash flow layout with one column per company.
