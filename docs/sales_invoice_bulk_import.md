# Fast Sales Invoice import (ng-group, ~10 lakh invoices)

Investigation date: 2026-07-28. Target site: `ng-group.raindropinc.com` (read-only API access).
Measurements taken on the local bench site `avinas1`, which mirrors the live schema and
data shape (48,837 SI locally vs 94,559 live, same items/warehouses/hooks).
All local test invoices were rolled back; nothing was committed.

---

## 1. Where things stand

The import is already running, via the Data Import UI, in hand-sliced `.xlsx` batches
(`Sales NGI 80.81 magh to chaitra…xlsx`, 500 rows each), `Submit After Import = 1`.

Measured from the live `Data Import` records (successful runs only):

| | |
| --- | --- |
| Throughput | **0.98 invoices/sec** (14,674 rows in 4.15 h) |
| Per invoice | ~1.05 s |
| Naive projection for 1,000,000 | **11.8 days** of continuous running |

That 11.8 days is optimistic, and the real number is much worse — see §2.1.
Roughly **40% of the recent import batches ended in `Error`**, so actual delivered
throughput is lower still.

Shape of the data (this matters):

- 1 item line per invoice (94,601 SI Items across 94,559 invoices).
- `Update Stock = 1`, perpetual inventory on for all 7 companies.
- Every row backdated to FY 80/81 (2023-24), while the stock ledger already runs to 2026-07.
- **Only 12 `Bin` rows exist for the entire group.** All NGI invoices post
  `NGI-ITEM-00167` into `Gas Purchase / Stock (Sales) - NGI` — one single bin already
  holding 28,695 stock ledger entries locally.

---

## 2. Measured cost breakdown

Per invoice, `insert()` + `submit()`, current production code path: **~1,400–1,590 ms**,
of which **84% is spent waiting on SQL** — 451 queries per invoice.

| Cost centre | ms/invoice | % |
| --- | ---: | ---: |
| `update_company_current_month_sales` (ERPNext) | **674** | 43% |
| `future_sle_exists` (backdating check) | **201** | 13% |
| `load_from_db` — 140 repeated master reads | 118 | 8% |
| `update_qty_in_future_sle` (rewrites future SLE) | **110** | 7% |
| `db_query.build_and_run` (74 `get_all` calls) | 47 | 3% |
| everything else | ~250 | 16% |

**The avinashgroup_app custom hooks are not the problem.** The tax pipeline, the
numbering engine, dynamic approval, the audit event mapper and credit control do not
appear anywhere in the top 26 cost centres. Every significant cost is stock ERPNext.

### 2.1 The dominant cost is a dashboard counter, and it gets worse as you import

`erpnext/setup/doctype/company/company.py:update_company_current_month_sales` runs on
every Sales Invoice submit. It exists only to refresh `Company.total_monthly_sales`,
a dashboard field. Its query is:

```sql
SELECT SUM(base_grand_total) ... FROM `tabSales Invoice`
WHERE DATE_FORMAT(`posting_date`, '%m-%Y') = '07-2026' AND docstatus = 1 AND company = ...
```

`DATE_FORMAT(posting_date, …)` is not sargable, so no index can be used:

```
EXPLAIN -> type: ALL, possible_keys: NULL, key: NULL, rows: 41832
```

It **full-scans `tabSales Invoice` on every single invoice you submit**. Measured cost
is 9.42 µs per row in the table, so the cost per invoice grows linearly with the number
of invoices already imported:

| `tabSales Invoice` rows | this hook costs, per invoice |
| ---: | ---: |
| 48,837 (measured) | 460 ms |
| 100,000 | ~0.9 s |
| 500,000 | ~4.7 s |
| 1,000,000 | **~9.4 s** |

Integrated over a 1M-row import that is ≈ **54 days in this one hook alone**. The
current approach does not take 12 days — it does not realistically finish.

Note the irony: every imported invoice is dated FY 80/81, so it never matches the
current month the query is summing. The full scan is pure waste for this import.

### 2.2 Backdated stock postings are the second multiplier

Because each row is backdated against a ledger that already extends to 2026-07,
every submit hits `future_sle_exists` and creates a **Repost Item Valuation**, and
`update_qty_in_future_sle` rewrites the future rows of that bin. With only 12 bins,
all 1M invoices pile onto the same handful of ledgers — this is the quadratic term.

Live evidence right now: 35 Repost Item Valuation rows stuck `In Progress` since
2026-07-26, 16 `Failed`, and a stream of `Unable to repost item valuation` errors, all
`QueryDeadlockError (1213)` on `NGI-ITEM-00167 / Gas Purchase / Stock (Sales) - NGI`.

### 2.3 Measured effect of each fix

Local, same invoice shape, dashboard fix applied cumulatively:

| Configuration | ms/inv | inv/s |
| --- | ---: | ---: |
| baseline — exactly what production does now | 1,403 | 0.71 |
| + skip `update_company_current_month_sales` | **330** | 3.03 |
| + `update_stock = 0` | **180** | 5.57 |
| + `frappe.flags.in_import` | **172** | 5.80 |

**8.1× on a single process**, before any parallelism.

Keeping the stock ledger is still viable if the order is right:

| Stock handling (dashboard fix applied) | ms/inv |
| --- | ---: |
| `update_stock=1`, backdated (what happens today) | 466–708 |
| `update_stock=1`, **chronological** (no repost created) | **195–201** |
| `update_stock=0` | 166–170 |

Importing in chronological order recovers almost all of the benefit **without giving up
the stock ledger** — 2.4–3.5× versus backdating. Note, however, that chronological
ordering is **not achievable for this particular import**; see §7.

---

## 3. Do not parallelise naively

Tested 1, 2, 4 and 8 concurrent importer processes, with distinct customers per worker
and per-invoice transaction scope:

| processes | throughput | |
| ---: | ---: | --- |
| 1 | 4.84 inv/s | |
| 2 | 4.94 inv/s | |
| 4 | 4.64 inv/s | 2 workers died: `QueryDeadlockError` |
| 8 | 4.69 inv/s | 6 workers died: `QueryDeadlockError` |

Throughput is **flat** — extra processes buy nothing and start deadlocking at 4+.
This matches the deadlocks live is already producing. Live has only 2 RQ workers
(`long,default,short` and `short,default`), and the import job and the repost queue are
currently fighting over them.

If parallelism is attempted later, it must be partitioned by company (separate naming
series, separate Company/Bin rows), and re-measured — do not assume it scales.

---

## 4. The name-collision bug wasting ~40% of batches

Live batches are failing with:

```
DuplicateEntryError: ('Sales Invoice', 'NGI-SB-80/81-16292', IntegrityError(1062, ...))
```

— and rows 496, 497, 498, 499, 500, 501 all report **the same name**.

Cause, reproduced locally:

```
tabSeries['NGI-SB-82/83-'].current = 28103
  make_autoname -> NGI-SB-82/83-28104   (current now 28104)
  after rollback, current = 28103
  make_autoname -> NGI-SB-82/83-28104   <-- same name again
```

`make_autoname` increments `tabSeries` **inside the row's transaction**. The Data
Import wraps each row in a savepoint and rolls back on failure, so the counter rolls
back with it. Once `tabSeries.current` is behind the real `max(name)` — which is the
state live is in — the first row collides, rolls back, and **every subsequent row in
the batch is handed the identical name and also fails**. One bad row kills the whole
remaining batch.

Two fixes, use either or both:

1. Resync the counter before every run:
   ```sql
   UPDATE tabSeries s
   SET current = (SELECT MAX(CAST(SUBSTRING_INDEX(name,'-',-1) AS UNSIGNED))
                  FROM `tabSales Invoice` WHERE name LIKE CONCAT(s.name,'%'))
   WHERE s.name = 'NGI-SB-80/81-';
   ```
2. Better: add an explicit **`ID` column** to the import template holding the invoice
   name (the sheet already carries `Invoice No.`). That bypasses `make_autoname`
   entirely, removes the shared-counter contention, and makes reruns idempotent —
   a re-import of an already-loaded row fails only that row.

---

## 5. Recommended plan

Ordered by measured payoff.

**Before starting**

1. Drain the repost queue: the 35 `In Progress` / 16 `Failed` Repost Item Valuation
   rows must be resolved before a large import, or they will deadlock against it.
2. Resync the `NGI-SB-80/81-` (and every other target prefix) `tabSeries` counter, and
   add an `ID` column to the template.
3. Take a backup / snapshot.

**The import itself**

4. **[APPLIED 2026-07-28] Set `Selling Settings.sales_update_frequency` to `Monthly`.**
   No code needed — `sales_invoice.py:484` and `:573` already guard the call behind
   `== "Each Transaction"`, which is what live was set to. Flipping it to `Monthly`
   stops the full scan entirely. This is the single biggest win (4.25x).
   Side effects, both checked: `Company.total_monthly_sales` stops refreshing (the daily
   `cache_companies_monthly_sales_history` job updates `sales_monthly_history` and
   `transactions_annual_history`, but NOT that field); and `update_project()` is skipped,
   which is irrelevant here — live has 0 Projects and 0 invoices with a project set.
   Worth leaving off permanently: the query full-scans `tabSales Invoice` on every
   submit by every user, forever, and grows with the table.
5. **Set `Update Stock = 0`.** See §7 — this is the only way to stop item revaluation
   for this import, because chronological ordering is not available to you. (~165 ms/inv)
6. **Drive it from a script, not the Data Import UI.** Hand-slicing 500-row xlsx files
   and queueing them one at a time adds large idle gaps (a 10-row import took 255 s of
   wall clock, nearly all of it queue wait). A single long-running script that reads the
   full file, sets `frappe.flags.in_import = True`, and commits every N rows removes
   that overhead and makes the run restartable.
7. Keep it to **one importer process**, per §3.

**Projected result**

| | per invoice | 1,000,000 invoices |
| --- | ---: | ---: |
| today | ~1,050 ms, degrading | ≫ 54 days, will not finish |
| after fixes | ~170–200 ms, flat | **~2.0–2.4 days** |

The "flat" matters as much as the number: removing the full scan is what stops the
import getting slower the longer it runs.

---

## 6. Longer-term

- `update_company_current_month_sales` is a bad query for this site regardless of the
  import — it full-scans `tabSales Invoice` on every invoice submitted by every user,
  forever. Worth a permanent override that rewrites the predicate to a sargable
  `posting_date BETWEEN <month start> AND <month end>`.
- With 1M invoices on 12 bins, any future backdated stock document will trigger a
  repost across a million-row ledger. Consider whether these companies need perpetual
  inventory on the gas item at all.

---

## 7. Can we stop item revaluation?

Short answer: **only by setting `Update Stock = 0`.** There is no setting that disables
reposting while you keep writing backdated stock ledger entries.

### There are two separate costs, not one

| | what it is | can it be switched off? |
| --- | --- | --- |
| **Repost Item Valuation docs** | created in `stock_controller.py:1376` via `repost_future_sle_and_gle()`, called from `sales_invoice.py:472` — only when `future_sle_exists()` is true | only by not backdating, or not writing SLEs |
| **Inline repost of the current voucher** | `repost_current_voucher()` → `update_entries_after()` + `update_qty_in_future_sle()` (`stock_ledger.py:120-145`) | **no** — runs unconditionally inside `make_sl_entries` whenever an SLE is written |

The second one is the 110 ms `update_qty_in_future_sle` line in the §2 table. It has no
flag. If a stock ledger entry is created, it runs.

### Do NOT disable the repost scheduler

The obvious move — `Stock Reposting Settings → limit_reposting_timeslot`, or unscheduling
the hourly `repost_entries()` — **only stops reposts from executing, not from being
created**. `create_item_wise_repost_entries()` (`stock_controller.py:1788`) makes and
submits one Repost Item Valuation document per invoice; it de-duplicates only within a
single voucher's own SLEs, never against what is already queued. De-duplication happens
later, in `repost_entries()` → `deduplicate_similar_repost()`, i.e. only once they run.

So suppressing the scheduler during a 1M-row import would leave **~1,000,000 submitted
Repost Item Valuation documents** queued up. Live already carries **177,361** of them —
nearly double its 94,559 Sales Invoices. This route makes things strictly worse.

### Why chronological ordering is not an option here

Measured (dashboard fix applied to all three):

| | ms/inv | RIV created | SLE created |
| --- | ---: | ---: | ---: |
| backdated, `update_stock=1` | 847 | **1.0 / invoice** | 1.0 |
| strictly chronological, `update_stock=1` | 181 | **0** | 1.0 |
| `update_stock=0` | 165 | **0** | 0 |

Chronological genuinely produces zero reposts — verified by instrumenting the branch:
both `future_sle_exists()` and `repost_required_for_queue()` return `False`, provided
each invoice's `posting_datetime` is unique and strictly increasing. (If a whole day's
invoices share `posting_time 00:00:00`, each one sees its same-day siblings as "future"
entries and the benefit is lost — worth knowing for any future import.)

But it is unavailable for *this* import. Live's stock ledger is current: the newest SLE
is dated **2026-07-28** (today), and **79,446 of 95,791 SLEs (83%) are dated after
2024-07-15** — i.e. after the FY 80/81 range being imported. You are loading 2023-24
data underneath a ledger that is live through today, so every imported row is backdated
by construction. Ordering the file correctly changes nothing.

Making chronological work would mean removing or rebuilding two years of newer stock
entries first — far more disruptive than the import itself.

### Conclusion

Set `Update Stock = 0` for the historical import. That gives 0 SLE, 0 reposts, and
165 ms/invoice. The tradeoff is real and should be a conscious accounting decision:
these invoices produce no stock ledger entries and no COGS GL entries.

Two things to weigh on the other side:

- `Bin.actual_qty` for the main NGI bin is currently **−55,060,098**. The perpetual
  valuation on these gas items is already not meaningful, so the ledger being skipped is
  not the loss it would normally be.
- If stock quantity/valuation for the historical period is needed later, it can be
  established far more cheaply with a single dated **Stock Reconciliation** per
  item-warehouse than by having a million invoices each rewrite the ledger.
