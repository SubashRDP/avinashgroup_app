# One Category, Start to Finish: Computers (Pool B)

A complete walk through one category, using the real asset already on
demo-nggroup. Each step says **what to do**, **what you should see**, and **why**.

| | |
|---|---|
| Site | demo-nggroup.raindropinc.com |
| Company | Nepal Gas Udhyog Pvt. Ltd. (NGI) |
| Category | **NGI-ACat-00004, Computer, Printer & Accessories** |
| Item | NGI-ITEM-00236, laptop dell |
| Example asset | **NGI-AST-00001**, Rs 1,50,000, in use 2026-11-05 (Kartik 2083) |
| Purchase Invoice | NGI-PI-83/84-00087 |

Other categories work exactly the same; only the pool, rate and accounts change
(guide: [fixed-assets-user-guide.md](fixed-assets-user-guide.md), section 2).

---

## The life of the asset at a glance

```
Category ─► Item ─► Purchase Invoice ─► Asset (draft) ─► Submit
   (once)    (once)    cost into Pool B      schedule        │
                                                             ▼
             every Asar end: depreciation posts automatically
                                                             │
                    repairs ─► expense under Pool B repairs  │
                                                             ▼
                                     Sell / Scrap ─► asset closed
```

---

## Step 1: Check the category (once)

**Do:** open **Asset Category → NGI-ACat-00004**.

**You should see:**

| Field | Value |
|---|---|
| Company | Nepal Gas Udhyog Pvt. Ltd. |
| Tax Pool | **B** |
| Fixed Asset Account | 111103 - Pool B - Office Equipments, Furnitures & Fixtures - NGI |
| Accumulated Depreciation Account | 111193 - Accumulated Depreciation - Pool B ... - NGI |
| Depreciation Expense Account | 555102 - Depreciation on Pool B ... - NGI |
| Finance Books | Written Down Value (locked), rate **25%** |

Frequency and Total Number of Depreciations are **not shown**: they are always
yearly, and the number of years is filled by the system.

**Why:** Schedule-2 s.1 puts computers in **Pool B**, and s.3(1) gives Pool B
**25%**, on the written-down value, once a year. Pool B has its own three
accounts, so the balance sheet shows Pool B's cost and depreciation separately,
which the tax return needs.

**You change nothing here.** If something looks different, stop and tell IT.

---

## Step 2: The item (once per kind of asset)

**Do:** open **Item → NGI-ITEM-00236** (or create a new item for a new kind of
asset, e.g. a desktop).

**You should see / set:**

| Field | Value | Why |
|---|---|---|
| Maintain Stock | **off** | A fixed asset is not stock for sale |
| Is Fixed Asset | **on** | Purchases go to the asset account, not an expense |
| Asset Category | **NGI-ACat-00004** | This decides the pool, rate and accounts |
| Auto Create Assets on Purchase | **on** | A Purchase Receipt (or an invoice with Update Stock) creates the draft asset for you |

**Why:** the item links every purchase to the right category, so nobody has to
pick an account or a rate by hand.

---

## Step 3: Buy it: Purchase Invoice

**Do:** **Purchase Invoice → New**: supplier, item NGI-ITEM-00236, qty 1,
rate **1,50,000**, VAT 13%. **Submit.**

**You should see** (Accounting Ledger of NGI-PI-83/84-00087):

| Account | Dr | Cr |
|---|---|---|
| 111103 Pool B - Office Equipments ... | **1,50,000** | |
| VAT - NGI | 19,500 | |
| 343100 Trade Payables - Domestic | | 1,69,500 |

A plain Purchase Invoice (Update Stock off) does **not** create the asset.
Create it in step 4 with **Asset → New** and pick this invoice in the
**Purchase Invoice** field. (With a Purchase Receipt, or Update Stock ticked,
ERPNext makes the draft asset itself.)

**Why:**
- The cost goes **straight into Pool B's account**. A fixed asset is capital
  expenditure: it is not deductible as an expense (s.21(3)) but through
  depreciation.
- **VAT is not part of the cost.** It is reclaimed as input VAT. Transport,
  installation or anything needed to bring the laptop into use **is** part of
  the cost: add it on the same invoice line or as a Landed Cost Voucher.

---

## Step 4: Complete the asset

**Do:** **Asset → New** (or open the draft, if one was created), link the Purchase Invoice, and check (here **NGI-AST-00001**):

| Field | Value | Why |
|---|---|---|
| Location | kathmandu | Where it is kept |
| Purchase Date | 2026-11-05 | Bill date |
| **Available-for-use Date** | **2026-11-05** (Kartik 2083) | The day it **started being used**. This decides the first year, so be exact |
| Gross Purchase Amount | 1,50,000 | From the invoice |
| Calculate Depreciation | **on** | |
| Finance Books row | WDV 25%, filled by itself | Do not change |

**Save.** Open the **Asset Depreciation Schedule** link.

**You should see:**

| Year (BS) | Date (Asar end) | Depreciation | Value after |
|---|---|---|---|
| 83/84 | **2027-07-16** | **37,500.00** | 1,12,500.00 |
| 84/85 | 2028-07-15 | 28,125.00 | 84,375.00 |
| 85/86 | 2029-07-15 | 21,093.75 | 63,281.25 |
| 86/87 | 2030-07-16 | 15,820.31 | 47,460.94 |
| 87/88 | 2031-07-16 | 11,865.24 | 35,595.70 |
| … | … | … | … |

**Why:**
- **37,500 = 1,50,000 × 25%, a full year.** Kartik falls in **Shrawan to Poush**,
  so Schedule-2 s.2(5) counts the whole cost this year. Bought in Magh to
  Chaitra it would be 2/3 (25,000); in Baisakh to Asar, 1/3 (12,500).
- **Year two = what is left × 25%** (1,12,500 × 25% = 28,125). That is the
  written-down value method, s.2(2).
- **Dated on the last day of Asar**, the end of the income year. Asar end is the
  15th or 16th of July depending on the year; the system follows the real
  calendar.

---

## Step 5: Submit the asset

**Do:** **Submit** the asset.

**You should see:** status **Submitted**. No new accounting entry: the cost was
already posted by the Purchase Invoice in step 3.

**Why:** submitting fixes the schedule. From now on the system owns the yearly
depreciation.

---

## Step 6: Every year at Asar end (automatic)

**Do:** nothing. On the night after **2027-07-16**, ERPNext's daily job posts
the first entry.

**You should see:** a Journal Entry on 2027-07-16:

| Field / Account | Value |
|---|---|
| JV Type | Journal Entry |
| Document No | next number in NGI's Journal Entry series for 83/84 |
| Dr 555102 Depreciation on Pool B ... | 37,500 |
| Cr 111193 Accumulated Depreciation - Pool B ... | 37,500 |

and in the schedule, row 1 now links to that Journal Entry. The same happens
every Asar end after.

**Why:** s.19(1): depreciation **shall** be deducted every year. It is
compulsory, so it is automatic, and it cannot be skipped in a loss year.

---

## Step 7: Repairs

**Do:** for a repair bill (e.g. a new laptop battery, Rs 8,000), make a
**Purchase Invoice** (or Journal Entry) to an expense account **under
`549200 Repair & Maintenance-Pool B`**, e.g. **549202 R & M - Computer &
Printers - NGI**. Do **not** use the laptop item (that would make a new asset).

**Why:** Section 16 allows repairs up to **7% of Pool B's** year-end base; any
excess is added to Pool B next year. The tax report reads the Pool B repair
accounts to apply that limit, so the pool must be right.

A **major upgrade** that adds life or capacity is not a repair; ask Accounts.

---

## Step 8: Moving it (optional)

**Do:** **Manage → Transfer Asset** to change its location or custodian.

**Why:** keeps the Fixed Asset Register showing where each asset is. No
accounting effect.

---

## Step 9: The end: sell or scrap

### Sell
**Do:** **Manage → Sell Asset**. A Sales Invoice opens: enter the customer and
price, **submit**.

**You should see:**
- a part-year depreciation row up to the **sale date**, posted;
- the Sales Invoice posts the sale, removes the cost (Cr 111103) and the
  accumulated depreciation (Dr 111193), and books the **gain or loss**;
- status **Sold**.

### Scrap (broken, lost, no value)
**Do:** **Manage → Scrap Asset**.

**You should see:** part-year depreciation to today, a scrap Journal Entry
(JV Type Journal Entry, with a Document No), status **Scrapped**.

**Why (books vs tax):**
- In the **books**, ERPNext treats each asset separately: it writes this laptop
  off and books a gain or loss.
- For **tax**, s.4 has **no gain or loss per asset**. The sale price is simply
  subtracted from Pool B and the pool carries on. The **tax depreciation
  report** works this out; you just sell or scrap normally.

**Never** cancel a submitted asset to get rid of it.

---

## Step 10: Check it in the reports

| Report | Filter | Shows |
|---|---|---|
| **Fixed Asset Register** | Company NGI | The laptop: cost 1,50,000, depreciation to date, value |
| **Asset Depreciations and Balances** | Company NGI, year 83/84 | Category totals: opening, additions 1,50,000, depreciation 37,500 (after Asar end), closing |
| **Asset Depreciation Ledger** | Asset NGI-AST-00001 | Each depreciation entry |
| **General Ledger** | Account 111103 / 111193 / 555102 | Pool B's cost, accumulated depreciation, expense |

---

## Quick reference

| When | You do | System does |
|---|---|---|
| Once | Category set up by IT | Pool B, 25%, three Pool B accounts |
| Once per kind of asset | Item: Is Fixed Asset, category, auto create | |
| Buying | Purchase Invoice | Cost to 111103 (draft Asset only with Purchase Receipt / Update Stock) |
| Same day | Asset: location, **real in-use date**, Calculate Depreciation, Save, check, Submit | Schedule: thirds rule, Asar-end dates |
| Every Asar end | Nothing | Dr 555102 / Cr 111193, numbered JE |
| Repairs | Expense to 5492xx (Pool B repairs) | |
| End of life | Manage → Sell Asset / Scrap Asset | Part-year depreciation, gain/loss |
