# Numbering Configuration — data-driven document numbering

A generic, rule-driven way to give any document a custom number (e.g. a
branch-wise Sales Invoice number) without code changes. Rules are configured in
the **Numbering Configuration** doctype; the generated number is stored in a
field on the document (by default `custom_branch_name`) — the document's own
`name`/ID is **not** changed, so existing numbering keeps working.

Examples of numbers this can produce:

```
NGK/KTM/SI/82-83/000001     company / branch / type / fiscal year / number
NGK/KTM/SR/82-83/000001     same, for a return (via a condition)
PE-RCP-82/83-000001         Payment Entry (Receive) — own series
PE-PAY-82/83-000001         Payment Entry (Pay) — separate series
inv-82/83-000001            simple: code + fiscal year + number
INV-000001-82/83            number can sit anywhere in the order
```

---

## 1. How a rule works

A **Numbering Configuration** has three parts:

1. **Scope** — Document Type (required) + optional Company and Branch.
   Blank Company/Branch = applies to all.
2. **Conditions** (*Apply only when…*) — rows of `field = value`; **all** must
   match the document. This is how returns (`is_return = 1`), payment types
   (`payment_type = Receive`), or any other field-based variant get their own
   series. A rule with no conditions is a default/base rule.
3. **Date window** (*Applies during…*) — optional **Valid From / Valid Upto**
   dates compared against the document's date (Posting/Transaction Date, or any
   date field you pick). Use this for **cut-over dates**: one rule valid up to a
   date (e.g. number read from a document field like remarks), another valid
   from the next day with the new format. A dated rule beats an equally-scoped
   undated one.
4. **Segments** — an ordered table that *builds* the number. Each row is one of:

   | Segment type | What it produces | Example |
   |---|---|---|
   | Static Text | fixed text | `INV`, `SI`, `KTM` |
   | Normal / Return Code | one code for normal docs, another when `is_return = 1` | `SI` / `SR` |
   | Document Field | the value of a field on the document | `custom_vehicle_no` |
   | Fetch from Link | follow a Link field, read a field on the linked record | `custom_branch → Branch.branch` |
   | Company Abbr | the document company's `abbr` | `NGK` |
   | Branch Abbr | the document branch's **Branch Abbr** (set on the Branch master) | `KTM` |
   | Fiscal Year | fiscal year of the document's posting/transaction date | `82-83` |
   | Number | the running counter (exactly one required) | `000001` |

   Segments are joined with the rule's **Separator** (`/`, `-`, …). Empty
   segments are skipped. When the separator is `/`, the fiscal year's own `/`
   is shown as `-` so it can't be confused with a separator.

**Which rule wins?** When several enabled rules match a document, the **most
specific** one wins: +1 for Company, +1 for Branch, +1 per condition.

**Counters** are per unique segment combination (the series key = all non-Number
segments joined). So SI vs SR, Receive vs Pay, each branch, and each fiscal year
all count independently. Backdated documents use *their own date's* fiscal year
and therefore continue that year's series.

---

## 2. Setting up — the form helps you

- **Live Preview** at the bottom shows the number as you build it, and lists the
  conditions in plain language.
- **Field dropdowns** — condition fields and segment fields are picked from the
  chosen Document Type (no typing fieldnames). Condition *values* are smart:
  checkboxes offer 1/0, Select fields offer their own options.
- **Branch list** filters by the chosen Company.
- **Store Number In** lists only text fields of the doctype and defaults to
  `custom_branch_name`.
- **Test on a Document** (button) — pick a real document and see the exact
  number the rule would produce **without consuming the counter**, plus whether
  the rule would match it at all.
- **Apply to Other Companies** (button) — clone the rule for many companies in
  one go.

### Recipe: branch-wise Sales Invoice + Return — ONE rule

Document Type `Sales Invoice`, Company `NGK…` (Branch optional), **no
conditions**, segments:
*Company Abbr, Branch Abbr, Normal / Return Code (`SI` / `SR`), Fiscal Year,
Number*; separator `/`.

→ normal invoices get `NGK/KTM/SI/82-83/000001…`, returns get
`NGK/KTM/SR/82-83/000001…` — separate counters, one rule.

(Set each Branch's **Branch Abbr** on the Branch master, e.g. `KTM`.)

### Recipe: one rule for ALL branches

Use the **Branch Abbr** segment and leave the rule's Branch blank. Every branch
then gets its own code and its own counter from a single rule. (For codes stored
elsewhere, **Fetch from Link** does the same for any field on any linked master.)

### Recipe: Payment Entry — Receive vs Pay

Two rules on `Payment Entry`, conditions `payment_type = Receive` / `= Pay`,
segments `Static PE, Static RCP|PAY, Fiscal Year, Number`, separator `-`.

---

## 3. Behaviour guarantees

- **Nothing changes until you add a rule.** No matching rule → the target field
  falls back to the document's normal name.
- **Legacy migration**: the old hardcoded Grishma `BRANCH_CODE_CONFIG` was
  replaced by 9 seeded rules (`scripts/seed_numbering_rules.py`) with identical
  formats and series keys — sequences continue unchanged.
- **Generate once** — a document's number is never regenerated on later edits.
- **Delete rollback** — deleting the document holding the *last* number of a
  series steps the counter back (mid-series gaps stay, like core Frappe).
- **Backdating** — fiscal year and counter come from the document's own date.

---

## 4. Technical notes

- Doctypes: `Numbering Configuration` (+ child tables `Numbering Condition`,
  `Numbering Segment`) under `avinash_group_app/doctype/`.
- Engine: `custom_code/Override/naming_series.py` —
  `_match_numbering_rule` (scope + conditions, most-specific),
  `_build_from_segments` (segment resolution + `getseries` counter; the Number
  segment may sit anywhere), `_revert_engine_series` (rollback),
  all invoked from the existing `set_custom_branch_name` /
  `revert_series_on_delete` hooks (wired via `AuditEventMapper` — no hooks.py
  change).
- Preview/test uses `commit_series=False`, which *peeks* the next counter value
  without incrementing.
- To number a **new doctype**: make sure it has a text field to store the number
  (e.g. `custom_branch_name`) and that the doctype is in `AuditBase.doctypes`;
  then just add rules. No code changes.

---

## 5. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Number field just shows the document name | No enabled rule matches (check scope + conditions with **Test on a Document**). |
| A segment is missing from the number | Its source was empty on the document (empty segments are skipped). |
| "Add exactly one Number segment" | Every rule needs one (and only one) Number segment. |
| Fiscal year segment empty | No Fiscal Year record covers the document's date. |
| Wrong rule fires | A more specific rule matches — check Company/Branch/conditions; most specific wins. |
