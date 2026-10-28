# Letters of Credit (LC module)

Import letters of credit for the group's foreign purchases: steel, valves and machinery from India and third countries. The module tracks each LC from the application to the bank until it closes. Every money step posts its own Journal Entry.

- Code: `avinashgroup_app/lc/` (its own Module Def, `LC`). See [`lc/README.md`](../avinashgroup_app/lc/README.md) for what lives where.
- User guide: [`user-guide/13-letters-of-credit.md`](user-guide/13-letters-of-credit.md).

## 1. Why it exists

ERPNext has no letter of credit. Before this module, an import paid through a bank LC showed up only as a bank payment to the supplier. That left several things outside the books:

- **Margin:** the cash the bank blocks when it opens the LC was booked by hand, if at all.
- **Bank charges:** commission, SWIFT, amendment and discrepancy charges went to an expense account. They never reached the stock's landed cost.
- **Exchange difference:** the gap between the invoice rate and the bank's settlement rate was worked out on paper.
- **Dates:** nothing warned about the latest shipment date, expiry, usance maturity, or the customs proof the bank expects.
- **NRB rules:** nothing checked the rules that bind the terms. These are the BCI report for large sight LCs, the 180-day usance limit for trading firms, and the named customs point.

## 2. Environment and deploy

1. Run `bench --site avinas1 migrate`. It syncs the module, the two custom fields (`Journal Entry-letter_of_credit`, `Landed Cost Voucher-letter_of_credit`), the LC workspace, reports and print format. It then runs `lc.install.after_migrate`, which:
   - writes the LC Settings defaults;
   - sets JV Type to `Bank Entry`;
   - adds a **Bs Conversion** record for Letter of Credit, so the application, expiry and latest-shipment Mitis fill server-side.
2. In **LC Settings**, click **Create Missing Accounts**. It adds **LC Margin** and **LC Charges Clearing** under Current Assets for each of the seven companies. Then set **Firm Type** per company (Industry or Trading).
3. Every company needs an **Exchange Gain / Loss Account** on its Company record. A settlement with an exchange difference refuses to post without one.
4. A supplier invoiced in USD or INR needs a payable account in that currency, set on the Supplier's Accounts table. ERPNext refuses a USD Purchase Invoice booked to an NPR creditor.

> On the dev site `avinasdemo.raindropinc.com`, `migrate` stops at an unrelated HRMS patch before fixtures sync. Sync the module by hand instead (the script is in §9):
>
> 1. Create Module Def `LC`.
> 2. Run `frappe.model.sync.sync_for("avinashgroup_app")`.
> 3. Run `sync_fixtures("avinashgroup_app")`.
> 4. Run `avinashgroup_app.lc.install.after_migrate()`.
>
> The first hand sync on that site failed once with "DocType LC Settings not found". A rerun, and a later clean sync from scratch, both went through. The cause was not found. If it recurs during `migrate`, rerun it.

## 3. The lifecycle

```
Draft ─submit→ Applied ─open (bank LC no., margin)→ Opened ─→ Partly Settled ─→ Settled ─close→ Closed / Expired
                  │                                    │
                  └─ add bank charge (any time) ───────┴─ deposit margin, amend, add shipment

Shipment:  Shipped ─docs received→ Docs Received ─accept (usance only)→ Accepted ─settle→ Settled ─customs proof
```

- Each step is a button on the submitted LC that calls `lc/lifecycle.py run_action`. Each adds one **History** (`LC Event`) row.
- **Undo Last Step** (Accounts Manager) reverses the newest step:
  - cancels its Journal Entry;
  - deletes the rows it added (charges, amendment rows, a shipment);
  - restores the shipment row it touched;
  - restores the LC's lifecycle and amendable fields from the JSON snapshot on the History row.
- The LC's position is recomputed from its rows after every step by `lifecycle.position()`: shipped, settled, available, margin held, charges and status.
- **Cancel** is allowed only while the LC is Applied and has no later steps. An opening commission booked on an Applied LC is a later step, so undo it first.

## 4. Accounting

| Step | Entry |
|---|---|
| Open (with margin) / Deposit Margin | Dr LC Margin / Cr Bank |
| Add Bank Charge, amendment charge | Dr LC Charges Clearing / Cr Bank |
| Settle a shipment | Dr Supplier (at the invoice's booked rate, against the Purchase Invoice; as an advance if none is linked)<br>Dr / Cr the company's Exchange Gain / Loss account (bank rate − booked rate)<br>Cr LC Margin (margin used)<br>Cr Bank (the rest) |
| Close | Dr Bank / Cr LC Margin (margin still held) |
| Create → Landed Cost Voucher | The LCV credits LC Charges Clearing and loads the charges onto the linked Purchase Receipt / stock-updating Purchase Invoice |

**Steps that post nothing:**
- Applying for and opening an LC: an LC is a bank promise, not a payment.
- Usance **acceptance**: the supplier stays in Accounts Payable at the invoice rate until the bank pays at maturity. The maturity is tracked on the shipment.

**Settlement details:**
- *Margin used* defaults to the shipment's share of the margin held, or all of it on the last drawing. The dialog shows the entry before posting (`settlement_preview`).
- ERPNext values a Journal Entry row that references a Purchase Invoice at the invoice's own conversion rate (`JournalEntry.set_exchange_rate`). The exchange row is therefore computed from that same rate, so the entry balances.
- Supplier payables in company currency are also handled: the row is the LC amount × booked rate, in NPR.

All entries are Bank Entries, numbered through LC Settings → JV Type. Their reference is the bank's LC number, and they are marked cleared on their own date.

## 5. Nepal Rastra Bank rules

These are LC Settings fields, not constants, because NRB revises its forex circular several times a year.

- **Source:** the NRB Unified Foreign Exchange Circular 2082, as amended on 6 Apr 2026 (Circular 10/2082/83) and 5 Oct 2026, plus banks' published LC terms.
- **Not checked against the original:** these rules were researched from secondary sources (the NRB site was unreachable). Check them against the current circular.

| Rule | Where enforced | Default |
|---|---|---|
| BCI report on the beneficiary for a sight LC ≥ USD 50,000, ≤ 1 year old | `validate_bci` on submit | 50,000 / 365 days |
| Trading firm usance ≤ 180 days (industries: per contract) | `check_usance_limit` on validate and amendment | 180 |
| Nepal customs point named in the LC | required field, checked on submit | — |
| NRB margin % | default for the LC's Margin % | Industry 2, Trading 10; e-payment customs point 1 / 3 |
| India imports above INR 3 crore need an LC | headline on the Purchase Order | 30,000,000 |
| Third-country draft / TT limit | headline on the Purchase Order | USD 50,000 |
| Customs proof to the bank within N days of settlement | `customs_proof_due` on the shipment, daily digest | 120 (**not confirmed** from NRB text; set what the bank enforces) |

## 6. Guards (`lc/guards.py`)

- A Purchase Invoice or Purchase Receipt linked to a shipment of a submitted LC cannot be cancelled.
- A Journal Entry with `letter_of_credit` set can be cancelled only by the LC's own Undo or Cancel (they set `INTERNAL_CANCEL_FLAG`).
- In `lifecycle.py`:
  - No shipment after the latest shipment date or after expiry.
  - Shipments may not total more than LC amount × (1 + tolerance).
  - With partial shipment not allowed, only one shipment, and it must be the full amount.
  - A Purchase Invoice or Receipt links to one shipment only, and must be in the LC's currency, company and supplier.
  - Documents presented after expiry are refused. Documents presented after the presentation period are noted as a discrepancy, not refused, because the bank may waive it.
  - Close is refused while any shipment is unsettled.

## 7. Daily digest

`lc.notifications.daily_run` runs from `scheduler_events` cron `35 8 * * *`, ten minutes after the PDC digest. It emails the LC Settings digest role a list of everything due within "Warn This Many Days Ahead" (default 15), with overdue items in red:

- latest shipment dates coming up;
- LCs expiring;
- usance bills maturing;
- customs proofs due.

## 8. Reports, print, workspace

- **LC Register:** each LC's position, ship-by and expiry dates.
- **LC Maturity:** accepted usance bills, with days left and value at today's rate.
- **LC Margin and Charges:** per company and bank: margin deposited, used, released and held; charges booked, capitalised by LCVs, and pending.
- **LC Cost Sheet:** per shipment of one LC: the bank's debit, the exchange difference, its share of LC charges and of the LCV duty, freight and clearing, then the landed cost and landed rate per unit of LC currency.
- **Print format:** **LC Summary** prints the terms, position, shipments and document checklist.
- **Workspace:** `LC`.

## 9. Tests

`lc/doctype/letter_of_credit/test_letter_of_credit.py` has 15 tests. Everything they create is rolled back. They run against Grihalaxmi:

- They copy one of its stock-updating Purchase Invoices into a USD invoice (booked rate 133) for a throw-away supplier with a USD payable account.
- They settle at a bank rate of 135.

**What they cover:**
- **Full sight-LC run:** checked against the GL (margin, exchange loss 20,000, bank, invoice cleared).
- **Settlement:** an advance settlement with no invoice linked.
- **Usance:** acceptance and maturity.
- **NRB checks:**
  - the trading-firm usance limit and margin default;
  - the BCI rule both ways.
- **Shipment checks:**
  - tolerance and dates;
  - partial shipment.
- **Undo:**
  - amendment + undo;
  - undo of a settlement (invoice re-opens);
  - the cancel guards.
- **Close:** margin release.
- **Landed cost:** the LCV draft.
- **Output:** all four reports, the digest, and the print format.

`bench run-tests` fails at bootstrap on the dev bench. Run the suite from the bench's `sites/` folder with this:

```python
# run_lc.py:  ../env/bin/python run_lc.py
import os, sys, unittest
os.chdir("/home/frappe/frappe-bench/sites")        # site log paths are cwd-relative
import frappe
frappe.init(site="avinasdemo.raindropinc.com", sites_path="."); frappe.connect()
frappe.flags.in_test = True
suite = unittest.defaultTestLoader.loadTestsFromName("avinashgroup_app.lc.doctype.letter_of_credit.test_letter_of_credit")
ok = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
frappe.db.rollback(); frappe.destroy(); sys.exit(not ok)
```

Result on 27 Oct 2026, avinasdemo: `Ran 15 tests … OK`.

**Gotchas found writing them:**
- On this site, a Purchase Invoice is submitted by the app on insert.
- Supplier needs `custom_company` for its naming.
- Supplier Groups are company-scoped.
- `custom_document_no` must be numeric.

## 10. Not built

- **Bank facility limits:** per-bank LC limits and their usage.
- **Trust-receipt / import loans:** with their interest.
- **Usance acceptance liability:** not booked as a separate liability. It is tracked on the shipment only (§4).
- **MT700 handling:** import of the bank's MT700 text, and a printed Bi.Bi.Ni Form 3 in the bank's own layout.
- **Revolving and transferable LCs.**
- **LCs in company currency:** refused, since an import LC is in the supplier's currency.
- **Automatic expiry:** an expired LC is closed by a person, because the bank may still honour documents under a waiver.
- **Customs-proof deadline:** the 120-day rule is unverified (§5).
