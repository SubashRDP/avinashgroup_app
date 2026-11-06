# Fixed Assets and Depreciation: the Law and Our ERPNext Plan

Prepared for: Accounts / ACCA
Applies to: Nepal Gas Udhyog group (NGI, NGG, NGK, NGN, GLMI, GEPL, SGU)
Date: 2083 Kartik (2026-11-05)

---

## Part 1: What the law says

### 1.1 Which law applies

The governing law is the **Income Tax Act 2058**. It was never replaced. Each
year's **Finance Act** amends parts of it. The law in force today is the 2058 Act
**with all amendments up to Finance Act 2083**.

For depreciation, very little has changed since the Act was written:

| Finance Act | What changed for fixed assets / depreciation |
|---|---|
| 2060 onwards | s.16 repairs cap raised from 5% to **7%**; excess goes into the pool **next year** |
| 2060 onwards | s.19(1) "may deduct" became "**shall** deduct", so depreciation is **compulsory** |
| 2062 | Aircraft overhaul exempt from repairs cap (not relevant to us) |
| 2067 | 50% first-year depreciation for own power generation assets; 100% for fiscal printers / cash machines |
| After 2067 (exact year not confirmed) | +1/3 extra rate extended to **special (manufacturing) industries** and some infrastructure; 50% power rule extended to **any person** |
| 2082 | Cooperatives removed from the +1/3 extra rate |
| 2083 | **No change** to depreciation |

The pool rates (5 / 25 / 20 / 15%), the pool method, the thirds rule and the
disposal rules have **not changed since 2058**.

### 1.2 What is a depreciable asset

**Section 2(aak):** property used in a business or investment to earn income,
which **declines in value** through wear and tear, age or the passage of time.
Stock-in-trade is excluded.

**Land is not depreciable.** It does not decline in value.

### 1.3 The five pools (Schedule-2, s.1 and s.3)

| Pool | Assets | Rate |
|---|---|---|
| **A** | Buildings, structures and similar permanent structures | **5%** |
| **B** | Computers, data processing equipment, furniture, fixtures, office equipment | **25%** |
| **C** | Automobiles, buses, minibuses | **20%** |
| **D** | Construction and excavation equipment, plant and machinery, and **everything not listed elsewhere** | **15%** |
| **E** | Intangible assets (software, licences, etc.) | 100 ÷ useful life (rounded to the nearest half year), **each asset its own class** |

**Pool E, as built.** s.3(1) sets the E rate as cost divided by the period of
use, the period adjusted to the nearest half year, and s.2(3) applies every
pool's rate to its reducing base. Read literally, a 5-year licence is **20%
reducing balance**, first year by the thirds rule (s.2(5) covers "any class"),
never the +1/3 (s.3(2) is A-D only). In the year the right expires, what is left
is written off: an expired right is a disposal with no proceeds (s.4). Some
secondary sources teach Pool E as straight line (cost ÷ life each year). The
system follows the literal reading; **the tax adviser should confirm** before
the first intangible is filed. Example, Rs 3,00,000 software, 5 years, in use
from Bhadra 2083: 60,000 · 48,000 · 38,400 · 30,720 · 24,576, then 98,304 on
expiry in Bhadra 2088.

**Our cylinders, filling plant and machinery** go in **Pool D**.
**Generators, ATMs and lockers** used commercially go in **Pool B**, not D. This
comes from two Supreme Court rulings: Kisht Bank 073-RB-0146 and S Development
Bank 075-RB-0158.

### 1.4 How depreciation is calculated (Schedule-2, s.2)

Depreciation is calculated on the **whole pool**, not asset by asset, using
**reducing balance** (written down value).

```
Depreciation for the year = Closing pool base × Rate
```

**Closing pool base** =
  last year's closing base, minus last year's depreciation
  **+** additions this year (under the thirds rule below)
  **−** sale proceeds of assets sold this year
  (never below zero)

### 1.5 The thirds rule for new assets (Schedule-2, s.2(5))

A new asset does not enter the pool at full cost straight away. How much enters
this year depends on **when it was bought or first used, whichever is later**:

| Bought / first used in | Added to pool this year | Added next year |
|---|---|---|
| Shrawan to Poush (first 6 months) | **3/3** (full cost) | nothing |
| Magh to Chaitra | **2/3** of cost | 1/3 |
| Baisakh to Asar (last 3 months) | **1/3** of cost | 2/3 |

### 1.6 Small balance write-off (Schedule-2, s.2(6))

If a pool's balance after depreciation is **below Rs 2,000**, the **whole
remaining balance** is written off as depreciation that year.

This is a rule for the **whole pool**, not a minimum value for an asset. The
Act has **no capitalisation threshold**: a Rs 1,500 chair is still capital
expenditure (s.21(3) allows capital expenses only through depreciation), goes
into Pool B and is depreciated at 25% with the rest of the pool.

### 1.7 Selling or scrapping an asset (Schedule-2, s.4)

There is **no gain or loss per asset**. The sale proceeds are subtracted from
the pool.

- If **proceeds are more than the pool base**, the excess is **taxable income**.
- If **every asset in a pool is sold** (the pool is dissolved):
  - proceeds above the remaining value: the difference is **income**;
  - proceeds below the remaining value: the difference is a **deductible loss**.

### 1.8 Repairs and maintenance (Section 16)

- Repairs on depreciable assets are deductible up to **7% of the pool's
  depreciation base at year end**, calculated **pool by pool**.
- Any **excess** is not lost. It is **added to that pool's base at the start of
  next year** and depreciated from then on.

> To confirm with the tax adviser: we read "depreciation base at year end" as the
> base **before** that year's depreciation (the "A" in the formula). This is the
> usual practice.

### 1.9 Extra one-third rate (Schedule-2, s.3(2))

Some taxpayers get the A to D rates **increased by one third**:

| Pool | Normal | With +1/3 |
|---|---|---|
| A | 5% | 6.67% |
| B | 25% | 33.33% |
| C | 20% | 26.67% |
| D | 15% | 20% |

**Who qualifies:**
- **Special industries** under s.11(2kha), meaning manufacturing industries
- Trams, ropeways, cable cars, roads, bridges, tunnels, railways and airports (s.11(3cha))
- Public infrastructure (BOT) and power projects (s.11(3tha), s.19(2))
- Cooperatives **no longer qualify** from 2082/83

**The extra rate is compulsory.** An eligible company must claim it. It is not
optional (Supreme Court, Triveni Spinning, 074-RB-0345).

**For our group:**
- **GLMI** manufactures cylinders, so it is almost certainly a special industry.
- **The gas bottling companies** need a decision from the tax adviser.

### 1.10 Special full or partial write-offs

| Asset | Rule |
|---|---|
| Assets generating power for **own use** (e.g. generator, solar) | **50%** of cost deductible in the year acquired (s.3(3)) |
| Fiscal printer and cash machine used for billing | **100%** of cost deductible in the year bought (s.3(4)) |
| Pollution control / R&D expenditure above 50% of income | Capitalised and depreciated in Pool D (s.17, s.18) |

---

## Part 2: Worked example

**NGI, Pool D, FY 82/83**

| | Rs |
|---|---|
| Opening base (last year's closing, after depreciation) | 10,00,000 |
| Machine X bought in **Bhadra** for 6,00,000: **full** | + 6,00,000 |
| Machine Y bought in **Magh** for 3,00,000: **2/3 now** | + 2,00,000 |
| Old machine sold for | − 50,000 |
| **Closing pool base** | **17,50,000** |
| **Depreciation @ 15%** | **2,62,500** |
| Balance after depreciation | 14,87,500 |
| Add the remaining 1/3 of Machine Y next year | + 1,00,000 |
| **Opening base FY 83/84** | **15,87,500** |

**Repairs on Pool D assets** this year: Rs 1,50,000.
- Cap = 7% × 17,50,000 = **1,22,500** deductible.
- Excess **27,500** is added to Pool D's base at the start of 83/84.

**If NGI were a special industry**, depreciation would be 20% × 17,50,000 = **3,50,000**.

### Why per-asset depreciation gives the same answer

Follow Machine Y (cost 3,00,000, bought in Magh):

| | Pool view | Per-asset view |
|---|---|---|
| Year 1 | 2,00,000 enters the pool × 15% = **30,000** | 3,00,000 × 15% × 2/3 = **30,000** |
| Year 2 | (2,00,000 − 30,000 + 1,00,000) × 15% = **40,500** | (3,00,000 − 30,000) × 15% = **40,500** |

The two methods agree every year. ERPNext can therefore depreciate **asset by
asset** and still produce the legal figure. Only a few items work on the whole
pool and must be done in a report (see Part 3).

---

## Part 3: Our plan in ERPNext

### 3.1 Decisions taken

| # | Decision |
|---|---|
| 1 | Follow the **current law**: the Income Tax Act 2058 with all amendments to Finance Act 2083 |
| 2 | **Book depreciation follows the law**: written down value at Schedule-2 rates, yearly, first year by the thirds rule |
| 3 | Every Asset Category carries its **Tax Pool** (A / B / C / D / E / Not Depreciable) |
| 4 | Each pool has its own **cost**, **accumulated depreciation** and **depreciation expense** account |
| 5 | **Land** is non-depreciable |
| 6 | **Work in progress** sits in CWIP and moves into the right pool when capitalised (e.g. Filling Plant to Pool D) |
| 7 | **Generators** go in **Pool B** (Supreme Court) |
| 8 | Rates and limits are kept as **settings**, so a future Finance Act only needs a value change |
| 9 | Testing is done first on **demo-nggroup**, not on live |

### 3.2 Chart of accounts per company

| Pool | Cost | Accumulated depreciation (new) | Depreciation expense | Repairs |
|---|---|---|---|---|
| Land | 111101 | — | — | — |
| A Buildings | 111102 | 111192 | 555101 | 5491xx |
| B Office equip / furniture / computers | 111103 | 111193 | 555102 | 5492xx |
| C Vehicles | 111104 | 111194 | 555103 | 5493xx |
| D Plant & machinery | 111105 | 111195 | 555104 | 5494xx |
| D Cylinders | 111106 | 111196 | 555105 | 5494xx |
| CWIP | 1113xx | — | — | — |

The new accumulated depreciation accounts sit under fixed assets as **contra
accounts**. Until now, categories pointed at **345109 Provision for Accumulated
Depreciation**, which is a **liability** account.

### 3.3 What ERPNext will do vs what the report will do

| Item | Where |
|---|---|
| Rates, written down value, thirds rule for the first year | **ERPNext**, posted yearly as journal entries |
| +1/3 rate for special industries | **ERPNext**, as a higher rate on that company's categories |
| 50% own-power and 100% fiscal printer write-offs | **ERPNext**, as special categories |
| Sale proceeds reducing the pool (no per-asset gain/loss) | **Tax report** |
| Rs 2,000 small-pool write-off | **Tax report** |
| 7% repairs cap and carry-forward | **Tax report** |
| Opening pool balances from the last return | **Tax report** |

ERPNext books a **gain or loss on each asset sold**. The tax report reverses that
and applies the pool rule. This is the main reconciling item between book
profit and taxable profit.

### 3.4 Work plan

| Step | Work | Status |
|---|---|---|
| 1 | Study the law and its amendments | **Done** |
| 2 | Tax Pool field and setup script (accounts, categories, Land, CWIP) | **Done on demo-nggroup** (2026-11-05): 41 accounts, 68 categories |
| 3 | Nepal depreciation rule in ERPNext (WDV, thirds rule, yearly at fiscal year end) | **Built and tested** (see 3.5) |
| 4 | Set rates on all categories, including +1/3 for confirmed special industries | **Normal rates done on demo-nggroup** (62 categories). +1/3 waits for decision B |
| 5 | Test on demo-nggroup with sample assets bought in each of the three periods, sold, and repaired | **Purchase timing tested.** Sale and repairs go with the report in step 6 |
| 6 | **Schedule-2 Tax Depreciation report** per company and fiscal year | After step 5 |
| 7 | Enter opening pool balances and existing assets | Needs decision C |
| 8 | Review with Accounts, then move to live | Last |

### 3.5 Test result (demo-nggroup, 2026-11-05)

Three test assets, cost Rs 3,00,000 each, Pool B (25%), created and then removed:

| In use from | First year (FY 82/83) | Second year (FY 83/84) | Matches the law |
|---|---|---|---|
| Bhadra 2082 (Shrawan to Poush) | 75,000 (full year) | 56,250 | Yes |
| Magh 2082 (Magh to Chaitra) | 50,000 (2/3) | 62,500 | Yes |
| Baisakh 2083 (Baisakh to Asar) | 25,000 (1/3) | 68,750 | Yes |

Each year's entry is dated on that year's Asar end (15 or 16 July).

**Full test run (2026-11-05), all passed**, everything rolled back afterwards:

| Test | Result |
|---|---|
| All 69 categories point at their pool's accounts and rate | Pass |
| Thirds rule at all 6 boundary dates (1 Shrawan, end Poush, 1 Magh, end Chaitra, 1 Baisakh, end Asar) for Pools A, B, C, D | Pass |
| Second year = written-down value × rate; total depreciation = cost | Pass |
| Every yearly entry dated on Asar end | Pass |
| Existing asset (bought earlier) gets a full year | Pass |
| Land refuses depreciation | Pass |
| Posted entry: Dr pool depreciation expense, Cr pool accumulated depreciation, dated Asar end | Pass |
| Scrapping: depreciation to the scrap date, then the scrap entry | Pass |
| Pool E: rate = 100 ÷ useful life, half-year rounding, thirds rule, write-off in expiry year | Pass |

The test run found one real problem, now fixed: **depreciation entries could not
be posted at all.** Every Journal Entry here needs a JV Type and a Document No,
and ERPNext's automatic depreciation entries had neither, so the yearly posting
would have failed on Asar end. Asset entries now get JV Type "Journal Entry" and
the next number in that series, the same way payroll journals already do.
If Accounts wants a separate JV Type for depreciation, it needs its own
numbering rule per company.

Two known limits:
- ERPNext needs a fixed number of years, so each asset runs at its rate until
  **less than Rs 2,000** is left (never fewer than B 17, C 21, D 29, A 90 years),
  and that small remainder is written off in the final row. A 10-arab asset
  therefore runs about 55 years; it no longer dumps crores into year 18.
- The Nepali calendar converter stops at BS 2100 (about 2043 AD). Schedule rows
  after that keep ERPNext's date, which can be a day off Asar end.

---

## Part 4: Decisions needed from Accounts

| # | Question | Notes |
|---|---|---|
| **A** | Is "7% of depreciation base" the base **before** depreciation? | Usual practice; please confirm |
| **B** | Which companies are **special industries** (+1/3)? | GLMI likely. NGI, NGG, NGK, NGN, GEPL, SGU? |
| **C** | **Opening pool balances** per company and pool | From the last filed return (D-01 depreciation schedule), 81/82 or 82/83 |
| **D** | How should existing assets come into ERPNext? | **Answered 2026-11-05: (ii) every asset individually** ("back entry"), as an existing asset with its opening accumulated depreciation; worked example in [fixed-assets-example-generator.md](fixed-assets-example-generator.md). Still for Accounts: the opening JE carries pool balances **net** (no opening accumulated depreciation), while each asset carries cost and accumulated depreciation, so the register and the ledger show the same value split differently |
| **E** | What to do with any balance on **345109** | Reclassify into the new pool accumulated depreciation accounts? |
| **F** | **SGU** has no asset categories | Copy the NGI set? |
| **G** | NGK "WIP" category | What will it become (building / plant / vehicle)? |
| **H** | WIP categories with no CWIP account: GEPL Filling Plant and Civil Work, NGI Civil Work, NGN Vehicle | Create the CWIP accounts? |
| **I** | Do any companies have generators or solar for **own power** (50% rule) or **fiscal printers** (100% rule)? | Need their own categories |
| **J** | **Low-value assets**: capitalise everything, or expense items below a set amount in the books? | The Act has **no minimum value**: s.21(3) disallows capital expenses except through depreciation, and the Rs 2,000 rule (s.2(6)) is per **pool**, not per asset. Expensing small durable items is a book policy; for tax they would still need to go into the pool |

---

## Sources

- Income Tax Act 2058, English, with Finance Acts to 2067 (Law Commission, via ICAN):
  <https://en.ican.org.np/_browsable/file/career/8Income-Tax-Act-2058.pdf>
  (s.2(aak) p.18, s.16-19 pp.36-39, Schedule-2 pp.182-189, FA 2067 pp.624-625)
- IRD: Income Tax Act 2058 as amended by Finance Act 2082 (Nepali, official):
  <https://ird.gov.np/content/13405/income-tax-act--2058--as-amended-by/>
  **Not yet compared word for word.** Its download link only works in a browser.
- Schedule II, current text: <https://nepallaws.com/Laws/income-tax-act-2058-2002/schedule-ii-relating-to-section-19/assessment-of-depreciation-deduction/>
- Section 16, current text: <https://nepallaws.com/Laws/income-tax-act-2058-2002/chapter-5-deductible-amounts/section-16-repair-and-maintenance-expenses/>
- ICAN, Federal Budget 2082/83 highlights: <https://en.ican.org.np/_browsable/file/resouces/Federal_Budget_2082_83_Highlights_V6.pdf>
- SAR, Amendments by Finance Bill 2082/83: <https://sar.com.np/wp-content/uploads/2025/02/Amendment-in-Tax-Laws-by-Budget-2082-83.pdf>
- Baker Tilly, Nepal Tax Fact 2025/26: <https://bakertilly.com.np/storage/download/1750310698_Tax_Fact_2025-2026.pdf>
- Shankar Associates, Finance Bill 2083 changes: <https://www.saca.com.np/changes-in-income-tax-act-2058-of-nepal-by-finance-bill-2083/>
- Supreme Court cases on +1/3 and Pool B: <https://sushilparajuli.com/depreciation-income-tax-nepal/>
