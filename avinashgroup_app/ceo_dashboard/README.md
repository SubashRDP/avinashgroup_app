# ceo_dashboard

The group-level CEO Dashboard at **/app/ceo-dashboard**: one screen for all
companies that cross-filters like a Power BI report (click a company, month,
segment or customer and every other chart narrows to it).

## Entry points

| What | Where |
| --- | --- |
| Data (whitelisted) | `api.get_dashboard(fiscal_year=None, force=0)`, `api.get_customer_invoices(...)` (drill-down) |
| Week figures (whitelisted) | `periods.get_days(fiscal_year, from_date, to_date)`: one week and the same weekdays 52 weeks earlier, for the Week period |
| Chart day rows (whitelisted) | `charts.get_daily(fiscal_year, from_date, to_date, prev_from, prev_to, customer=None)`: per-day totals so week / month / quarter charts can be drawn day by day or week by week |
| Money (whitelisted) | `money.get_money(fiscal_year=None, force=0)`: ledger balances (cash and bank, bank loans, customers, suppliers) at each month end, and gas purchase cost for the margin per kg |
| Compare chart (whitelisted) | `series.get_series(fiscal_year, years_back, force)`: day rows for sales, collections, purchases and expenses over the timeline |
| Buying (whitelisted) | `buying.get_buying(fiscal_year, years_back, force)`: Purchase Invoice rows per day x company x supplier x category (LP Gas / Direct expenses / Indirect expenses / Fixed assets / Other, from the Item Group name) and supplier payments, on the sales timeline |
| Credit snapshot | `credit_snapshot.build()` (cron every 4 h via hooks.py, queues on long), `credit_snapshot.get_credit()`, `credit_snapshot.refresh()` |
| Page (desk route, roles) | `avinash_group_app/page/ceo_dashboard/` |
| Dashboard script / styles | `public/js/ceo_dashboard.js`, `public/css/ceo_dashboard.css` |

The page loader adds its own `?v=` to the two asset URLs. **When you change
either file, bump `CEO_DASHBOARD_ASSET_VERSION` in the page's .js and the
`modified` stamp in its .json**, re-import the Page (or migrate), then
`frappe.clear_cache()` (each user's cached boot info holds the old stamp).
Without that, browsers keep the old file for up to a year.

## Who sees it

Roles `Group CEO`, `System Manager`, `Accounts Manager` (in `api.ROLES` and the
Page JSON). Company User Permissions narrow the companies; nothing finer, since
the figures are read with raw SQL for speed.

## Deliberately not here

Fixing or flagging the books: money figures are shown exactly as the ledger
has them (the user handles bad data). Also not here: receipts booked through
Journal Entry (collections count Payment Entries only), fixed assets, and any
margin beyond gas (sale price minus gas purchase price).

No doctypes. One scheduled job (credit snapshot, every 4 hours); its JSON file in the site's private folder is the only thing written. One answer per fiscal year (sales, and money separately) is
cached for 30 minutes; the Refresh button bypasses it. See docs/ceo-dashboard.md.
