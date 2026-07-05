# CBMS Integration (Nepal IRD e-Billing) — Technical Reference

> Chapter 5 of the technical documentation. Audience: developers.
> User-facing guide: [`../user_guide/05-cbms-billing.md`](../user_guide/05-cbms-billing.md)

CBMS is Nepal IRD's **Central Billing Monitoring System**. Every submitted Sales
Invoice (and Sales Return / credit note) must be reported to IRD in real time.
The integration is entirely server-side: Python hooks + three doctypes. There is
no client script and no print-format change.

## 1. File inventory

| File | Role |
|------|------|
| `custom_code/CBMS/sales_invoice_hooks.py` | `on_submit` / `before_cancel` doc_events; payload field mapping; CBMS doc creation |
| `custom_code/CBMS/api_client.py` | HTTP client to IRD; payload builders; result recording |
| `custom_code/CBMS/scheduler.py` | retry + reconcile cron jobs (every 5 min) |
| `custom_code/CBMS/utils.py` | BS-date, fiscal-year, invoice-number helpers |
| `doctype/cbms_bill/`, `cbms_bill_return/`, `cbms_config/` | the three doctypes |
| `patches/create_cbms_custom_fields.py` | adds `custom_reason_for_return` to Sales Invoice |
| `hooks.py:83-85, 168-169, 246-251` | doc_event + scheduler wiring |
| `pyproject.toml:12` | `nepali-datetime` dependency |

## 2. Design invariants

1. **A Sales Invoice submission can never be blocked by CBMS.** The submit hook
   wraps everything in try/except and logs to Error Log
   (`sales_invoice_hooks.py:199-203`).
2. **Every network call runs in a background job** (`frappe.enqueue`, queue
   `default`, timeout 300 s), never inline (`sales_invoice_hooks.py:197-198`).
3. **Two independent safety nets** run every 5 minutes: *retry* (CBMS docs exist
   but aren't Synced) and *reconcile* (submitted invoices with no CBMS doc at
   all).
4. **A Synced invoice cannot be cancelled** — corrections flow through a Sales
   Return, which becomes a CBMS Bill Return.
5. **Returns are ordered after their originals** — a Bill Return is only POSTed
   once the referenced Bill is Synced (`api_client.py:171-175`).
6. **Production IRD endpoints only** — there is no sandbox mode. Go-live is
   controlled solely by `enable_cbms` + `enable_from_date` in CBMS Config.

## 3. Payload construction

### 3.1 Shared fields — `build_cbms_fields` (`sales_invoice_hooks.py:68-126`)

- `buyer_pan` ← Customer `tax_id`; `seller_pan` ← Company `tax_id` (cached)
- `buyer_name` ← `customer_name` or `customer`
- `fiscal_year` ← `utils.cbms_fiscal_year(posting_date)` → IRD dotted format,
  e.g. `"2081.082"` (`utils.py:25-35`)
- **Line-value basis** `_line_value` (`:44-49`): per item `custom_total`
  (net + excise, maintained by the selling taxes handler — chapter 4) when
  present, else `base_net_amount`. VAT is levied on net+excise, so this is the
  correct base.
- `tax_exempted_sales` — sum of line values where `custom_vat_apply_on == "VAT 0%"`
- `taxable_sales_vat` — sum of line values of all other lines
- `vat` — the VAT **actually booked** (`_booked_vat` `:52-65`):
  `custom_total_vat_amount`, falling back to summing `base_tax_amount` of tax
  rows whose `account_head` starts with `VAT`. Never recomputed.
- **Export detection** `is_export_invoice` (`:32-41`): currency ≠ NPR, or the
  Customer's Territory ancestor tree lies outside Nepal (empty / "Nepal" /
  "All Territories" = domestic). Exports put the whole value in `export_sales`,
  zero taxable/exempt, and `total_sales = base_grand_total`.
- `total_sales` = `base_grand_total − exempt_sales` for domestic invoices
- `discount` — `base_discount_amount` only when `apply_discount_on == "Net
  Total"`; stored on the CBMS doc **only** (the IRD API has no discount field)
- All amounts `flt(..., 2)`; absolute values throughout, so returns store
  positive numbers.

### 3.2 Bill extras (`create_cbms_bill` `:129-143`)

`invoice_number` = `utils.cbms_invoice_number` — the invoice's branch-wise
running number `custom_branch_name` (set by the naming engine, chapter 4),
falling back to `doc.name`; `invoice_date` (AD) and `invoice_date_bs` (BS,
dash format).

### 3.3 Return extras (`create_cbms_bill_return` `:146-171`)

`ref_invoice_number` = the **original** invoice's `invoice_number` looked up
from the CBMS Bill of `return_against`; `credit_note_number` = this return's
branch number; `credit_note_date` / `_bs`; `reason_for_return` = Sales Invoice
`custom_reason_for_return` or default `"Goods Returned"`.

### 3.4 HTTP payloads (`api_client.py`)

- Bill → `POST https://cbapi.ird.gov.np/api/bill` (`_build_bill_payload` `:53-69`):
  `username`/`password` (from CBMS Config, `get_password`), seller/buyer PAN,
  buyer name, fiscal year, invoice number, `invoice_date` (dotted BS),
  `total_sales`, `taxable_sales_vat`, `vat`, `_other_sales_fields` (`:38-50` —
  excise/hst/esf all zero for this business, plus `export_sales`,
  `tax_exempted_sales`), `isrealtime: True`, `datetimeClient` (ISO).
- Return → `POST https://cbapi.ird.gov.np/api/billreturn`
  (`_build_return_payload` `:79-97`): same base, plus `ref_invoice_number`,
  `credit_note_number`, `credit_note_date`, `reason_for_return`.
  ⚠️ `buyer_pan` goes through `_buyer_pan_decimal` (`:72-76`) → int or None,
  because the billreturn endpoint declares buyer_pan as a nullable decimal and
  rejects any string (even `""`) with HTTP 400.
- `REQUEST_TIMEOUT = 30` s. URLs are hardcoded constants (`api_client.py:11-13`).

## 4. Submit / cancel flow

### on_submit (`sales_invoice_hooks.py:174-205`)

1. Idempotency lock: cache key `cbms_processing_{doc.name}`, 300 s TTL; released
   in `finally`.
2. Load the enabled CBMS Config for the company (`get_cbms_config` `:18-21`);
   return if none, or if `posting_date < enable_from_date` (`in_cbms_scope`
   `:24-29`) — no retroactive reporting.
3. `is_return` → `create_cbms_bill_return` + enqueue `send_return_to_cbms`;
   else `create_cbms_bill` + enqueue `send_bill_to_cbms`.
4. Creation helpers are idempotent — they skip if a CBMS doc already exists for
   this invoice (also enforced by the `unique` constraint on `sales_invoice`).
5. Return special case: if the original invoice has no CBMS Bill yet, creation
   returns None — the reconcile job picks it up later.
6. `frappe.db.commit()` before enqueue.

### before_cancel (`:208-220`)

If the matching CBMS doc has `sync_status == "Synced"` → `frappe.throw` blocks
cancellation. Pending/Failed/absent → cancel freely. There is **no reversing
call to IRD**.

## 5. Scheduler (every 5 minutes, `hooks.py:246-251`)

- `retry_failed_cbms_syncs` → `queue_failed_for_company` (`scheduler.py:26-59`):
  per enabled company, re-enqueue sends for CBMS Bills/Returns with
  `sync_status != "Synced"`, capped at `bill_retry_batch_size` /
  `return_retry_batch_size` (default 50 each).
- `reconcile_missing_cbms_bills` (`scheduler.py:87-135`): per company, find
  submitted Sales Invoices (`posting_date >= enable_from_date`) with **no** CBMS
  doc at all, create the doc and enqueue the send. Each invoice is
  try/except-wrapped with Error Log on failure.

## 6. Send logic and status model

`send_bill_to_cbms` (`api_client.py:127-158`) / `send_return_to_cbms` (`:160-200`):

- Skip if already Synced; abort if config disabled.
- Response classification `_response_code` (`:100-108`): accepts bare `"200"`
  text or `{"message":"200"}` JSON.
- **Bills:** success codes `{"200","101"}` — 101 ("Bill already exists") counts
  as success.
- **Returns:** success code `{"200"}` **only** — for returns 101 means "Bill
  does not exist" and is a failure. This asymmetry is deliberate
  (`api_client.py:15-17`).
- Error codes (`BILL_ERRORS`/`RETURN_ERRORS` `:19-35`): 100 credentials
  mismatch, 102 save exception, 103 unknown, 104 model invalid, 105 bill does
  not exist (returns).
- `_record_result` (`:111-124`): sets `sync_status`, truncates `sync_response`
  to 500 chars, increments `attempt_count`, sets `last_attempt`,
  `update_modified=False`, commits.
- Both senders **never raise**: exceptions are logged, rolled back, status
  forced to Failed, committed, return False — a failure loops harmlessly every
  5 minutes until fixed.

Status fields on both CBMS Bill and CBMS Bill Return:

| Field | Type | Meaning |
|-------|------|---------|
| `sync_status` | Select Pending/Synced/Failed (default Pending) | list-view + standard filter |
| `attempt_count` | Int | send attempts |
| `last_attempt` | Datetime | last try |
| `sync_response` | Small Text ≤500 | last IRD code+message |
| `datetime_client` | Datetime | timestamp reported to IRD |

All CBMS doc fields are read-only in the UI; `track_changes` is on.

## 7. CBMS Config doctype (one per company)

| Field | Type | Notes |
|-------|------|-------|
| `company` | Link, unique | `autoname: field:company` |
| `enable_cbms` | Check (default 0) | master switch |
| `enable_from_date` | Date | go-live; mandatory when enabled |
| `username` / `password` | Data / Password, reqd | IRD API credentials |
| `bill_retry_batch_size` / `return_retry_batch_size` | Int (default 50) | per-run retry caps |

Controller (`cbms_config.py:10-15`) enforces one config per company. Whitelisted
`sync_failed_now(cbms_config_name)` (`:18-24`) manually queues all failed docs
for that company — callable from console/API (no UI button exists).
Permissions: System Manager + Accounts Manager (full).

## 8. Troubleshooting quick reference

| Symptom | Cause / fix |
|---------|-------------|
| `sync_response` = `100: API credentials do not match` | Fix Username/Password in CBMS Config |
| Return stuck Pending, never POSTs | Original invoice's CBMS Bill not Synced yet — fix that first; return auto-recovers |
| Invoice submitted but no CBMS Bill | on_submit hook failed (see Error Log) — reconcile job creates it within 5 min |
| Cannot cancel invoice | It is already reported to IRD — issue a Sales Return instead |
| Need immediate retry | `bench --site avinas1 console` → `frappe.get_doc("CBMS Config", "<company>").sync_failed_now("<company>")` or call `queue_failed_for_company` |

## 9. IRD print-copy labeling (Tax Invoice / Copy of Original)

IRD e-billing requires the software to count how many times an invoice is
printed and to label reprints as copies of the original. The print title is
derived from a counter on each Sales Invoice:

| Print # | Title shown |
|---------|-------------|
| 1st     | `Tax Invoice` |
| 2nd     | `Copy of Original` |
| 3rd     | `Copy of Original 2` |
| nth     | `Copy of Original (n-1)` |

**Pieces:**

- **Field** `Sales Invoice.custom_print_count` (Int, read-only, no_copy,
  print_hide) — created by patch
  `avinashgroup_app.patches.add_sales_invoice_print_count`.
- **Hook** `custom_code/SalesInvoice/print_count.py::before_print`
  (registered on Sales Invoice `before_print`). On a *real* print of a
  submitted invoice it does an atomic `custom_print_count = custom_print_count + 1`
  and commits (printview/download are GET requests, so the commit is explicit).
  A "real print" = `trigger_print=1` (browser Print button) or a PDF/server
  print `cmd`. Opening the Print **preview** does NOT consume a number — the
  preview shows the title the *next* print will get.
- **Print format** `Avinash Sales invoice` reads `doc.custom_print_count`
  to choose the title (see the `{% set print_count_no ... %}` block at the top
  of its HTML). Sales **Returns** are unaffected — they print via
  `Avinash Sales Return` and the title block is gated on `not doc.is_return`.

The print format HTML lives only in the DB (custom, non-standard format), not
in a fixture — re-running the patch will not touch it. If the format is ever
re-imported/overwritten, re-apply the `print_count_no` title block.
