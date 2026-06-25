# Product Wise Invoice Customer Portal

**App:** `avinashgroup_app`
**Author:** Abhidha
**Status:** ✅ Implemented & verified on `mysite1` (deploy + restart workers on live)

Today's changes, in order. Each task: **What & why → How it works → Files → How to test → Gotcha.**

---

## 1. Party Ledger — "Show Contract Form" default ON

**What & why:** The `show_contract_form` filter now defaults to **checked (1)**. Previously it
defaulted to unchecked, which *hid* Journal Entries of JV type "Contract Form". Default-on means
those entries are **included** by default; the user can untick to hide them.

**How it works:**
- Only the **filter default** changed (`0` → `1`) in the report JS; the server logic was already
  in place. When the box is **ticked**, the report skips the `NOT EXISTS` clause that excludes
  `Journal Entry.custom_p_type = 'Contract Form'`; when unticked, those JEs are excluded.
- Applied to the shared `conditions`, so opening balance + period rows stay consistent.

**Files:**
- `avinash_group_app/report/party_ledger/party_ledger.js` — filter `default: 0` → `default: 1`
  (and the explanatory comment flipped).
- `avinash_group_app/report/party_ledger/party_ledger.py` — existing `show_contract_form` gate
  (unchanged).

**How to test:** Open **Party Ledger** → "Show Contract Form" is ticked → Contract-Form JEs appear
in the ledger. Untick → they disappear.

> ⚠️ Client-side default only — hard-refresh the report page so the browser loads the updated JS.

---

## 2. Customer Statement — hide deposit / security accounts

**What & why:** The customer-facing **Customer Statement** must not show deposit / security
accounts (cylinder deposits, dealer security deposit), and they must not affect the running
balance. These are not trade balances and shouldn't appear on a customer's statement.

**How it works:**
- Added a **gated** exclusion to Party Ledger's `execute`: when the caller passes
  `exclude_account_patterns` (a list of `account_name` LIKE patterns), it adds
  `gle.account NOT IN (SELECT name FROM tabAccount WHERE account_name LIKE …)` to the shared
  conditions — so **opening + period rows** both drop them and the running balance stays correct.
- Matched on **`account_name`** (not the numbered id), so every company's variant is excluded
  regardless of its number/abbr suffix.
- The Customer Statement page passes the patterns in both `get_statement` (screen) and
  `download_pdf`.

**Excluded accounts** (`EXCLUDE_ACCOUNT_PATTERNS`):
| Pattern | Account |
|---------|---------|
| `Deposit Customers Cylinders%` | 313101 Deposit Customers Cylinders (I) |
| `Record of Deposit Cylinders%` | 313102 Record of Deposit Cylinders (1013) |
| `%Security Deposit%Dealer%` | 313201 Security Deposit from Dealers (live server) |

**Files:**
- `avinash_group_app/report/party_ledger/party_ledger.py` — new gated
  `exclude_account_patterns` block (after the Contract-Form gate).
- `templates/pages/customer_statement.py` — `EXCLUDE_ACCOUNT_PATTERNS` constant, passed in
  `get_statement` and `download_pdf`.

**How to test:** Open `/customer_statement` for a customer who has deposit-account entries →
those lines are gone (screen + PDF). The **desk Party Ledger report still shows them** (it
doesn't pass the filter). Verified on Karnali: 17,683 → 17,440 rows (243 deposit lines dropped),
no SQL errors.

> ⚠️ The desk report is unaffected by design. The dealer account doesn't exist on `mysite1`; the
> `%Security Deposit%Dealer%` pattern catches it on the live server. If its name won't contain
> both "Security Deposit" and "Dealer", update the pattern.

---

## 3. Product Wise Invoice Details — new customer portal page

**What & why:** A customer self-service version of the **Sales Analysis Product-wise Invoice
Details** report, scoped to the logged-in customer's own customer(s), **with returns** and
**without Agent rows**.

**How it works:**
- New portal page at **`/product_wise_invoice_details`** (title "Product Wise Invoice Details").
- **Security:** reuses the Customer Statement guard — `_get_portal_customers`,
  `_get_allowed_companies`, `_resolve_request` — so a portal user only ever sees their own
  customers (empty selection → their customers in the company, never "all").
- **Reuse:** `get_data` calls the report's `build_rows(filters, include_return, include_agent=False)`
  — `include_agent=False` drops the "No Agent" / Agent Sales / Returns / Net rows. Rows are
  flattened by `_shape` (product / customer / section / invoice / summary) for an HTML table.
- **Filters:** Company (defaults to **Nepal Gas Karnali** when available), From/To date
  (AD `YYYY-MM-DD` text + Nepali BS picker), **Include Return** toggle (default on).

**UI styling (this page):** all text black; header bar grey (`#6c757d`); proper checkbox with
black accent; product/customer rows show **Code in column 1, Name in column 2** with a gap above
each product block; the "Invoice"/"Return" label sits in the Invoice Number column.

**Files:**
- `templates/pages/product_wise_invoice_details.py` — `get_context`, whitelisted `get_data`,
  `_shape`.
- `templates/pages/product_wise_invoice_details.html` — filters + table render (inline JS).
- Reuses `avinash_group_app/report/sales_analysis_product_wise_invoice_details/`.

**How to test:** Log in as a customer portal user → `/product_wise_invoice_details` → pick a
company with data (e.g. Nepal Gas Karnali) → product → customer → Invoice + Return rows, **no
Agent rows**.

> ⚠️ If the default company has no sales (e.g. Grihalaxmi) you'll see "No invoices found" — switch
> the Company dropdown. Server-side change → the dev server auto-reloads; on live, restart workers.

---

## Files changed — summary

| File | Change |
|------|--------|
| `report/party_ledger/party_ledger.js` | `show_contract_form` default `0` → `1`. |
| `report/party_ledger/party_ledger.py` | Gated `exclude_account_patterns` exclusion (opening + period). |
| `templates/pages/customer_statement.py` | `EXCLUDE_ACCOUNT_PATTERNS`; passed in `get_statement` + `download_pdf`. |
| `templates/pages/product_wise_invoice_details.py` | **New** — portal page server (get_context, get_data, _shape). |
| `templates/pages/product_wise_invoice_details.html` | **New** — portal page UI. |
| `docs/Docs of Reports- Abhidha.md` | Updated to document the above (Party Ledger, Customer Statement, new portal page). |

## Deploy notes
- Python changes (party_ledger.py, customer_statement.py, the new portal page) need the web
  workers reloaded — auto on the dev server; **`bench restart`** on live.
- JS change (party_ledger.js) — hard-refresh the browser.
- No schema/migration changes.
