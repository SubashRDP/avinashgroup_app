# Worked example: entering an old generator (back entry), all 5 years

For: accounts and store staff entering assets the company already owned
before ERPNext. One asset, start to finish, every click, every figure.

Every number below was produced by the system itself (tested on
**demo-nggroup**, 2026-11-05, then rolled back). If your screen shows something
different, stop and ask Accounts.

Main user guide: [fixed-assets-user-guide.md](fixed-assets-user-guide.md).

---

## The example

| | |
|---|---|
| Company | Nepal Gas Udhyog Pvt. Ltd. (NGI) |
| Asset | Generator 62.5 KVA |
| Bought and started using | **15 Bhadra 2078** (31-08-2021) |
| Cost (without VAT) | **Rs 5,00,000** (VAT 65,000 was claimed back, so it is not part of the cost) |
| Pool | **B, 25%** (generators go in B, not D: Supreme Court ruling) |
| Today | Kartik 2083, FY 83/84 |

**The 5 years.** The generator has been used through five fiscal years,
78/79 to 82/83. We are now in the sixth, 83/84.

---

## First, understand where each year goes

NGI's books came into ERPNext as an **opening balance on 1 Shrawan 2082**, the
first day of FY 82/83. That opening balance **already includes this generator**,
at its value on that day. So:

| Fiscal year | Depreciation | Where it is booked |
|---|---|---|
| 78/79 | 1,25,000.00 | old books (before ERPNext) |
| 79/80 | 93,750.00 | old books |
| 80/81 | 70,312.50 | old books |
| 81/82 | 52,734.38 | old books |
| **Total before ERPNext** | **3,41,796.88** | you type this as the opening figure |
| 82/83 | 39,550.78 | **ERPNext posts it** (on 32 Asar 2083) |
| 83/84 | 29,663.08 | **ERPNext posts it** on 32 Asar 2084 |
| 84/85 onward | 25% of what is left, each year | ERPNext, every Asar end |

**The value of the generator on 1 Shrawan 2082** (the opening day) is
5,00,000 − 3,41,796.88 = **1,58,203.12**. That amount is part of the Pool B
opening balance. Accounts should confirm this before you start.

### How these figures are worked out

Pool B is 25% a year on the value left (written down value).

| Year | Value at start | × 25% | Depreciation | Value at end |
|---|---|---|---|---|
| 78/79 | 5,00,000.00 | full year (bought in Bhadra) | **1,25,000.00** | 3,75,000.00 |
| 79/80 | 3,75,000.00 | | **93,750.00** | 2,81,250.00 |
| 80/81 | 2,81,250.00 | | **70,312.50** | 2,10,937.50 |
| 81/82 | 2,10,937.50 | | **52,734.38** | 1,58,203.12 |
| 82/83 | 1,58,203.12 | | **39,550.78** | 1,18,652.34 |
| 83/84 | 1,18,652.34 | | **29,663.08** | 88,989.26 |

**The first year depends on the month** the asset came into use (the thirds rule):

| In use from | First year |
|---|---|
| Shrawan to Poush | cost × 25% (full) |
| Magh to Chaitra | cost × 25% × **2/3** |
| Baisakh to Asar | cost × 25% × **1/3** |

Our generator came in Bhadra, so the first year is full.

> **Use the figure from the old books.** If the old books used this same method,
> it equals the table. If they show something else for the years before
> ERPNext, type what the old books show and tell Accounts.

---

## Before you start: checklist

- [ ] Accounts confirms the generator is **inside the opening balance**
      (1 Shrawan 2082). If it is not, do **not** use this page; ask Accounts.
- [ ] You know the **cost**, the **date it came into use**, and the
      **depreciation already booked** before ERPNext (3,41,796.88 here).
- [ ] You know **how many years** were booked before ERPNext (4 here: 78/79,
      79/80, 80/81, 81/82).

---

## Step 1: the Item (once for each kind of asset)

1. In the search bar at the top, type **Item** and open **Item List**.
2. Click **+ Add Item**.
3. Fill in:

   | Field | Enter |
   |---|---|
   | Item Name | Generator 62.5 KVA |
   | Company | Nepal Gas Udhyog Pvt. Ltd. |
   | Item Group | your company's group for fixed assets |
   | Maintain Stock | **untick** |
   | Is Fixed Asset | **tick** |
   | Asset Category | **Office Equipments** (NGI-ACat-00005). Generators are Pool B |

4. Click **Save** (Ctrl+S).

If the item already exists, skip this step.

---

## Step 2: the Asset

1. Search **Asset** and open **Asset List**. Click **+ Add Asset**.
2. Fill in the top part:

   | Field | Enter | You will see |
   |---|---|---|
   | Item Code | Generator 62.5 KVA | **Asset Name** and **Asset Category** (*Office Equipments*) fill in |
   | Tax Pool | (nothing, it fills itself) | **B** |
   | Company | Nepal Gas Udhyog Pvt. Ltd. | |
   | Location | where it is (e.g. kathmandu) | |
   | **Is Existing Asset** | **tick** | **Purchase Invoice** disappears; **Opening Accumulated Depreciation** and **Opening Number of Booked Depreciations** appear |
   | Purchase Date | **31-08-2021** (15 Bhadra 2078) | |
   | **Available-for-use Date** | **31-08-2021** (15 Bhadra 2078) | |
   | Net Purchase Amount | **5,00,000** (without VAT) | |
   | Calculate Depreciation | tick | the **Depreciation** section opens |
   | **Opening Accumulated Depreciation** | **3,41,796.88** | |
   | **Opening Number of Booked Depreciations** | **4** | |

3. Scroll to **Depreciation → Finance Books**. One row is already there,
   copied from the category. Click the arrow on the right of the row to open it.
   You see **Depreciation Method: Written Down Value** (locked) and
   **Rate of Depreciation (%): 25**. Leave both.
4. In that row, type **Depreciation Posting Date: 16-07-2026** (32 Asar 2083).

   **Why this date:** it is the Asar end of the **first year ERPNext must
   post**. Four years were booked before ERPNext (78/79 to 81/82), so the next
   one is 82/83, which ends on 32 Asar 2083.

   | Years booked before ERPNext | Asset in use from FY | Depreciation Posting Date |
   |---|---|---|
   | 4 | 78/79 | 32 Asar 2083 (16-07-2026) |
   | 3 | 79/80 | 32 Asar 2083 (16-07-2026) |
   | the rule | | the Asar end of FY 82/83, for anything in the opening balance |

   For **every** asset that is in the 1 Shrawan 2082 opening balance this date
   is the same: **16-07-2026**. Only the opening figures change.

5. Click **Save** (Ctrl+S).

---

## Step 3: check what you see after Save

**Finance Books row** (open it with the arrow):

| Field | Shows |
|---|---|
| Depreciation Method | Written Down Value |
| Rate of Depreciation (%) | 25 |
| Depreciation Posting Date | 16-07-2026 |

There is no number of years to see or enter; the system sets it.

**Depreciation Schedule** (scroll down):

| Row | Date | Nepali date | Depreciation | Accumulated |
|---|---|---|---|---|
| 1 | 16-07-2026 | 32 Asar 2083 | **39,550.78** | 3,81,347.66 |
| 2 | 16-07-2027 | 32 Asar 2084 | **29,663.08** | 4,11,010.74 |
| 3 | 15-07-2028 | 31 Asar 2085 | 22,247.32 | 4,33,258.06 |
| 4 | 15-07-2029 | 31 Asar 2086 | 16,685.48 | 4,49,943.54 |
| … | | | | |
| 13 | 16-07-2038 | 32 Asar 2095 | 5,011.30 | **5,00,000.00** |

Check three things:

1. **Row 1 is 39,550.78.** That is (5,00,000 − 3,41,796.88) × 25%. A full
   year: the thirds rule was already used up in 78/79.
2. **Row 1 "Accumulated" is 3,81,347.66.** That is your opening 3,41,796.88 plus row 1.
3. **The last row brings it to 5,00,000.** The schedule runs until the cost is
   fully written off; the last row takes the small remainder.

If row 1 is not 39,550.78, the opening figures are wrong. Fix them before
submitting.

---

## Step 4: Submit

1. Click **Submit**, then **Yes**.
2. You see the status **Submitted**.
3. **Nothing is posted to the accounts.** This is correct: the generator's
   value is already in the opening balance, so entering it posts nothing. Only
   depreciation will post. To see this for yourself, open the **General Ledger**
   report and set **Voucher No** to the asset's ID (e.g. `NGI-AST-00001`):
   there are no rows.

---

## Step 5: the next morning

ERPNext posts depreciation **once a night** (around 1 AM). Any row whose date
has already passed is posted in that night's run. Row 1 (32 Asar 2083) is in
the past, so it posts the first night.

Open the Asset again the next day. You see:

- Status **Partially Depreciated**.
- In the **Depreciation Schedule**, row 1 now has a **Journal Entry** link, e.g.
  `NGI-JE-82/83-02481`. The **82/83** in the name shows it went into FY 82/83.
- Click the link. The Journal Entry shows:

  | Account | Debit | Credit |
  |---|---|---|
  | 555102 Depreciation on Pool B - Office Equipments, Furnitures & Fixtures | 39,550.78 | |
  | 111193 Accumulated Depreciation - Pool B - Office Equipments, Furnitures & Fixtures | | 39,550.78 |

  Entry type: **Depreciation Entry**. Posting date: **16-07-2026** (32 Asar 2083).

- Row 2 (32 Asar 2084) has **no** link yet. It posts by itself on that night.

---

## The full picture after Step 5

| Fiscal year | Depreciation | Value at year end | Where to see it |
|---|---|---|---|
| 78/79 | 1,25,000.00 | 3,75,000.00 | old books (inside the opening figure) |
| 79/80 | 93,750.00 | 2,81,250.00 | old books |
| 80/81 | 70,312.50 | 2,10,937.50 | old books |
| 81/82 | 52,734.38 | 1,58,203.12 | old books; the asset's **Opening Accumulated Depreciation** |
| **82/83** | **39,550.78** | **1,18,652.34** | ERPNext: Journal Entry `NGI-JE-82/83-…` |
| 83/84 | 29,663.08 | 88,989.26 | ERPNext, posts on 32 Asar 2084 |

On the Asset, **Finance Books → Value After Depreciation** shows **1,18,652.34**.

---

## Where else to see it

| Report | Search for | What you see |
|---|---|---|
| Fixed Asset Register | **Fixed Asset Register** | the generator: Gross Purchase Amount 5,00,000, Opening Accumulated Depreciation 3,41,796.88, Depreciated Amount (what ERPNext posted), Asset Value |
| Asset Depreciation Ledger | **Asset Depreciation Ledger** | one line per posted year: 82/83 39,550.78 |
| General Ledger | **General Ledger**, Account = `111193 …Pool B…` | the Credit of 39,550.78 on 16-07-2026 |

---

## What can go wrong

| You see | It means | Do this |
|---|---|---|
| **"This asset already has 4 depreciation periods booked. The depreciation start date must be at least 4 periods after the available for use date."** | **Depreciation Posting Date** is empty, or too early | Type **16-07-2026** in the Finance Books row (Step 2.4) |
| **Purchase Invoice** is required | **Is Existing Asset** is not ticked | Tick it. Old assets never get a new Purchase Invoice |
| Row 1 is not 39,550.78 | Opening Accumulated Depreciation or Net Purchase Amount is wrong | Check both against the old books, then save again |
| Row 1 is cost × 25% (1,25,000) | Opening figures left at 0 | Fill Opening Accumulated Depreciation and Opening Number of Booked Depreciations |
| No Journal Entry on row 1 the next day | The nightly job did not run | Ask Accounts / IT. Do not make a Journal Entry by hand |
| Net Purchase Amount includes VAT (5,65,000) | VAT was added to the cost | Use the amount **without** VAT, unless VAT was not claimed back |

---

## Why not a back-dated Purchase Invoice?

It looks simpler: make a Purchase Invoice dated 15 Bhadra 2078 and let the
system do everything. It **does** work mechanically (tested): ERPNext posts all
five years. But for NGI it is **wrong**:

- the opening balance on 1 Shrawan 2082 **already holds** the generator
  (1,58,203.12), so the invoice would add **5,00,000 a second time**;
- it would post four years of depreciation (78/79 to 81/82) into years that are
  **before** the opening balance, changing figures that were already closed.

Use the back-dated Purchase Invoice only for an asset that is **not** in any
opening balance and whose purchase really belongs in ERPNext's years. Ask
Accounts first.
