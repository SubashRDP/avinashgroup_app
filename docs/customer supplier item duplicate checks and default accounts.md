# Customer / Supplier / Item — Duplicate Checks & Default Accounting Row

**App:** `avinashgroup_app`
**Author:** Abhidha
**Date:** 2026-06-28
**Status:** ✅ Implemented (client-side) — needs `bench restart` / clear-cache + browser hard-refresh

Today's changes, in order. Each task: **What & why → How it works → Files → How to test → Gotcha.**

All four are **client-side form scripts** (`doctype_js`) — there is no server hook and no schema
change. Everything is scoped to the master's **`custom_company`** field (the custom "Company" Link
on Customer / Supplier / Item; the standard masters have no native company field).

---

## 1. Duplicate Tax ID warning — Customer & Supplier

**What & why:** When creating/saving a Customer or Supplier, if **another** party of the same type
in the **same company** already uses the same `tax_id`, warn the user before the save commits. The
same tax_id under a **different** company is allowed (stays silent).

**How it works:**
- On the form `validate` event, an async check queries for another record with the same `tax_id`
  + `custom_company` (excluding the current doc).
- If found, the save is paused (`frappe.validated = false`) and a `frappe.confirm` shows:
  *"Tax ID **{id}** already exists for company **{company}** (Customer/Supplier **{ID}**). Do you
  want to continue?"* — **[Yes] [No]**.
- **Yes** → save proceeds. **No** → save aborts, nothing written. The **{ID}** is a clickable link
  to the existing record (`/app/customer/<name>` or `/app/supplier/<name>`).
- Non-blocking by design — it only gates on the user's answer, it never hard-`throw`s.

**Files:**
- `public/js/party_duplicate_check.js` — `check_party_duplicates`, `find_duplicate`,
  `confirm_save`, `party_link`.
- `hooks.py` — `doctype_js` for **Customer** and **Supplier**.

**How to test:** Create a second Customer in the same company with a tax_id that already exists →
confirm dialog appears with the linked ID and "Do you want to continue?". Use a different company →
no dialog.

---

## 2. Duplicate Name warning — Customer & Supplier

**What & why:** Same idea as #1, but for the party **name** (`customer_name` / `supplier_name`)
within the same company.

**How it works:**
- Same `validate` handler, checked **before** the tax_id check. If a same-company duplicate name
  exists, a `frappe.confirm` shows:
  *"Customer/Supplier **{name}** already exists for company **{company}** (**{ID}**). Do you want
  to create it again?"* — **[Yes] [No]**.
- **No** on the name dialog aborts the save immediately (the tax_id check is skipped). **Yes**
  continues to the tax_id check.
- The two checks use **different questions** on purpose: name → *"Do you want to create it again?"*,
  tax_id → *"Do you want to continue?"*.

**Files:** same as #1 (`public/js/party_duplicate_check.js`).

**How to test:** Create a second Customer with an existing name in the same company → name dialog →
No aborts, Yes continues to the tax_id check (if any).

---

## 3. Default Accounting Row — Customer & Supplier

**What & why:** The **Default Accounts** (`accounts`, child *Party Account*) table should start with
**one row** pre-filled with the selected company, so users don't have to add it manually.

**How it works:**
- On `refresh` and on `custom_company` change: if the `accounts` table is **empty**, add one row
  with `company = custom_company`.
- If a row already exists, the default row's `company` is **always kept in sync** with the selected
  company — change the company A → B and the row's Company flips to B too.

**Files:**
- `public/js/party_default_account.js` — `ensure_default_account_row`.
- `hooks.py` — same `doctype_js` entries as #1 (Customer & Supplier load both JS files).

**How to test:** New Customer/Supplier → pick Company → one accounting row appears with that company.
Change the company → the row's Company updates.

> ⚠️ The shared `company_filter.js` also removes child-table rows whose company no longer matches the
> form's company (and shows a "Removed N row(s)…" toast). Our script re-adds/syncs the row, so the
> end state is correct; the toast is a separate, pre-existing behaviour.

---

## 4. Default Accounting Row — Item Master

**What & why:** Same as #3 for the **Item** master's **Item Defaults** (`item_defaults`, child
*Item Default*) table — one row by default, Company auto-filled from the Item's `custom_company`.

**How it works:** Identical logic to #3 (`ensure_default_item_row`): empty → add one row with
`company = custom_company`; otherwise keep the default row's company synced on company change.

**Files:**
- `public/js/item_default_account.js` — `ensure_default_item_row`.
- `hooks.py` — `doctype_js` for **Item**.

**How to test:** New Item → pick Company → one Item Defaults row appears with that company. Change
the company → the row's Company updates.

---

## Files changed — summary

| File | Change |
|------|--------|
| `public/js/party_duplicate_check.js` | **New** — duplicate name + tax_id confirm dialogs (Customer/Supplier). |
| `public/js/party_default_account.js` | **New** — default `accounts` row, company auto-fill/sync. |
| `public/js/item_default_account.js` | **New** — default `item_defaults` row, company auto-fill/sync. |
| `hooks.py` | `doctype_js` entries for Customer, Supplier (two files each) and Item. |

## Deploy notes
- **Client-side only** — no Python, no schema/migration.
- After deploy: `bench --site <site> clear-cache && bench restart`, then **hard-refresh** the
  browser (Ctrl+Shift+R) so the new JS loads.
