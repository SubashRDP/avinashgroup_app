# `pdc/`: post-dated cheques

The PDC module: post-dated cheques received from customers or issued to suppliers,
tracked from the day the paper changes hands until it clears, bounces, is returned or is replaced.
Each step posts its own Journal Entry through a holding account.

- Full developer doc: [`docs/pdc-management.md`](../../docs/pdc-management.md).
- User guide: [`docs/user-guide/12-post-dated-cheques.md`](../../docs/user-guide/12-post-dated-cheques.md).

The module is its own Module Def, `PDC` (in `modules.txt`), so its doctypes, reports, print formats
and workspace live here rather than under `avinash_group_app/`.

## What lives where

| File | Owns | Entry point |
|---|---|---|
| `accounting.py` | The Journal Entry for each step: rows, holding accounts, cancel-with-flag | called by `lifecycle.py` and the cheque controller |
| `lifecycle.py` | The state machine, the guards (early / stale / bank account), the History row, undo, bulk actions, replacement, "from invoice" | `run_action`, `undo`, `bulk_action`, `make_replacement`, `make_from_invoice`, `get_outstanding_invoices` (whitelisted) |
| `notifications.py` | The party SMS (through `sparrow_sms`), due reminders and the daily email digest | `daily_run` (`scheduler_events` → cron `25 8 * * *`) |
| `payment_entry_bounce.py` | Bounce, re-present and replacement for cheques entered straight in Payment Entry: the record that tracks them and the PE cancel guard | `bounce`, `make_replacement_payment_entry` (whitelisted); `doc_events` on Payment Entry (`before_cancel`, `on_cancel`, `on_submit`) |
| `invoice_guard.py` | Refuses cancelling an invoice an active cheque settles, or a cheque's JE | `doc_events` → `before_cancel` on Sales Invoice, Purchase Invoice and Journal Entry |
| `install.py` | Settings defaults, the default JV Type, number cards and charts; "Create Missing Accounts" | `after_migrate`; the PDC Settings button |
| `templates/pdc_digest.html` | Body of the digest email | `notifications.send_daily_digest` |
| `doctype/pdc_cheque/` | The cheque: validation, submit (holding entry), cancel, form and list JS, tests | |
| `doctype/pdc_settings/` | Per-company holding accounts, rules, digest and SMS switches | |
| `doctype/pdc_cheque_reference/`, `pdc_cheque_event/`, `pdc_company_account/` | Child tables: invoices settled, History, per-company accounts | |
| `report/` | PDC Register, PDC Maturity, PDC Bounce Analysis | |
| `print_format/` | PDC Deposit Slip, PDC Cheque Receipt | |
| `workspace/pdc/` | The PDC workspace | |

Outside this folder:

- `public/js/invoice_pdc.js` adds "Create → PDC Cheque" on invoices. It is loaded through `app_include_js`.
- `public/js/payment_entry.js` holds the Payment Entry **Cheque** menu: Cheque Bounced dialog, Cheque Record, Replace With New Payment.
- `fixtures/custom_field.json` holds `Journal Entry-pdc_cheque`, `Payment Entry-pdc_cheque` and `Payment Entry-pdc_replacement_of`.

## Doctypes it touches

- **Journal Entry:** it creates, submits and cancels these; they carry the `pdc_cheque` link.
- **Sales Invoice** and **Purchase Invoice:** it reads their outstanding amounts and blocks cancelling them.
- **Payment Entry:** never changed by a bounce. It gets the `pdc_cheque` / `pdc_replacement_of` links and its `custom_cheque_bounce` flag kept in step; cancel is refused while its cheque has bounced.
- **Account:** "Create Missing Accounts" creates Cheques in Hand, Cheques Issued and Cheque Bounce Charges.
- **Sparrow SMS Log:** a row is written for every SMS attempt.
- **Number Card** and **Dashboard Chart:** created once by `install.after_migrate`.
