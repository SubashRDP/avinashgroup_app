# Fixed Assets in ERPNext: User Guide

For: accounts and store staff entering fixed assets
Applies to: NGI, NGG, NGK, NGN, GLMI, GEPL (SGU once its categories exist)
Status: live on **demo-nggroup** for testing (2026-11-05). Not yet on the live site.

The law behind all of this is explained in
[fixed-assets-depreciation-guide.md](fixed-assets-depreciation-guide.md).
This guide covers only **what to do in ERPNext**.

---

## 1. What the system does for you

Once an asset is entered with the right **Asset Category**, ERPNext:

- picks the **pool and rate** from the category (A 5%, B 25%, C 20%, D 15%);
- applies the **thirds rule** to the first year, based on the Nepali month the
  asset came into use;
- dates each year's depreciation on the **fiscal year end** (last day of Asar);
- **posts the depreciation journal entry automatically** on that date, to the
  pool's own accounts.

**You never type a rate or a depreciation start date.** If you find yourself
changing either, stop and ask Accounts.

---

## 2. Choosing the right Asset Category

Categories are per company: they start with the company code, e.g. `NGI-ACat-00009`.
Always pick one from **your own company**.

| The asset is... | Category | Pool / rate |
|---|---|---|
| Land, land development | Land | Not depreciated |
| Office building, plant building, boundary wall, civil works | Building / Building and Boundries | A, 5% |
| Computer, laptop, printer, accessories | Computer, Printer & Accessories | B, 25% |
| Office equipment: AC, water dispenser, CCTV, phone | Office Equipments | B, 25% |
| **Generator** | Office Equipments | B, 25% (Supreme Court ruling) |
| Furniture, fixtures, racks | Furniture & Fixtures | B, 25% |
| Car, jeep, motorcycle, bus, truck, bobtail tanker | Vehicle | C, 20% |
| Excavator, crane, forklift and other construction / handling equipment | Plant & Machinery | D, 15% |
| Filling plant machinery, compressors, pumps, weighing scales | Plant & Machinery | D, 15% |
| LPG cylinders | Cylinders | D, 15% |
| Anything else that lasts more than a year | Other Fixed Assets | D, 15% |
| Software, ERP / accounting licence, other licence bought for more than a year | Software (Pool E) | E, 100 ÷ useful life |
| Trademark, brand, copyright bought from someone | Brands, Trademarks & Copyrights (Pool E) | E, 100 ÷ useful life |
| Something **still being built or installed** | the matching **WIP** category | see section 5 |

Software, licences and trademarks (Pool E): see **section 3A**, click by click.

**Low-value items.** There is no minimum value in the tax law: a durable item
(chair, kettle, small tool) is a fixed asset whatever it cost. Things used up
within a year (stationery, consumables) are expenses, not assets. Whether small
durable items are expensed in the books is for Accounts to decide (decision J in
the depreciation guide); until then, ask.

Not sure? Ask Accounts **before** submitting. Changing the category after
depreciation has been posted is messy.

The Item must also be set up as a fixed asset: on the Item, tick **Is Fixed
Asset** and set its **Asset Category**.

---

## 3. Buying a new asset

### Step 1: Purchase
Make the **Purchase Receipt / Purchase Invoice** as usual, using the fixed asset
item.

- If the item has **Auto Create Assets on Purchase** ticked, a draft Asset is
  created for you when the receipt or invoice is submitted.
- If not, create the Asset yourself (step 2) and link the purchase document.

### Step 2: The Asset form
Open the draft Asset (or **Asset → New**) and check:

| Field | What to enter |
|---|---|
| Company | Your company |
| Item Code | The fixed asset item |
| Asset Category | Filled from the item; check it against section 2 |
| Location | Where the asset is kept |
| Purchase Date | Date on the bill |
| **Available-for-use Date** | The day it **actually started being used**. This decides the thirds rule, so be accurate |
| Net Purchase Amount | Filled from the purchase document; must include transport, installation and other costs to bring it into use |
| Calculate Depreciation | **Ticked** (except Land) |
| Is Existing Asset | **Not** ticked for a new purchase |
| **Useful Life (Years)** | Pool E only (appears for Software / Trademarks): the licence's period of use, e.g. 5. Half years allowed; it is rounded to the nearest half year. The rate and number of years are set from it when you save |

In the **Depreciation** section, the row is filled from the category. Leave
**Depreciation Start Date** alone: the system sets it to the fiscal year end
when you save.

### Step 3: Save and check the schedule
After saving, open the **Asset Depreciation Schedule** linked on the form and
check the first row:

| Available-for-use date in... | First year's depreciation should be |
|---|---|
| Shrawan to Poush | cost × rate (full year) |
| Magh to Chaitra | cost × rate × **2/3** |
| Baisakh to Asar | cost × rate × **1/3** |

Example: a Rs 3,00,000 computer (25%) in use from Magh shows **Rs 50,000** in
the first row, dated on Asar end.

### Step 4: Submit
Submit the Asset. From now on, depreciation posts by itself every Asar end.

---

## 3A. Software, licences and trademarks (Pool E), click by click

> **Status:** built and tested, **not yet switched on** on any site. Until
> Accounts applies it, the categories and the Useful Life field below do not
> exist yet. Everything else in this guide is unchanged.

Software, an ERP or accounting licence, or a trademark you bought is an
**intangible** asset. It goes in **Pool E**. Unlike A to D, Pool E has **no fixed
rate**: each licence gets its own rate from **how many years it can be used**.
You type the years; the system works out the rest.

### Where to see what changed

**1. The new categories**

1. In the search bar at the top, type **Asset Category** and open **Asset Category List**.
2. You see a new column, **Tax Pool**, with A, B, C, D, E or Not Depreciable.
3. In the filter boxes at the top of the list, set **Tax Pool** to **E**.
4. You see two rows for your company:
   - `XXX-ACat-000nn` **Software (Pool E)**
   - `XXX-ACat-000nn` **Brands, Trademarks & Copyrights (Pool E)**

   `XXX` is your company code (NGI, NGG, NGK, NGN, GLMI, GEPL, SGU).
5. Open **Software (Pool E)**. You see:
   - **Tax Pool:** E
   - **Finance Books** table: one row, **Written Down Value**, every **12** months.
     The rate shows **0** and the number of depreciations shows **1**. **This is
     correct.** Each asset gets its own rate when you save it. Do not change
     the category.
   - **Accounts** table: `111201 Pool E -Capitalized Software`,
     `111291 Accumulated Amortization - …`, `555200 Amortization A/c`.

**2. The new accounts** (Accounts staff only)

1. Search **Chart of Accounts** and open it. Pick your company.
2. Expand **Fixed Assets → Intangible Assets**.
3. You see a new group, **111290 Accumulated Amortization**, holding
   **111291** (software) and **111293** (trademarks).
4. Under **Indirect Expenses → Depreciation & Amortizations**, the account
   **555200 Amortization A/c** has not moved. Only its type changed, to
   *Depreciation*, so the asset categories can use it.

**3. The new fields on the Asset form**

1. Search **Asset** and open **Asset List**, then click **+ Add Asset**.
2. Pick an **Asset Category**. Right below it you now see **Tax Pool**
   (grey, filled by itself).
3. When the Tax Pool shows **E**, a new box appears under it: **Useful Life (Years)**.
   For any other pool the box stays hidden.

### Entering a licence, step by step

Example: an ERP licence for **Rs 3,00,000**, valid **5 years**, in use from
**4 Bhadra 2083**.

**Step 1: the Item (once per kind of licence)**

1. Search **Item** and click **+ Add Item**.
2. Fill **Item Name** (e.g. *ERP Licence*) and the **Company**.
3. **Untick** *Maintain Stock*. **Tick** *Is Fixed Asset*.
4. In **Asset Category**, pick **Software (Pool E)** of **your company**.
5. Save.

**Step 2: buy it**

Make the **Purchase Invoice** with this item as usual. If the item has *Auto
Create Assets on Purchase*, a draft Asset is made for you. Otherwise go to Step 3.

**Step 3: the Asset**

1. Open the draft Asset (or **Asset List → + Add Asset**).
2. Check these fields:

   | Field | Enter | You will see |
   |---|---|---|
   | Item Code | ERP Licence | Asset Category fills in: *Software (Pool E)* |
   | Tax Pool | (nothing, it fills itself) | **E** |
   | **Useful Life (Years)** | **5** | |
   | Company | your company | |
   | Location | where it is used (e.g. Head Office) | |
   | Purchase Date | the bill date | |
   | Net Purchase Amount | 3,00,000 | |
   | **Available-for-use Date** | the day it **started being used**: 4 Bhadra 2083 | |
   | Calculate Depreciation | ticked | |
   | Is Existing Asset | **not** ticked | |

   - **Useful Life** is the licence term: a 1-year subscription is 1, a 3-year
     licence is 3. Half years are fine (2.5). Anything else is **rounded to the
     nearest half year**: 3.3 becomes 3.5, 3.2 becomes 3.
   - **Not sure of the term?** Look at the licence agreement or invoice, or ask
     Accounts. Do not guess: the term decides the rate.

3. Click **Save** (Ctrl+S).

**Step 4: check what the system filled in**

1. Scroll down to **Depreciation → Finance Books**. Open the row (click the arrow
   on its right). You see:
   - **Depreciation Method:** Written Down Value
   - **Rate of Depreciation (%):** **20** (that is 100 ÷ 5 years)
   - **Total Number of Depreciations:** **5**
   - **Depreciation Posting Date:** the coming Asar end (16-07-2027 = 32 Asar 2084)

   You did not type any of these. If you change the Useful Life and save again,
   they change with it.

2. Scroll to **Depreciation Schedule**. For this example you see:

   | Date | Nepali date | Depreciation | Total so far |
   |---|---|---|---|
   | 16-07-2027 | Asar end 2084 | 60,000 | 60,000 |
   | 15-07-2028 | Asar end 2085 | 48,000 | 1,08,000 |
   | 15-07-2029 | Asar end 2086 | 38,400 | 1,46,400 |
   | 16-07-2030 | Asar end 2087 | 30,720 | 1,77,120 |
   | 16-07-2031 | Asar end 2088 | 24,576 | 2,01,696 |
   | 20-08-2031 | Bhadra 2088, **licence expires** | **98,304** | **3,00,000** |

   - Each year is 20% of what is **left**, not of the cost.
   - The **last row is bigger**. That is the right: when the licence expires,
     the rest is written off in that year. This is expected, not an error.
   - The first year follows the **thirds rule** like every other asset. The
     same licence in use from **Magh** would show **40,000** (2/3) in the first
     row; from **Baisakh**, **20,000** (1/3).

3. If the numbers look like this, click **Submit**. From then on each year's
   amortization posts by itself, to `555200` and `111291`.

### What you might see go wrong

| You see | It means | Do this |
|---|---|---|
| Red message **"Missing Fields: Useful Life (Years)"**, or **"… is in Pool E: enter its Useful Life (Years) …"** | The category is Pool E and the years are empty | Type the licence term in **Useful Life (Years)** and save again |
| **Useful Life (Years)** box is not there | The category is not Pool E (check Tax Pool), or Pool E is not switched on yet on this site | Check the category; otherwise ask Accounts |
| Rate is **100%** and only 1 row | Saved before Pool E was switched on | Ask Accounts; do not submit |
| Category list shows Software (Pool E) of **another** company | Wrong company picked | Use the one starting with **your** company code |

**Do not** use Pool E for a **lease** (right-of-use asset) or for **goodwill**.
There is no category for them on purpose; ask Accounts.

---

## 4. Depreciation each year

Nothing to do. Accounts Settings has **Book Asset Depreciation Entry
Automatically** switched on, so ERPNext posts one journal entry per asset on
each Asar end:

- **Debit**: `5551xx Depreciation on Pool ...` (the pool's expense account)
- **Credit**: `11119x Accumulated Depreciation - Pool ...`

To check, see section 9.

---

## 5. Assets under construction (WIP)

Use a **WIP** category (e.g. *WIP - Filling Plant*, *WIP - Civil Work*) for
something that is bought or built over time and **not yet in use**.

1. Book every purchase for it against the WIP item. The cost goes to the
   **Capital Work in Progress** account (`1113xx`), not to the pool, and **is
   not depreciated** while in progress.
2. When it is **ready and in use**, set the **Available-for-use Date** and
   submit the Asset. ERPNext moves the cost from CWIP into the pool account
   (e.g. Filling Plant into Pool D) and starts depreciation from that date.

If one asset is built from many purchases (a full filling plant), use
a **composite asset** and the **Capitalize Asset** button (Asset Capitalization) to combine them into one asset. Ask Accounts the
first time.

---

## 6. Selling or scrapping an asset

**Sell:** open the submitted Asset, then **Manage → Sell Asset**. This makes a Sales
Invoice. On submit, ERPNext posts depreciation up to the sale date and books the
gain or loss.

**Scrap** (damaged, lost, no value): open the Asset, then **Manage → Scrap Asset**.

Do **not** cancel the Asset or delete its depreciation entries instead.

> Tax note: the tax law has no gain or loss per asset; the sale price is
> subtracted from the pool. The tax depreciation report (coming) handles this
> difference. In ERPNext you just sell or scrap normally.

---

## 7. Repairs and maintenance

Book repairs as an **expense** (Purchase Invoice or Journal Entry) to the
repair account **under the pool the asset belongs to**:

| Asset's pool | Repair accounts under |
|---|---|
| A (buildings) | `549100 Repair & Maintenance-Pool A` |
| B (computers, office equipment, furniture, generators) | `549200 Repair & Maintenance-Pool B` |
| C (vehicles) | `549300 Repair & Maintenance-Pool C` |
| D (plant, machinery, cylinders) | `549400 Repair & Maintenance-Pool D` |

**Getting the pool right matters.** The tax law caps repairs at 7% of each
pool, and the tax report reads these accounts pool by pool.

A **major improvement** that adds life or capacity (e.g. a new engine, a plant
extension) may need to be added to the asset's cost instead. Ask Accounts.

---

## 8. Assets you already own (before ERPNext)

**Not ready yet.** Accounts is deciding how old assets come in: one opening
balance per pool, or every asset individually (decision D in the depreciation
guide). Until then, **do not enter old assets** with *Is Existing Asset*.

---

## 9. Reports to check

| Report | Shows |
|---|---|
| **Fixed Asset Register** | Every asset, its category, cost, depreciation to date and value |
| **Asset Depreciations and Balances** | Totals by category for a period: opening, additions, depreciation, closing |
| **Asset Depreciation Ledger** | Each depreciation entry posted |
| Asset's own **Depreciation Schedule** | Future and posted depreciation for one asset |

The **Schedule-2 tax depreciation report** (by pool, with the 7% repairs cap and
the sale rule) is being built.

---

## 10. Do's and don'ts

**Do**
- pick the category from **your own company**;
- enter the **real** available-for-use date;
- include transport and installation in the cost;
- book repairs to the **right pool's** repair account;
- use **Sell Asset** / **Scrap Asset** to dispose.

**Don't**
- change the rate, method or depreciation start date on an asset;
- use Land for buildings, or Office Equipment for vehicles;
- submit a WIP asset before it is actually in use;
- enter old assets yet (section 8);
- cancel a submitted asset to "fix" it. Ask Accounts.

---

## Not covered yet

- **+1/3 rate for special industries** (likely GLMI). Waiting for Accounts / the
  tax adviser. Rates will change on those companies' categories only.
- **50% rule for own power generation** and **100% for fiscal printers**. These
  will get their own categories once confirmed.
- **Pool E method** is waiting for the tax adviser to confirm (reducing balance at
  100 ÷ life, as built, or straight line). Goodwill and right-of-use (lease)
  assets have no category on purpose; ask Accounts.
- **SGU** has no asset categories yet.
