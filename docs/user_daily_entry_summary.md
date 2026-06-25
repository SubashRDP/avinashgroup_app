# User Daily Entry Summary Report

Report path: `avinashgroup_app/avinash_group_app/report/user_daily_entry_summary/`

## Purpose

For a chosen **user** and a single **day**, count the documents that user
**created** that day, broken down by **document type** and current **status**:

| Document Type | Draft | Submitted | Cancelled | Total |
|---|---|---|---|---|

It answers "what did this person enter today, and where did those entries land?"
— useful for monitoring daily data-entry volume and how much of it is still
sitting in Draft vs. submitted vs. cancelled. Only the document types you
configure are scanned, so the report stays fast.

## Filters

| Filter | Type | Notes |
|---|---|---|
| **User** | Link → User | Required. The author whose entries are counted. |
| **Date** | Date | Required. Defaults to today. A single day (00:00:00–23:59:59). |
| **Document Type** | MultiSelectList | Optional. Narrows to specific tracked doctypes; empty = all configured. |

## What gets counted

For each configured doctype, the report runs **one query** against that doctype's
own table:

```sql
SELECT
    SUM(docstatus = 0) AS draft,
    SUM(docstatus = 1) AS submitted,
    SUM(docstatus = 2) AS cancelled
FROM `tab<DocType>`
WHERE owner = <user>
  AND creation BETWEEN <day-start> AND <day-end>
```

- **owner** — the account that created the document. (For documents loaded by a
  bulk import, `owner` is the importing account, e.g. `Administrator`.)
- **creation** — the timestamp the document was first inserted, bounded to the
  selected day.
- **docstatus** — Frappe's document state: `0` Draft, `1` Submitted, `2` Cancelled.

`Total` = Draft + Submitted + Cancelled = all documents the user created that day.
Rows with a zero total are omitted. Doctypes are listed busiest-first.

**Notes**
- Only **parent** documents are counted — child-table rows are never counted.
- **Non-submittable** doctypes have no real submit state, so all their documents
  count as **Draft** (docstatus 0).
- Only doctypes the **running user** has read permission for are shown.

## Drill-down

Every status count is a link. Clicking it opens the target doctype's **list view**
filtered to exactly those documents:

```
/app/<doctype>/view/list?owner=<user>&creation=["between",[<from>,<to>]]&docstatus=<n>
```

> Implementation note: scalar filter values (`owner`, `docstatus`) are placed in
> the URL **raw**. JSON-stringifying them would add literal quotes
> (`owner="x"`), which the list view treats as part of the value — so the list
> would open empty. Only the `["between", ...]` date filter is JSON-encoded.

## Configuration — which doctypes are scanned

The scanned list is driven by the **User Daily Entry Summary Settings** Single
doctype (System Manager only):

1. Go to **User Daily Entry Summary Settings**.
2. In **Tracked Doctypes**, add a row per doctype you want counted (e.g.
   `Sales Invoice`, `Purchase Invoice`, `Payment Entry`).
3. Save.

Keep this list focused — the report runs one query per tracked doctype, so a
short, deliberate list keeps it fast. The list is read from a Redis-cached Single
doc, so reading it adds no per-run database cost.

Related doctypes:
- `User Daily Entry Summary Settings` — the Single holding the configuration.
- `User Daily Entry Summary Doctype` — the child table row (`document_type`).

## Performance

The "Created" filter is `owner = user AND creation BETWEEN day`. Frappe indexes
`modified` by default but **not** `creation`, so without help this would be a full
table scan (~110k rows on Sales Invoice ≈ 0.3s for one doctype/day, growing over
time).

A composite **`(owner, creation)`** index — named `daily_entry_owner_creation` —
is added to every tracked doctype's table by the patch
`avinashgroup_app/patches/add_creation_index_daily_entry.py`. It matches the
query exactly (equality on `owner`, range on `creation`), turning the scan into a
seek:

| | Access | Time (worst-case bulk day) |
|---|---|---|
| Without index | full scan | ~0.32s |
| With `(owner, creation)` index | index range seek | ~0.04s |

The patch is **idempotent** (skips tables that already carry the index) and runs
on `bench migrate`. On normal days the result set is tiny and the query is
effectively instant.

### Read replica

The report is read-only, so it executes on the **read replica** (`:3307`). The
index is created on the master via the patch and **replicates automatically** via
GTID DDL replication — no separate action is needed on the replica.

## Files

| File | Role |
|---|---|
| `report/user_daily_entry_summary/user_daily_entry_summary.py` | Query logic, columns, tracked-doctype lookup |
| `report/user_daily_entry_summary/user_daily_entry_summary.js` | Filters + status-count drill-down links |
| `doctype/user_daily_entry_summary_settings/` | Single doctype holding the tracked-doctype list |
| `doctype/user_daily_entry_summary_doctype/` | Child table (`document_type`) |
| `patches/add_creation_index_daily_entry.py` | Adds the `(owner, creation)` index per tracked doctype |

## Deployment

```bash
cd apps/avinashgroup_app && git pull && cd ../..
bench --site <site> migrate          # runs the (owner, creation) index patch
bench build --app avinashgroup_app   # picks up the report JS
bench --site <site> clear-cache
bench restart
```

Verify the index landed:

```bash
bench --site <site> mariadb --execute \
  "SHOW INDEX FROM \`tabSales Invoice\` WHERE Key_name='daily_entry_owner_creation';"
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Report is empty | No doctypes configured in **User Daily Entry Summary Settings**, or the selected user created nothing that day. |
| Counts look low for a real user | Bulk-imported documents are owned by the **importing account** (often `Administrator`), not the human author — `owner` reflects who inserted the row. |
| A doctype never appears | It isn't in the tracked list, the running user lacks read permission, or the doctype doesn't exist. |
| Drill-down opens an empty list | Make sure the latest JS is built/cache-cleared and hard-refresh the browser; the link relies on raw (unquoted) scalar filter values. |
| Report is slow | Confirm the `daily_entry_owner_creation` index exists on the tracked tables (run `bench migrate`, or check via the verify command above). |
