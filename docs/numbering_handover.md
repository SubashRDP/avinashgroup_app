# Document Numbering — Handover

**Audience:** whoever maintains the Numbering Configuration system next (dev or admin).
**What this is:** a map into the existing documentation, the gotchas that actually trip
people up, and the state of the live rules. It does **not** re-explain the whole system —
the docs listed in §6 already do that well. Read this first, then dive into whichever doc §6
points you at.

> Last reviewed: 2026-07-19. The live rules are edited directly on the site, so treat any
> "current state" table (§5) as a snapshot — **always re-fetch before acting.** See §7.

---

## 1. The 60-second mental model

There are **two numbers** on every document, and they are independent:

| # | Field (default) | What it is | Who sets it |
|---|---|---|---|
| Document No. | `custom_document_no` | The running serial (0001, 0002 …) | Server, atomically, per *scope* |
| Voucher number / name | `custom_name` (or `custom_branch_name`) | The formatted label built from *segments* | Server, from the rule's segments |

The formatted name usually **embeds** the Document No. as one of its segments. So the serial
is drawn once (into `custom_document_no`) and then pulled into the pretty name.

A **Numbering Configuration** record is one *policy*: which documents it applies to, how the
name is formatted, and how the serial is scoped/reset.

---

## 2. THE gotcha: two condition tables, two different jobs

This is the single thing that confuses everyone (it confused us for a full session). A rule
has **two** condition child-tables and they do **completely different** jobs:

| Table | Field name | Job | Code |
|---|---|---|---|
| **Voucher-No conditions** | `conditions` | Decides **IF the rule applies at all** (rule selection) | `_rule_matches` |
| **Doc-No conditions** | `document_no_conditions` | Decides whether to **draw a serial**, *only after* the rule is already selected | `_docno_eligible` |

They are checked **in that order, and it stops at the first gate.** Rule selection
(`_rule_matches`) looks **only** at the Voucher-No `conditions` — it never reads
`document_no_conditions`.

**Consequence (the trap):** if the Voucher-No condition is *narrower* than the Doc-No `In`
list, the extra types named in the `In` list are **dead** — the rule is rejected before that
list is ever read.

> **Analogy:** the Voucher-No condition is the **door** to the rule; the Doc-No `In` list is a
> **sign inside the room**. A type named on the sign but not allowed through the door never
> gets in to read the sign.

Real example we hit (Payment Entry `d932e`, since fixed): Voucher-No was `Equals "Bank
Customers Receipt"` but the Doc-No list was `In (Bank Customers Receipt, NOC Payment, Contra…)`.
Result: **NOC & Contra could never be numbered.** Fix was to *empty* the Voucher-No condition
(so the rule matches all Payment Entries) and let the Doc-No `In` list do the gating.

**Rule of thumb:** if you want the Doc-No `In` list to actually gate several types, the
Voucher-No condition must be **at least as wide** — usually **empty** (matches everything) or
the same `In` list.

---

## 3. Gotcha: fiscal-year reset lives in Group-By, not the segment

Every rule has a **Fiscal Year segment** in the *name* — but that only formats the label. What
actually makes the serial **restart each Nepali fiscal year** is having `custom_fiscal_year`
in the **Group Document No. By** table (`docno_group_by`). See `_group_by_scope` — it turns
`custom_fiscal_year` into a `year_start..year_end` date filter on the counter's scope.

- Group-By **has** `custom_fiscal_year` → serial resets each FY (0001 again on 83/84). ✅
- Group-By **missing** it → serial keeps climbing across years even though the label shows the
  new FY. ❌ (This was the bug on PR-02076, PI-590d3, PI-d7672 — all since fixed.)

The tell is asymmetry between sister rules: if the Grishma variant resets per FY and the
all-companies variant doesn't (or vice-versa), one of them is wrong.

---

## 4. Gotcha: "name without number"

When a rule builds the name for a document that is **not eligible** for a serial (excluded by
Doc-No conditions), the `custom_document_no` segment resolves to blank. `_join_parts` skips
empty segments, so you get a *clean but incomplete* label — the serial is simply missing:

```
Eligible  (Bank Entry):    NGI-BE-000042-82/83
Excluded  (Opening Entry): NGI-OE-82/83          ← no serial
```

Why it matters: the serial is the only thing that makes each voucher unique. Two excluded-type
documents in the same company + FY produce the **identical** string. If `custom_name` is
unique-indexed the second save **throws duplicate**; if not, you get **two vouchers sharing a
number**. (See the `naming_custom_name_dup_bug` note — PE/JE are index-protected, PI/PR were
not.)

It is only a problem **if excluded-type documents actually get created.** So for every rule
that numbers a *subset* (Voucher-No matches all, Doc-No `In` a few types), the question to
answer is: *"Do we ever create the types NOT in the `In` list, and should they be
auto-numbered?"* If yes → add them to the `In` list. If no → leave it.

---

## 5. Live rules — ng-group (snapshot 2026-07-19)

Site: `https://ng-group.raindropinc.com/`. Nine rules, all enabled. **This is a snapshot —
they are edited live; re-fetch before trusting it (§7).**

| Rule | Company | Numbers | FY reset | Notes |
|---|---|---|---|---|
| Sales Invoice - 76971 | ALL | Number segment, per company+code+FY | via prefix | Group-By lists `custom_branch` but it's **inert** (`auto_document_no=0`); cosmetic only |
| Sales Invoice - GEPL - ae8ad | Grishma | per-branch (Branch Abbr segment) | via prefix | wins over 76971 for Grishma |
| Purchase Receipt - 02076 | ALL | `custom_receipt_type In (Other Purchase Receipt)` | ✅ | other receipt types → name without number (confirm intent) |
| Purchase Receipt - GEPL - 7236d | Grishma | same gate | ✅ | wins for Grishma |
| Purchase Invoice - 590d3 | ALL | all PIs (no conditions) | ✅ | — |
| Purchase Invoice - GEPL - d7672 | Grishma | `custom_purchase_type Equals "Gas Purchase Invoice"` | ✅ | other Grishma PIs fall to 590d3 |
| Payment Entry - d932e | ALL | `custom_p_type In (Bank Customers Receipt, NOC Payment, Contra…)` | ✅ | Voucher-No empty → matches all PEs; other p_types → name without number (confirm intent) |
| Payment Entry - GEPL - 486fd | Grishma | `custom_p_type Equals "Bank Customers Receipt"` | ✅ | branch-wise; wins for Grishma BCR |
| Journal Entry - 35438 | ALL | `custom_p_type In (Bank Entry, Party Journal, Debit Note, Credit Note)` | ✅ | other p_types → name without number (confirm intent) |

**Open items (not bugs — confirm-intent):** the four "numbers a subset" rules above
(JE-35438, PR-02076/7236d, PE-d932e) — verify the excluded types are meant to be manual (§4).
Cosmetic: remove the inert `custom_branch` Group-By row on SI-76971.

**Specificity / overlap:** where an all-companies rule and a Grishma rule both match, the
Grishma one wins (`_rule_specificity` = +1 company, +1 branch, +1 per condition; ties broken
deterministically by name). No ambiguous ties currently.

---

## 6. Where the documentation lives (read these for depth)

| Doc | Read it for |
|---|---|
| `docs/document_numbering.md` | **Start here.** User/admin guide: the two numbers, scope, conditions, worked examples, recipes |
| `docs/numbering_configuration.md` | The Numbering Configuration form field-by-field; auto/manual switch; legacy cut-over; series continuity |
| `docs/branch_wise_numbering.md` | Branch-wise recipes (Sales Invoice + Return in one rule; all-branches; Payment receive vs pay) |
| `docs/SALES_INVOICE_NUMBERING.md` | Deep-dive on the multi-rule, most-specific-wins pattern with backdated-migration examples |
| `docs/document_numbering_developer.md` | **Internals.** Save-lifecycle hook order, `apply_document_no` decision tree, concurrency model, name building, caching, invariants |
| `docs/todo_o1_numbering_fast_path.md` | The "trust the counter" O(1) fast-path optimization |
| `Document_Numbering_System.pdf` | Original design write-up |

---

## 7. How to inspect a rule safely (read-only)

The live site can be read without any write. Fetch a rule and dump its shape:

```bash
# read-only GET; auth = token <api_key>:<api_secret>
curl -s -H "Authorization: token <KEY>:<SECRET>" \
  "https://ng-group.raindropinc.com/api/resource/Numbering%20Configuration/<NAME>"
```

Check, for any rule you audit:
1. **Voucher-No `conditions`** vs **Doc-No `document_no_conditions`** — is the door at least as
   wide as the sign? (§2)
2. **`docno_group_by`** — does it include `custom_fiscal_year` if the serial should reset per
   year? (§3)
3. **Fetch-from-Link segments** — does the `fetch_field` actually exist on the linked doctype?
   A missing one resolves to empty silently (`warn_bad_fetch_field` only warns at save).
4. **Overlap** — is there another enabled rule with the same scope? The more-specific one wins;
   equal specificity is flagged by `warn_duplicate_scope`.

Non-consuming preview from inside the app: `Numbering Configuration.test_number(reference)` —
returns `{matches, number}` without drawing the counter (`commit_series=False`).

**Operational lesson from this handover:** these rules are edited on the live site during
setup. During this review, four rules I'd flagged as buggy had **already been fixed** by the
time I looked again — the data I first pulled was stale. **Always re-fetch immediately before
giving a verdict or making a change.**

---

## 8. Key code (app: `avinashgroup_app`)

| File | Contains |
|---|---|
| `custom_code/Override/naming_series.py` | The engine. Key fns: `apply_document_no`, `_docno_scope` / `_group_by_scope` / `_rule_docno_scope`, `_match_numbering_rule` / `_rule_matches` / `_docno_eligible`, `_condition_matches`, `_build_from_segments` / `_resolve_segments` / `_join_parts` |
| `avinash_group_app/doctype/numbering_configuration/` | The config doctype + `validate()` guards (`validate_segments`, `validate_condition_fields`, `warn_duplicate_scope`, legacy cut-over) and `test_number` |
| `avinash_group_app/doctype/numbering_segment|numbering_condition|numbering_document_no_condition|numbering_group_by_field/` | The child tables |

Invariants to preserve (full list in the developer guide §9): serials are drawn under a
per-scope row lock (never collide); imports never auto-number (they must carry the number);
the target field is forced `read_only` + `no_copy`; a value that arrived by import/REST is
never blanked.
