# Selling & Buying dashboards

Dashboards at the top of the stock **Selling** (`/app/selling`) and **Buying**
(`/app/buying`) workspaces, in the same style as the HR Dashboard on `/app/hr`.
Code: `avinashgroup_app/sales_purchase/` (see its README for entry points).

## What a user sees

```
[ hero: Company ▾  Branch ▾  Month | Fiscal year  ‹ Kartik 2083 ›  ⟳ ]
[       Net sales  Rs 89.85 Cr   ▼48% vs same days of last period    Bills | Parties | Avg bill ]
[ Sales | Returns | Money received ]
[ Trend: columns = this period, grey line = previous ]     [ Top customers / suppliers ]
[ By branch | By company ]
[ Top items ]
[ Reports: list of the user's reports → each opens in a new tab ]
```

- Amounts are excl. VAT (`base_net_total`); the hero also shows incl. VAT.
- "Same days of" compares only as far into the previous period as we are into
  this one (day 19 of Kartik vs days 1–19 of Ashwin).
- **No shortcuts.** Tiles and customer rows are information only; clicking a
  company bar only narrows the dashboard itself.
- **Reports open in a new tab.** The list shows only reports the user's role
  may open (Report roles + Custom Role, same check as the report page). Each
  report is a link to the desk's own report page, opened in a new tab, with the
  dashboard's company, branch (`branch` filter) and period filled in; a report
  sets only the filters it has. The links follow the dashboard: change the
  company or period and the next report opened uses the new values.
- Selling = blue, Buying = violet; light and dark desk themes both work.

## Hidden for now (kept in code, switched off)

To keep the page to figures and reports, these are turned off — nothing is
deleted, each comes back with one change:

| Part | Switch |
| --- | --- |
| Report list groups Transactions, Masters (document lists, not reports) | `HIDDEN_MENU_GROUPS` in `sales_purchase/dashboard.py` — remove the label |
| Non-report links inside menu groups (e.g. "Letters of Credit") | `SHOW_DOCUMENT_LINKS = True` in `dashboard.py` |
| "Waiting for next step" card (open quotations, orders, receipts, drafts) | `SHOW_PIPELINE = True` in `dashboard.py` |
| Quick actions card | `SHOW_QUICK_ACTIONS = true` in `public/js/trade_dashboard.js` |
| "New order" quick action | re-add the commented line in `TEXT.selling/buying.actions` |

After changing the payload shape, bump the cache key prefix
(`trade_dashboard:v2:`) so users do not get an old cached answer.

## Who sees what

| Side | Roles |
| --- | --- |
| Selling | Sales User, Sales Manager, Accounts User, Accounts Manager, System Manager |
| Buying | Purchase User, Purchase Manager, Accounts User, Accounts Manager, System Manager |

Every number is read with `frappe.get_list`, so it follows role permissions,
Company / Branch User Permissions and the fiscal-year access rule — the same
rows the user sees in the list view. Strict user permissions is off, so a
branch-restricted user also sees bills with no branch set.

Checked on mysite1 (2026-11-04) as `jiwan.chhatkuli@nepalgas.com.np` (Sales User,
NGG Chitwan only): only NGG in the company list, only Chitwan in the branch list,
another company/branch in the request → PermissionError, no Buying dashboard.

## Known limits

- **No receivable / payable card.** 239,722 of 292,376 submitted Sales Invoices
  still carry an `outstanding_amount` (payments made by Journal Entry without
  being matched), so invoice-based ageing reports ~Rs 27.5 billion. The GL route
  takes ~40s on 5.6M GL rows. Use Debtors Summary / Accounts Receivable.
- **Branch is mostly empty** outside GEPL (~7% of Sales Invoices have
  `custom_branch`), so the NG companies show mostly "No branch".
- Purchase Order and Material Request have no branch field; with a branch
  picked, their queue counts are for all branches and say so.
- Money received/paid counts Payment Entries only, not Journal Entries.
- Speed: answers are cached per user + filter, 5 min (month) / 30 min (fiscal
  year); ⟳ skips the cache. Cold load on mysite1 (128 MB InnoDB buffer pool):
  ~5s month, ~30s fiscal year for all companies.

## Gotchas found building it

- `frappe.require` picks its loader from the file extension — a `?v=1` on the
  asset URL throws `this._handlers[...] is not a function`.
- Each company has its own item codes for the same product, so top items are
  grouped by item name + stock UOM.
