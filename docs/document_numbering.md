# Document Numbering — User & Admin Guide

How the **Document No.** and **Voucher No.** on transactions are generated, how to
configure numbering from the desk with **Numbering Configuration** rules, and what
to expect in every situation — typing, duplicating, editing, importing.

> Developer documentation (architecture, concurrency, extension points, testing):
> see [document_numbering_developer.md](document_numbering_developer.md).

---

## 1. The two numbers

| Field | Label | What it is | Example |
|---|---|---|---|
| `custom_document_no` | **Document No.** | the running counter — `1, 2, 3…` | `104` |
| `custom_name` / `custom_branch_name` | **Voucher No.** | the formatted string built *around* the counter | `GEPL-an-RC-000104-82/83` |

The **Document No.** is the thing that counts. The **Voucher No.** is a label
assembled from it (company, type, branch, the number, fiscal year…). Change the
Document No. and the Voucher No. updates to match.

- The number shown **before saving is a preview**. The real, collision-free number
  is locked **on Save** — two people can never get the same one, even saving in the
  same instant.
- The first document of a new scope starts at **1**; a new fiscal year restarts at **1**.
- The field is **mandatory**: every document either auto-numbers or the user types a
  number. It is never saved empty (exception: one legacy company is exempt).

---

## 2. When does the Document No. auto-fill?

Two levels decide it — a rule wins over the built-in defaults.

### Level 1 — Built-in defaults (no configuration at all)
Out of the box these doctypes auto-number, gated by a *type* field:

| Doctype | Type field | Types that auto-number |
|---|---|---|
| **Journal Entry** | `custom_p_type` | Bank Entry · Party Journal · Debit Note · Credit Note |
| **Payment Entry** | `custom_p_type` | Bank Customers Receipt · NOC Payment · Contra Voucher- cash to bank |
| **Purchase Invoice** | `custom_purchase_type` | Purchase Return |
| **Purchase Receipt** | `custom_receipt_type` | Other Purchase Receipt |

With no rule:
- the count is **company-wide**: Company + Type-code + Fiscal Year. Branches share
  one sequence.
- the name format is fixed: `ABBR-CODE-000001-FY` (e.g. `GEPL-NOC-000001-82/83`).
- any type NOT in the table gets **no** auto number — the user types one.
- typed duplicates are always rejected (no policy choice).

If every rule is deleted or disabled tomorrow, this is what the system falls back
to — nothing breaks.

### Level 2 — Numbering Configuration rules (configurable)
A rule with **✅ Auto-fill Document No.** takes over for the documents it matches:
you control **when** it fills (conditions), **what scope** it counts by (segments),
**which field** it writes, and **what happens on duplicates**.

**Precedence for the number:**
1. **User typed a value** → always kept (manual override), only duplicate-checked.
2. **A matching Auto-fill rule** → the rule decides. Its Document No. conditions can
   also *restrict* numbering — a matching Auto-fill rule is **authoritative**, the
   built-in list is not consulted.
3. **No such rule** → the built-in defaults above.

---

## 3. Numbering Configuration — the form

Awesome bar → **New Numbering Configuration**.

| Field | Meaning |
|---|---|
| **Document Type** | Which doctype this rule applies to. Fills the field pickers below. |
| **Company** | Optional — blank = all companies. Setting it *scopes* the rule to one company. |
| **Branch** | Optional — blank = all branches. ⚠️ To count *per branch*, use the **Branch Abbr segment**, not this. Setting a Branch here *restricts* the rule to that branch. |
| **Enabled** | Turn the rule on/off. |
| **Auto-fill Document No.** | The switch that makes the rule generate the Document No. (not just the name). |
| **Document No. field** | *(shown when Auto-fill is on)* Which field the number is written into. Default `custom_document_no`; type another field name if a doctype stores it differently. |
| **On Duplicate Document No.** | *(shown when Auto-fill is on)* What happens when a **manually-typed** number is already used: **Throw Error** (default — save rejected with a next-number hint) or **Use Next Available Number** (silently bumped, you're alerted). Auto numbers never duplicate either way. |
| **Voucher No. Conditions** | When the rule builds the **name** (field + value; ALL must match). |
| **Document No. Conditions** | *(shown when Auto-fill is on)* When to **auto-fill the number** — a separate list with operators. Empty = number every doc the rule names. |
| **Segments** | The ordered building blocks of the number (drag to reorder). |
| **Separator** | Joins segments, e.g. `-` → `GEPL-an-RC-000104-82/83`. |
| **Target Field** | Where the built name is stored (`custom_name` or `custom_branch_name`). |
| **Live Preview** | Shows what the number would look like as you edit. Use the **Test** button to try it against a real document. |

---

## 4. Segments — the building blocks

| Segment | Produces | Notes |
|---|---|---|
| **Company Abbr** | `GEPL` | the company's abbreviation |
| **Branch Abbr** | `an` | the branch's `custom_abbr` (only appears if the branch has one) |
| **Fiscal Year** | `82/83` | from the document's date |
| **Fetch from Link** | `RC` | a field read off a linked record (e.g. the type's code) |
| **Static Text** | any fixed text | |
| **Document Field** | a field's value | e.g. `custom_document_no` — the counter's slot in the name |
| **Number** | the auto counter | an alternative to a Document Field for the number |
| **Normal / Return Code** | one text normally, another on a return | |

**Digits** zero-pads a number (e.g. `6` → `000104`). **Attach** glues a segment onto
the previous one with no separator (e.g. number `104` + Document Word `A` → `104A`).

> **To auto-fill, a rule needs a number position** — either a **Number** segment or a
> **Document Field** pointing at the **Document No. field** — so there's a slot to count.

---

## 5. The one concept that explains it all: **scope**

The counter is keyed by **every non-number segment**. Whatever you put *before* the
number decides what restarts the count:

- Segments `[Company Abbr] [Branch Abbr] [code] [Number] [Fiscal Year]` → the number
  counts **per company + branch + code + year**. Each branch gets its own `1, 2, 3…`.
- Drop **Branch Abbr** → the count is **company-wide**.

That's it. Add a dimension to the prefix → the count splits along it.

**The number follows the document.** If a *draft* is edited onto a different series
— branch `an` → `kt`, or its type changed to one owned by another rule — it is
**renumbered into the new series on save**, and the old number is given back to its
series if it was the last one drawn. Submitted documents never change.

---

## 6. Conditions & operators — the "if this then this"

**Voucher No. Conditions** decide when the *name* is built (Equals only).
**Document No. Conditions** decide when the *number* is auto-filled, and support operators:

| Operator | Use it for |
|---|---|
| **Equals** / **Not Equals** | one exact value |
| **In** / **Not In** | a **list** in one row: `Bank Entry, Party Journal, Debit Note` |
| **Is Set** / **Is Not Set** | "this field must be filled" (a `0`/unchecked/blank counts as *not set*) |

The **Field** is type-able: pick a suggestion or type any field name (doctypes differ).
Conditions AND together — all must match.

**The form reacts live.** The preview watches every field your rules' conditions and
segments read — set the last missing condition field and the number appears; break a
condition and it clears. (The watch list is derived from the rules automatically.)

---

## 7. Worked example — receipts numbered per branch

> Number each branch's Bank Customers Receipts independently, and only when a branch is set.

1. **Document Type** = `Payment Entry`, **Company** = *(your company)*, **Branch** = *(blank)*
2. ✅ **Auto-fill Document No.**, **Document No. field** = `custom_document_no`
3. **Voucher No. Conditions:** `custom_p_type` = `Bank Customers Receipt`
4. **Document No. Conditions:** `custom_branch` **Is Set**
5. **Segments:** `Company Abbr` · `Branch Abbr` · `Fetch from Link`(field `custom_p_type`, fetch `data_hrcj`) · `Document Field`(`custom_document_no`, Digits 6) · `Fiscal Year`
6. **Separator** `-`, **Target Field** `custom_name`

→ Branch `an` gets `GEPL-an-RC-000001-82/83`, `000002`…; a different branch restarts at `1`;
a receipt with no branch is named but **not** auto-numbered (the user types a number —
the field is mandatory).

---

## 8. Common recipes

| Goal | How |
|---|---|
| **Per-branch numbering** | Add a **Branch Abbr** segment |
| **One type list, one rule** | Document No. Condition `custom_p_type` **In** `A, B, C` |
| **Only number some docs** | Put the restriction in **Document No. Conditions** (e.g. `custom_branch Is Set`) |
| **Custom format for one customer** | Voucher No. Condition `customer` = `<customer ID>` (see gotcha #1) |
| **Number into a differently-named field** | Set **Document No. field** to that field |
| **Add a letter suffix** | Number + a `Document Field: custom_document_word` with **Attach** on |
| **Forgiving duplicates** | **On Duplicate Document No.** = `Use Next Available Number` |

---

## 9. Manual override, duplicates & feedback

- **Type a number** in Document No. → it becomes yours (kept, only checked for
  uniqueness). **Clear the field** → back to auto.
- The grey hint under the field tells you what's happening:
  - *"Auto — assigned on save (preview: 104)."* → it will be numbered for you.
  - *"Manually entered. Clear the field to auto-number."* → you own it.
  - *"Set Type, Company and Date to auto-number, or type a number."* → something's missing.
- **Instant duplicate warning:** type a taken number and within half a second an
  orange alert appears — *"Document No. 5 is already used by GEPL-PAYREC-82/83-00009.
  Next available is 10."* — before you even save.
- **At save**, a typed duplicate follows the rule's **On Duplicate** policy:
  - **Throw Error** (default): *"Document No. 13 is already used by … Next available
    number is 14."* → type the suggested number, or clear the field for auto.
  - **Use Next Available Number**: the save succeeds with the next free number and an
    orange alert tells you what happened.
- **Live sync between users:** when someone else consumes a number, other open forms'
  previews refresh automatically over the realtime socket — two screens don't sit on
  the same preview. (The save itself was always collision-free; this keeps previews honest.)

---

## 10. Duplicating, amending, editing

| Action | What the number does |
|---|---|
| **Duplicate** a document | The copied number is **blanked immediately** on the new form — it belongs to the original. A fresh preview/number is drawn for the new doc. |
| **Amend** a cancelled document | **Keeps** the original's number (the voucher name gets the `-1`/`-2` suffix). |
| **Edit a draft** onto another series (branch/type/date change) | **Renumbered on save** into the new series; the old number returns to its series if it was the last drawn. |
| **Edit a draft's** other fields (same series) | Number stays. |
| **Delete** the doc holding the **last** number of a series | The number is freed — the next document reuses it. Mid-series deletes leave a gap (by design). |
| **Submit** | Number and name freeze permanently. |

---

## 11. Data Import & API

| Import row / API payload | Result |
|---|---|
| **No** Document No. | Auto-numbered in sequence, like the desk |
| **Has** a number (legacy data) | **Kept exactly**, marked as manual, duplicate-checked |
| Blank row after a numbered one | Continues **past** the imported numbers |
| **Duplicate** number in the file | That **row fails visibly** in the import log with the next-number hint — imported data is never silently renumbered |
| Doesn't satisfy the rule's conditions | Left blank (fails the mandatory check → visible row error, type a number in the file) |

Rule of thumb: **desk previews are disposable, payload values are intentional.**
Whatever a file or API sends is treated as real data.

---

## 12. Gotchas

1. **Link fields store the ID, not the label.** A condition on Customer/Supplier/Branch
   must use the **ID** (`NGK-CUS-00098`), not the display name (`Muskan Kirana Pasal`).
2. **Most specific rule wins.** Company + Branch + each Voucher condition each add
   specificity. Keep **one** rule per case to avoid ambiguity.
3. **Auto-fill needs a number position** (a Number segment or a Document Field on the
   Document No. field), or there's nothing to count.
4. **Branch Abbr needs the branch's abbreviation set** (`Branch → custom_abbr`), else
   that segment is empty and skipped.
5. **A matching Auto-fill rule is authoritative** — it can turn numbering *off* for docs
   its Document No. conditions exclude, even shipped types. Scope the Voucher conditions
   so a rule only owns the documents you intend.
6. **After changing app code**, users need one hard refresh (Ctrl+Shift+R) to load the
   new form JavaScript. The *server* numbering is always current — only the on-screen
   preview can lag behind a stale browser cache.

---

## 13. Troubleshooting

| Symptom | Check |
|---|---|
| Number doesn't preview while typing | Are ALL the rule's Document No. Conditions met? Watch the grey hint. Hard-refresh once if the app was updated. |
| Number never fills on save | Is the type in the built-in list, or covered by an enabled Auto-fill rule whose conditions pass? Run the console check below. |
| "Duplicate Document Number" on save | Someone holds that number. Use the suggested next number, clear the field for auto, or set the rule's On Duplicate policy to auto-bump. |
| Wrong series / doesn't restart per branch | The scope is the segments *before* the number — add/remove **Branch Abbr** there. The **Branch field on the rule** filters which docs match; it does not split the count. |
| Rule doesn't match at all | Link-field conditions need IDs (gotcha #1); check Company on the rule vs the doc. |

Inspect any document's numbering decision from the console:

```bash
bench --site <site> console
```
```python
from avinashgroup_app.custom_code.Override import naming_series as ns
d = frappe.new_doc("Payment Entry")
d.company = "…"; d.posting_date = "2026-07-06"
d.payment_type = "Pay"; d.custom_p_type = "NOC Payment"; d.custom_branch = "…"

ns._match_numbering_rule(d)       # which rule wins (None -> built-in fallback)
ns._docno_scope(d)                # the scope/series it resolves to (None -> not numbered)
ns.peek_next_document_no(d)       # the next number (no side effect)
```

Run the automated suite (51 tests: rules, operators, concurrency, imports, fuzz):

```bash
bench --site <site> run-tests --module avinashgroup_app.test_document_numbering \
  --skip-before-tests --skip-test-records
```

---

*Engine: `avinashgroup_app/custom_code/Override/naming_series.py`. Rules doctype:
`Numbering Configuration` (+ `Numbering Condition`, `Numbering Document No Condition`,
`Numbering Segment`). Tests: `avinashgroup_app/test_document_numbering.py`.
Developer guide: [document_numbering_developer.md](document_numbering_developer.md).*
