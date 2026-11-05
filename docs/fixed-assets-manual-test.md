# Fixed Assets: Manual Test Checklist

Site: **demo-nggroup.raindropinc.com**
Company: **Nepal Gas Udhyog Pvt. Ltd. (NGI)**
Item used: **NGI-ITEM-00236 (laptop dell)**, category **NGI-ACat-00004 Computer, Printer & Accessories** (Pool B, 25%)

Every expected figure below was checked by the automated run
(`scripts/check_fixed_assets.py`, 14/14 pass, 2026-11-05).

## Before you start

The server must be restarted once so it loads the new code:

```
sudo supervisorctl restart frappe-bench-web: frappe-bench-workers:
```

**How to tell it was not restarted:** in Test 3 the first row shows about
**Rs 36,800** (ERPNext counting days) instead of **Rs 50,000**.

---

## Test 1: Category is set up by law

**Do:** open **Asset Category → NGI-ACat-00004**.

**Check:**

| Field | Expected |
|---|---|
| Tax Pool | B |
| Accounts row: Fixed Asset Account | 111103 - Pool B - Office Equipments, Furnitures & Fixtures - NGI |
| Accumulated Depreciation Account | 111193 - Accumulated Depreciation - Pool B - ... - NGI |
| Depreciation Expense Account | 555102 - Depreciation on Pool B - ... - NGI |
| Finance Books row | Written Down Value, 25% rate, 17, frequency 12 |

**Why:** Schedule-2 s.1 puts computers in **Pool B**; s.3(1) sets Pool B at
**25%**. Depreciation is **reducing balance** (s.2(2)), **once a year**. Each pool
has its own accounts so the books show each pool's balance, which the tax return
needs. "17" is only ERPNext's required end year (less than 1% left).

---

## Test 2: Land is not depreciated

**Do:** open **Asset Category → NGI-ACat-00003 (Land)**.

**Check:** **Tax Pool = Not Depreciable**, **Non Depreciable Category ticked**, no
accumulated depreciation or depreciation expense account.

**Why:** s.2(aak): depreciable property is property that **loses value**. Land
does not.

---

## Test 3: New asset, in use in **Magh** (2/3 of a year)

**Do:** **Asset → New**

| Field | Enter |
|---|---|
| Company | Nepal Gas Udhyog Pvt. Ltd. |
| Item Code | NGI-ITEM-00236 |
| Asset Name | TEST Magh laptop |
| Location | kathmandu |
| Purchase Date | **2026-01-19** (Magh 5, 2082) |
| Available-for-use Date | **2026-01-19** |
| Gross Purchase Amount | **3,00,000** |
| Calculate Depreciation | ticked |

**Save** (do not submit). Open the **Asset Depreciation Schedule** link.

**Check:**

| Row | Date | Amount |
|---|---|---|
| 1 | **2026-07-16** (Asar end 2083) | **50,000.00** |
| 2 | 2027-07-16 | **62,500.00** |
| 3 | **2028-07-15** | 46,875.00 |

**Why:**
- **Row 1 = 3,00,000 × 25% × 2/3 = 50,000.** Schedule-2 s.2(5): an asset first
  used in **Magh to Chaitra** enters the pool at **2/3** of its cost that year.
- **Row 2 = (3,00,000 − 50,000) × 25% = 62,500.** In the pool, year two adds the
  last 1/3. Per asset that is the same as written-down value on cost less year
  one (guide, Part 2).
- **Dated on Asar end:** depreciation is for the **income year**, which ends on
  the last day of Asar.
- **Row 3 is the 15th, not the 16th:** Asar end moves between 15 and 16 July. The
  system follows the real Nepali calendar so no entry falls into the next year.

---

## Test 4: New asset, in use in **Bhadra** (full year)

**Do:** same as Test 3, but Purchase Date and Available-for-use Date
**2025-08-19** (Bhadra 3, 2082), name *TEST Bhadra laptop*.

**Check:** row 1 **75,000.00** on 2026-07-16; row 2 **56,250.00**.

**Why:** s.2(5): first used in **Shrawan to Poush**, so **full cost** enters the
pool. 3,00,000 × 25% = 75,000.

---

## Test 5: New asset, in use in **Baisakh** (1/3 of a year)

**Do:** same, dates **2026-04-18** (Baisakh 5, 2083), name *TEST Baisakh laptop*.

**Check:** row 1 **25,000.00** on 2026-07-16; row 2 **68,750.00**.

**Why:** s.2(5): **Baisakh to Asar** enters at **1/3**. 3,00,000 × 25% × 1/3 = 25,000.

---

## Test 6: You cannot move the start date

**Do:** on the Test 3 asset, in the Finance Books row change **Depreciation
Posting Date** to any other date (e.g. 2026-12-31). **Save.**

**Check:** it goes back to **2026-07-16**.

**Why:** the law fixes when depreciation is counted (the income year), so it is
not left to the person entering. This stops a wrong date from moving
depreciation into the wrong year.

---

## Test 7: Land refuses depreciation

**Do:** **Asset → New**, Asset Category **NGI-ACat-00003 (Land)**, tick
**Calculate Depreciation**, save.

**Check:** error *"This asset category is marked as non-depreciable..."*.

**Why:** as Test 2. Land cannot be depreciated by mistake.

---

## Test 8: Asset owned before ERPNext (existing asset)

**Do:** **Asset → New**

| Field | Enter |
|---|---|
| Item Code | NGI-ITEM-00236 |
| Asset Name | TEST existing laptop |
| Location | kathmandu |
| **Is Existing Asset** | ticked |
| Available-for-use Date | **2023-08-18** (Bhadra 1, 2080) |
| Gross Purchase Amount | **1,00,000** |
| Opening Accumulated Depreciation | **43,750** |
| Opening Number of Booked Depreciations | **2** |
| Calculate Depreciation | ticked |
| Finance Books row → Depreciation Posting Date | **2026-07-16** |

**Save.** Check the schedule:

| Row | Date | Amount |
|---|---|---|
| 1 | 2026-07-16 | **14,062.50** |
| 2 | 2027-07-16 | **10,546.88** |

**Why:** the two years already booked (80/81: 25,000, 81/82: 18,750) used up the
first-year rule. From now on it is a **full year** on what is left:
(1,00,000 − 43,750) × 25% = 14,062.50. Here you **do** enter the posting date,
because only you know how many years were booked before.

---

## Test 9: Depreciation posts correctly

**Do:** **Submit** the Test 8 asset. Row 1 (2026-07-16) is already due, so
ERPNext's daily job posts it **the next morning** (it runs around 1 am). To post
it now instead, run in your SSH terminal:

```
cd /home/frappe/frappe-bench && bench --site demo-nggroup.raindropinc.com execute erpnext.assets.doctype.asset.depreciation.post_depreciation_entries
```

(The asset's *Manage → Create Depreciation Entry* button is only for assets
without automatic depreciation, so it does not show here.)

**Check:** the schedule's row 1 now has a **Journal Entry**. Open it:

| | Expected |
|---|---|
| Posting Date | **2026-07-16** |
| JV Type | **Journal Entry** |
| Document No | filled (next number in NGI's Journal Entry series for 82/83) |
| Dr | **555102** Depreciation on Pool B ... **14,062.50** |
| Cr | **111193** Accumulated Depreciation - Pool B ... **14,062.50** |

**Why:**
- s.19(1): depreciation **"shall"** be deducted every year. It is compulsory,
  so the system posts it automatically.
- Expense and accumulated depreciation go to the **pool's own accounts**.
- **JV Type and Document No:** every Journal Entry on this site must have them.
  Before today's fix, ERPNext's automatic depreciation entries had neither and
  **failed**, so nothing would have posted on Asar end.

---

## Test 10: Scrapping an asset

**Do:** on the submitted Test 8 asset, **Manage → Scrap Asset**.

**Check:**
- Status becomes **Scrapped**.
- A new schedule row dated **today**, for part of the year. Done on
  **2026-11-05** it is **3,236.30** (10,546.88 × 112 days ÷ 365). On another day
  it is 10,546.88 × days since 17 July ÷ 365.
- A scrap Journal Entry with **JV Type Journal Entry** and a **Document No**:
  - Cr **111103** Pool B (cost): 1,00,000
  - Dr **111193** Accumulated Depreciation: 61,048.80 (if done on 2026-11-05)
  - Dr **445101** Gain on disposal: 38,951.20 (the loss)

**Why:** in the **books**, ERPNext writes the asset off with a gain or loss.
For **tax**, s.4 has no gain or loss per asset; the sale value (here nil) leaves
the pool, and the pool carries on. That difference is the tax report's job. The
scrap entry also needs JV Type and Document No, fixed together with Test 9.

---

## After testing

Tests 3 to 8 leave records on demo-nggroup. **Draft** assets (3 to 7) can be
deleted. The Test 8 asset is submitted with posted entries: keep it as a demo
example, or ask me to remove it.

## Result sheet

| Test | What | Pass / Fail | Note |
|---|---|---|---|
| 1 | Category set by law | | |
| 2 | Land not depreciable | | |
| 3 | Magh: 50,000 / 62,500, Asar-end dates | | |
| 4 | Bhadra: 75,000 / 56,250 | | |
| 5 | Baisakh: 25,000 / 68,750 | | |
| 6 | Start date resets to Asar end | | |
| 7 | Land refuses depreciation | | |
| 8 | Existing asset: 14,062.50 / 10,546.88 | | |
| 9 | Posting: accounts, JV Type, Document No | | |
| 10 | Scrap: part-year + scrap entry | | |
