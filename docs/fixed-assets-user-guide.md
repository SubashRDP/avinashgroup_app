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
| Something **still being built or installed** | the matching **WIP** category | see section 5 |

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
| Gross Purchase Amount | Filled from the purchase document; must include transport, installation and other costs to bring it into use |
| Calculate Depreciation | **Ticked** (except Land) |
| Is Existing Asset | **Not** ticked for a new purchase |

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
- **Intangibles (Pool E)**, e.g. software licences. No category yet; ask Accounts.
- **SGU** has no asset categories yet.
