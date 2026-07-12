# O(1) document-numbering fast path ("trust the counter")

**Status: IMPLEMENTED 2026-07-13** in `custom_code/Override/naming_series.py`
(`_floor_verified` / `_mark_floor_verified` / `_series_row_exists`, used by
`_draw_next_document_no`, `peek_next_document_no`, `_build_from_segments`).
One deliberate hardening over the original plan: the marker is set ONLY when a
scan OBSERVES data_max <= counter in committed state — never on the strength
of the same transaction's reseed, which a rollback would revert while the
Redis marker survived. The benchmark table below is kept for reference.

## Why

1-crore load tests on avinas1 (2026-07-12) proved the numbering engine is
correct at any scale but O(n) per save: every draw and every form preview
re-scans the scope (`SELECT MAX(CAST(custom_document_no AS UNSIGNED)) …
WHERE custom_name LIKE '<prefix>-%-<FY>%'`).

Measured at 10,000,000 rows in one scope (peek / draw ms):

| doctype          | baseline | at 1 crore        |
|------------------|----------|-------------------|
| Journal Entry    | 104 / 2  | 15,128 / 11,532   |
| Payment Entry    | 25 / 1   | 36,623 / 20,734   |
| Purchase Invoice | 27 / 1   | 55,445 / 35,700   |

Correctness held everywhere (sequential draws, duplicate rejection) — only
latency degrades. Pain starts around ~1M rows per scope (~2 s/save).

## The fix (option 3 of 3 considered)

The `tabSeries` counter is already authoritative and O(1); the scan is only a
safety net for data written OUTSIDE the app (raw-SQL imports, restored
backups), because in-app manual numbers already bump the counter via
`_keep_counter_above_manual` (naming_series.py:1067).

Change `custom_code/Override/naming_series.py`:

1. Redis marker `docno_floor_verified:<series key>`, TTL 1 h.
2. `_draw_next_document_no` (~line 1094): skip the
   `_current_max_document_no` floor scan when the scope's tabSeries row
   exists AND the marker is set (pass floor=1 to the unchanged GREATEST
   upsert). Scan + set marker otherwise (first draw / hourly re-verify).
3. `peek_next_document_no` (~line 1042): same skip; when it does scan, set
   the marker ONLY if `data_max <= current` (peek must never bless a
   lagging counter — it doesn't reseed).
4. `_build_from_segments` (~line 2205): same treatment for the voucher-name
   Number-segment floor (`_series_data_floor` scan); marker set only on the
   `commit_series=True` path.

Nothing else changes: upsert SQL, locking, manual-path duplicate check,
delete-revert all stay as-is.

## Verify when implementing

- `bench --site avinas1 run-tests --app avinashgroup_app --module avinashgroup_app.test_document_numbering` (61 green)
- `… --module avinashgroup_app.test_ngk_numbering_format` (2 green)
- Crore benchmark: reload 10M JE rows (`scripts/loadtest_ngk_numbering.py`),
  confirm first draw ~seconds (seed) then peek/draw ~ms; burst still strictly
  sequential; duplicate still rejected; `cleanup()` after.
