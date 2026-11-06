# sales_purchase

The Selling and Buying dashboards shown at the top of the stock **Selling**
(`/app/selling`) and **Buying** (`/app/buying`) workspaces.

## Entry points

| What | Where |
| --- | --- |
| Data (whitelisted) | `dashboard.get_dashboard(mode, company, branch, period, …)` and `dashboard.get_menu(mode)` (the reports list) |
| Page script | `public/js/trade_dashboard.js` (+ `public/css/trade_dashboard.css`) |
| Placement on the workspace | `public/js/trade_workspace.js`, loaded from `app_include_js` in `hooks.py` |

`mode` is `selling` or `buying`. The two sides share one implementation;
`MODES` in `dashboard.py` holds what differs (doctype, party field, roles).

## Who sees what

- Roles per side are in `MODES[...]["roles"]` (and copied in `trade_workspace.js`).
- Every figure goes through `frappe.get_list`, so Company / Branch User
  Permissions and the fiscal-year access rule apply exactly as in list views.
  Strict user permissions is off, so a branch-restricted user also sees bills
  with no branch set — same as their Sales Invoice list.
- Cards for a doctype the user cannot read are left out; reports the user's
  role cannot open are not listed. A chosen report runs inside the dashboard
  as the real report page (in a frame), so its own permission checks apply.

## Deliberately not here

- **Receivable / payable and ageing.** Most Sales Invoices still carry an
  `outstanding_amount` (payments went through unmatched Journal Entries), and the
  GL route is ~40s on 5.6M GL rows. Use Debtors Summary / Accounts Receivable.
- Purchase Order and Material Request have no branch field, so the branch filter
  does not narrow them; the card says "all branches".

No doctypes, no scheduled jobs, nothing writes. Answers are cached per user and
filter for 5 min (month) / 30 min (fiscal year); the refresh button bypasses it.
