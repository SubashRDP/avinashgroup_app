# Letters of Credit (LC module)

Import letters of credit for the group's foreign purchases: steel, valves and machinery from India and third countries. Each LC is kept as its own **cost file**, from opening until the goods sit in stock or the fixed-asset register. Every money step posts its own Journal Entry.

- Code: `avinashgroup_app/lc/` (its own Module Def, `LC`). See [`lc/README.md`](../avinashgroup_app/lc/README.md) for what lives where.
- User guide: [`user-guide/13-letters-of-credit.md`](user-guide/13-letters-of-credit.md).

**History.** The first version (commit `7b4469f`, Oct 2026) hung the LC off Purchase Orders, settled Purchase Invoices and capitalised charges through a Landed Cost Voucher. In Nov 2026 the accounts team asked for the LC to stand on its own: its own goods list, every cost collected on it, and a transfer to stock or fixed assets at the end. That is the design below. `patches/lc_standalone_cost_file.py` removes what the old design left in the database.

## 1. Why it exists

ERPNext has no letter of credit. An import paid through a bank LC used to show up only as a bank payment, which left several things outside the books:

- **Landed cost:** commission, SWIFT, amendment and documentation charges, marine insurance, import and excise duty, clearing, ICP booking, and freight to and from the border went to expense accounts. They never reached the stock's value.
- **Margin:** the cash the bank blocks when it opens the LC was booked by hand, if at all.
- **Usance:** the liability between acceptance and maturity, and the exchange difference at maturity, were worked out on paper.
- **Dates:** nothing warned about the latest shipment date, expiry, maturity, or the customs proof the bank expects.

The Nepali practice is an "LC account": one ledger per import, debited with everything, then transferred to purchases. Here that ledger is **LC Goods in Transit** (one account per company; the `letter_of_credit` link on each voucher separates the LCs).

## 2. Environment and deploy

1. Run `bench --site avinas1 migrate`. It syncs the module, the three custom fields (`Journal Entry-`, `Stock Entry-`, `Asset-letter_of_credit`), the workspace, reports and print formats. It then:
   - runs `patches.lc_standalone_cost_file` (removes the five old child doctypes and the Landed Cost Voucher field; carries an old "LC Charges Clearing" account over as the transit account; maps old statuses);
   - runs `lc.install.after_migrate`: LC Settings defaults, JV Type `Bank Entry`, the Bs Conversion rows (open, expiry, maturity, depart, reach Mitis), and the 16 default **LC Cost Types**.
2. In **LC Settings**, click **Create Missing Accounts**. It adds **LC Margin** and **LC Goods in Transit** under Current Assets for each of the seven companies, and picks the **Input VAT** account from the company's Purchase Taxes and Charges Template. Then set **Firm Type** per company.
3. Every company needs an **Exchange Gain / Loss Account** for usance LCs.
4. LC Goods in Transit must **not** be a Stock-type account: it is the Difference Account of the transfer's Stock Entry, and ERPNext refuses a Stock account there.

> On the dev site `avinasdemo.raindropinc.com`, `migrate` stops at an unrelated HRMS patch before fixtures sync. Sync by hand from `sites/`:
> `frappe.model.sync.sync_for("avinashgroup_app")`, then `frappe.utils.fixtures.sync_fixtures("avinashgroup_app")`, then `patches.lc_standalone_cost_file.execute()`, then `lc.install.after_migrate()`, then commit.

## 3. The lifecycle

```
Draft ─submit (LC No., margin)→ Open ─Depart Date→ In Transit ─Reach Date→ Arrived
      ─Transfer→ Transferred ─Close→ Closed

While not closed:  Costs grid (Save / Update posts new rows) · Deposit Margin
Goods, sight:      Pay Goods (bank rate, margin used), in parts up to amount + tolerance
Goods, usance:     Accept Bill (rate, maturity) → Pay at Maturity (bank rate, margin used)
```

- **Submit** needs the LC No. and the bank account. The margin taken at opening is posted then.
- **Shipment fields** (depart, reach, B/L, ports, customs point, Pragyapan, customs proof) and the **amendable terms** (amount, tolerance, expiry, maturity, latest shipment date) are allow-on-submit. Change them, then click **Update**. `before_update_after_submit` re-checks them, because Frappe skips `validate()` there, and `on_update_after_submit` recomputes the status. The goods rows are editable until the transfer.
- **Costs** are typed into the **Costs** grid (allow-on-submit). On save the controller checks new rows (`lifecycle.prepare_cost_row`). On submit or `on_update_after_submit`, each unposted row posts its JE (`post_cost_row`) and gets its own History row. A posted row's inputs may not change (`check_cost_edits`). Deleting a posted row cancels its JE and drops its History row (`remove_cost_row`), and is refused for goods rows and after the transfer. Undo recomputes the totals from the rows (`refresh_position`) rather than trusting the snapshot, because of these out-of-order deletions. `add_cost` stays as an API for scripts and tests.
- **Money steps** are buttons calling `lifecycle.run_action`. Each adds one **History** (`LC Event`) row with a JSON snapshot:
  - the LC's totals;
  - the old values of the child rows it touched;
  - the rows it added;
  - the documents it created elsewhere.
- **Undo Last Step** (Accounts Manager) restores the rows, cancels or deletes those documents, and cancels the JE. A transfer cannot be undone once one of its Assets is submitted.
- **Totals and status** are recomputed from the rows after every step by `lifecycle.position()`.
- **Cancel** is allowed only while the LC has no step after "Opened". It cancels the opening margin entry.

## 4. Accounting

| Step | Entry |
|---|---|
| Submit with margin / Deposit Margin | Dr LC Margin / Cr Bank |
| Cost row, paid by Bank | Dr LC Goods in Transit (cost) + Dr Input VAT (VAT) / Cr Bank or Cash |
| Cost row, paid via Party | the same debits / Cr the party's payable (party = the transporter, insurer or agent) |
| Cost of group **VAT** (Customs VAT) | the whole amount is Dr Input VAT; none of it is cost |
| Pay Goods (sight) | Dr LC Goods in Transit (LC currency × bank rate) / Cr LC Margin (margin used) / Cr Bank (the rest) |
| Accept Bill (usance) | Dr LC Goods in Transit (× acceptance rate) / Cr Supplier |
| Pay at Maturity | Dr Supplier (acceptance value, against the acceptance JE) / Dr or Cr Exchange Gain/Loss (bank − acceptance) / Cr LC Margin / Cr Bank |
| Transfer, stock rows | Stock Entry (Material Receipt) at landed rates: Dr Stock / Cr LC Goods in Transit |
| Transfer, asset rows | Dr each Asset Category's Fixed Asset account / Cr LC Goods in Transit, plus a draft Asset per row |
| Close | Dr Bank / Cr LC Margin (margin still held), and anything left in transit to the account chosen in the dialog |

**Rules worth knowing:**

- **Usance exchange.** The exchange difference at maturity goes to profit and loss, not into the cost. The goods are valued at the rate on the day the liability arose.
- **Margin used.** The default is the payment's share of the margin held, or all of it on the payment that clears the rest. The dialog lets you override it.
- **Supplier payable.** A supplier payable in the LC currency is valued at the rate we pass. A payable in NPR is booked at LC amount × rate.
- **Voucher type.** Bank-moving entries are Bank Entries (reference = the LC No., cleared on their own date). Party and transfer entries are Journal Entries. All are numbered through LC Settings → JV Type.
- **Transit balance.** `accounting.transit_balance(lc)` reads the GL: the transit account's balance over this LC's submitted JEs and Stock Entries. The transfer allocates exactly that figure.

## 5. The transfer (`lc/transfer.py`)

- **Allocation.** The transit balance is shared over the goods rows by **value** (row amount in the LC currency) or by **quantity** (LC → Share Costs By). It is rounded to the paisa, and the largest row takes the remainder.
- **Checks before it runs** (`preview`, also shown in the dialog):
  - the Reach Date is set;
  - the goods are paid or accepted;
  - the transit balance is above zero;
  - every row has an item: a stock item with a warehouse of the company, or a fixed-asset item whose category has a Fixed Asset account for the company.
- **Warning only.** Goods not yet fully paid. A later payment stays in transit until Close clears it.
- **Stock Entry.** `basic_rate` is set per stock UOM, with `set_basic_rate_manually`. `basic_amount` is set too, because ERPNext only computes it for rates it sets itself.
- **Assets.** The Asset is created with `is_existing_asset = 1`, `calculate_depreciation = 0`, and `ignore_mandatory` (Location is the user's to fill). That way ERPNext neither asks for a Purchase Receipt nor posts the value a second time: the JE already holds it.
- **Once per LC.** A cost booked after the transfer stays in transit until Close posts it to the account the user picks.

## 6. Nepal Rastra Bank rules

These are LC Settings fields, not constants, because NRB revises its forex circular several times a year.

- **Source:** the NRB Unified Foreign Exchange Circular 2082, as amended on 6 Apr 2026 (Circular 10/2082/83) and 5 Oct 2026, plus banks' published LC terms.
- **Not checked against the original:** these rules were researched from secondary sources, because the NRB site was unreachable. Check them against the current circular.

| Rule | Where enforced | Default |
|---|---|---|
| BCI report on the beneficiary for a sight LC ≥ USD 50,000, ≤ 1 year old | `validate_bci` on submit | 50,000 / 365 days |
| Trading firm usance ≤ 180 days (industries: per contract) | `check_usance_limit` on validate | 180 |
| NRB margin % | default for the LC's Margin % | Industry 2, Trading 10; e-payment customs point 1 / 3 |
| Customs proof to the bank within N days of the first goods payment | daily digest | 120 (**not confirmed** from NRB text; set what the bank enforces) |

## 7. Guards

- **Cancelling from their own forms** (`lc/guards.py`). A Journal Entry or Stock Entry with `letter_of_credit` set can be cancelled only by the LC's own Undo or Cancel, which set `INTERNAL_CANCEL_FLAG`. Those internal cancels set `ignore_links`, because the LC's rows still point at the voucher.
- **Amounts.** Goods paid and accepted may not pass LC amount × (1 + tolerance). An amendment may not take the amount below what is already paid.
- **Goods rows.** They cannot change after the transfer, and the Reach Date cannot be cleared.
- **Dates.** The Depart Date cannot be before the open date, and the Reach Date cannot be before the Depart Date. Departing after the latest shipment date only warns, because the bank may accept it as a discrepancy.
- **Close.** Refused while a usance bill is unpaid, or while the goods are not transferred.

## 8. Daily digest

`lc.notifications.daily_run` runs from `scheduler_events` cron `35 8 * * *`, ten minutes after the PDC digest. It emails the digest role everything due within "Warn This Many Days Ahead" (default 15), with overdue items in red:

- latest shipment dates of LCs not yet departed;
- expiry of LCs not yet arrived;
- usance bills maturing;
- customs proof due (`has_customs` set, proof date empty, first goods payment + N days).

## 9. Reports, print, workspace

- **LC Cost Sheet** (report and print format): every cost line by group, with subtotals, the total landed cost and VAT beside it. Then each goods row's share and landed rate per unit. After the transfer these are the figures used; before it, an estimate.
- **LC Register:** each LC: paid / accepted, still to pay, dates (open, expiry, maturity, depart, reach), landed cost, VAT, margin, status.
- **LC Maturity:** accepted usance bills not yet paid, with days left, the accepted value, and the value at today's rate.
- **LC Margin and Charges:** per company and bank: margin deposited, used, released and held; cost by group; in stock or assets; still in transit.
- **LC Summary** print: terms, shipment, goods with their landed cost, cost summary.
- **Workspace:** `LC`. It includes the LC Cost Type list under Setup.

## 10. Tests

`lc/doctype/letter_of_credit/test_letter_of_credit.py` has 14 tests. Everything they create is rolled back. They run against Grihalaxmi with:

- a throw-away supplier and insurer;
- one stock item and one fixed-asset item.

**Worked example** (sight LC, USD 10,000 at 135; steel 100 × 80 to stock, a press 1 × 2,000 to assets):

| | Amount (NPR) |
|---|---:|
| Goods | 1,350,000 |
| Commission | 5,000 |
| SWIFT | 1,500 |
| Insurance (on credit) | 3,000 |
| Import duty | 40,000 |
| Excise duty | 10,000 |
| Freight (on credit) | 20,000 |
| **Landed cost** | **1,429,500** |

VAT of 32,600 (customs VAT 30,000 plus freight VAT 2,600) is kept out of the cost. Shared by value, the steel gets 1,143,600 (11,436 per unit) and the press gets 285,900.

**What they cover:**

- **The sight run:** checked against the GL from margin to close.
- **Costs grid:** typed into a draft and posted on submit; added on Update; a posted row refused when changed; a deleted row cancelled; undo afterwards.
- **Usance:** acceptance at 133 and payment at 135, giving an exchange loss of 20,000 to P&L, with the supplier cleared.
- **Undo:** undo of the transfer and of a payment, and undo refused once an Asset is submitted.
- **Guards:** the cancel guards; amount and tolerance; the transfer blockers; close requirements, including a late cost cleared on close; cancel only before any step; LC No. needed to submit.
- **NRB checks:** the trading-firm usance limit and margin default; the BCI rule both ways.
- **Output:** all four reports, the digest and both print formats.

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

Result on 25 Nov 2026, avinasdemo and demo-nggroup: `Ran 14 tests … OK`.

**Gotchas found writing them:**
- On this site, Supplier and Item both need `custom_company` for their naming.
- Supplier Groups and Item Groups are company-scoped.
- `Document.cancel()` sets `docstatus = 2` in memory even when `before_cancel` refuses, so reload before reusing the doc.

## 11. Not built

- **Several shipments per LC with separate arrivals:** an LC has one depart / reach date and one transfer. Partly shipped LCs are transferred once everything arrives, or split into two LCs.
- **Costs in foreign currency:** costs are entered in company currency (what the bank debited).
- **TDS on clearing / freight bills:** book those bills as Purchase Invoices if TDS applies. The LC's "on credit" cost row does not withhold.
- **Bank facility limits, trust-receipt / import loans, revolving and transferable LCs.**
- **Customs-proof deadline:** the 120-day rule is unverified (§6).
