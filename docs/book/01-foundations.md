# Part I — Foundations

---

# Chapter 1. The ground you stand on

Before any code: know exactly what you are running against. Most of the
scariest incidents in this project were not bad logic — they were correct logic
pointed at the wrong site, the wrong virtualenv, or the wrong working directory.

## 1.1 One bench, several sites

```
/home/sijan/frappe-15/          ← bench root (on the other machine: /home/dell/frappe-v15)
├── apps/     frappe, erpnext, hrms, rdp_common_app, avinashgroup_app, sarathi_app
└── sites/    avinas1, avinas, nepalgas, rpl
```

| Site | What it is |
| --- | --- |
| **`avinas1`** | **The working site.** Assume it for everything unless told otherwise. |
| `avinas1-7yr` | Historical data copy. Read from it; never change it. |
| `sarathilive` | A different product's live site. Only appears for IRD/CBMS work. |
| `nepalgas`, `avinas`, `rpl`, `demo` | Older or scratch copies. Not in normal use. |

`sites/currentsite.txt` already says `avinas1`, so a bare `bench` command hits
it. **Pass `--site avinas1` anyway.** It costs nine characters and it puts the
intent in the shell history, where the next person reading your command can see
what you meant rather than what the file happened to contain that day.

```bash
bench --site avinas1 mariadb -e "SELECT name FROM \`tabSales Invoice\` LIMIT 5"
bench --site avinas1 console
bench --site avinas1 migrate
```

## 1.2 Two virtualenvs that are not interchangeable

This one is worth memorising:

| Path | What it is | Use it for |
| --- | --- | --- |
| `…/frappe-env` (or your bench CLI env) | the **bench command-line tool** | running `bench` |
| `…/frappe-15/env` | the **Frappe framework** | any standalone script that does `import frappe` |

Use the wrong one and you get an import error that looks like a broken
installation but is only a wrong interpreter.

## 1.3 The working directory is load-bearing

Frappe's logger builds its log path as `os.path.join(site, "logs", logfile)` —
**relative to the current directory**. So a standalone script must run from
`sites/`:

```bash
cd /home/sijan/frappe-15/sites            # not the bench root
/home/sijan/frappe-15/env/bin/python myscript.py
```

```python
import frappe
frappe.init(site="avinas1", sites_path="/home/sijan/frappe-15/sites")
frappe.connect()
```

> **The trap.** Run that from the bench root instead and you get
> `FileNotFoundError: …/frappe-15/avinas1/logs/database.log`, or worse, Frappe
> silently creates a stray `frappe-15/avinas1/` directory that *looks* like a
> site and is not one. One such ghost already exists on the server. If you ever
> see a site directory outside `sites/`, that is what it is — do not "fix" it by
> copying config into it.

## 1.4 `bench execute` cannot call private helpers

`bench --site avinas1 execute` runs your dotted path through **RestrictedPython**,
which rejects any name beginning with `_`. The numbering engine and several
other modules keep their real logic in `_`-prefixed helpers, so:

- to poke at a private helper → `bench console` or a standalone script,
- `bench execute` → only for public, whitelisted-style entry points.

## 1.5 The read replica

`avinas1` runs with `read_from_replica: 1` against MariaDB on `127.0.0.1:3307`.

- **Script reports and list views read the replica.**
- **All writes go to the master** on `:3306`.

Two consequences you will meet in practice. First, a report can show data a few
moments stale — that is replication lag, not a bug in your query. Second, if
replication breaks, reports silently serve old data while writes keep
succeeding; that is a much nastier failure than an outage. The runbook is
`docs/db-master-slave-replication.md`.

## 1.6 The seven companies

Everything company-scoped — fiscal years, accounts, numbering rules, print
templates, CBMS configs — normally has to be created **seven times**:

| Company | Abbr |
| --- | --- |
| Nepal Gas Udhyog Pvt. Ltd. | NGI |
| Nepal Gas Udhyog (Gandaki) Pvt. Ltd. | NGG |
| Nepal Gas Udhyog (Karnali) Pvt. Ltd. | NGK |
| Nepal Gas Udhyog (Narayani) Pvt. Ltd. | NGN |
| Grihalaxmi Metal Industries Pvt. Ltd | GLMI |
| Grishma Enterprises Pvt. Ltd. | GEPL |
| Sambriddhi Gas Udhyog Pvt. Ltd. | SGU |

"It works on NGI" is not "it works." Nearly every rule in this app is scoped by
company, and several are scoped by **company *and* fiscal year** — Chapter 4
explains why that pairing keeps recurring.

`developer_mode` and `server_script_enabled` are on for `avinas1`, which is why
doctype JSON changes land in the repo when you edit a doctype in the desk. That
is a feature and a hazard: check `git status` before you commit.

---

# Chapter 2. Frappe, as this app actually uses it

You do not need all of Frappe. You need the eight mechanisms below, because
this app is built almost entirely out of them. Everything in Parts III–V is an
application of something on this list.

Read `avinashgroup_app/hooks.py` alongside this chapter. It is 464 lines and it
is the table of contents for the entire app.

## 2.1 Document events (`doc_events`)

The main extension point: "run my function when a document does X."

```python
sales_invoice_specific_events = {
    "before_validate": [...],
    "validate": [...],
    "before_print": "…print_count.before_print",
}
```

The lifecycle you must hold in your head:

```
insert:  before_validate → validate → before_save   → (db insert)  → on_update
submit:  before_validate → validate → before_submit → (db update)  → on_submit
cancel:                               before_cancel → on_cancel
delete:                               on_trash      → after_delete
```

> **The trap — `before_save` vs `validate`.** `before_save` and `before_submit`
> are **mutually exclusive branches** in Frappe's `run_before_save_methods`.
> A document that is inserted *already submitted* (`docstatus=1` on insert) runs
> `before_submit` and **never runs `before_save` at all**.
>
> This app creates documents that way in two places — desk-saved Sales Invoices
> (Chapter 5) and device-marked Attendance (Chapter 10) — and in both cases
> `before_save` hooks silently did nothing, with no error to point at.
>
> **The rule: put pipeline logic on `validate`, not `before_save`.** `validate`
> runs on both paths. `hooks.py` says exactly this in comments above both
> `sales_invoice_specific_events` and `attendance_events`; the comments are
> there because the bug happened.

Hook **order within one event is the order in the list**, and this app depends
on it. On Sales Invoice `validate`:

1. build the taxes table (`salesinvoice_taxes.before_save_salesinvoice`),
2. assert the taxes table matches the computed totals (`validate_salesinvoice`),
3. enforce the credit limit (`credit_control.validate_sales_invoice`).

Step 3 reads `doc.grand_total`, which is only correct after step 1. Reorder
these and credit control starts checking a number that does not exist yet.

## 2.2 Wildcard hooks (`"*"`) — power with a tax

Four subsystems here hook **every doctype in the system**:

```python
_add_doc_event("*", "validate",    "…naming_series.apply_engine_numbering")
_add_doc_event("*", "validate",    "…dynamic_approval.validate")
_add_doc_event("*", "on_submit",   "…sparrow_sms.sms_dispatch.on_submit")
```

That is how numbering, approvals and SMS became *configuration* rather than
code: you add a rule record, not a hook.

The tax: your function now runs on every save of every document on the site,
including Frappe's own internal bookkeeping. So each of these follows the same
discipline —

**A cached gate as the first statement.** Before any real work, a Redis-cached
lookup answers "does this doctype have any rule at all?" Unconfigured doctypes
cost one cache read and return. `sparrow_sms/sms_dispatch.py` keeps the
doctype set under `sparrow_sms_rule_doctypes`; the numbering engine and
`dynamic_approval` do the same thing.

If you add a wildcard hook without a gate, you will not notice — until an
import of 50,000 rows takes four hours.

## 2.3 Class overrides (`override_doctype_class`)

When you need to change a *method* of a core document, not just add behaviour
around it:

```python
override_doctype_class = {
    "Sales Invoice": "…Override.overrides.CustomSalesInvoice",
    "Purchase Order": "…Override.overrides.PurchaseOrder",
    # nine in total
}
```

Your class subclasses ERPNext's and overrides one or two methods. Use this only
when a hook genuinely cannot do the job — an override pins you to ERPNext's
internals, so every upgrade must re-check it. The nine here are inventoried in
`docs/technical/04-taxes-and-overrides.md`.

## 2.4 Whitelisted-method overrides

The heavier hammer: replace a *server endpoint* the desk calls.

```python
override_whitelisted_methods = {
    "frappe.desk.form.save.savedocs":       "…SalesInvoice.save_and_submit.savedocs",
    "frappe.utils.print_format.download_pdf": "…printing.chrome_pdf.download_pdf",
    "frappe.client.get_list":               "…fiscal_year_filter.filtered_get_list",
    "frappe.desk.reportview.export_query":  "…utils.report_excel.export_query",
    "frappe.model.workflow.apply_workflow": "…workflow_admin_bypass.apply_workflow",
    # …
}
```

This is how Save became Save-and-Submit, how PDFs started rendering through
Chrome, and how list exports gained a letterhead. It is powerful and it is
invisible: nothing in the desk hints that the endpoint was replaced. **Always
leave a comment saying why** — the existing entries do.

> **The trap.** The dict currently lists `frappe.utils.print_format.download_pdf`
> twice (lines 379 and 381 of `hooks.py`). Same target, so it is harmless —
> Python keeps the last. It is still worth cleaning up, and it is a good
> reminder that this dict has no validation whatsoever: a typo'd key simply
> never takes effect, silently.

## 2.5 Monkey patches (`before_request` / `before_job`)

Some core behaviour is not reachable by hook or override, so it gets patched at
request start:

```python
before_request = [
    "…Override.auto_insert_item_price.patch_insert_item_price_set_company",
    "…Override.repost_valuation_notify.patch_repost_valuation_disable_error_email",
]
before_job = [
    "…Override.repost_valuation_notify.patch_repost_valuation_disable_error_email",
]
```

> **The trap.** `before_request` fires for **web requests only**. Background
> workers never see it. The repost-valuation patch had to be repeated in
> `before_job` precisely because the repost runs in a worker — the patch worked
> perfectly in testing and did nothing in production. If you patch something
> that background jobs also execute, register it in both places.

## 2.6 Scheduler

```python
scheduler_events = {
    "hourly":      ["…biometric.heartbeat.check_bridge_heartbeats"],
    "hourly_long": ["…biometric.attendance_self_heal.heal_unlinked_checkins"],
    "cron": {"*/5 * * * *": ["…CBMS.scheduler.retry_failed_cbms_syncs"]},
}
```

Note the deliberate choice of `hourly_long` for the attendance self-heal: it
puts the job in the **same queue bucket as HRMS's auto-attendance**, so each
hour runs "HRMS marks what it can → we repair what it couldn't" in that order.
Queue choice is scheduling logic, not a performance detail.

And note what is *absent*: no cron creates CBMS Bills. Chapter 6 explains why
that absence is the single most important design decision in the integration.

## 2.7 Jinja methods

Functions exposed to print formats:

```python
jinja = {"methods": [
    "…CBMS.utils.bs_date_str",
    "…printing.escp_invoice.ngi_escp",
    "…SalesInvoice.print_count.invoice_copy_titles",
    "…printing.overlay.overlay_pos",
    # one per printed form
]}
```

This is why the print formats stay thin: a format is a template that calls a
Python function, so the hard logic (coordinates, copy titles, BS dates) is in
`.py` files under version control rather than inside a database-stored HTML
blob. Chapter 7 makes this concrete.

## 2.8 Permission hooks

Two different mechanisms, and you need both:

```python
permission_query_conditions = {…}   # SQL WHERE — filters LIST views
has_permission = {…}                # per-document — guards a single doc
```

`permission_query_conditions` keeps rows out of lists and reports;
`has_permission` stops someone opening a document by URL. Implement only the
first and the list looks secure while every record stays reachable by guessing
a name. `fiscal_year_filter.py` registers both, for ~60 doctypes, from one
tuple — see Chapter 9.

## 2.9 Fixtures — scope them or regret them

```python
fixtures = [
    {"dt": "Email Template", "filters": {"name": ["in", [ …four names… ]]}},
    {"dt": "Custom Field",   "filters": {"name": ["in", [ …two names… ]]}},
    "Company Filter Config",
]
```

Every fixture in this app that touches a shared doctype is **filtered by
explicit name**. That is not fussiness. An unfiltered `"Custom Field"` fixture
exports *every custom field on the site* and, on the next site's `migrate`,
overwrites theirs. Scope by name, and the fixture can only ever touch the
records you listed.

Related, at the bottom of `hooks.py`:

```python
company_data_to_be_ignored = ["Biometric Device", "Numbering Configuration",
                              "CBMS Config", "Sparrow SMS Settings", …]
```

ERPNext's *Company → Delete Transactions* wipes every doctype carrying a
Company link. Your configuration masters carry one. Without this list, one
support action deletes your numbering rules and your IRD credentials.

## 2.10 Patches

`patches.txt` runs migrations once per site, in order, and never again. Use one
for any data change that must happen on every site — backfilling a new field,
renaming a value. Do not use `after_migrate` for that; it runs *every* migrate.

The legitimate `after_migrate` use in this app is idempotent re-pinning:

```python
after_migrate = ["…printing.setup.ensure_chrome_generator"]
```

Re-importing a standard print format resets its `pdf_generator` field to the
default, so this pins it back to `chrome` after every migrate — a repair that
must run repeatedly, not a one-time change. That is the distinction: **patch =
once; after_migrate = keeps re-asserting a truth that migrate keeps undoing.**

---

Next: **[Part II — Nepal: BS dates, VAT, and what the IRD demands](02-domain.md)**
