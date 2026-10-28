# PDC management: developer documentation

Post-dated cheques (PDCs) received from customers and issued to suppliers. Each cheque is tracked from the day it changes hands until it clears, bounces, comes back, or is replaced. Each step posts its own Journal Entry through a holding account. Modelled on [pdc_management](https://github.com/vinaymishraofficial/pdc_management) (MIT), and extended with:

- bulk deposit and clear
- a deposit slip
- re-depositing a bounced cheque
- SMS to the party through Sparrow SMS

**The group's day-to-day flow is §12:** cheques are entered straight into Payment Entry, as before. When one bounces, a PDC Cheque record takes over the bounce, re-presentation and replacement. The PDC flow in §3–§8 is still there for real post-dated cheques.

For users: [user-guide/12-post-dated-cheques.md](user-guide/12-post-dated-cheques.md). The code map is in [`pdc/README.md`](../avinashgroup_app/pdc/README.md).

Last checked against the code: 27 October 2026 (11 Kartik 2083).

---

## 1. Why this exists

ERPNext books a cheque as a **Payment Entry** to the bank on the day it is entered, and it has no idea of a cheque's life after that. A PDC is not money in the bank. It sits in a drawer until its date. Then it is deposited, and then it either clears or bounces. With only Payment Entries:

- the bank balance includes cheques that have not reached their date yet;
- nobody is reminded when a cheque in the drawer reaches its date, so cheques go stale (in Nepal a cheque is valid for 6 months);
- a bounce is a manual reversal. The app's earlier `custom_code/payment_entry/cheque_bounce.py` does exactly that for Payment Entries, and it stays for cheques booked that way.

The PDC module puts the cheque in a **holding account** (*Cheques in Hand* or *Cheques Issued*) until the bank says it cleared. Every step leaves a dated Journal Entry and a History row.

## 2. Environment

| | |
|---|---|
| Module Def | `PDC` (`modules.txt`), folder `avinashgroup_app/pdc/` |
| Doctypes | PDC Cheque (submittable), PDC Settings (single), PDC Cheque Reference, PDC Cheque Event, PDC Company Account (child) |
| Reports | PDC Register, PDC Maturity, PDC Bounce Analysis (Script Reports; they read from the replica like every report on avinas1) |
| Print formats | PDC Deposit Slip, PDC Cheque Receipt |
| Workspace | PDC (4 number cards and 2 charts, created by `install.after_migrate`) |
| Custom field | `Journal Entry-pdc_cheque` (fixture) |
| Roles | Accounts User: create, submit and run steps. Accounts Manager: also cancel, amend and Undo Last Step. System Manager: everything. |

### Deploy

1. `bench --site avinas1 migrate`. This syncs the module, the custom field fixture, and runs `pdc.install.after_migrate`, which writes the settings defaults, sets the JV Type to `Bank Entry` and creates the number cards and charts.
2. In **PDC Settings**, click **Create Missing Accounts**. It adds a row for each of the seven companies and creates three accounts in each:
   - *Cheques in Hand* under Current Assets
   - *Cheques Issued* under Current Liabilities
   - *Cheque Bounce Charges* under Indirect Expenses

   If you want existing accounts used instead, pick them by hand.
3. Check **JV Type for Cheque Entries**. It decides which Numbering Configuration numbers the cheque JEs (see §9).
4. Optionally switch on SMS (§7).

> On the dev test site `avinasdemo.raindropinc.com`, `migrate` currently stops at an unrelated HRMS patch (`add_leave_type_permission_for_ess`: "limit has not set for user type Employee Self Service"). That error comes before fixtures sync and `after_migrate` run, so on that site run them by hand: `sync_fixtures("avinashgroup_app")` and `avinashgroup_app.pdc.install.after_migrate()`.

## 3. The state machine

```
 RECEIVED                                          ISSUED
 ────────                                          ──────
 Draft ─submit→ In Hand ─deposit→ Deposited        Draft ─submit→ Issued
                  │  └───────clear──────┐  │                       │ ├─clear→ Cleared ─bounce→ Bounced
                  │                     ▼  ├─clear→ Cleared        │ ├─bounce→ Bounced
                  │                Cleared │         │             │ └─stop→ Returned
                  │                        └─bounce─┐│bounce
                  │                                 ▼▼
                  ├─return→ Returned ◄─return── Bounced ─re-deposit→ Deposited
                  │                                 │
 Bounced / Returned ─replace→ new draft cheque; when submitted, original → Replaced
 In Hand / Issued (no later step) ─cancel→ Cancelled
```

The transition rules live in `lifecycle.py` (`_require` calls at the top of each step):

| Step | Received from | Issued from | Function |
|---|---|---|---|
| Deposit | In Hand | none | `deposit` |
| Clear | In Hand, Deposited | Issued | `clear` |
| Bounce | Deposited, Cleared | Issued, Cleared | `bounce` |
| Re-deposit | Bounced | none | `redeposit` |
| Return / Stop | In Hand, Bounced | Issued | `return_cheque` |
| Replace | Bounced, Returned | Bounced, Returned | `make_replacement`, then submit of the new cheque calls `mark_replaced` |
| Undo Last Step | any step except the first and "Replaced" | same | `undo_last_step` |
| Cancel | In Hand, with History length 1 | Issued, with History length 1 | `PDCCheque.before_cancel` / `on_cancel` |

### How a step is recorded

`record_event(cheque, event, date, values, journal_entry, ...)`:

1. snapshots the `LIFECYCLE_FIELDS` as they are now;
2. writes `values` with `db_set`;
3. appends a **PDC Cheque Event** row with `db_insert`. The row holds the event, its date, the status after it, the JE, the bank account, the user, and the snapshot as JSON (`previous_values`).

Steps never call `save()` on the submitted cheque. That way the Update-After-Submit checks can't get in the way, and only the lifecycle fields can change.

**Undo Last Step** is generic:

1. cancel the last row's JE (with `INTERNAL_CANCEL_FLAG` set);
2. write the snapshot back;
3. delete the row.

It refuses the first row (cancel the cheque instead) and a "Replaced" row (cancel the replacement instead, which calls `unmark_replaced`).

## 4. Accounting

All entries are in company currency. A party account in any other currency is refused in `validate_party`. One Journal Entry is posted per step, dated the step's date, with `cheque_no`/`cheque_date` set, `pdc_cheque` linked, and `custom_p_type` taken from PDC Settings.

| Step | Received cheque (Customer) | Issued cheque (Supplier) | Voucher type |
|---|---|---|---|
| Submit | Dr Cheques in Hand; Cr Customer, one row per invoice (`reference_type` Sales Invoice) plus an advance row (`is_advance`) for any unallocated amount | Dr Supplier per Purchase Invoice and advance; Cr Cheques Issued | Journal Entry |
| Deposit | no entry; History row only | none | none |
| Clear | Dr Bank; Cr Cheques in Hand. `clearance_date` is set on the JE | Dr Cheques Issued; Cr Bank. `clearance_date` is set | Bank Entry |
| Bounce before clearing | Dr Customer (reversal rows, which re-open the invoices); Cr Cheques in Hand | Dr Cheques Issued; Cr Supplier (reversal) | Journal Entry, or Bank Entry if there are charges |
| Bounce after clearing | Dr Customer (reversal); Cr Bank | Dr Bank; Cr Supplier (reversal) | Bank Entry |
| Bounce charges (same JE) | Dr Cheque Bounce Charges, or Dr Customer on account when "Recover From Party" is ticked; Cr the bank deposited to | Dr Cheque Bounce Charges; Cr the bank written on | |
| Re-deposit | Same as Submit, but each invoice is capped at its current outstanding and the rest goes to advance | none | Journal Entry |
| Return / Stop | Dr Customer (reversal); Cr Cheques in Hand. If the cheque was already Bounced, no entry is posted | Dr Cheques Issued; Cr Supplier (reversal) | Journal Entry |

**Reversal rows** come from `accounting.reversal_party_rows(cheque, settling_je)`. They are the settling entry's *current* party rows with debit and credit swapped. The settling entry is the JE of the last `Received` / `Issued` / `Re-deposited` event. The rows are read from the JE, not from the cheque's References table, because Payment Reconciliation may have split an advance row onto an invoice since then. Reading the rows follows that change.

- An **invoice row** keeps its invoice reference, which re-opens the invoice.
- An **advance row** is reversed *on account*, with no reference. ERPNext only lets a receivable row reference a Journal Entry when it is credited (a payable row when debited). Reversing a customer advance debits the receivable, so it fails with "you can select reference document only if account gets credited". After the reversal JE is submitted, `accounting.reconcile_advances` matches the original advance row against it with `erpnext.accounts.utils.reconcile_against_document`, the same call Payment Reconciliation makes. The Payment Ledger then nets to zero, so Accounts Receivable shows neither an open advance nor an open debit. Undo Last Step cancels the reversal JE, ERPNext un-links the match, and the advance is open again.

**Bank reconciliation:** clearance JEs get `clearance_date` at once. A bounce after clearing is a normal Bank Entry, and it shows in the Bank Reconciliation Statement until it is cleared there.

## 5. Validation and guards

| Guard | Where |
|---|---|
| Amount > 0. Issued cheques need a Company Bank Account. The party account must be a Receivable / Payable account of the company, in company currency | `PDCCheque.validate_party` |
| References must be Sales Invoices for a Customer and Purchase Invoices for a Supplier, submitted, for the same company, party and party account. No duplicates. Allocated ≤ outstanding. Total allocated ≤ amount | `PDCCheque.validate_references` |
| Unallocated amount only when **Allow Unallocated Amount** is on | `validate_references`, `accounting.settlement_party_rows` |
| Duplicate cheque number for the same party, type and drawer's bank (when **Block Duplicate** is on) | `validate_duplicate` |
| Two cheques racing for one invoice: invoices are row-locked (`for_update`) and re-checked in `before_submit` | `PDCCheque.before_submit` |
| No deposit or clear before the cheque date; nothing presented after **Cheque Valid For (Months)** | `lifecycle.validate_presentable` |
| The step's bank account must be a non-group Bank or Cash account of the same company | `lifecycle._bank_account` |
| A Sales / Purchase Invoice cannot be cancelled while an active cheque (In Hand, Issued, Deposited or Cleared) settles it | `invoice_guard.block_invoice_cancel` |
| A cheque's JE cannot be cancelled from the JE form | `invoice_guard.block_je_cancel` |
| Cancel only before the first step; Undo needs Accounts Manager | `PDCCheque.before_cancel`, `lifecycle.UNDO_ROLES` |

## 6. Bulk actions, printing and "from invoice"

- **List → Actions → Deposit Selected / Clear Selected** (`pdc_cheque_list.js`) calls `lifecycle.bulk_action(names, action, posting_date, bank_account)`. Each cheque runs inside its own savepoint, and a failure is rolled back to that savepoint. The dialog lists every cheque that was not done, with the reason. A blank bank account on Clear means each cheque's own deposit or bank account is used.
- **PDC Deposit Slip** (Jinja) lists every received cheque of the company with the same `deposit_date` and `deposit_account` as the cheque you print it from. Open it from the **Deposit Slip** button on any deposited cheque.
- **PDC Cheque Receipt** is the acknowledgement handed to the customer.
- **Create → PDC Cheque** on a submitted Sales or Purchase Invoice calls `lifecycle.make_from_invoice`. It returns an unsaved draft (built by `_unsaved`, which sets `__islocal` so `frappe.model.sync` names it) with that invoice's outstanding amount allocated.
- **Get Outstanding Invoices** on the cheque calls `lifecycle.get_outstanding_invoices`. It fills the References table with the oldest-due invoices first, up to the cheque amount.

## 7. Notifications

### SMS to the party

Settings live in PDC Settings → **SMS to Party (via Sparrow SMS)**:

| Field | Meaning |
|---|---|
| Send SMS to Party | Master switch. Off by default |
| On Cheque Received / Reminder Before Cheque Date / On Cheque Cleared / On Cheque Bounced | One switch per event |
| Days Before | Reminder lead time |
| *… Message* | Jinja template over the cheque (`{{ doc.party_name }}`, `{{ doc.cheque_no }}`, `{{ doc.amount }}`, `{{ doc.cheque_date }}`, `{{ doc.bounce_reason }}`, …) |

`notifications.send_party_sms(cheque, event)` sends only when all three are on: the master switch, the event's switch, and **Sparrow SMS Settings → Enabled**.

It reuses `sparrow_sms.sms_dispatch._process_after_commit`, which runs only after the transaction commits. That means:

- a rolled-back step sends nothing;
- every attempt writes a **Sparrow SMS Log** row (`reference_doctype` PDC Cheque, `recipient_field` `pdc.<event>`);
- a failed direct send falls back to the queue.

The mobile number is looked up in this order:

1. the cheque's **Mobile No**;
2. the party's `custom_mobile_number`, then `mobile_no`;
3. the primary or latest linked Contact.

If no number is found, the attempt is still logged as Failed with the reason. An SMS never blocks the step that triggered it.

> **SMS Notification Rule** records also work on PDC Cheque (submit and cancel events) and ignore these switches. Use one mechanism or the other, or the party gets two messages.

### Daily job

`notifications.daily_run` runs from cron `25 8 * * *` (Asia/Kathmandu, before banks open). It does two things:

1. `send_due_reminders` sends an SMS for each *In Hand* received cheque dated between today and today + Days Before. `last_reminder_on` makes sure it is sent once per cheque.
2. `send_daily_digest` emails every enabled System User who has **Send To Role**. The email lists:
   - received cheques In Hand dated within *Cheques Due Within* days, or overdue;
   - issued cheques still Issued in the same window;
   - cheques that bounced since yesterday.

   Nothing is sent when all three lists are empty.

## 8. Reports and workspace

| Report | What | Notes |
|---|---|---|
| PDC Register | Every submitted cheque filtered by company, type, status, party and **cheque date** range; summary totals per status | |
| PDC Maturity | Open cheques (Received: In Hand or Deposited; Issued: Issued) in buckets Overdue / 0–7 / 8–30 / 31–60 / 61+ days from *As On*; per cheque or per party; bar chart | |
| PDC Bounce Analysis | Per party: cheques, amount, times presented, **bounce events** (from History, so a bounced-then-cleared cheque still counts), bounce %, bounced amount, charges, most common reason | Charges are the cheque's current `bounce_charges`; an earlier bounce's charge on a re-deposited cheque is not summed |

The workspace's number cards (in hand, due this week, issued outstanding, bounced this month) and charts (by status, by cheque date) are created by `install.ensure_dashboard`. Number Card and Dashboard Chart are not module-syncable in v15, so they can't ship as JSON. It only creates records that are missing and never edits existing ones.

## 9. Gotchas

- **Journal Type on a bounce.** Both bounce dialogs (Payment Entry and cheque record) ask for the Journal Type (`custom_p_type`), defaulting to PDC Settings → JV Type. It is passed down `bounce(..., jv_type)` → `accounting.post_bounce` → `make_journal_entry(jv_type=)`. Every other step uses the settings value. A type with no Numbering Configuration rule for the company is refused with "Journal Type … has no numbering rule", not ERPNext's bare `custom_document_no` error.
- **JE numbering.** Journal Entry carries the mandatory custom fields `custom_p_type` (JV Type) and `custom_document_no`. The numbering engine fills `custom_document_no` from the Numbering Configuration of the JV Type. If the JV Type in PDC Settings has no numbering rule for a company, every step for that company fails on the JE's mandatory Document No. Fix the rule; don't clear the field.
- **Frappe Workflow on Journal Entry.** Cheque JEs are inserted and submitted directly. If a site puts an approval workflow on Journal Entry, those submits will be refused by the workflow. In that case exempt the cheque JEs (for example with a workflow condition on `pdc_cheque`).
- **Seven companies.** Accounts are per company. "Create Missing Accounts" adds every company without a row, and a missing row stops a submit with "Set the cheque holding accounts".
- **BS dates.** The module stores AD dates, like ERPNext. Cheque naming uses the BS fiscal year: `NGI-PDC-83/84-00001`, via `make_name_with_fiscal_year`. That throws nothing if there is no Fiscal Year row, but then falls back to `NGI-PDC-00001`.
- **Miti fields.** rdp_common_app's **Bs Conversion** records map AD dates to the BS `custom_*_miti` fields. For Journal Entry that is `posting_date → custom_posting_miti` and `cheque_date → custom_reference_miti`. The desk fills them only in the browser. `utils/bs_miti.py` (`"*"` validate) fills them server-side on every document a record covers, with the app's exact converter (`utils/bs_converter.py`, nepali_datetime). That covers the cheque JEs too; the replacement Payment Entry draft calls `set_mitis` itself, because it opens unsaved.
- **Replica.** Reports read the replica (`read_from_replica`). Right after a step, a report may lag by a moment.
- **Settings defaults.** A Single's JSON defaults land only when the form is saved. `install.apply_settings_defaults` writes every default that has never been stored, so `allow_on_account`, the validity and the SMS texts work before anyone opens the form.
- **Old Payment Entry bounces.** `custom_code/payment_entry/cheque_bounce.py` and the Party Ledger's "Cheque Bounce -" handling are untouched. They apply only to cheques booked as Payment Entries.
- **`company_data_to_be_ignored`.** PDC Settings is in that list, so **Delete Transactions** keeps it. PDC Cheques are transactions and are deleted.

## 10. Tests

`pdc/doctype/pdc_cheque/test_pdc_cheque.py` has 22 tests: 16 in `TestPDCCheque` and 6 in `TestPaymentEntryBounce` (§12). They cover:

- the full received lifecycle with GL balances checked;
- advances;
- bounce before and after clearing, with charges both expensed and recovered;
- bounce, return and undo of a cheque carrying an advance (nothing left open in the Payment Ledger);
- re-deposit;
- return, replace and cancel of the replacement;
- undo;
- the issued lifecycle;
- every guard;
- bulk deposit carrying on past a failing cheque;
- SMS switches;
- Payment Entry cheques:
  - bounce with charges, then undo, then a second bounce that reuses the record, then re-present;
  - replacement by a new Payment Entry, and cancelling it;
  - an unallocated Payment Entry;
  - a supplier payment;
  - refusing a Payment Entry already bounced the old way.

The tests use an existing submitted invoice with outstanding > 50,000, preferring a company that has both open Sales and Purchase Invoices. Everything they create is rolled back.

`bench run-tests` fails at bootstrap on the dev bench. Run the suite with this:

```python
# run_pdc.py: ../env/bin/python run_pdc.py   (from the bench's sites/ folder)
import os, sys, unittest
os.chdir("/home/frappe/frappe-bench/sites")        # site log paths are cwd-relative
import frappe
frappe.init(site="avinasdemo.raindropinc.com", sites_path="."); frappe.connect()
frappe.flags.in_test = True
suite = unittest.defaultTestLoader.loadTestsFromName("avinashgroup_app.pdc.doctype.pdc_cheque.test_pdc_cheque")
ok = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
frappe.db.rollback(); frappe.destroy(); sys.exit(not ok)
```

`TestPaymentEntryBounce` rolls back to a savepoint after each test, because every test bounces the same Payment Entry.

Result on 27 Oct 2026, avinasdemo: `Ran 22 tests … OK`.

## 11. Not built

- Multi-currency cheques. Holding accounts and party accounts must be in company currency.
- Partial bounce or partial clearance (the bank returns the whole cheque).
- Projecting PDCs into cash-flow reports. Net Position of Cash and Bank's "Consider Post Dated Cheques" filter is still about GL `is_pdc` and does not read this module.
- Cheque *printing* for issued cheques. Use the existing NG Cheque Print formats on the payment side.
- Accounting dimensions beyond Cost Center.
- Bounce charges on an issued cheque recovered from the supplier.

## 12. Cheques entered in Payment Entry

The group enters every cheque straight into a **Payment Entry**, to the bank, and does not use the PDC holding flow. That stays as it is. This section covers what happens when one of those cheques bounces. The code is in `pdc/payment_entry_bounce.py`.

### Why the old button was replaced

`custom_code/payment_entry/cheque_bounce.py` wrote the PE's GL rows back, swapped, under the PE's own voucher number and always dated today. It had:

- no bounce date, reason or bank charges;
- no undo, re-presentation or replacement;
- a `frappe.db.commit()` in the middle of the request.

The Payment Entry button no longer calls it. It stays only so the PEs it already bounced keep a readable origin. Party Ledger still reads their `Cheque Bounce -` rows, and such a PE is **refused** by the new flow, because reversing it again would double the bounce.

### Flow

```
Payment Entry (submitted, unchanged)
  └─ Cheque ▸ Cheque Bounced  (date, reason, bank charges, recover from party, Journal Type)
       1. register_from_payment_entry: PDC Cheque, status Cleared, payment_entry = PE,
          History row 1 "Received"/"Issued" → payment_entry (no JE)
       2. lifecycle.bounce: one JE = the PE's GL rows swapped + charges
       PE: custom_cheque_bounce = "Cheque Bounced", pdc_cheque = the record
  On the record (or PE ▸ Cheque menu):
     Re-present ......... JE = the PE's GL rows again (invoices capped at outstanding) → Cleared
     Replace With New Payment ... draft PE (pdc_replacement_of); its submit → original Replaced,
                                  its cancel → back to Bounced
     Replace With PDC Cheque .... the existing PDC replacement (for a post-dated new cheque)
     Return to Party ............ no entry; status Returned
     Undo Last Step ............. cancels the step's JE, flag re-synced
  PE ▸ Cheque ▸ Undo Bounce ..... payment_entry_bounce.undo_bounce: the same undo, from the PE,
                                  only while "Bounced" is the record's latest step (Accounts Manager)
```

### Accounting

`accounting.payment_entry_rows(cheque, pe, swap)` rebuilds the PE's effect from its **GL Entries** rather than from its fields, so deductions (TDS and the like) and a separate advance account come out right without special cases. The rows are built like this:

| PE GL row | Bounce (`swap=True`) | Re-present (`swap=False`) |
|---|---|---|
| Bank / cash | swapped: Cr bank (Receive) or Dr bank (Pay) | as posted |
| Deduction accounts | swapped | as posted |
| Party, against an invoice | swapped, invoice reference kept, so the invoice re-opens | as posted, capped at the invoice's current outstanding; any remainder becomes an advance |
| Party, against the PE itself (unallocated) | swapped on account, then reconciled against the bounce JE (`reconcile_advances`, `voucher_type` Payment Entry) | as posted, `is_advance` Yes |

The bounce is always "after clearance", so no holding account is involved. The PDC Settings row is needed only for the **Cheque Bounce Charges** account (`get_company_accounts(..., require_holding=False)`).

Reconciling a PE advance makes ERPNext re-save that PE: it adds a reference row and, with a separate advance account, posts a pair of GL rows. `_payment_entry_gl` drops that pair (the row against the bounce JE and its offset against the PE), so a later re-present reads only the original payment. If ERPNext refuses the reconciliation, the bounce still stands: the two stay open on account for Payment Reconciliation, with an Error Log naming the cheque.

### Fields

| Field | On | Meaning |
|---|---|---|
| `pdc_cheque` | Payment Entry | The record that tracks this PE's cheque |
| `pdc_replacement_of` | Payment Entry | This PE replaces that bounced cheque |
| `custom_cheque_bounce` | Payment Entry | Existing flag. `lifecycle.sync_payment_entry_flag` sets it to "Cheque Bounced" while the record is Bounced, Returned or Replaced, and clears it after Undo or Re-present |
| `payment_entry` | PDC Cheque, PDC Cheque Event | The PE the cheque was entered in. A record with it gets **Re-present** instead of Re-deposit |
| `replaced_by_payment_entry` | PDC Cheque | The replacement PE |
| `pdc_payment_entry` | Journal Entry | The PE whose cheque this JE bounces or re-presents. Set by `accounting.make_journal_entry` from the cheque's `payment_entry` |

**Connections.** The Payment Entry form's Connections section has a **Cheque Bounce** group listing the PDC Cheque and the Journal Entries. It comes from `override_doctype_dashboards` → `payment_entry_bounce.get_payment_entry_dashboard`; Payment Entry ships no dashboard of its own, so this only adds to whatever other apps add. The PDC Cheque's own Connections section (`pdc_cheque_dashboard.py`) lists every Journal Entry it posted and its Payment Entry.

### Guards

| Guard | Where |
|---|---|
| Only a submitted Receive or Pay PE for a Customer or Supplier, in company currency | `validate_payment_entry` |
| A PE bounced by the old button is refused | `validate_payment_entry` (`OLD_BOUNCE_REMARK`) |
| A second bounce of the same cheque is refused (the record is already Bounced) | `lifecycle.bounce` → `_require` |
| The original PE cannot be cancelled while its record is Bounced, Returned or Replaced | `payment_entry_bounce.before_cancel` |
| Cancelling the PE cancels a record left Cleared with nothing posted (after an undone bounce) | `payment_entry_bounce.on_cancel` |
| The replacement PE is built fresh, so the numbering fields (`custom_document_no` …) are never copied | `make_replacement_payment_entry` |

### Deploy

The PDC Cheque and PDC Cheque Event doctypes gained fields, and Payment Entry gained the two custom fields above (fixtures). Run `bench --site avinas1 migrate` and clear the cache, so the new `doc_events` on Payment Entry load, then restart the web server.

