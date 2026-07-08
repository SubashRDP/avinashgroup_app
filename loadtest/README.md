# Load test rig — 100 users, transactions only

Purpose: find where the app's logic breaks under volume and concurrency —
tax handlers, numbering engine, fiscal-year permission SQL, dynamic
approval, credit-limit checks, GL/stock ledger writes. **No masters are
created**; the seeder samples the site's existing customers, suppliers,
items, warehouses and accounts.

Covered transaction doctypes (12): Sales Invoice, Purchase Invoice, Sales
Order, Purchase Order, Quotation, Supplier Quotation, Material Request,
Delivery Note, Purchase Receipt, Stock Entry, Journal Entry, Payment Entry.

> **Run this against a throwaway copy of the site, not a DB you care
> about.** Restore with `bench --site <copy> restore <backup>` first if
> needed. The site must have `"allow_tests": true` in site_config.json —
> every seeder entry point refuses to run without it.

## 1. One-time setup

```bash
cd ~/frappe-15

# 100 load users with functional roles (NOT System Manager, so the
# fiscal-year permission SQL actually runs for them) + credentials CSV
bench --site avinas execute avinashgroup_app.loadtest.setup_users.make_users

# stock docs at random quantities need negative stock during the test
bench --site avinas execute avinashgroup_app.loadtest.seed.set_negative_stock

# 1 background worker will choke under submit load — raise it for the test
bench set-config -g background_workers 4
```

Install locust once: `pip install locust` (any Python ≥3.9 env).

## 2. Seed data volume — one core per doctype

`run_seed.sh` starts one bench process per doctype (≤8 in parallel on this
8-core box):

```bash
# logic path: insert + submit through every hook/override, with GL/SLE
bash apps/avinashgroup_app/loadtest/run_seed.sh 5000 full

# volume path: draft rows straight into the tables (thousands/sec) to
# crush list views, counts, link searches, permission SQL by sheer size
bash apps/avinashgroup_app/loadtest/run_seed.sh 1000000 fast
```

Watch progress: `tail -f apps/avinashgroup_app/loadtest/logs/Sales_Invoice.log`
Each worker prints rate/ETA every 200 docs and ends with a JSON summary
including an **error taxonomy** (exception type → count + first message).
Per-doc failures (credit limit hit, insufficient stock, validation throws)
are counted, not fatal — those counts are themselves findings.

### About "1 crore per doctype"

1 crore (10,000,000) × 12 doctypes ≈ 120M parent rows + ~300M child rows
+ GL/SLE — roughly **400–600 GB**. This machine has 159 GB free, so a full
1-crore-everywhere run does not fit. Realistic staging:

| Stage | Command | Fits? |
|-------|---------|-------|
| 1M per doctype, fast | `run_seed.sh 1000000 fast` | yes (~40–60 GB, hours) |
| 1 crore on the 2 hottest (SI + PE) only | `bench execute ...seed_one --kwargs '{"doctype":"Sales Invoice","count":10000000,"mode":"fast"}'` | tight but yes |
| 1 crore × all 12 | — | needs ~500 GB disk |

Most logic crushes long before 1 crore: list views and the fiscal-year
`permission_query_conditions` degrade visibly at 1–2M rows/table.

## 3. Fire 100 concurrent users

```bash
cd ~/frappe-15/apps/avinashgroup_app
locust -f loadtest/locustfile.py --host http://localhost:8000 \
       -u 100 -r 5 --run-time 20m
# open http://localhost:8089 for live charts, or add --headless
```

Traffic mix per user (session-cookie login, like real Desk):

| weight | task | what it crushes |
|--------|------|-----------------|
| 8 | list views | fiscal-year permission SQL + big-table scans |
| 5 | create + submit (`seed.make_one`) | full hook stack, numbering engine, tax handlers, GL/SLE, credit limits — under real user permissions |
| 4 | form loads | getdoc + child table fetch on huge tables |
| 3 | counts | `get_count` on millions of rows |
| 3 | link searches | Customer/Item/Supplier search queries |
| 2 | `get_item_details` | the app's override of the ERPNext method |
| 1 | General Ledger report | GL Entry aggregation over the seeded volume |

## 4. What to watch while it runs

```bash
# request latency / errors: the locust UI itself
# DB: lock waits and deadlocks are the classic first casualty
mysql -e "SHOW ENGINE INNODB STATUS\G" | grep -A 20 "LATEST DETECTED DEADLOCK"
mysql -e "SHOW FULL PROCESSLIST" | grep -v Sleep

# slow queries (enable first):
mysql -e "SET GLOBAL slow_query_log=1; SET GLOBAL long_query_time=1;"

# workers / queue backlog
cd ~/frappe-15 && bench --site avinas doctor

# app errors thrown by hooks under load
# Desk: /app/error-log — or:
bench --site avinas execute frappe.client.get_count --kwargs '{"doctype":"Error Log"}'
```

Expected first failure points, in rough order:
1. **Naming series / numbering engine contention** — concurrent submits
   serialize on the series row lock; watch for lock-wait timeouts on
   `tabSeries` and the custom Numbering Configuration path.
2. **Stock ledger serialization** — Delivery Note / Stock Entry / Purchase
   Receipt submits on the same item+warehouse queue behind each other.
3. **Fiscal-year permission SQL** — every list view for the 100 users runs
   the custom WHERE conditions; on multi-million-row tables this is the
   list-view killer.
4. **Credit-limit checks** — per-customer unpaid-bill scans get slower as
   seeded unpaid invoices pile up, then start throwing (counted in the
   error taxonomy).
5. **Background queue backlog** — submits enqueue follow-up jobs; with few
   workers the queue grows unboundedly (`bench doctor`).

## 5. Cleanup

```bash
bench --site avinas execute avinashgroup_app.loadtest.seed.purge
bench --site avinas execute avinashgroup_app.loadtest.setup_users.delete_users
bench --site avinas execute avinashgroup_app.loadtest.seed.set_negative_stock --kwargs '{"enabled": 0}'
```

`purge` deletes fast-mode drafts (`LT-*`) and every full-mode document
logged in `sites/avinas/loadtest_seeded_*.txt`, including their GL / Stock
Ledger / Payment Ledger rows. On a throwaway site, `bench restore` of the
pre-test backup is faster and cleaner.
