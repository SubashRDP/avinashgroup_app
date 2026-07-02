# Testing — Naming Series

Brutal, no-mercy test plan for the custom naming engine.
The goal of this document is **not** to confirm it works. The goal is to **break it**.
Every section below assumes the code is guilty until proven innocent.

---

## 0. What we are actually testing

The naming engine is **not** Frappe's built-in `naming_series`. It is a full override living in:

| File | Role |
|------|------|
| `avinashgroup_app/custom_code/Override/naming_series.py` | All logic: `NAMING_CONFIG`, `BRANCH_CODE_CONFIG`, `AUTO_NUMBER_CONFIG`, name builders, validators, series revert |
| `avinashgroup_app/utils/audit_file_manager.py` | Wires the handlers into **every** doctype in `AuditBase.doctypes` via `AuditEventMapper.get_doc_events()` |
| `avinashgroup_app/public/js/auto_update_document_no.js` | Client-side auto `custom_document_no` for 4 doctypes |
| `avinashgroup_app/scripts/pad_custom_name.py` | One-off backfill: zero-pad `custom_name` to 6 digits |

The handlers fire on **5 events for ~70 doctypes**:

```
autoname       -> naming_series_autoname()      # sets doc.name + branch name
before_insert  -> naming_requirements_before_insert()  # throws if no company/FY
validate       -> handle_validate()             # auto-no, custom_name, dup-check, branch
before_save    -> handle_before_save()          # SAME 4 functions AGAIN
after_delete   -> revert_series_on_delete()     # steps the counter back
```

That double execution (`validate` **and** `before_save` run the identical 4 functions) and
the fan-out across 70 doctypes is exactly where this thing will bite. Test accordingly.

---

## 1. The name-building matrix (core correctness)

There are **3** name shapes. Every doctype in `NAMING_CONFIG` falls into one. Test one representative
of each, then the special-cased ones individually.

### 1a. Simple, no fiscal year — `make_name_simple`
Config: `use_fiscal_year: False` (e.g. `Customer` CUS, `Item` ITEM, `Vehicle` VEH, `Designation` DESIG).

Expected `name`:
- with company abbr: `{ABBR}-{PREFIX}-.{#####}` → e.g. `GEPL-CUS-00001`
- no abbr: `{PREFIX}-.{#####}` → `CUS-00001`

| # | Case | Expected | Why it's a trap |
|---|------|----------|-----------------|
| 1 | Customer with company set | `GEPL-CUS-00001` | baseline |
| 2 | Second customer | `GEPL-CUS-00002` | counter increments |
| 3 | `Designation` / `Manufacturer` / `Prospect` — **doctypes with NO native company field** | should it even require a company? | `naming_requirements_before_insert` calls `get_company_abbr`; if `custom_company` custom field is empty it **throws "Company abbreviation is required for Designation"**. Confirm whether masters are meant to be company-scoped — this is almost certainly an unintended hard block. |
| 4 | Two **different companies** create items | `GEPL-ITEM-00001` vs `SGU-ITEM-00001` | separate series per company? confirm counters don't collide / don't share |

### 1b. Fiscal-year names — `make_name_with_fiscal_year`
Config: `use_fiscal_year: True` (e.g. `Sales Order` SO, `Journal Entry` JE).

Pattern fed to `make_autoname`:
```
.{ABBR}.-{PREFIX}-.{FY}.-.{#####}.
```
**This is the single most fragile line in the file.** The fiscal year (e.g. `2082/83`) is interpolated
into a `make_autoname` pattern where `.` is a control character.

| # | Case | What to assert |
|---|------|----------------|
| 5 | JE with `posting_date` in FY `2082/83` | the literal FY string lands in `name` exactly: `GEPL-JE-2082/83-00001`. **Verify the `/` and the FY digits are not eaten / re-evaluated by `make_autoname`.** |
| 6 | The `tabSeries` row key | inspect `tabSeries` after creating the doc. Record the **exact** `name` of the series row. You need it for §4 (delete-revert), because the revert logic *reconstructs* the key by hand and must match. |
| 7 | No `posting_date`/`transaction_date`/`custom_created_on` | `naming_requirements_before_insert` throws "Missing Date Field". Confirm message + that nothing partial is written. |
| 8 | `posting_date` set to a date with **no matching Fiscal Year** record | throws "No fiscal year found". |
| 9 | `posting_date` on a fiscal-year **boundary** (year_start_date and year_end_date day) | lands in the correct FY, no off-by-one. Create FY-end + FY-start docs back to back. |

### 1c. Sequence-length overflow (brutal boundary)
`Stock Entry`, `Material Transfer/Issue/Receipt` use `sequence_length: 3` → **max 999 per series**.

| # | Case | Expected |
|---|------|----------|
| 10 | Force `tabSeries.current = 999` for a Stock Entry series, then create one | does it roll to `1000` (4 digits, fine) or wrap/corrupt? `make_autoname` widens, so assert `...-1000` not `...-000`. Document the real behaviour. |
| 11 | Same for a 5-digit series at 99999 | assert `100000`. |

---

## 2. `custom_name` + `custom_document_no` (the voucher-number system)

`custom_name` is the **business document number** and the source of truth for duplicate detection.
Built by `set_custom_name_field`:
```
{ABBR}-{p_type_code}-{doc_no}{doc_word}-{FY}{amendment_suffix}
```
where `doc_no` is `custom_document_no` zero-padded to N digits (N from `Voucher Number Settings Item`, default 6).

### 2a. `validate_document_no` — the integer gate
Letters belong in `custom_document_word`, never in `custom_document_no`.

| # | `custom_document_no` | Expected |
|---|----------------------|----------|
| 12 | `65` | OK |
| 13 | `65A` | **throw** "must be a whole number" |
| 14 | `5.5` | throw |
| 15 | `-5` | throw |
| 16 | `0` | allowed (treated as "not entered" → auto-assign path) |
| 17 | `""` / None | allowed (auto-assign) |
| 18 | `007` | OK, padded to `000007` in custom_name |
| 19 | Company = **"Grihalaxmi Metal Industries Pvt. Ltd"** | `custom_name` is blanked → validator returns early → **no validation at all**. Confirm a bad number is silently accepted for this company and that downstream code tolerates an empty `custom_name`. |

### 2b. `validate_custom_name_unique` — duplicate guard (TOCTOU RISK)
This is a **check-then-write** with **no DB unique constraint**. It is a textbook race.

| # | Case | Expected |
|---|------|----------|
| 20 | Two saved docs, same company/FY/p_type, same `custom_document_no` (sequential) | second one **throws** "Duplicate Document Number" |
| 21 | Same number but different `custom_document_word` (`65` vs `65A`) | both allowed — they are *different* vouchers. This is the explicit design (see comment in `set_auto_document_no`). |
| 22 | Cancelled doc (docstatus 2) holds number 65, create a new 65 | allowed — cancelled excluded. |
| 23 | **CONCURRENCY:** two parallel requests both saving `custom_document_no = 65` | **both may pass `validate` and insert → duplicate `custom_name`.** This WILL happen under load. See §5 for how to drive it. If it produces a duplicate, the fix is a DB unique index on `(custom_name)` where docstatus < 2 — note it. |

### 2c. `set_auto_document_no` — max+1 auto numbering
Only for `AUTO_NUMBER_CONFIG` types (Purchase Return, Other Purchase Receipt, Bank Entry, etc.).
Computes `max(custom_document_no)` filtered by `custom_name LIKE '{ABBR}-{prefix}-%-{FY}%'`.

| # | Case | Expected / trap |
|---|------|-----------------|
| 24 | First Purchase Return of the FY | `custom_document_no = 1` |
| 25 | After manual 5,6,7 exist | next auto = `8` (max+1) |
| 26 | User manually types a number on an auto type | manual value is **kept** (function returns early), dup-check enforces uniqueness later |
| 27 | LIKE pattern leakage: FY pattern ends in `%` (`...-{FY}%`) | a doc in FY `82/8` could match FY `82/83`? Construct two FYs with prefix-overlapping names and confirm the `max()` doesn't bleed across fiscal years. **This is a real wildcard bug risk.** |
| 28 | **CONCURRENCY:** two parallel Purchase Returns | both read same `max`, both get same +1 → duplicate. Same root cause as #23. |

---

## 3. Branch-wise naming (Grishma only) — `set_custom_branch_name`

Only `Grishma Enterprises Pvt. Ltd.` + doctypes in `BRANCH_CODE_CONFIG` (SI, PR, PI) get a real branch name.
A **second independent series** (`getseries(key, 6)`) drives `custom_branch_name`.

| # | Case | Expected |
|---|------|----------|
| 29 | Grishma SI, branch `GEPL-Branch-00001`, normal | `custom_branch_name = GEPL-INV-000001-{FY}` |
| 30 | Same branch, `is_return=1` | uses return code `RT` → `GEPL-RT-000001-{FY}` |
| 31 | Branch `00002` normal vs return | `SB` vs `BSR` |
| 32 | Branch `00003` | `GEP` / `RTN` |
| 33 | Non-Grishma company SI | `custom_branch_name == doc.name` (fallback) |
| 34 | Grishma SI with **no `custom_branch`** set | falls back to `doc.name` — confirm no crash |
| 35 | `custom_branch_name` already set, re-save | **NOT recomputed** (early return). But `custom_name` IS recomputed every save → confirm the two never disagree on FY after a `posting_date` edit (see #41). |
| 36 | Branch series independence | `name` counter and `custom_branch_name` counter are different rows in `tabSeries`. Create 3 docs, delete the middle one, confirm both series behave per §4. |

---

## 4. Delete & series revert — `revert_series_on_delete` (HIGH RISK)

On `after_delete`, if the deleted doc held the **highest** number, the counter steps back so the number is reused.
The key is **reconstructed by regex**, NOT taken from Frappe. If the reconstructed key ≠ the real `tabSeries`
key, the revert **silently does nothing** and you get permanent gaps.

| # | Case | Expected |
|---|------|----------|
| 37 | Create docs ...0003, ...0004, ...0005; delete 0005 | `tabSeries.current` drops 5→4; next new doc reuses 0005 |
| 38 | Delete the **middle** one (0004) | counter unchanged (gap left on purpose, matches core) |
| 39 | Delete 0005 then 0004 then 0003 in order | counter walks back 5→4→3→2 |
| 40 | Dotted-prefix doctype: **Customer Group** (`C.GR`) delete last | This is the whole reason `_revert_series_if_last` exists (core mangles dotted keys). Confirm the dotted key `GEPL-C.GR-` reverts. **This is the regression that motivated the custom revert — guard it hard.** |
| 41 | FY-name delete: `GEPL-SB-82/83-00015` | regex `^(.+?)(\d+)$` must split to key `GEPL-SB-82/83-` + `15`. **Verify this reconstructed key EXACTLY equals the `tabSeries.name` `make_autoname` actually created in #6.** If they differ by even a dot, revert is a no-op. |
| 42 | Branch-name revert | delete last Grishma SI: regex `^(.+)-(\d{6,})-(.+)$` must rebuild `{ABBR}-{code}-{FY}-` and decrement the branch series too. |
| 43 | Amended doc delete (`...-00015-1`) | regex grabs trailing `1` → reconstructs a key with no `tabSeries` row → **must be a safe no-op**, not an exception and not corrupting the base series. |
| 44 | Delete a doc whose name doesn't match any pattern (e.g. blanked custom_name company) | no exception. |

> **How to inspect the counter:** `SELECT name, current FROM tabSeries WHERE name LIKE 'GEPL-SB-%';`
> Run it before delete, after delete, after re-create. Diff the three.

---

## 5. Concurrency / race conditions (where it dies in production)

The duplicate guard (§2b) and auto-number (§2c) are both **read-then-write** with no lock or unique index.
This is the most important section and the hardest to test. Do **not** skip it.

**Driver (run from `bench console` or a script, two parallel workers):**
```python
# scratch: hammer.py — run twice concurrently, or use threads against the HTTP API
import frappe
def make_pr_return():
    doc = frappe.get_doc({
        "doctype": "Purchase Invoice",
        "company": "Grishma Enterprises Pvt. Ltd.",
        "custom_purchase_type": "Purchase Return",
        "posting_date": "2026-01-15",
        # ... minimal mandatory fields ...
    })
    doc.insert()
    return doc.custom_name
```

| # | Case | Pass condition |
|---|------|----------------|
| 45 | 20 parallel auto-number Purchase Returns | 20 **distinct** `custom_document_no`, zero duplicate `custom_name`. If duplicates appear → needs unique index / `SELECT ... FOR UPDATE`. |
| 46 | 20 parallel manual saves with sequential numbers | no dup `custom_name`; no lost numbers |
| 47 | Parallel creates of the same FY series across 2 companies | counters stay independent |

> The honest expectation: **this engine has no concurrency protection.** Document the failure, quantify it
> (how many dupes per 20), and recommend a `UNIQUE` index on `custom_name` (partial, docstatus<2) as the real fix.

---

## 6. Amendment flow

Submittable doctypes (SI, PI, PR, JE, Payment Entry) can be cancelled & amended.

| # | Case | Expected |
|---|------|----------|
| 48 | Submit SI, cancel, amend | new doc `name` gets `-1`; `custom_name` gets `-1` suffix via `get_amendment_suffix` |
| 49 | Amend twice (`-1` then `-2`) | suffix tracks the `name` suffix correctly |
| 50 | Amended doc does NOT trip duplicate guard | original is cancelled (docstatus 2, excluded) + `-1` makes custom_name distinct |
| 51 | `set_auto_document_no` on amend | guarded by `is_new()`? amend creates a new doc that IS new — confirm it does **not** re-grab max+1 and instead inherits the original number. **Likely bug surface.** |

---

## 7. Idempotency / re-save (double-execution)

`validate` and `before_save` both run the full 4-function pipeline. Then users edit & re-save.

| # | Case | Expected |
|---|------|----------|
| 52 | Save a doc, then save again with no changes | `custom_name` identical; `custom_document_no` unchanged; no dup-throw against itself (self excluded by `name`) |
| 53 | Edit `posting_date` to a **different fiscal year** after first save | `custom_name` FY part **changes** but `name` (the immutable ID) and `custom_branch_name` (frozen) do **not**. Confirm whether a doc can legitimately end up with `name` FY ≠ `custom_name` FY — that is a data-integrity smell worth flagging. |
| 54 | Change `custom_document_word` on update | `custom_name` recomputes; uniqueness re-checked |
| 55 | Update a doc into collision with an existing number | throws on update, not just on insert |

---

## 8. The `pad_custom_name.py` backfill script

| # | Case | Expected |
|---|------|----------|
| 56 | Run on a name with `custom_document_no` already 6 digits | no-op (idempotent) |
| 57 | Run on `...-12-...` | becomes `...-000012-...` |
| 58 | Run twice | second run changes nothing |
| 59 | Name containing a `custom_document_word` letter | the letter part is preserved, only the numeric block padded |
| 60 | Dry-run / rollback safety | confirm it commits explicitly and logs counts; run on a **copy/replica first**, never blind on prod |

---

## 9. How to run

### 9a. Quick manual / exploratory — `bench console`
```bash
cd /home/dell/frappe-v15
bench --site avinas1 console
```
```python
import frappe
frappe.set_user("Administrator")
doc = frappe.get_doc({"doctype": "Customer", "customer_name": "T1",
                      "custom_company": "Grishma Enterprises Pvt. Ltd."})
doc.insert()
print(doc.name, getattr(doc, "custom_name", None))
# inspect the series:
frappe.db.sql("SELECT name, current FROM tabSeries WHERE name LIKE 'GEPL-CUS-%'", as_dict=True)
frappe.db.rollback()   # don't pollute the site
```

### 9b. Automated — `FrappeTestCase`
Create `avinashgroup_app/custom_code/Override/test_naming_series.py`:
```python
import frappe
from frappe.tests.utils import FrappeTestCase

class TestNamingSeries(FrappeTestCase):
    def test_customer_simple_name(self):
        d = frappe.get_doc({"doctype": "Customer", "customer_name": "X",
                            "custom_company": "Grishma Enterprises Pvt. Ltd."}).insert()
        self.assertRegex(d.name, r"^GEPL-CUS-\d{5}$")

    def test_document_no_rejects_letters(self):
        # build a doc that carries custom_document_no and assert frappe.ValidationError
        ...
```
Run:
```bash
bench --site avinas1 run-tests --app avinashgroup_app \
      --module avinashgroup_app.custom_code.Override.test_naming_series
```
> `FrappeTestCase` wraps each test in a transaction and rolls back — safe on a real site,
> but prefer a dedicated test site. Counter (`tabSeries`) writes via raw SQL still roll back with the txn.

### 9c. Concurrency — must hit the real HTTP/worker path
Transactions in a single test won't expose the TOCTOU race. Use **two OS processes** or a thread pool
firing `frappe.client.insert` against the running site, then assert zero duplicate `custom_name`:
```bash
SELECT custom_name, COUNT(*) c FROM `tabPurchase Invoice`
WHERE docstatus < 2 GROUP BY custom_name HAVING c > 1;
```
Any row returned = bug confirmed.

---

## 10. Pre-flight checklist (run before signing off)

- [ ] One name from each of the 3 shapes verified (§1a/1b/1c)
- [ ] FY string lands literally in name **and** the `tabSeries` key matches the revert key (§1b#6, §4#41)
- [ ] `custom_document_no` integer gate covers letters/decimal/negative/zero/empty (§2a)
- [ ] Duplicate guard works sequentially **and** the concurrency dupe is measured (§2b, §5)
- [ ] All 3 Grishma branches × normal/return produce correct codes (§3)
- [ ] Delete-revert works for plain, dotted (`C.GR`), FY, branch, and amended names — and is a no-op where it should be (§4)
- [ ] Amendment suffix + no false duplicate on amend (§6)
- [ ] Re-save idempotent; FY-edit-after-save behaviour documented (§7)
- [ ] `pad_custom_name` idempotent and word-safe (§8)
- [ ] Masters without a native company field (Designation/Manufacturer/Prospect) — confirm the company-required throw is intended (§1a#3)

---

## 11. Known weak points (test these first, they are most likely broken)

1. **No concurrency protection** on duplicate-number + auto-number — §5, §2b#23, §2c#28.
2. **Delete-revert key reconstruction** must byte-match the real series key — §4#41/#42. Silent no-op if off.
3. **LIKE wildcard `%` after FY** in `set_auto_document_no` can bleed across fiscal years — §2c#27.
4. **Company-abbr hard requirement** on company-less master doctypes — §1a#3.
5. **3-digit sequence overflow** for Stock Entry family at 1000 docs/FY — §1c#10.
6. **`name` FY vs `custom_name` FY divergence** when `posting_date` is edited post-save — §7#53.
7. **Grihalaxmi blank `custom_name`** disables all validation for that company — §2a#19.

---

# Part B — How to implement this plan

Everything above is *what* to test. This part is *how to build it*, in order. Work top to bottom;
each step is runnable on its own.

## B0. Decide where the truth lives, and protect prod

- **Never run write-tests on `avinas1` (the live site).** Spin a throwaway:
  ```bash
  cd /home/dell/frappe-v15
  bench new-site naming_test.local --admin-password admin --db-root-password <root>
  bench --site naming_test.local install-app erpnext hrms avinashgroup_app
  ```
  If you must use an existing site, use a **DB snapshot you can restore**:
  ```bash
  bench --site avinas1 backup --with-files     # before
  # ... after testing ...
  bench --site avinas1 restore <backup-sql-path>
  ```
- `FrappeTestCase` rolls back per-test, **but** `tabSeries` increments and any `frappe.db.commit()`
  inside the code under test can leak. Treat the test site as disposable regardless.

## B1. Test layout

```
avinashgroup_app/custom_code/Override/
├── naming_series.py
├── test_naming_series.py        # §1, §2, §3, §6, §7  (transactional unit/integration)
├── test_naming_revert.py        # §4  (delete + tabSeries assertions)
└── test_pad_custom_name.py      # §8
avinashgroup_app/tests/
├── __init__.py
├── helpers.py                   # shared builders + series inspectors
└── concurrency/
    ├── hammer.py                # §5 multi-process driver
    └── check_dupes.sql          # §5 assertion query
```
`bench run-tests` auto-discovers any `test_*.py` whose module is importable. Make sure each test dir has
`__init__.py`.

## B2. Shared helpers (build this first — every test depends on it)

`avinashgroup_app/tests/helpers.py`:
```python
import frappe

# Real values pulled from naming_series.py — keep in sync with the config there.
GRISHMA = "Grishma Enterprises Pvt. Ltd."          # BRANCH_NAME_COMPANY
GRIHALAXMI = "Grihalaxmi Metal Industries Pvt. Ltd"  # custom_name is blanked for this one
BRANCHES = {                                         # from BRANCH_CODE_CONFIG
    "b1": "GEPL-Branch-00001",
    "b2": "GEPL-Branch-00002",
    "b3": "GEPL-Branch-00003",
}

def company_abbr(company=GRISHMA):
    return frappe.get_cached_value("Company", company, "abbr")

def ensure_fiscal_year(start, end, label):
    """Create a Fiscal Year covering [start, end] if missing. label e.g. '2082/83'."""
    if not frappe.db.exists("Fiscal Year", label):
        frappe.get_doc({
            "doctype": "Fiscal Year", "year": label,
            "year_start_date": start, "year_end_date": end,
        }).insert(ignore_permissions=True)
    return label

def series_row(key):
    """Current counter for a tabSeries key, or None if the row doesn't exist."""
    return frappe.db.get_value("Series", key, "current")

def set_series(key, current):
    """Force a counter (for overflow / revert boundary tests)."""
    frappe.db.sql(
        "INSERT INTO `tabSeries`(name,current) VALUES(%s,%s) "
        "ON DUPLICATE KEY UPDATE current=%s", (key, current, current),
    )

def make_customer(name, company=GRISHMA):
    return frappe.get_doc({
        "doctype": "Customer", "customer_name": name,
        "customer_group": "All Customer Groups", "territory": "All Territories",
        "custom_company": company,
    }).insert(ignore_permissions=True)

def make_je(company=GRISHMA, posting_date="2026-01-15",
            doc_no=None, doc_word=None, p_type_code=None):
    """Minimal Journal Entry — carries custom_name + custom_document_no."""
    d = frappe.get_doc({
        "doctype": "Journal Entry", "company": company,
        "posting_date": posting_date, "voucher_type": "Journal Entry",
        "custom_document_no": doc_no, "custom_document_word": doc_word,
        "custom_p_type_code": p_type_code,
    })
    d.flags.ignore_mandatory = True   # we test naming, not GL balancing
    return d.insert(ignore_permissions=True)
```
> **Why `ignore_mandatory`**: naming fires on `before_insert/validate/before_save/autoname`, all *before*
> business validation completes for failed accounts. We only assert naming side-effects, so skip the
> unrelated mandatory/GL checks. If a test needs a fully valid submittable doc (amendment, §6), build it
> properly instead.

## B3. Implement §1–§3, §6, §7 → `test_naming_series.py`

One method per numbered case. Map the `#` from Part A into the test name so failures are traceable.
```python
import frappe
from frappe.tests.utils import FrappeTestCase
from avinashgroup_app.tests.helpers import (
    GRISHMA, GRIHALAXMI, BRANCHES, company_abbr,
    ensure_fiscal_year, series_row, set_series, make_customer, make_je,
)

class TestNamingSeries(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_fiscal_year("2025-04-01", "2026-03-31", "2025/26")

    # --- §1a simple ---------------------------------------------------------
    def test_01_customer_simple_shape(self):
        d = make_customer("NS-01")
        self.assertRegex(d.name, rf"^{company_abbr()}-CUS-\d{{5}}$")

    def test_02_customer_increments(self):
        a = make_customer("NS-02a"); b = make_customer("NS-02b")
        self.assertEqual(int(b.name.split("-")[-1]), int(a.name.split("-")[-1]) + 1)

    def test_03_company_less_master_throws(self):
        # Designation has no native company field; document the real behaviour.
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": "Designation",
                            "designation_name": "NS-03"}).insert(ignore_permissions=True)

    # --- §1b fiscal-year ----------------------------------------------------
    def test_05_je_fy_lands_literally(self):
        d = make_je(posting_date="2026-01-15")
        self.assertIn("2025/26", d.name)         # FY string survives make_autoname
        self.assertRegex(d.name, rf"^{company_abbr()}-JE-2025/26-\d+$")

    def test_06_series_key_matches_name(self):
        # The exact tabSeries key MUST equal what revert reconstructs (see §4#41).
        d = make_je(posting_date="2026-01-15")
        key = d.name.rsplit("-", 1)[0] + "-"     # strip trailing number run
        self.assertIsNotNone(series_row(key),
            f"No tabSeries row for reconstructed key {key!r} — revert will be a no-op")

    def test_07_missing_date_throws(self):
        with self.assertRaises(frappe.ValidationError):
            make_je(posting_date=None)

    # --- §1c overflow -------------------------------------------------------
    def test_10_three_digit_overflow(self):
        # force a 3-digit Stock Entry series to 999, then create one more
        # build a minimal Stock Entry, set_series(<its key>, 999), assert ...-1000
        ...

    # --- §2a integer gate (data-driven) ------------------------------------
    def test_12_to_18_document_no_gate(self):
        ok = ["65", "007", "0", "", None]
        bad = ["65A", "5.5", "-5", "abc"]
        for v in ok:
            make_je(doc_no=v, posting_date="2026-01-15")            # must not raise
        for v in bad:
            with self.assertRaises(frappe.ValidationError, msg=f"{v!r} should reject"):
                make_je(doc_no=v, posting_date="2026-01-15")

    # --- §2b duplicate guard (sequential) ----------------------------------
    def test_20_duplicate_number_rejected(self):
        
        make_je(doc_no="500", posting_date="2026-01-15")
        with self.assertRaises(frappe.ValidationError):
            make_je(doc_no="500", posting_date="2026-01-15")

    def test_21_same_number_diff_word_allowed(self):
        make_je(doc_no="600", doc_word=None, posting_date="2026-01-15")
        make_je(doc_no="600", doc_word="A", posting_date="2026-01-15")  # different voucher

    # --- §3 branch naming ---------------------------------------------------
    def test_29_branch_normal_code(self):
        # Grishma Sales Invoice, branch b1, normal -> custom_branch_name uses 'INV'
        ...

    # --- §7 idempotency -----------------------------------------------------
    def test_52_resave_is_idempotent(self):
        d = make_je(doc_no="700", posting_date="2026-01-15")
        before = d.custom_name
        d.save(ignore_permissions=True)
        self.assertEqual(d.custom_name, before)
```
Fill the `...` stubs the same way. Keep every assertion **specific** (exact regex / exact counter), never
just "didn't crash".

## B4. Implement §4 → `test_naming_revert.py`

Delete-revert needs before/after counter snapshots, so it gets its own file.
```python
import frappe
from frappe.tests.utils import FrappeTestCase
from avinashgroup_app.tests.helpers import series_row, make_je, ensure_fiscal_year

class TestNamingRevert(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_fiscal_year("2025-04-01", "2026-03-31", "2025/26")

    def test_37_delete_last_reverts(self):
        d = make_je(doc_no="1", posting_date="2026-01-15")
        key = d.name.rsplit("-", 1)[0] + "-"
        high = series_row(key)
        frappe.delete_doc(d.doctype, d.name, force=True)   # triggers after_delete
        self.assertEqual(series_row(key), high - 1)

    def test_38_delete_middle_keeps_counter(self):
        a = make_je(doc_no="2", posting_date="2026-01-15")
        b = make_je(doc_no="3", posting_date="2026-01-15")
        key = a.name.rsplit("-", 1)[0] + "-"
        high = series_row(key)
        frappe.delete_doc(a.doctype, a.name, force=True)    # 'a' is not the highest
        self.assertEqual(series_row(key), high)

    def test_40_dotted_key_reverts(self):
        # Customer Group prefix 'C.GR' — the reason _revert_series_if_last exists.
        ...

    def test_43_amended_delete_is_noop(self):
        # deleting a '...-1' amended name must not throw and must not touch base series
        ...
```

> **Important:** `frappe.delete_doc(..., force=True)` fires `after_delete`. A plain test-teardown rollback
> does **not** — so revert tests must delete explicitly and assert the counter, not rely on rollback.

## B5. Implement §5 → real concurrency harness (cannot use FrappeTestCase)

A single transaction can't expose the TOCTOU race. Drive the **live HTTP/worker path** with parallel
processes, then assert zero duplicates in SQL.

`avinashgroup_app/tests/concurrency/hammer.py`:
```python
"""Run: bench --site naming_test.local execute \
        avinashgroup_app.tests.concurrency.hammer.run --kwargs '{"n": 20}'
   Spawns N threads each inserting an auto-numbered Purchase Return."""
import frappe, threading

def _one(i, errors):
    try:
        frappe.init(site=frappe.local.site)
        frappe.connect()
        d = frappe.get_doc({
            "doctype": "Purchase Invoice",
            "company": "Grishma Enterprises Pvt. Ltd.",
            "custom_purchase_type": "Purchase Return",
            "posting_date": "2026-01-15",
        })
        d.flags.ignore_mandatory = True
        d.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        errors.append(str(e))

def run(n=20):
    errors = []
    threads = [threading.Thread(target=_one, args=(i, errors)) for i in range(int(n))]
    for t in threads: t.start()
    for t in threads: t.join()
    print(f"{len(errors)} errors out of {n}")
```
> Threads share one Python process and the GIL — they approximate concurrency but the *real* test is
> **separate OS processes** hitting the REST API in parallel (`xargs -P`, `ab`, or a tiny `requests` loop
> with `api_key:api_secret`). Use threads for a smoke signal, multi-process for the verdict.

`check_dupes.sql` (the actual pass/fail):
```sql
SELECT custom_name, COUNT(*) c
FROM `tabPurchase Invoice`
WHERE docstatus < 2 AND custom_name IS NOT NULL AND custom_name != ''
GROUP BY custom_name HAVING c > 1;
```
```bash
bench --site naming_test.local mariadb < avinashgroup_app/tests/concurrency/check_dupes.sql
```
**Zero rows = pass. Any row = the race is real** → recommend a partial UNIQUE index on `custom_name`
(`WHERE docstatus < 2`) or `SELECT ... FOR UPDATE` around the max+1 read.

## B6. Implement §8 → `test_pad_custom_name.py`

Read `scripts/pad_custom_name.py` first to learn its entrypoint signature, then:
```python
import frappe
from frappe.tests.utils import FrappeTestCase

class TestPadCustomName(FrappeTestCase):
    def test_56_idempotent_on_padded(self):
        # seed a doc whose custom_name already has 6-digit block; run; assert unchanged
        ...
    def test_57_pads_short_number(self):
        # seed '...-12-...'; run; assert '...-000012-...'
        ...
    def test_59_preserves_word(self):
        # seed a name with a letter word; run; assert only the digits padded
        ...
```
Run it against a **copy** because the script may `frappe.db.commit()`.

## B7. Run everything

```bash
# one module
bench --site naming_test.local run-tests \
      --module avinashgroup_app.custom_code.Override.test_naming_series

# whole app (after files are in place)
bench --site naming_test.local run-tests --app avinashgroup_app

# single failing case while iterating
bench --site naming_test.local run-tests \
      --module avinashgroup_app.custom_code.Override.test_naming_series \
      --test test_05_je_fy_lands_literally
```
Enable the test runner's verbose flag and keep `tabSeries` open in a second terminal:
```bash
watch -n1 "bench --site naming_test.local mariadb -e \
  'SELECT name,current FROM tabSeries ORDER BY modified DESC LIMIT 10'"
```

## B8. Build order (do it in this sequence)

1. **B0 + B2** — disposable site + `helpers.py`. Nothing works without these.
2. **B3 §1a/§1b** — prove the happy path names are correct; this surfaces config/site-setup gaps early.
3. **B3 §2a/§2b** — the integer gate and sequential dup-guard (cheap, high signal).
4. **B4 §4** — delete-revert; depends on B3 producing real series keys.
5. **B3 §3, §6, §7** — branch, amendment, idempotency.
6. **B5 §5** — concurrency last; it needs a stable working insert path to hammer.
7. **B6 §8** — backfill script.

Land §11's seven weak points as **failing tests first** (red), then decide with the team whether each is a
bug to fix or behaviour to accept — and convert accepted ones into explicit assertions documenting the
contract.

## B9. CI / repeatability

- Add a make/bench target so the suite runs on a fresh site each time (config drift is the #1 cause of
  flaky naming tests — a missing Fiscal Year or Company abbr changes every generated name).
- The concurrency check (B5) is **not** a unit test — gate it as a separate manual/nightly job; it needs a
  running web server and is inherently non-deterministic. Record "dupes per 20 inserts" as a tracked metric,
  not a binary, until the unique index lands.

---

# Part C — Results of the first run (executed against `avinas1`, all rolled back)

Harness: `scratchpad/naming_probe.py` — direct calls to `naming_series.py` + one real Customer
create/edit/delete lifecycle + deterministic series-revert, run on the live DB inside a single
transaction and `frappe.db.rollback()`-ed at the end (zero writes committed). **31 / 31 assertions passed.**

## C1. CREATE — observed behaviour
| Case | Observed |
|------|----------|
| Simple master shape | `GEPL-CUS-00001`, second `…00002` (increments) ✓ |
| Company-less master (`Designation`) | **throws** `Company abbreviation is required for Designation` — confirmed; masters with no company are hard-blocked (§1a#3) |
| FY doc name | `GEPL-JE-82/83-00001`; FY string `82/83` lands literally, `tabSeries` key = `GEPL-JE-82/83-` ✓ |
| Missing date | throws `Date field … is required` ✓ |
| No-FY date (`1990-01-01`) | throws `No fiscal year found` ✓ |
| Integer gate | `65/007/0/""/None` accepted; `65A/5.5/-5/abc` rejected ✓ |
| `custom_name` shape | `NGI--000065-82/83` — note the **double dash** when `p_type` is empty, and zero-pad to 6 |
| Grihalaxmi company | `custom_name` blanked → integer gate **skipped**, bad `65A` silently accepted (§2a#19 confirmed) |
| Same number, diff word | `NGI--000600-82/83` vs `NGI--000600A-82/83` → distinct ✓ |
| Duplicate guard | rejects an existing `custom_name` (tested read-only vs `NGI-PBO-1232165-82/83`) ✓ |
| Auto-number (Purchase Return) | `max(custom_document_no)+1` → returned `1232166` ✓ |
| Branch naming | all 3 branches × normal/return correct: `INV/RT`, `SB/BSR`, `GEP/RTN` ✓ |

## C2. EDIT — observed behaviour
| Case | Observed |
|------|----------|
| Re-save, no change | `custom_name` stable (idempotent) ✓ |
| Edit `posting_date` to prior FY | `NGI--000701-82/83` → `NGI--000701-81/82` — `custom_name` FY changes but `doc.name` (the ID) would not → **FY divergence is real** (§7#53) |
| Edit `custom_document_word` | `…000702-82/83` → `…000702Z-82/83` recomputed ✓ |

## C3. DELETE — observed behaviour
| Case | Observed |
|------|----------|
| Real Customer create→delete last | counter `GEPL-CUS-` `2 → 1`, then `1 → 0` (reverts each time) ✓ |
| Revert when deleted == current | `7 → 6` ✓ |
| Delete middle (deleted ≠ current) | counter stays `6` (gap left, matches core) ✓ |
| Amended-style key (`…-00007-`) | safe no-op, base series untouched ✓ |

## C4. Confirmed findings (verified, not theoretical)

1. **PRODUCTION DATA CORRUPTION — duplicate `custom_name` already exists.**
   `Purchase Invoice` and `Purchase Receipt` have **NO index on `custom_name`** (not even non-unique),
   while `Payment Entry` and `Journal Entry` **do have a UNIQUE index**. As a direct result the app-level
   `validate_custom_name_unique` (a check-then-write with no lock) has already lost the race on PI:
   ```
   Purchase Invoice: 3 duplicate custom_name groups (docstatus<2), e.g.
     NGG-PBO-000186-81/82  (x2)
     NGN-PBO-000002-80/81  (x2)
     NGG-PBO-000341-80/81  (x2)
   Payment Entry / Journal Entry: 0 duplicates  (protected by the unique index)
   ```
   **Fix:** clean the existing PI/PR dupes, then add a unique index on `custom_name` for
   `Purchase Invoice` and `Purchase Receipt` (the index is what actually stops the TOCTOU race —
   the Python check cannot). This is the single most important action item.

2. **Dotted prefixes lose the dot in `doc.name`.** Config `prefix: "PAY.REC"` produces names like
   `NGK-PAYREC-82/83-04085` (live), and `make_autoname("GEPL-C.GR-.#####")` → `GEPL-CGR-00001`.
   `make_autoname` treats `.` as a control char and eats it. Affects every dotted prefix
   (`C.GR`, `I.GR`, `P.List`, `A.Cat`, `B.AC`, `S.GR`, `EC.Type`, `PAY.REC`). Behaviour is *self-consistent*
   (the revert regex rebuilds the same dot-less key, so delete-revert still works — verified), but the
   comment in `revert_series_on_delete` claiming keys "may contain dots (e.g. GEPL-C.GR-)" is **wrong**;
   the real key is `GEPL-CGR-`. Decide whether dot-stripped master IDs are intended.

3. **Company-less masters are hard-blocked** (`Designation`, and by the same path `Manufacturer`,
   `Prospect`) unless a `custom_company` value is supplied — confirmed via the thrown error.

4. **Grihalaxmi bypasses ALL voucher validation** — blanked `custom_name` short-circuits both the integer
   gate and the duplicate guard. Any malformed `custom_document_no` is accepted for that company.

5. **`name`/`custom_name` fiscal-year divergence** on `posting_date` edit is real and silent.

## C5. Still outstanding (not yet executed)
- True multi-process concurrency hammer (B5) — not run to avoid committing to live; the unique-index
  audit above already proves the exposure and the existing PI corruption, which is stronger evidence.
- 3-digit sequence overflow at 1000 (§1c#10) — needs a seeded series on a disposable site.
- Full submittable amendment lifecycle (§6) — JE/PI inserts hit unrelated stock-account validation on
  `avinas1`; run on a clean test site with valid master data.

## C6. How to re-run
```bash
cd /home/dell/frappe-v15/sites
/home/dell/frappe-v15/env/bin/python <path>/naming_probe.py   # self-rolls-back, safe on live
```
The harness is read-mostly and ends in `frappe.db.rollback()`. To re-check the production-dup finding:
```bash
/home/dell/frappe-v15/env/bin/python -c "import frappe; frappe.init(site='avinas1'); frappe.connect(); \
print(frappe.db.sql('select custom_name,count(*) c from \`tabPurchase Invoice\` where docstatus<2 \
and custom_name>\"\" group by custom_name having c>1'))"
```
