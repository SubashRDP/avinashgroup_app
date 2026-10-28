# `lc/`: letters of credit

The LC module tracks import letters of credit from the application to the bank until they close. It covers margin, bank charges, amendments, shipments, usance acceptance, settlement at the bank's rate, customs proof, and the charges' way into landed cost. Each money step posts its own Journal Entry.

- Full developer doc: [`docs/lc-management.md`](../../docs/lc-management.md).
- User guide: [`docs/user-guide/13-letters-of-credit.md`](../../docs/user-guide/13-letters-of-credit.md).

The module is its own Module Def, `LC` (in `modules.txt`), so its doctypes, reports, print format and workspace live here. It shares no code with `pdc/`. Its layout copies PDC's.

## What lives where

| File | Owns | Entry point |
|---|---|---|
| `accounting.py` | The Journal Entry for each money step, the settlement figures, the Landed Cost Voucher draft | called by `lifecycle.py`; `make_landed_cost_voucher` (whitelisted) |
| `lifecycle.py` | The state machine, the shipment guards, the History row and undo, the position totals, PO → LC and the PO hint | `run_action`, `undo`, `settlement_preview`, `make_from_purchase_order`, `purchase_order_hint` (whitelisted) |
| `guards.py` | Refuses cancelling a linked Purchase Receipt or Invoice, or an LC's JE | `doc_events` → `before_cancel` on Purchase Invoice, Purchase Receipt, Journal Entry |
| `notifications.py` | The daily email digest of LC dates | `daily_run` (`scheduler_events` → cron `35 8 * * *`) |
| `install.py` | Settings defaults, the default JV Type, the Bs Conversion record; "Create Missing Accounts" | `after_migrate`; the LC Settings button |
| `templates/lc_digest.html` | Body of the digest email | `notifications.send_daily_digest` |
| `doctype/letter_of_credit/` | The LC: NRB checks (BCI, usance limit, customs point), submit / cancel, form and list JS, tests | |
| `doctype/lc_settings/` | Per-company accounts and firm type, NRB limits, digest | |
| `doctype/lc_shipment/`, `lc_charge/`, `lc_amendment/`, `lc_document/`, `lc_purchase_order/`, `lc_event/`, `lc_company_account/` | Child tables | |
| `report/` | LC Register, LC Maturity, LC Margin and Charges, LC Cost Sheet | |
| `print_format/lc_summary/` | LC Summary | |
| `workspace/lc/` | The LC workspace | |

Outside this folder:

- `public/js/purchase_order_lc.js` adds "Create → Letter of Credit" and the NRB headline on Purchase Orders. It is loaded through `app_include_js`.
- `fixtures/custom_field.json` holds `Journal Entry-letter_of_credit` and `Landed Cost Voucher-letter_of_credit`.

## Doctypes it touches

- **Journal Entry:** it creates, submits and cancels these; they carry the `letter_of_credit` link.
- **Purchase Invoice:** a settlement clears it at its own conversion rate. It cannot be cancelled while linked to a shipment.
- **Purchase Receipt:** where a Landed Cost Voucher puts the LC's charges. It cannot be cancelled while linked to a shipment.
- **Landed Cost Voucher:** drafted by "Create → Landed Cost Voucher", carrying the `letter_of_credit` link.
- **Purchase Order:** read for "Create → Letter of Credit" and the hint; never changed.
- **Account:** "Create Missing Accounts" creates LC Margin and LC Charges Clearing.
- **Bs Conversion:** one record, `Letter of Credit`, made by `install.after_migrate`.
