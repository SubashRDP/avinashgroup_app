# `lc/`: letters of credit

The LC module keeps each import letter of credit as its own cost file. The goods (item group, item, description, qty, rate), the bank charges, insurance, customs duty, clearing and freight are all debited to **LC Goods in Transit**. On arrival, the total moves into stock (a Stock Entry) or fixed assets (a JE plus a draft Asset) at landed cost. It links to no Purchase Order or Purchase Invoice. Each money step posts its own Journal Entry.

- Full developer doc: [`docs/lc-management.md`](../../docs/lc-management.md).
- User guide: [`docs/user-guide/13-letters-of-credit.md`](../../docs/user-guide/13-letters-of-credit.md).

The module is its own Module Def, `LC` (in `modules.txt`), so its doctypes, reports, print formats and workspace live here. It shares no code with `pdc/`. Its layout copies PDC's.

## What lives where

| File | Owns | Entry point |
|---|---|---|
| `accounting.py` | The Journal Entry for each money step, the maturity figures, the LC's transit balance | called by `lifecycle.py` and `transfer.py` |
| `lifecycle.py` | The steps (cost, margin, goods payment, acceptance, maturity, close), the History row and undo, the totals and status | `run_action`, `undo`, `margin_suggestion`, `maturity_preview` (whitelisted) |
| `transfer.py` | Spreading the landed cost over the goods, the Stock Entry, the asset JE and draft Assets, undoing them | `transfer_preview` (whitelisted); `transfer` via `run_action` |
| `guards.py` | Refuses cancelling an LC's Journal Entry or Stock Entry from its own form | `doc_events` → `before_cancel` on Journal Entry, Stock Entry |
| `notifications.py` | The daily email digest of LC dates | `daily_run` (`scheduler_events` → cron `35 8 * * *`) |
| `install.py` | Settings defaults, the default JV Type, the Bs Conversion rows, the default LC Cost Types; "Create Missing Accounts" | `after_migrate`; the LC Settings button |
| `templates/lc_digest.html` | Body of the digest email | `notifications.send_daily_digest` |
| `doctype/letter_of_credit/` | The LC: NRB checks (BCI, usance limit), submit / cancel, Update-after-submit checks, form and list JS, tests | |
| `doctype/lc_settings/`, `lc_company_account/` | Per-company accounts (margin, transit, VAT) and firm type, NRB limits, digest | |
| `doctype/lc_cost_type/` | The cost master: name and group (Bank Charges, Insurance, Customs, Clearing, Freight, VAT, Other) | |
| `doctype/lc_item/`, `lc_cost/`, `lc_event/` | Child tables: goods, costs, History | |
| `report/` | LC Register, LC Maturity, LC Margin and Charges, LC Cost Sheet | |
| `print_format/` | LC Summary, LC Cost Sheet | |
| `workspace/lc/` | The LC workspace | |

Outside this folder:

- `fixtures/custom_field.json` holds `Journal Entry-letter_of_credit`, `Stock Entry-letter_of_credit` and `Asset-letter_of_credit`.
- `patches/lc_standalone_cost_file.py` removes the October 2026 design's child doctypes and the Landed Cost Voucher field.

## Doctypes it touches

- **Journal Entry:** it creates, submits and cancels these. They carry the `letter_of_credit` link.
- **Stock Entry:** the transfer's Material Receipt. Its Difference Account is LC Goods in Transit.
- **Asset:** a draft per fixed-asset row, marked "existing asset" because the JE already holds its value. The user completes and submits it.
- **Account:** "Create Missing Accounts" creates LC Margin and LC Goods in Transit.
- **Bs Conversion:** one record, `Letter of Credit`, made and kept up to date by `install.after_migrate`.
