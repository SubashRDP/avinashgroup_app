# Numbering Configuration — how document numbering works

Engine: `avinashgroup_app/custom_code/Override/naming_series.py`
Doctype UI: `avinashgroup_app/avinash_group_app/doctype/numbering_configuration/`
Form JS: `public/js/auto_update_document_no.js` (Document No. field), `public/js/numbering_preview.js` (voucher-name alert)
Tests: `avinashgroup_app/test_document_numbering.py`

---

## 1. The two numbers

Every voucher has **two related numbers**, managed by two cooperating mechanisms:

| | What it is | Where it's stored | Who generates it |
|---|---|---|---|
| **Voucher No.** | The formatted display number, e.g. `GEPL-INV-000123-82-83` | The rule's **Target Field** (default `custom_branch_name`, can be `custom_name`) | The **rule engine** (`set_custom_branch_name`) from the rule's Segments |
| **Document No.** | The bare running counter, e.g. `123` | `custom_document_no` (+ optional letter tail in `custom_document_word`) | `apply_document_no` — atomic max+1 under a per-scope lock |

They connect when a rule's Segments include a `Document Field: custom_document_no`
segment — the voucher number then *contains* the document number.

When **no rule** exists for a doctype, fallbacks apply: the voucher name comes from
the legacy `NAMING_CONFIG`/`set_custom_name_field` path, and Document No.
eligibility comes from the hardcoded `AUTO_NUMBER_CONFIG` dict. **Rules always win
over fallbacks.**

## 2. One rule = one numbering policy

A **Numbering Configuration** record says: *for this Document Type (optionally this
Company/Branch), when these conditions match — build this number, store it here,
and optionally auto-fill the Document No.*

### Scope & matching
- `document_type` (required), `company` (blank = all), `branch` (blank = all).
- **Voucher No. Conditions** (child: *Numbering Condition*, plain `field = value`):
  ALL must match for the rule to apply.
- **Most specific rule wins**: specificity = (company set? +1) + (branch set? +1) +
  (number of conditions). Ties break deterministically by rule name, and tied rules
  are reported as **ambiguous** (form alert + warning on rule save) — fix by making
  one rule more specific or disabling one.

### Output
- `target_field` — where the built voucher number is written (auto-marked
  `no_copy`, auto-indexed).
- `separator` — joins segments (`-`, `/`, …).

### Segments (child: *Numbering Segment*, ordered, drag to reorder)
| Segment type | Produces | Notes |
|---|---|---|
| Static Text | fixed text (`INV`) | |
| Normal / Return Code | `static_value`, or `return_value` when `is_return = 1` | **the built-in return/normal switch for the voucher name** |
| Company Abbr | `Company.abbr` | |
| Branch Abbr | `Branch.custom_abbr` of `custom_branch` | puts branch into the series key → per-branch counters |
| Fiscal Year | FY of posting/transaction date | `/` in FY becomes `-` if separator is `/` |
| Document Field | any field value | `Digits` zero-pads numeric values |
| Fetch from Link | field on a linked record (e.g. type → code) | |
| Number | the running counter | at most one; may sit anywhere in the order |

- **Attach** (`join_previous`): glue to previous part with no separator (`0001`+`A` → `0001A`).
- Empty segments are skipped.
- **No Number segment = pass-through rule**: joins the values as-is, consumes no
  counter (used to copy legacy numbers, e.g. from `custom_narration`).
- The counter's **series key** is the joined non-Number segment values — two
  documents that resolve the same prefix share a counter.

### Legacy cut-over (one rule covers both eras)
`legacy_upto` + `legacy_source_field` (+ optional `date_field`): documents dated on
or before the cut-over **copy** their number from the source field (no counter);
later documents generate from Segments. Empty source → falls through to the next
matching rule.

### Auto-fill Document No. (per rule — the auto/manual switch)
- `auto_document_no` (check): when ON and the rule matches, `custom_document_no`
  is auto-drawn by the server at save.
- **Normal Documents / Return Documents** selects (`normal_docno_mode` /
  `return_docno_mode`, each `Auto` or `Manual`, default **Auto**): the simple
  per-kind switch. A document with `is_return` checked uses the Return mode,
  everything else the Normal mode. `Manual` means the user must type the number
  (the form shows the field required). Blank (rules saved before these shipped)
  behaves as Auto.
- **Document No. Conditions** (child: *Numbering Document No Condition*, with
  operators `Equals / Not Equals / In / Not In / Is Set / Is Not Set`): advanced
  gate on top of the modes — the number is auto-filled **only when ALL match**.
  They are **independent of the Voucher No. conditions** — one rule can name
  every document but number only a subset. Empty list = number everything the
  modes allow.
- **Group Document No. By** (child: *Numbering Group By Field*): the admin picks
  the fields whose value combinations each count on their OWN sequence (1, 2,
  3, …) — e.g. `company` + `custom_p_type_code` + `custom_fiscal_year` gives
  every company/type-code/year its own numbers. `custom_fiscal_year` is special:
  it groups by the fiscal year of the posting/transaction date (date-range
  matched, so old rows with an empty stored column still count). Group-by scopes
  scan by real column filters, so an existing series **continues** even when the
  voucher format changes. Empty table = group by the rule's number prefix
  (default), or the legacy `company|code|fiscal-year` scope.
  **Caution:** only group by a field (e.g. `custom_branch`) if the voucher NAME
  also contains it — otherwise two groups can draw the same number and collapse
  into identical names, which the uniqueness guard rejects.
- An Auto-fill rule is **authoritative**: documents failing its Document No.
  conditions are NOT numbered (the hardcoded fallback is not consulted).
- `document_no_field` — store the number somewhere other than
  `custom_document_no` (counters isolated per field).
- `duplicate_action` — manual number already used: `Throw Error` (default) or
  `Use Next Available Number`.

## 3. Document No. lifecycle (server-authoritative)

The browser **never generates or predicts** the number.

1. **Form (new doc)** — the client asks one endpoint,
   `get_document_no_status(doc)` → `{auto, next, ambiguous}`:
   - `auto=true` → the field is **hidden**; the number does not exist until saved.
   - `auto=false` → the field is shown and **required**; typing triggers a live
     duplicate check (`check_document_no_availability`).
2. **Save** — `apply_document_no` (validate + before_save hooks, idempotent):
   - draws atomically: `GREATEST(counter, data max) + 1` under a per-scope
     `tabSeries` row lock — concurrent savers can't collide;
   - scope = rule-derived (its resolved prefix; Branch Abbr ⇒ per-branch) or the
     legacy `company|code|fiscal year` scope when the rule has no number position;
   - manual values (flag `custom_document_no_manual`) are kept, uniqueness-checked,
     and bump the counter above themselves;
   - amendments are **pinned** to the cancelled original's number;
   - a draft edited onto a different scope (branch/company/date/type) gives its
     number back (if last) and redraws from the new series;
   - imports/REST keep payload numbers verbatim (visible error on duplicates).
3. **After save** — the field is visible: read-only when auto-drawn, editable when
   manual.
4. **Delete** — last-issued number returns to the counter; mid-series gaps stay.

Mandatory note: `custom_document_no` is statically `reqd` on Purchase
Invoice/Receipt; that's satisfied because the server fills it during `validate`,
before the mandatory check. The form JS lifts `reqd` client-side while hiding it.

## 4. Recipe: *normal = manual, return = auto* (same doctype)

E.g. Sales/Purchase Invoice vs their Returns, split by the standard `is_return`
checkbox. ONE rule using the mode selects:

| Setting | Value |
|---|---|
| Document Type | Purchase Invoice (or Sales Invoice, …) |
| Company / Branch | as needed (per-branch series ⇒ add a Branch Abbr segment or per-branch rules) |
| Auto-fill Document No. | ✔ |
| **Normal Documents** | **Manual** — user must type the number |
| **Return Documents** | **Auto** — server assigns at save |
| Voucher No. Conditions | empty (one rule names everything) |
| Segments | e.g. Company Abbr · Normal/Return Code (`PB`/`PRTN`) · Number(6) · Fiscal Year |

Result: a **return** hides the Document No. and gets it server-drawn at save; a
**normal** invoice shows the field as required manual entry. The *name* works for
both (the Normal/Return Code segment switches the prefix). Live example on site
`avinas`: rule *Purchase Invoice - feec8*.

For splits other than normal/return, use the **Document No. Conditions** instead
(or in addition): `In` a list of types (`custom_p_type In Bank Entry, Party
Journal`), `Is Set` (number only when a branch is chosen), `Not Equals`, etc.

## 4b. Recipe: Payment Entry — auto by type, dynamically grouped

Live example on site `avinas`: rule *Payment Entry - 62ce7*.

| Setting | Value |
|---|---|
| Auto-fill Document No. | ✔ (modes Auto) |
| Document No. Conditions | `custom_p_type` · `In` · `Bank Customers Receipt, NOC Payment, Contra Voucher- cash to bank` |
| Group Document No. By | `company` · `custom_p_type_code` · `custom_fiscal_year` |
| Target / Segments | `custom_branch_name` (not on PE ⇒ naming untouched); segments unused for the number |

The listed types are auto (hidden field, server-drawn); every other type is
manual. The grouping reproduces the legacy company+code+fiscal-year scope but is
now **admin-editable** — and because group-by scans real columns, the existing
series continued (verified: it picked up right after the historical max). To add
`custom_branch` to the grouping, first put a Branch Abbr into the voucher-name
format (see the Caution in §2).

## 5. Series continuity — read before adding a rule to a live doctype

The Document No. scope changes when a rule with a number position starts matching
documents that were previously numbered by the fallback (pattern moves from
`custom_name` to the rule's target/prefix). A new pattern matches no history →
**the series restarts at 1**. To continue an existing series, make the rule's
resolved prefix reproduce the stored format (see `_temp_rule` in the tests, and the
seed scripts `scripts/seed_numbering_rules.py`, `seed_sales_invoice_numbering.py`,
which are byte-compatible with the legacy formats). Test first with **Test on a
Document** (consumes nothing).

## 6. Form tools & plumbing

- **Live Preview** box, **Test on a Document** (real doc, no counter consumed),
  **Apply to Other Companies** (bulk duplicate), duplicate-scope warning on save.
- Caches: per-request → redis (`numbering_rules::<doctype>`), cleared on any rule
  save/delete. Rule fetch is 3 queries total (no N+1).
- Wildcard hooks run the engine for **any** doctype with an enabled rule
  (`apply_engine_numbering` on validate/before_save; series revert on delete).
- To put the Document No. UI on a new doctype: add the `custom_document_no`
  (+ `_manual`) fields and list the doctype in `DOCNO_DOCTYPES` in
  `auto_update_document_no.js`.

## 7. Current deployment note (site `avinas`)

As of 2026-07-09 the site has **zero** Numbering Configuration rules — every
doctype runs on the fallbacks. The per-rule features above are fully functional
but only activate once rules are created (manually or via the seed scripts).
