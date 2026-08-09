# Part VI — Legacy, lessons, and playbooks

---

# Chapter 12. Importing the old software's history

Two importers, written a day apart, and between them they contain most of what
is worth knowing about moving data from a dead system into a live one.

## 12.1 Why the annexure import had to exist

The Materialized Report draws its rows from **CBMS Bill**, and a bill is only
ever written when an invoice is submitted through the CBMS hook — which began
at e-billing go-live. Every invoice before that has no bill, so the report was
**empty for 79/80–82/83** no matter what the invoices themselves contained.

The old software had exported those years as *Annexure-7* sheets. So:

> This loads them back, so the report reproduces them **with no change to the
> report itself**.

That framing is the win. Faced with "the report is empty for old years", the
tempting fix is to make the report fall back to Sales Invoice when no bill
exists — a second code path, forever, in a statutory report. Loading the
history into the shape the report already reads keeps the report a single,
verifiable thing.

`legacy_annexure_import/import_legacy_annexure.py`, and the sheets themselves
are **shipped with the importer** (`legacy_annexure_import/sheets/`) so the
import is reproducible on any site rather than depending on a file in
somebody's Downloads folder.

## 12.2 The seven disciplines these importers follow

**1. Dry run by default.**

```python
run(path, company=None, fiscal_year=None, commit=False, limit=None, …)
```

Nothing writes unless `commit=True`. Both importers print a JSON summary —
counts of matched, created, skipped, ambiguous, plus samples — so you inspect
the summary *before* the run that writes.

**2. Idempotent.** An invoice that already has a CBMS Bill is skipped. Print
counts are *added* to existing rows because the counter is total sheets. You
can always run it again.

**3. Know exactly what your join key identifies.** The old number lives in
`custom_branch_name` and is unique only **within a company and a fiscal
year** — the old ERPs numbered each company independently and restarted every
year, so `NGK/000001` exists in both 77/78 and 79/80. The NGI register embeds
both (an `NGI` prefix and a `/82-83` suffix) so its rows resolve; a register
carrying neither does not.

**4. Refuse to guess on ambiguity.**

> Any register number that still matches several invoices is reported under
> `ambiguous_register_rows` and imported for **NONE** of them, rather than
> crediting the sheets to whichever invoice the scan happened to return last.

Importing to the wrong invoice is worse than not importing. A skipped row is a
visible gap; a wrong row is invisible corruption.

**5. Copy verbatim, deliberately, and say so.** The import copies the sheet as
it is, because the goal is to reproduce what the old software recorded — not to
restate it in ERPNext's terms. That is a decision, not laziness, and §12.3 is
its counterweight.

**6. Take each field from the right source, not the nearest one.** "Entered By"
comes from the **invoice's** `custom_created_by`, not from the sheet — the sheet
names the old software's user (`"ASHISH"`), who is not a Frappe user; the audit
field names the clerk. Recorded as a dated decision in the docstring
(2026-08-05).

**7. Rows that fail, fail alone.** A rejected row does not abort the batch —
measured and documented (commit `5c546ae`).

> **The trap that could have reached the tax office.** Imported bills describe
> invoices that were reported to the IRD *years ago by the old software*. If
> they are written with a status other than `Synced`, then
> `retry_failed_cbms_syncs` — the `*/5 * * * *` cron from Chapter 6 — will pick
> them up and **actually send four years of historical bills to the IRD.**
>
> The importer therefore emits an explicit warning in its own result:
>
> ```python
> if unsynced_status != "Synced":
>     result["retry_warning"] = (
>         "Bills written as {0} are picked up by retry_failed_cbms_syncs and WILL be "
>         "sent to the IRD. Disable that job before committing."
>     )
> ```
>
> **When you write records into a table that a background job is watching, you
> have queued work — not stored data.** Before any bulk insert, ask what
> schedulers select from that table and what status values they act on.

## 12.3 Verification is a separate, later step

`verify()` compares every imported CBMS Bill against its own Sales Invoice.
Its docstring is the most honest thing in the codebase:

> The bills carry what the OLD software recorded; the invoices carry what
> ERPNext holds today. Nothing has ever checked the two against each other —
> the import copied the sheet verbatim, by design, so that the report would
> reproduce it. This is where the two stories are held up side by side.
>
> **A mismatch is not automatically an import fault.** An invoice amended after
> the legacy export, a customer renamed since, a differently-rounded discount —
> each shows up here and each means something different. The point is to see
> WHICH field disagrees and on how many rows, then judge.

Note the shape: read-only, per-field mismatch counts, a few examples of each,
a tolerance for floats. It does not "fix" anything, and it does not claim a
mismatch is a bug. **Reconciliation reports inform a human decision; they do
not make it.**

## 12.4 The migration checklist

Before writing an importer:

- [ ] What is the join key, and what does it uniquely identify — globally, or
      only within some scope?
- [ ] What happens to rows that match nothing? To rows that match several?
- [ ] Is it idempotent? What does a second run do?
- [ ] Does it default to a dry run that prints a summary?
- [ ] Which background jobs watch the table I am writing to?
- [ ] For each field: is the source the sheet, or the live record? Why?
- [ ] How will anyone verify this afterwards — and is that a separate tool?
- [ ] Are the source files version-controlled with the importer?

---

# Chapter 13. The rules this app taught

If you read nothing else, read this. Every item cost real debugging time.

## Frappe

**1. Put pipeline logic on `validate`, not `before_save`.**
`before_save` and `before_submit` are mutually exclusive. A document inserted
already-submitted never runs `before_save`. This app was bitten twice, in
unrelated places (Sales Invoice desk saves, device-marked Attendance).

**2. `validate` may run twice — keep it idempotent.**
Save-and-Submit runs the whole pipeline on both passes. Anything that counts,
appends or calls out does not belong there.

**3. Wildcard `"*"` hooks need a cached gate as their first statement.**
Otherwise you tax every save of every document on the site.

**4. `before_request` does not run in background workers.**
Register the same patch in `before_job` if workers execute the patched code.

**5. Scope every fixture by explicit name.**
An unfiltered `Custom Field` fixture exports the whole site and overwrites the
next one.

**6. Guard your config masters with `company_data_to_be_ignored`.**
Otherwise *Delete Transactions* takes your numbering rules and API credentials
with it.

**7. `patch` = once; `after_migrate` = a truth that migrate keeps undoing.**

**8. Changing a fieldtype is a data migration.**
Password → Data leaves the real value in `__Auth` and literal asterisks in the
row, and nothing masks anything afterwards.

**9. `bench execute` cannot reach `_`-prefixed names** (RestrictedPython), and
standalone scripts must run from `sites/`.

**10. Never assign `doc_events` directly here** — it is seeded by
`AuditEventMapper.get_doc_events()`; always merge via `_add_doc_event`.

## Data and concurrency

**11. Lock, then check — never check, then lock.**
And a uniqueness check must be `SELECT … FOR UPDATE`: under `REPEATABLE READ` a
plain `SELECT` cannot see a concurrent commit.

**12. Scope by the fields, not by the string.**
Deriving a series from the *shape* of a number orphans its history the day the
format changes.

**13. When you aggregate a group to "the row that matters", pick the row, then
read all its columns.** Two independent `MIN()`s invent a person who did
nothing at that time.

**14. `no_copy` + "never recalculated" is silent data loss.**
Every mapping path must explicitly restore such fields — the return-VAT bug.

**15. Writing rows into a table a scheduler watches is queueing work.**

**16. A compliance record snapshots facts; it does not hold live links.**
CBMS Bill stores an author's *name*, so the record survives the user.

**17. Framework audit fields are often the wrong "who".**
`owner` was the API user; the clerk was in `custom_created_by`.

## Integrations

**18. Never let an integration block the business transaction.**
Cheap local write inside the transaction → network call after commit, with a
hard timeout → failure enqueues → a bounded, batched cron owns it from there.

**19. Never let a background job take an irreversible action from configuration
it did not verify.** A cron that mass-created bills swept up nine months of
out-of-scope invoices. Irreversible actions must follow deterministically from
an explicit human action.

**20. A visible gap you must fix beats an automatic action you cannot undo.**

**21. Do not normalise away an API's inconsistencies.** `101` means success on
one endpoint and failure on the other. Two explicit sets, with a citation.

**22. An outbound client should return true/false and never raise**, so a
background job cannot spin on an unhandled exception.

## Access control

**23. Guard every entry point or none.** List conditions, per-document
permission, *and* the generic `get_list` API.

**24. Cached permissions need an explicit invalidation hook.**

## Physical output

**25. Measure the renderer before you debug the CSS.**
Ubuntu's wkhtmltopdf silently renders everything at 0.7688×.

**26. Two output paths that must agree about a measurement: one reads the
other's numbers.** Copied coordinates drift.

**27. Where a convention genuinely varies per case, make it mandatory and throw
when it is missing.** A convenient default printed half the forms wrong.

**28. A workaround for one mode must be gated on that mode.**
The A5 clamps were mangling the real form.

**29. Keep global shifts and per-field nudges separate — in the code and in the
commit message.** It is how you know what to revert.

## Working method

**30. Reproduce the broken state before fixing it.** The Sparrow token patch
was verified by recreating `avinasdemo`'s exact state on `avinas1`, then
checking recovery, a second run, a hand-retyped token, and the
nothing-to-recover case.

**31. When recovery may be impossible, fail to empty, not to plausible.**

**32. Write the *why* next to the code, with the date and the decision.**
Nearly every quotation in this book came from a docstring or a comment in this
repo. That is why the book could be written at all — and why the next person
will not undo a decision they cannot see.

---

# Chapter 14. Playbooks

## 14.1 "This invoice has the wrong number"

1. Run the tracer (Chapter 4.6) — do not reason from the string.
2. `GENERATED` → find the rule: which Numbering Configuration matched, what is
   its scope (`docno_group_by`), what is the counter in `tabSeries`?
3. `SUPPLIED` → the write carried it. Import, REST or script. For a legacy row
   this is **correct**.
4. Scope surprises? Check whether the doc's company/branch/date changed after
   creation (`_redraw_docno_if_scope_changed`) and whether `lock_group_fields`
   should have prevented it.
5. Duplicates → check the rule's `duplicate_action` and whether the write came
   through an import (`frappe.flags.in_import` always throws).

## 14.2 "The invoice didn't reach the IRD"

1. Does the invoice have a **CBMS Bill** at all?
   - No → the `on_submit` hook failed. **Look in the Error Log.** Nothing will
     create it for you; closing the gap is an explicit backfill (`backfill.py`).
   - Yes → continue.
2. `sync_status`? `Pending`/`Failed` with a rising `attempt_count` means the
   cron is trying. Read `sync_response`.
3. Is the invoice **in scope** — `posting_date >= CBMS Config.enable_from_date`,
   and is `enable_cbms` on for that company?
4. Credentials: response code `100` is "credentials do not match". And check
   the token/password is not a row of asterisks (Chapter 9.1).
5. Returns: remember `101` means *failure* on the return endpoint.
6. CBMS Activity Report and CBMS Sync Log hold the history.

## 14.3 "The print is in the wrong place"

1. **Whole print shifted?** → adjust `X0_MM` / `Y0_MM` (or the overlay's
   `ox`/`oy`) in that form's `escp_*.py`. Never nudge every field.
2. **One field in the wrong box?** → adjust that field's entry in `POS`.
3. **Everything shrunk into the top-left corner?** → wkhtmltopdf. Confirm the
   format's `pdf_generator` is `chrome`; if it reverted, `migrate` re-imported
   it — `ensure_chrome_generator` should re-pin it.
4. **Right on the sprocket form, wrong on A5 (or vice versa)?** → the `page`
   argument to `overlay_pos`, and the A5-only clamps.
5. **Title half a label off?** → `COPY_LABEL_ANCHOR` on that form module.
6. **Spooler says success, head never moves?** → the printer queue is on the
   Epson driver, not **Generic / Text Only**.
7. **Bridge dead after a shutdown?** → Fast Startup. Confirm the scheduled task
   has both the boot *and* the sign-in trigger.

## 14.4 "The copy titles / print counts are wrong"

1. `invoice_copy_titles` is the only source of truth — check it first.
2. Is the series `pair=True` (dot-matrix, two sheets on the first print) or
   `pair=False`? The count is in **sheets**, not print events.
3. Did merely previewing increment it? It must not — only
   `printview?trigger_print=1`, a PDF download, or raw printing.
4. Old invoice with a strange starting count → the legacy import
   (`Sales Invoice Print Count`, added to rather than replaced).
5. Who reprinted it → **Sales Invoice Print Log**, one row per sheet.

## 14.5 "Attendance is wrong for a day"

1. Are the punches there as **Employee Checkin**? No → device/bridge; check the
   hourly heartbeat and the K40 Bridge.
2. Punches present but the day is **Absent** → F1/F2 from Chapter 10.2. Look
   for `skip_auto_attendance=1` on the checkins. The hourly self-heal should
   repair it; **Attendance Fix** does it on demand.
3. Checkin has no `shift` → F3. A shift assigned later does not retroactively
   select it; the self-heal re-runs `fetch_shift`.
4. Two employees' punches merged → duplicate device ID.
5. Salary slip days look wrong → BS month length, not a bug (Chapter 10.4).

## 14.6 "A user can't see / can wrongly see records"

1. Fiscal year: **User Fiscal Year Access** for that user and year.
2. Just changed it and nothing happened → the cache; `User.on_update` clears it,
   and there is a client-side cache too.
3. Visible in the list but not openable (or the reverse) → you have one of
   `permission_query_conditions` / `has_permission` and not the other.
4. Via the API but not the desk → `frappe.client.get_list` override.
5. Wrong-company links offered in a picker → `FILTER_CONFIG` / Company Filter
   Config for that doctype.

## 14.7 Adding a new company

1. Fiscal Year rows for that company (**before** the year rolls over).
2. Numbering Configuration rules — or seed them
   (`scripts/seed_numbering_rules.py`), keeping `tabSeries` keys if a sequence
   must continue.
3. CBMS Config: credentials and a correct `enable_from_date`.
   **Set the date before enabling** (Chapter 6.2).
4. Company Print Template → which print format/bridge queue.
5. If it prints on pre-printed forms: a new `escp_*.py` with its `POS` map,
   a `COPY_LABEL_ANCHOR`, an entry in `overlay.py`'s `_FORMS`, and a Jinja
   registration in `hooks.py`.
6. Company Filter Config, Dynamic Approval Settings, SMS rules as needed.
7. Test **on that company** — "it works on NGI" is not "it works".

## 14.8 Before you commit

- [ ] Does this run on `validate`, and is it idempotent?
- [ ] If it is a `"*"` hook, does it gate first?
- [ ] Does it block a business transaction on anything slow or remote?
- [ ] Could it take an irreversible action from stale configuration?
- [ ] Fixtures scoped by name? New config doctype added to
      `company_data_to_be_ignored`?
- [ ] Tested on more than one company?
- [ ] Is the **why** written next to the code, with the date?
- [ ] `git status` — did `developer_mode` drag unrelated doctype JSON in?

---

# Appendix. Where to look things up

**Start here:** `docs/README.md` — the full documentation index.

| Question | Go to |
| --- | --- |
| "What runs when?" | `avinashgroup_app/hooks.py` |
| "Where is file X and is it even wired up?" | `docs/technical/10-file-index.md` |
| "What was done to doctype Y?" | `docs/technical/13-per-doctype-reference.md` |
| "What is this custom field?" | `docs/technical/11-custom-fields-and-doctypes.md` |
| "What does this report do exactly?" | `docs/technical/12-reports-appendix.md` |
| "What is customised on the live site, including DB-only?" | `docs/technical/14-site-customization-inventory.md` |
| "How does the approval engine work?" | `docs/technical/02-dynamic-approval.md` (the three older approval docs are stale) |
| "How does CBMS work?" | `docs/technical/05-cbms-integration.md` + Chapter 6 here |
| "How do overlays / bridges work?" | `docs/how_overlay_print_works.md`, `docs/print_bridge_user_guide.md`, `docs/verification_guide_overlay_printing.md` |
| "How do I explain this to an accountant?" | `docs/user_guide/` (8 chapters) |
| "How is numbering configured?" | `docs/numbering_configuration.md`, `docs/SALES_INVOICE_NUMBERING.md`, `docs/document_numbering_developer.md` |
| "Where did this number come from?" | `.claude/skills/trace-number/SKILL.md` |
| "How do I set up a branch PC / printer?" | `docs/branch_pc_setup.md`, `docs/print_bridge_till_setup.md` |
| "Replication is behaving oddly" | `docs/db-master-slave-replication.md` |
| Nepali payroll / BS accounting | `apps/rdp_common_app/docs/` |

**Where the handoff notes are.** `docs/handoff_*.md` and
`docs/session_handoff_*.md` are dated snapshots written mid-problem. They are
useful for *how a decision was reached*, and unreliable for *what the code does
now*. When they disagree with the code, the code wins.

---

*End of the handbook. The best next step is to open `hooks.py` and trace one
Sales Invoice save all the way through — numbering, taxes, credit control,
submit, CBMS, print. Everything in this book is on that path.*
