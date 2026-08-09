# Part III — The transaction core

Three subsystems, in this order, because each depends on the one before:
a document gets a **number**, then its **taxes and totals**, then it is
**reported to the IRD**. Everything irreversible in this app is here.

---

# Chapter 4. Numbering

`custom_code/Override/naming_series.py` — ~3,000 lines, the largest single file
in the app. It exists because "what number does this document get?" turned out
to be one of the hardest questions in the system.

## 4.1 The problem

A Nepali invoice number is not a sequence. It looks like:

```
NGK-SB-82/83-04311
 │   │    │     └── counter, restarting each fiscal year
 │   │    └──────── fiscal year (BS)
 │   └───────────── document type code (SB = sales bill, SRTN = sales return)
 └───────────────── company / branch
```

And the requirements stack up:

- the counter restarts **per company, per fiscal year** — NGK holds `NGK/000001`
  in both 77/78 and 79/80,
- it must be **gapless** (the IRD, Chapter 3),
- some documents are numbered automatically, some are typed by hand, and the
  *same doctype* may want auto for returns and manual for normal invoices,
- imported legacy documents must keep the number they arrive with,
- amendments must keep the cancelled original's number,
- and two clerks pressing Save at the same moment must not get the same number.

Hardcoding this per doctype was the original approach (`NAMING_CONFIG`, still
present as a fallback). It did not survive contact with seven companies.

## 4.2 The engine: numbering became data

The current design is a rule engine driven by the **Numbering Configuration**
doctype. A rule is matched to a document, and the rule says how to build the
number:

| Rule field | What it controls |
| --- | --- |
| `document_type`, `company`, `branch` | which documents this rule matches |
| `conditions` | extra match criteria (Equals / In / Is Set …) |
| `segments` | **the format** — an ordered child table |
| `separator`, `target_field` | how segments join, and where the result is written |
| `docno_group_by` | what makes a *separate counter* |
| `normal_docno_mode` / `return_docno_mode` | Auto or Manual, separately for returns |
| `document_no_conditions` | which subset actually gets auto-numbered |
| `duplicate_action` | `Throw Error` or `Use Next Available Number` |
| `legacy_upto`, `legacy_source_field` | where old numbers come from |
| `lock_group_fields` | forbid edits that would move a doc to another series |

A **segment** (`Numbering Segment`) is one piece of the string: a static value,
a field of the document, a fetched field, or the counter (`number_length`
digits). This is why a new company or a new document type is a *data* change.

It is wired as a wildcard hook (Chapter 2.2):

```python
_add_doc_event("*", "validate",     "…naming_series.apply_engine_numbering")
_add_doc_event("*", "before_save",  "…naming_series.apply_engine_numbering")
_add_doc_event("*", "after_delete", "…naming_series.revert_engine_series_on_delete")
```

with a Redis-cached gate so doctypes with no rule cost essentially nothing.

The old hardcoded branch numbering was migrated into seeded rules by
`scripts/seed_numbering_rules.py`, using **identical formats and identical
`tabSeries` keys** — so live sequences continued without a jump. That is the
right way to replace a numbering scheme: keep the counter keys.

## 4.3 Scope — the idea to internalise

**Scope** = the set of documents that share one counter. Everything else in
this chapter is bookkeeping around it.

Scope can come from the rule's explicit `docno_group_by` rows, or be derived
from the prefix/pattern. The group-by path is the better one, and the reason is
worth quoting:

> Unlike the prefix/pattern scopes, this one scans by **filters on the real
> columns**, so history is visible even when the stored voucher format changes —
> an existing series continues instead of restarting.

In other words: if you scope by *the shape of the string*, then changing the
format orphans the history and the counter restarts at 1. If you scope by *the
fields the string was built from*, the history is still findable. Prefer
group-by fields.

`custom_fiscal_year` in a group-by is special-cased: it groups by the fiscal
year **of the posting date, resolved as a date range**, not by the stored
column — because the stored column is empty on old rows.

## 4.4 Concurrency: the ordering that matters

This is the subtlest code in the app, and the comment in `apply_document_no`
spells it out. When a user types a manual number:

```python
# ORDER MATTERS (concurrency): bump the counter FIRST — its
# INSERT..ON DUPLICATE KEY UPDATE takes the scope's tabSeries row lock
# (held to commit), so a concurrent save of the same scope blocks here
# until this one commits. Only THEN check for a duplicate, with a
# LOCKING read that sees the peer's committed row (a plain SELECT's
# REPEATABLE READ snapshot would miss it, letting two users who typed
# the same free number both save it).
_keep_counter_above_manual(doc, field, scope)
taken_by = _document_no_taken(doc, scope, doc.get(field), for_update=True)
```

Two lessons that generalise far beyond this file:

1. **Take the lock before you check.** Checking then locking is a race; locking
   then checking is not. Here the `tabSeries` row is used as the mutex, so the
   counter bump *is* the lock acquisition.
2. **Under `REPEATABLE READ`, a plain `SELECT` cannot see a concurrent commit.**
   A uniqueness check must be `SELECT … FOR UPDATE`, or it will cheerfully
   confirm that a number is free while another transaction is committing it.

Auto-drawn numbers ignore whatever the client previewed and are drawn under
the same per-scope lock. The client-side preview
(`public/js/auto_update_document_no.js`) is *optimistic display only* — never
trust a number that came from the browser.

## 4.5 The special cases, and why each exists

| Case | Behaviour | Why |
| --- | --- | --- |
| **Amendments** | pinned to the cancelled original's number, before any manual/auto logic | an amendment is the same IRD document |
| **Legacy imports** | the supplied number is stored verbatim | the old system's number *is* the identity |
| **Duplicate on import** | always throws, never auto-bumps | silently renumbering imported rows would be invisible inside a background job; `frappe.flags.in_import` is checked explicitly |
| **Duplicate typed in the desk** | per-rule: throw, or take the next free number with an orange alert | a clerk can see and react to an alert |
| **Draft whose scope changed** | number is **redrawn** | editing company/branch/date moves the doc to a different series; keeping the old number would corrupt two sequences |
| **Locked group fields** | the edit is rejected outright | some series must never be re-scoped, even by an amendment |

Also note `_docno_eligible`: when an Auto-fill rule matches, **it is
authoritative** — the hardcoded fallback is not consulted. That is what lets a
rule turn numbering *off* for a subset (returns auto, normals manual) rather
than only ever adding to it.

## 4.6 When a number looks wrong: use the tracer

Five different code paths can produce the value in a number field, and you
cannot tell which from the shape of the string. Do not guess — there is a
purpose-built tool, exposed as a Claude Code skill:

```bash
cd /home/sijan/frappe-15/sites
/home/sijan/frappe-15/env/bin/python -c "
import frappe
frappe.init(site='avinas1', sites_path='/home/sijan/frappe-15/sites'); frappe.connect()
from avinashgroup_app.scripts.trace_number import trace, trace_url
trace('Sales Invoice', 'NGK-SRTN-78/79-00417')
"
```

`trace_url('https://…/app/sales-invoice/NGK-SRTN-78%2F79-00417')` takes the desk
URL directly, which is usually how the question arrives.

| Verdict | Means |
| --- | --- |
| `GENERATED` | the engine drew it; the series key and counter are printed |
| `SUPPLIED` | the write carried it (import / REST / script) and it was stored verbatim — **correct** for legacy imports |
| … | see `.claude/skills/trace-number/SKILL.md` |

It is read-only: it peeks at counters without drawing, so it is safe on a live
site. Run it from `sites/`, and not through `bench execute` (Chapter 1.4 — the
engine's helpers are `_`-prefixed).

---

# Chapter 5. The Sales Invoice pipeline

Sales Invoice is where every subsystem meets. Read `hooks.py` lines 106–139
before this chapter.

## 5.1 The order of operations

```
before_validate:  salesinvoice_taxes.before_validate_salesinvoice
                  posting_miti.set_invoice_miti          ← BS miti from posting date

validate:         salesinvoice_taxes.before_save_salesinvoice   ← build taxes table
                  salesinvoice_taxes.validate_salesinvoice      ← assert it matches
                  credit_control.validate_sales_invoice         ← reads grand_total
                  (+ wildcard: numbering, dynamic approval, …)

on_submit:        CBMS.sales_invoice_hooks.on_submit             ← create the bill
before_print:     print_count.before_print                       ← IRD copy titles
onload/before_cancel/on_trash:  CBMS immutability guards
```

Two things to notice. The tax pipeline is on **`validate`, not `before_save`** —
§5.2 explains why that is not a style choice. And credit control is **last**,
because it reads `doc.grand_total`, which only becomes final once the taxes
table above it has been built.

## 5.2 Save *is* Submit — and the subtle way it was first done wrong

`custom_code/SalesInvoice/save_and_submit.py` overrides
`frappe.desk.form.save.savedocs` so that pressing **Save** on a Sales Invoice
draft also submits it, in one request and therefore **one database
transaction**.

Why: an invoice number is consumed the moment a draft is saved (the `tabSeries`
increment happens in that transaction). A draft that later failed to submit
would leave a **gap in the IRD numbering sequence**. Making save+submit atomic
means a failure rolls back the insert, the submit *and* the counter — no draft,
no consumed number, no gap.

Now the part worth reading twice. The obvious implementation is to rewrite the
action to `"Submit"` so the row is inserted with `docstatus=1` already. That is
what this module used to do, and it silently broke every `before_save` hook on
Sales Invoice:

> `savedocs` sets `doc.docstatus` **before** inserting, so a brand-new doc
> arrives already submitted. `Document.check_docstatus_transition` then picks
> `_action = "submit"`, and `run_before_save_methods` runs `before_submit`
> **instead of** `before_save` — the two are mutually exclusive branches.

Result: the audit-file hook and the wildcard numbering hook, both registered on
`before_save`, were skipped on every desk-created invoice, with nothing to
signal it.

The fix is structural, not a workaround: **save first with the action
unchanged, then submit the saved document as a second action.** Two actions,
one transaction. The insert sees `docstatus=0` and runs `before_save`; the
submit runs on a document that is no longer new and runs `before_submit`. Both
fire, in their normal order, and no compensation layer has to be maintained
when someone adds a hook next year.

The escalation deliberately does **not** apply when:

- the user lacks submit permission (they can still save plain drafts), or
- an active Workflow governs Sales Invoice (approvals need drafts, and
  `doc.submit()` would be blocked by `validate_workflow` anyway).

Only the desk endpoint is wrapped. Programmatic creation and Data Import are
untouched.

**The cost, stated honestly in the module docstring:** `validate` now runs on
*both* passes, so the VAT/excise pipeline executes twice per desk-created
invoice. That is acceptable only because the pipeline is deterministic — it
recomputes from the item rows and reaches the same answer — and because
`apply_document_no` is idempotent per save and keeps the number it already drew
on the second pass. **If you add anything to `validate` that is not
idempotent, it will run twice and you will have a bug.** Counters, appends,
external calls: not on `validate`.

## 5.3 Zero-quantity rows

ERPNext ships an "allow zero qty" checkbox for Quotation and Sales Order but
not for Sales Invoice. This business needs zero-qty rows on invoices, so the
app adds `Selling Settings-custom_allow_zero_qty_in_sales_invoice` as a
**name-scoped fixture** (Chapter 2.9) and reads it in
`salesinvoice_taxes.allow_zero_qty_rows`.

The pattern is worth copying: when core almost supports something, add the
missing switch in the same place core would have put it, ship it as a scoped
fixture, and read it where core reads its own.

## 5.4 Credit control

`custom_code/SalesInvoice/credit_control.py` enforces the customer credit limit
at `validate`, after totals are final. Because it is a `validate` hook it also
runs twice on desk saves — it is a pure check, so that is harmless. Keep it
that way.

---

# Chapter 6. CBMS — reporting to the IRD

`custom_code/CBMS/` — the integration with Nepal's Central Billing Monitoring
System. This is the part of the app where mistakes cannot be undone, and its
design is shaped end-to-end by that fact.

## 6.1 The pieces

| File | Role |
| --- | --- |
| `api_client.py` | HTTP to `cbapi.ird.gov.np`; never raises |
| `sales_invoice_hooks.py` | the **only** place a bill is created; immutability guards |
| `scheduler.py` | `*/5 * * * *` retry of unsynced bills |
| `backfill.py` | explicit, operator-initiated gap closing |
| `activity_log.py` | the audit trail behind the CBMS Activity Report |
| `utils.py` | BS dates, fiscal-year formatting, display names |

Doctypes: **CBMS Config** (per company: `enable_cbms`, `enable_from_date`,
credentials, retry batch sizes), **CBMS Bill**, **CBMS Bill Return**,
**CBMS Sync Log**.

## 6.2 Two rules that shape everything

**Rule 1 — nothing here may ever block or fail a Sales Invoice submission.**

Every code path inside the transaction does fast, local, non-throwing work. The
one network call — the realtime first send — runs **only after the transaction
commits** (`frappe.db.after_commit`), is capped at `SUBMIT_SEND_TIMEOUT`
seconds, and on anything but success hands off to the background queue and the
retry cron.

This is the general recipe for any outbound integration in Frappe:

```
inside the transaction:   write the local record, cheaply, without throwing
after_commit:             attempt the network call, with a hard timeout
on failure:               enqueue; let a scheduled retry own it from there
```

If the network call is inside the transaction, then a slow tax-office server
means clerks cannot bill. That is not a trade-off anyone would accept.

**Rule 2 — `sales_invoice_hooks.on_submit` is the *only* thing that creates
bills.** No cron, no scheduled job, ever.

The reasoning, from `scheduler.py`:

> Reporting a bill to IRD is irreversible (a Synced invoice can no longer be
> cancelled), so which invoices become bills must be a deterministic
> consequence of submitting them, not of when a cron happened to fire against
> the config of the moment.
>
> A cron that mass-created bills on a schedule once swept up **nine months of
> out-of-scope invoices** in the gap between enabling a config and correcting
> its Send From Date; because reporting a bill to IRD is irreversible, that
> class of mistake must not be reachable.

That is the incident behind the rule. Nine months of invoices were reported to
the tax office because a config was enabled before its date was right, and a
cron was willing to act on the config of that moment.

**The cost is accepted openly:** if the hook fails, the invoice has **no** CBMS
Bill, and nothing will create one behind your back. The failure goes to the
Error Log, and the gap must be closed by an explicit, human-initiated backfill.
A visible gap you must fix is safer than an automatic action you cannot undo.

## 6.3 Scope: the Send From Date

```python
def in_cbms_scope(config, posting_date):
    if not config.enable_from_date:
        return False
    return getdate(posting_date) >= getdate(config.enable_from_date)
```

Only invoices posted **on or after** the company's go-live date are ever
synced. No retroactive reporting of history. And since 2026-08-05 the date is
enforced **at the send**, not only at bill creation — belt and braces around
the incident above.

## 6.4 Immutability

Once a bill is `Synced`, the invoice is locked forever:

- `before_cancel` — refuses,
- `on_trash` — refuses,
- `onload` — flags the document so the desk form hides Cancel and Delete
  entirely.

Guard the server side *and* the UI: the server guard is the truth, the UI guard
stops a user discovering the truth as a red error at the worst moment.

## 6.5 Status model and retries

`CBMS Bill.sync_status` ∈ `Pending` / `Synced` / `Failed`, plus `is_synced`,
`is_realtime`, `attempt_count`, `last_attempt`, `sync_response`.

The cron re-sends everything not `Synced`, per company, in batches
(`bill_retry_batch_size`, default 50). Batching matters: an unbounded retry
sweep after an outage will happily saturate a worker for an hour.

## 6.6 The API's inconsistency you must not paper over

```python
BILL_SUCCESS_CODES   = {"200", "101"}   # 101 = "bill already exists"  → success
RETURN_SUCCESS_CODES = {"200"}          # 101 = "bill does not exist"  → failure
```

**The same response code means opposite things on the two endpoints.** Treating
101 as success on returns would silently mark unreported returns as done. Two
explicit sets, with a comment citing the vendor doc — do not "simplify" them
into one.

Similarly, `_amount()` rounds every value to 2 decimals on the way out, even
though `build_cbms_fields` already rounds, because records written by other
paths may carry more and CBMS rejects the whole model if they do.

And every function in `api_client.py` returns `True`/`False` and **never
raises** — so it is always safe to call from a background job without creating
an unhandled-exception retry loop.

## 6.7 What a bill carries

`CBMS Bill` stores denormalised copies: `invoice_number`, `invoice_date` and
`invoice_date_bs`, `fiscal_year`, `buyer_name`/`buyer_pan`, `seller_pan`, and
the full amount breakdown (taxable, VAT, excise, HST, ESF, export, exempted).

Note `created_by` is a **name string, not a User link**:

> The bill stores a NAME, not a User link, so the annexure's "Entered By"
> column survives a user being renamed, disabled or deleted — an IRD record
> must not lose its author, and the legacy print history it sits beside carries
> names from the old software that were never Frappe users at all.

That is the right instinct for any statutory record: **a compliance record
snapshots facts; it does not hold live references to mutable masters.**

Two related corrections landed on 2026-08-05, both of the same species:

- "Entered By" is `custom_created_by`, **not** `owner` — `owner` is the API
  user that pushed the invoice in, not the clerk who entered it;
- the Add event's timestamp is `custom_created_on`, **not** `creation`.

When a report must show *who did the business action*, framework audit fields
are frequently the wrong answer. Check what actually wrote the row.

---

Next: **[Part IV — Getting ink on paper](04-printing.md)**
