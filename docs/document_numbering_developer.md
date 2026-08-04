# Document Numbering — Developer Guide

Architecture, lifecycle, concurrency model, caching, client design, extension
points and testing for the numbering engine.

> User/admin documentation: [document_numbering.md](document_numbering.md).

**Code map**

| Piece | Path |
|---|---|
| Engine (everything server-side) | `avinashgroup_app/custom_code/Override/naming_series.py` |
| Rules doctype controller | `avinash_group_app/doctype/numbering_configuration/numbering_configuration.py` (+ `.js`, `.json`) |
| Child doctypes | `numbering_condition`, `numbering_document_no_condition`, `numbering_segment` |
| Client (preview, alerts, realtime) | `public/js/auto_update_document_no.js` (versioned in `hooks.py` `app_include_js`) |
| Manual-flag fields patch | `patches/add_document_no_manual_flag.py` |
| Unique-index patch | `patches/add_unique_custom_name_index.py` |
| Test suite | `avinashgroup_app/test_document_numbering.py` |

---

## 1. The model

Every audited document carries **two generated values**:

1. **Document number** — an integer counter in a *number field* (default
   `custom_document_no`, per-rule configurable via `document_no_field`). This is
   the thing that is drawn, previewed, deduplicated and reverted.
2. **Voucher name** — a formatted string in a *target field* (`custom_name` or
   `custom_branch_name`) assembled from rule segments (or the legacy hardcoded
   format), with the document number embedded at its number position.

Ownership of each value per doctype:

- **Rule engine** (`Numbering Configuration` exists & matches): name built by
  `_build_from_segments` into the rule's `target_field`; number drawn iff the
  rule has `auto_document_no` and its Document-No conditions pass
  (`_docno_eligible`). A matching auto-fill rule is **authoritative** — the
  hardcoded fallback is not consulted.
- **Legacy fallback** (no matching rule): number gated by `AUTO_NUMBER_CONFIG`
  (doctype → type-field → allowed types); name built by `set_custom_name_field`
  as `ABBR-CODE-{number:06d}-FY`; scope = company|code|fiscal-year.

`_engine_owns_field(doc, fieldname)` decides whether the legacy name writer must
back off because a rule targets that field.

---

## 2. Save lifecycle (hook order)

Registered in `hooks.py` `doc_events`:

```
validate     : handle_validate      (audited doctypes: PE/JE/PI/PR)
               apply_engine_numbering (wildcard "*", runs after)
before_save  : handle_before_save   (audited) + wildcard
after_delete : handle_after_delete / revert_engine_series_on_delete
```

Both `handle_validate` and `handle_before_save` run the same sequence — number
first, then name, then guards:

```
apply_document_no(doc)        # draw / keep / redraw the NUMBER
set_custom_name_field(doc)    # legacy name (backs off if engine owns field)
validate_document_no(doc)     # numeric sanity
validate_custom_name_unique(doc)
```

`apply_engine_numbering` (wildcard) additionally calls `set_custom_branch_name`
— the rule-driven name builder — for **every** doctype, so any doctype with a
number field can be rule-numbered without being listed anywhere.

`apply_document_no` is **idempotent within one save** via
`doc.flags._docno_assigned`; running it from three hooks costs one draw.

### 2.1 `apply_document_no` decision tree

```
not new?  ->  _redraw_docno_if_scope_changed(doc)   (drafts follow their scope; §5)
number field invalid/non-column?  ->  no-op (fail soft, §9)
MANUAL value? (_is_manual_document_no, §4)
    _keep_counter_above_manual()        # tabSeries upsert = SERIALIZATION POINT
    _document_no_taken(for_update=True) # locking read, sees latest commit (§3)
    taken?  policy 'Use Next Available' (and not import) -> bump + msgprint
            else -> frappe.throw (friendly, with next-number hint)
    kept value -> persist <field>_manual = 1
amendment with a number?  ->  keep (name gets -1/-2 suffix)
scope is None?  ->  desk form save: blank stale preview; else leave value; retry later hook
else  ->  doc.set(field, _draw_next_document_no(doc, scope)); flag manual=0
finally -> _notify_docno_drawn (realtime, after_commit)
```

---

## 3. Concurrency model — why it cannot collide

MariaDB runs **REPEATABLE READ**: a plain `SELECT` inside a transaction reads a
snapshot taken at the transaction's first read and **cannot see a peer's commit**
that happened after. Any duplicate check built on plain reads is therefore
race-prone by construction. The engine layers three mechanisms:

1. **Serialization point.** Both the auto draw (`_draw_next_document_no`) and the
   manual path (`_keep_counter_above_manual`) execute
   ```sql
   INSERT INTO `tabSeries` (name, current) VALUES (%(key)s, %(n)s)
   ON DUPLICATE KEY UPDATE current = GREATEST(...)
   ```
   on the scope's row (`docno:<doctype>|<scope key>`). The row X-lock is held to
   commit, so **same-scope savers queue single-file**. A single statement is used
   deliberately — the earlier `SELECT … FOR UPDATE` + `UPDATE` two-step deadlocked
   against core `getseries` (doc-name series).

2. **Atomic draw.** For auto numbers, `GREATEST(current + 1, floor)` with
   `floor = MAX(CAST(number AS UNSIGNED)) + 1` over the scope's LIKE pattern.
   `current + 1` under the row lock guarantees distinct numbers to concurrent
   savers; the floor continues an existing series, jumps past manual numbers, and
   self-heals a deleted/reset counter from data.

3. **Locking-read duplicate check.** After the serialization point, the manual
   path re-checks with `_document_no_taken(..., for_update=True)` — a
   `SELECT … FOR UPDATE`, which reads **latest-committed** rows regardless of the
   snapshot. Because the peer already committed (step 1 forced the wait), the
   duplicate is seen and resolved per policy. Two users typing the *same free
   number* concurrently: first keeps it, second gets bumped (or a friendly throw)
   — never two saves with one number.

**Backstop:** `custom_name` carries a **DB unique index** on PE/JE/PI/PR
(`add_unique_custom_name_index` patch — NULLs `''` first, skips if legacy dups
exist). Even a path that evades all Python checks becomes an IntegrityError, not
silent data corruption. Corollary: blank names must be `None`, never `''`
(multiple NULLs are legal under a unique index; two `''` are not).

**Uniqueness SCOPE (`_number_scope_filters`).** A voucher number is unique **per
company**, not group-wide: the old ERPs numbered each company independently, so
NGI's `RTN/000001` and NGK's `RTN/000001` are different documents and both must be
storable. `_other_doc_with_number` / `_validate_unique_number` therefore filter by
`company`.

Exception — a target field that carries a **DB unique index** (`custom_name` on
PE/JE/PI/PR) stays group-wide: the database enforces group-wide uniqueness
regardless, so scoping the Python check below the constraint would only trade a
readable error for an IntegrityError. Doctypes without a `company` field also stay
group-wide. `custom_branch_name` has no unique index, so Sales Invoice is the
field this scope actually governs.

Not yet DB-enforced: `custom_branch_name` has only a plain lookup index, so the
per-company rule rests on the Python check alone and two simultaneous saves can
still slip through. The durable shape is a composite `UNIQUE (company,
custom_branch_name)`, created in a patch and re-asserted from the `after_migrate`
hook — frappe's schema sync drops a unique index whose leading column's field is
not itself marked `unique` (`frappe/database/schema.py`), which is why ERPNext
re-creates `Bin`'s `unique_item_warehouse` in `on_doctype_update()`.

**Delete/revert:** `_revert_document_no_series` steps the counter back **only**
when the deleted doc held the scope's highest number, was auto-drawn (stored
manual flag = 0), wasn't an amendment, and its stored number still parses into
the *current* scope. Mid-series deletes leave gaps by design.

CAST-as-UNSIGNED appears in every max/duplicate query because the number column
is `Data` (varchar) on some doctypes — lexicographic MAX ("9" > "50") would
compute wrong floors.

---

## 4. Manual vs auto — provenance semantics

The hidden Check field `<number_field>_manual` (created by
`add_document_no_manual_flag` patch, `no_copy=1`) records ownership. The
classifier `_is_manual_document_no`:

| State | Verdict |
|---|---|
| flag field exists and = 1 | **manual** |
| field empty | auto |
| no flag field on the doctype | **manual** (can't distinguish → never overwrite) |
| **stored** doc, flag = 0 | auto (the flag is authoritative once saved — delete-revert relies on this) |
| **new** doc, value present, flag 0, **desk form save** | auto — the value is our own preview fill; the server draw overwrites it |
| **new** doc, value present, flag 0, **import/REST/script** | **manual** — payload values are intentional data (legacy imports!) |

"Desk form save" = `frappe.form_dict.cmd == "frappe.desk.form.save.savedocs"` and
not `frappe.flags.in_import` (`_is_desk_form_save`). This distinction is what
makes imports keep file numbers while desk previews stay disposable. When a
payload value is kept, the flag is persisted to 1 so the stored doc classifies
consistently forever.

Import extras: the duplicate policy's bump is **disabled** under
`frappe.flags.in_import` — a duplicate row must fail visibly in the import log,
never be silently renumbered.

The **voucher number** (`set_custom_branch_name`) follows the same rule, without
needing the flag: a value arriving from outside — import row, REST, script — is
stored **as given** and never re-derived, and a duplicate within its scope throws.
It used to be cleared and replaced with a freshly generated number whenever the
value was already held by another document, which silently discarded 417 imported
NGK return numbers on 2026-08-03 (their legacy `RTN/…` numbers collided with NGI's
across companies, and the import log showed success).

---

## 5. Scope — the series identity

`_docno_scope(doc)` → `{key, pattern, field, number_field}` or `None` (= not
auto-numbered):

- **Rule-derived** (`_rule_docno_scope`): resolve every segment; the number
  position (a `Number` segment, or the `Document Field` referencing the rule's
  `document_no_field`) becomes `%` in `pattern` and is *excluded* from `key`.
  Everything else — company abbr, branch abbr, fetched codes, static text —
  *is* the key: **whatever prefixes the number splits the count**. A
  non-default number field is appended to the key so two rules sharing a prefix
  but writing different fields never share a counter. `custom_document_word` is
  skipped (it's the glued letter tail, covered by the wildcard).
- **Legacy fallback**: `key = ABBR|CODE|FY`, `pattern = ABBR-CODE-%...` matched
  on `custom_name`.

Series key in `tabSeries`: `docno:<doctype>|<key>`. `pattern` is matched against
`field` (the rule's target) by `_current_max_document_no` and
`_document_no_taken`, so per-branch scopes only ever see their branch's rows.

**Drafts follow their scope** (`_redraw_docno_if_scope_changed`): on update of a
docstatus-0 doc, compare `_docno_scope(get_doc_before_save())` vs now; if the key
moved, revert the old number (`_revert_series_if_last`) and draw from the new
series. Skipped for manual numbers, amendments, submitted docs, and when the new
scope is None. The **name**-level counterpart is `_renumber_if_scope_changed`
inside `set_custom_branch_name`.

---

## 6. Name building

`_build_from_segments(doc, rule, commit_series=True)`:

- resolves segments in order (`_resolve_segments`), joins with the separator;
  `join_previous` ("Attach") glues a part onto the previous chunk with no
  separator (`_join_parts`);
- the number position is replaced by `getseries(key)` (commit) or a peek
  (preview/Test button);
- **pass-through rules** (no number position) just join resolved values — used
  for migrated legacy numbers (e.g. copy `narration`); empty result returns
  `None` so the next matching rule gets a chance;
- **legacy cut-over**: with `legacy_upto` set, docs dated on/before it copy the
  number from `legacy_source_field` instead of generating;
- amendments get the `-1`/`-2` suffix appended (`get_amendment_suffix`).

Rule matching (`_matching_numbering_rules`) sorts most-specific-first (company,
branch, condition count); `_rule_matches` requires company/branch (if set on the
rule) plus ALL Voucher conditions. Document-No condition operators live in
`_condition_matches` (Equals / Not Equals / In / Not In / Is Set / Is Not Set —
"set" treats `""`, `"0"`, `0`, None as unset).

---

## 7. Caching

Three layers, all invalidated by `clear_numbering_rules_cache()` (called from
the rules controller's `on_update`/`on_trash`):

1. `frappe.local._numbering_rules_cache` / `_numbering_doctypes_cache` — per
   request.
2. Redis: `numbering_rules::<doctype>` — fully-assembled rule dicts (rules +
   both condition tables + segments in 3 queries, no N+1);
   `numbering_configured_doctypes` — the gate that lets non-configured doctypes
   exit the wildcard hook cheaply.
3. The DB.

**Deploy window guard:** `_build_numbering_rules` probes
`frappe.db.has_column("Numbering Configuration", "duplicate_action")` before
selecting it, so code that ships ahead of `bench migrate` cannot 1054 every
save. Follow the pattern when adding rule columns.

**Anything that changes rules via raw SQL must call
`clear_numbering_rules_cache()` itself** — the test quarantine does.

---

## 8. Client (`auto_update_document_no.js`)

New-doc form machinery for the four audited doctypes (`AUTO_NUMBER_CONFIG`
mirror at the top of the file):

- **Preview**: debounced (400 ms) `get_next_custom_document_no` call; monotonic
  token discards stale responses; value-compare (`frm._auto_docno_value`)
  distinguishes our own `set_value` from a user edit; a focused input is never
  written over (`docno_input_focused`).
- **Manual flag management**: user types → flag 1 + hint; user clears → flag 0 +
  re-preview.
- **Dynamic watch fields**: `get_docno_watch_fields(doctype)` returns every field
  any enabled rule's conditions/segments read (+ legacy scope fields); the form
  binds a preview-refresh handler per field at `onload_post_render`. Static
  handler lists can't know rule-configured fields — without this, filling a
  condition field never refreshes the preview.
- **Duplicate warning while typing**: debounced
  `check_document_no_availability` → orange alert + field description with
  holder and next free number.
- **Duplicate (copy) hygiene**: a new form carrying a value with flag 0 (the
  flag is `no_copy`) is a copied number → blanked on load; amendments excluded.
- **Decline clearing**: preview returns `None` while we own a value → clear it
  (a broken condition must not leave a stale number on screen).
- **Realtime**: server publishes `docno_assigned` (payload: doctype only) to the
  **doctype room** `after_commit`; the client `doctype_subscribe`s on new forms
  and re-fetches, guarded to the on-route form only. Saved drafts get **no**
  live client writes — the server redraw at save is authoritative (writing peek
  values into stored drafts would renumber them wrongly).

**Versioning:** the file is served via `app_include_js` with a `?v=` query
string — bump it in `hooks.py` on every change, `bench build`, and users
hard-refresh once. The server never depends on the client being current.

### 8.1 Whitelisted endpoints

| Endpoint | Purpose | Guards |
|---|---|---|
| `get_next_custom_document_no(doc)` | non-reserving preview | never raises; scalars-only payload; **doc-level** read permission (`_client_payload_doc` — role-only checks would let a user probe other branches/companies) |
| `check_document_no_availability(doc)` | typing-time duplicate info `{taken, used_by, next}` | same, falls back to `custom_document_no` for non-default number fields |
| `get_docno_watch_fields(doctype)` | preview trigger list | role read; meta-filtered |
| `NumberingConfiguration.test_number(reference)` | rule Test button | doc method, no counter consumed |

---

## 9. Robustness rules (keep these invariants)

- **Rule-configured identifiers are untrusted.** Anything formatted into SQL as a
  column name goes through `_safe_col` (`^[A-Za-z0-9_]+$`) — a `%` in a field
  name breaks pymysql parameter binding; backtick-stripping alone is not enough.
  Non-column fieldtypes (Table/Section/…) are rejected via
  `frappe.model.no_value_fields + table_fields` checks. Misconfiguration must
  **fail soft** (skip the rule / fall back), never brick saves.
- **Whitelisted payloads**: parse defensively, strip lists/dicts, `try/except`
  to `None` — the form treats `None` as "no info", never as an error.
- **Realtime is best-effort** and always `after_commit` (a rolled-back save
  consumed nothing) — an outage must never block a save.
- **msgprint in hooks**: fine for desk, but anything running under imports/jobs
  must either be silenced or (like the duplicate bump) disabled there.
- **Blank generated names are `None`**, never `''` (unique index).

---

## 10. Extending

**Rule-driven numbering for a new doctype** needs no code: create the number
field (+ optionally `<field>_manual` Check, hidden, `no_copy=1`) and a rule with
a number position. The wildcard hook covers every doctype.

**A new shipped default**: add the doctype to `AUTO_NUMBER_CONFIG` in
`naming_series.py` **and** its mirror in `auto_update_document_no.js`; create
the custom fields (number + manual flag; add the number field to the manual-flag
patch's doctype list); decide whether the field is mandatory.

**A new segment type**: extend `_resolve_segment` (server), the
`segment_type` Select options in `numbering_segment.json`, and
`validate_segments` in the controller. Remember `_rule_docno_scope` — decide
whether the segment is part of the series key (default: yes, any non-number
segment splits the count).

**A new condition operator**: `_condition_matches` (server) +
`set_smart_value_options` in `numbering_configuration.js` (client value picker).

**A new rule column**: doctype JSON + `_build_numbering_rules` field list
(behind a `has_column` probe if it gates behavior) + `_rule_dict_from_config`
(the Test-button path builds rules from unsaved docs) + cache bump via any rule
save.

---

## 11. Testing

`avinashgroup_app/test_document_numbering.py` — 51 tests: scope derivation,
eligibility, operators, per-branch isolation, manual/duplicate/amendment paths,
imports, delete-revert, threaded concurrency, a seeded randomized fuzz
(`test_50`), a declarative spec matrix (`test_60/61`), and regression tests for
every bug found in review (races, import overwrite, draft redraw…).

```bash
bench --site <site> run-tests --module avinashgroup_app.test_document_numbering \
  --skip-before-tests --skip-test-records
```

Design rules the suite enforces (keep them when adding tests):

- **Non-polluting**: `setUp` snapshots every `docno:%` counter and branch abbr
  and restores them in cleanup — app hooks commit mid-save, so FrappeTestCase's
  rollback does NOT cover us. Real inserts register explicit force-delete
  cleanups.
- **Rule quarantine**: site-configured rules are authoritative and would flip
  outcomes, so `setUp` disables all enabled rules for the test's duration and
  restores after. Crash-safe: the cleanup is registered *before* the mutation
  and the disabled list is persisted as the global `numbering_test_quarantine`,
  healed by the next run's `setUpClass` if a run was killed.
- **Fixture-relative assertions**: tests peek the promise first and assert the
  assignment matches it, rather than hardcoding absolute numbers; temp rules use
  random tag segments so their series never touch production counters.
- `_temp_rule(...)` builds and auto-drops rules; `_pe/_je/_insert_je` build
  documents; concurrency tests open their own connections and commit.

Manual console debugging:

```python
from avinashgroup_app.custom_code.Override import naming_series as ns
ns._match_numbering_rule(d)   # winning rule (None -> fallback)
ns._docno_scope(d)            # {key, pattern, field, number_field} or None
ns.peek_next_document_no(d)   # promise, no side effect
```

---

## 12. Deployment checklist

1. `git pull` the branch on the server.
2. **`bench migrate` first** — creates new rule columns, manual-flag fields and
   the PI/PR unique indexes; the code's `has_column` probe covers the window,
   but don't rely on it.
3. `bench build` (client JS) and `bench restart`.
4. Users: one hard refresh (Ctrl+Shift+R) for the new form JS (`?v=` bump).
5. Rules are **data**, not code — they are configured per site, not shipped.
   (Seed scripts live in `avinashgroup_app/scripts/` if a site needs the
   standard set.)
6. Sanity: run the test suite on a staging site; check
   `Numbering Configuration` list loads and a known form previews.
