# Part V — Platform services

Four subsystems that are not about invoices but hold the rest of the system
together: **notifications**, **approvals**, **who can see what**, **attendance
and payroll**, and **reports**.

---

# Chapter 9. SMS, approvals, and access control

## 9.1 SMS: turning a hardcoded hook into a rules engine

The original implementation was a hook on Sales Invoice that sent an SMS. Then
another doctype needed one. Then a company needed different wording. The
rewrite (commit `8fcb45d`) replaced the code with **data**:

`sparrow_sms/sms_dispatch.py` is registered on `"*"` for `on_submit`,
`on_cancel`, `after_insert` and `on_update`. What actually sends is decided by
**SMS Notification Rule** records:

| Field | Meaning |
| --- | --- |
| `document_type`, `event` | when this rule is considered |
| `company` | scope it to one company |
| `condition` | a Code field — must evaluate true |
| `recipients` | child table of fields to pull numbers from |
| `message_template` | the text, with document fields interpolated |
| `enabled` | the off switch |

Adding an SMS is now a data-entry task. Two disciplines make that safe:

**A cached gate.** `CACHE_KEY_DOCTYPES = "sparrow_sms_rule_doctypes"` holds the
set of doctypes that have any rule at all. Every wildcard handler checks it
first, so unconfigured doctypes cost one Redis read (Chapter 2.2).

**Never block the document.** Same rule as CBMS: every handler is wrapped, the
HTTP call runs only after the transaction commits, and a failed direct attempt
falls back to the background queue. Nobody should ever be unable to submit a
delivery note because an SMS gateway is slow.

> **The trap — the Password fieldtype leaves a booby trap behind.** This one is
> worth memorising, because it will happen again on some other settings field.
>
> `token` was originally a **Password** field. Frappe stores a Password value in
> the `__Auth` table and writes a placeholder of literal asterisks —
> `"*" * len(value)`, see `base_document._save_passwords` — into the document
> row itself.
>
> Changing the fieldtype to **Data** undoes neither half. The real token stays
> stranded in `__Auth`; the asterisks stay in `tabSingles` as an ordinary Data
> value. And now **nothing masks anything**: the desk faithfully renders the
> asterisks that are genuinely stored, which looks exactly like a filled-in
> password box, and `sms_dispatch` posts that asterisk string to Sparrow as the
> token. Every send is rejected while the settings page looks perfect.
> `avinasdemo` sat in that state with 36 asterisks saved — and the
> `if not settings.token` guard passed, because asterisks are truthy.
>
> Fixed by a patch (`patches/sparrow_sms_token_as_data.py`) that moves the real
> value out of `__Auth`, clears the placeholder when there is nothing to
> recover, and forces the DocField to Data on sites whose doctype sync was
> skipped because `modified` was not older than the JSON's. Recovery is
> best-effort by design: if the `encryption_key` was rotated the decrypt fails,
> and **an empty field is the honest answer** — better than a plausible wrong
> one.
>
> Generalise three things from this: (1) **changing a fieldtype is a data
> migration, not a schema tweak**; (2) a truthiness check is not a validity
> check; (3) when recovery may be impossible, fail to *empty*, never to
> *plausible*.

## 9.2 Dynamic approval

`custom_code/dynamic_approval.py` (~1,400 lines) — a multi-level approval engine
that also runs on `"*"`, driven by **Dynamic Approval Setting** records with
match criteria, ordered approver rows, and fixed approvers.

The performance idea is worth stealing. Rather than resolve the approver chain
on every read, the engine **writes the answers onto the document** in hidden
fields:

```python
CURRENT_APPROVER_FIELD = "custom_current_approver"        # who must act now
TOTAL_LEVELS_FIELD     = "custom_total_approval_levels"   # how many levels
APPROVAL_SETTING_FIELD = "custom_approval_setting"        # pinned on first submit
APPROVAL_SECTION_FIELD = "custom_approval_section"
```

Workflow conditions then read a field instead of running a query — and pinning
the matched setting on first submission means later lookups skip criteria
scanning entirely (2 DB queries instead of N+3).

The UI is generic: `approval_workflow_auto.js` and
`approval_field_visibility.js` are loaded globally, so **any** doctype set up
via `setup_workflow` gets the banner and reject dialog with no per-doctype file.

Notification templates fall back to four auto-provisioned Email Templates
(shipped as name-scoped fixtures, Chapter 2.9); a Setting may link its own
instead. Admins customising wording should create their own template — those
are not fixtures, so `migrate` never overwrites them.

`workflow_admin_bypass.py` overrides `frappe.model.workflow.get_transitions`
and `apply_workflow` so administrators can unstick a stuck document.

> ⚠️ `docs/dynamic_approval_guide.md`, `dynamic_approval_workflow.md` and
> `dynamic_workflow.md` are **stale in places**. Read
> `docs/technical/02-dynamic-approval.md` §9 first.

## 9.3 Fiscal-year access control

`custom_code/fiscal_year_filter.py` restricts what a user can see to the fiscal
years granted to them (**User Fiscal Year Access** / **Fiscal Year Access
Control**), across ~60 submittable transaction doctypes listed in
`FILTERED_DOCTYPES`.

Both permission mechanisms are registered, from that one tuple:

```python
permission_query_conditions = {dt: f"…query_conditions_{slug}" for dt in FILTERED_DOCTYPES}
has_permission              = {dt: "…has_fiscal_year_permission" for dt in FILTERED_DOCTYPES}
```

Plus `frappe.client.get_list` is overridden (`filtered_get_list`), because that
endpoint is a side door that bypasses list-view conditions.

**Security lesson:** an access-control feature is only as good as its least
guarded entry point. List view, direct document open, and generic API — all
three, or none.

Caching: per-user fiscal access is cached and invalidated by a `User.on_update`
hook, with a client-side counterpart in `fiscal_year_cache.js`. Any cached
permission decision needs an explicit invalidation hook; otherwise granting
access appears not to work until the cache happens to expire.

## 9.4 Company filtering

`custom_code/globalfilter/globalfilter.py` scopes **Link field options** by
company: on a Nepal Gas (Gandaki) document, the Warehouse and Cost Center
pickers should not offer Karnali's.

`FILTER_CONFIG` declares, per doctype, the company field, the top-level Link
fields to validate, and the child tables plus their link fields. **Company
Filter Config / Company Filter Field** make the same thing configurable from
the desk, and both clear the Redis cache on update or delete.

Validation happens server-side (`validate_company_matching`) as well as in the
UI (`company_filter.js`) — the UI narrows the picker, the server refuses the
mismatch.

`Override/company_field_lock.py` and `setup_company_lock.py` prevent the
company field itself from being changed once a document exists, which would
otherwise re-scope it (and its number — Chapter 4.5).

## 9.5 Audit trail

`utils/audit_file_manager.py` defines `AuditEventMapper`, whose
`get_doc_events()` **builds the initial `doc_events` dict that `hooks.py` then
extends**:

```python
doc_events = AuditEventMapper.get_doc_events()      # hooks.py line 200
```

That is why `hooks.py` adds every other handler through `_add_doc_event()`
rather than assigning — it must merge into a dict that already has entries, and
it also de-duplicates and preserves ordering. **Never write
`doc_events["X"] = {...}` in this app**; you would silently drop the audit
hooks.

Reports built on the trail: **User Audit Trail**, **User Daily Entry Summary**
(with its own settings doctype), **Invoice Activity Report**, **CBMS Activity
Report**.

---

# Chapter 10. Attendance and payroll

## 10.1 The biometric pipeline

```
ZKTeco device ──(iclock/ADMS protocol)──► Frappe ──► Employee Checkin ──► Attendance
       │                                     │
   K40 Bridge (Windows)              biometric/iclock.py
                                     registered as a page_renderer
```

`hooks.py` line 11: `page_renderer = ["…biometric.iclock.IclockRenderer"]`. The
devices speak a fixed URL protocol that is not a Frappe route, so a page
renderer intercepts those paths. That is the right tool whenever a third-party
device or service demands URLs you do not control.

`k40_bridge/` is the Windows-side service (README + SETUP in that folder);
`biometric/heartbeat.py` runs hourly and alerts when a bridge goes quiet —
**Biometric Device Alert Recipient** holds who to tell. A device that stops
reporting is invisible until payroll runs, so the heartbeat is not optional.

`biometric/employee.py` validates that device IDs are unique — two employees
sharing one ID silently merges two people's attendance.

## 10.2 Self-healing, and why it had to exist

Stock HRMS auto-attendance is **fire-and-forget**: each (employee, day) gets
exactly one attempt. `biometric/attendance_self_heal.py` documents three
realistic ways that attempt fails *permanently and silently*:

| | Failure |
| --- | --- |
| **F1** | Device offline for days. Punches arrive after HRMS already marked the day Absent. `mark_attendance_and_link_log` raises `DuplicateAttendanceError` and sets `skip_auto_attendance=1` on those checkins **forever**; the wrong Absent stays. |
| **F2** | Any `ValidationError` while inserting Attendance — a missing Department, a misconfigured hook — poisons the checkins the same way. |
| **F3** | Punch stored while the employee had no shift assignment: the checkin has no `shift`, so the job never selects it, even after a shift is assigned later. |

The hourly `heal_unlinked_checkins` re-reconciles every (employee, day) in a
bounded lookback window that still has unlinked checkins:

- day already Present / Half Day / On Leave / WFH → link the orphan punches
- day marked Absent → replace it with attendance computed from the punches
- no attendance yet → create it
- shift missing on the checkin → re-run `fetch_shift` first

It runs in `hourly_long`, the same bucket as HRMS's own job, so the order is
"HRMS marks what it can → we repair what it couldn't" (Chapter 2.6). And the
lookback window is **bounded** — an unbounded self-heal is a rewrite of history
every hour.

**The pattern:** when you build on a fire-and-forget upstream job, you need a
*reconciler* — an idempotent, bounded pass that recomputes the desired state
from source data rather than trying to catch every failure at the moment it
happens. `Attendance Fix` is the manual counterpart, sharing the same
primitives.

> **The trap (again).** Attendance hooks are on **`validate`, not
> `before_save`** — auto attendance inserts Attendance *already submitted*, so
> `before_save` never fires. Same lesson as Chapter 2.1 and Chapter 5.2; this
> app has now been bitten by it in two unrelated places.

## 10.3 Allowances and BS reports

`payroll/attendance_allowance.py` sets the holiday flag and drives
**Employee Attendance Allowance**. The BS-calendar HR reports live here:
**Monthly Attendance BS**, **Monthly Attendance Summary BS**,
**Work on Holiday BS**, **Yearly Leave Details BS**.

## 10.4 rdp_common_app: BS payroll and BS accounting

The shared app carries the Nepali-calendar infrastructure used across products.

**BS-aware salary slips** — `nepal_hrms_common/payroll/salary_slip_bs.py`,
class `BSSalarySlip(SalarySlip)`. A BS fiscal year runs **Shrawan (month 4)
through Ashadh (month 3 of the next BS year)**, and BS months have **29–32
days** that do not align with AD months. HRMS computes everything on AD months,
which is wrong in three distinct ways:

| | AD behaviour | Correct BS behaviour |
| --- | --- | --- |
| Slip dates | AD month boundaries | BS month boundaries (Falgun = Feb 13 – Mar 14) |
| Working-days denominator | 28–31 | 29–32 |
| Income-tax spread | AD months remaining to FY end | BS months remaining to FY end |

`BSSalarySlip` overrides **four** methods of HRMS's `SalarySlip` — selectively.
That restraint is the point: subclass and override the minimum, so an HRMS
upgrade only breaks you where you actually disagreed.

**Deferred revenue/expense in BS months** — ERPNext spreads deferred amounts
over AD months; the Nepali report and the booking logic redistribute over BS
months (`nepali_calendar_reports/report/deferred_revenue_and_expense_nepali_date`).
Along with it: BS-period **Balance Sheet**, **Profit and Loss**, **Trial
Balance** and **Cash Flow** hierarchy reports.

**Desk quality-of-life** shipped from the same app, each fixing a real
annoyance:

- a **Nepali datepicker** that is *self-healing on cold/first load* — the
  original failed when the widget initialised before its data;
- a global **Fit Columns** checkbox for query reports that **re-applies on every
  render**, not just the first;
- the month-picker popup no longer clipped by the report-filter container;
- a **Custom Code Injector** doctype for site-specific snippets.

---

# Chapter 11. Reports

Thirty-plus reports live in `avinash_group_app/report/`. Do not read them all.
Read `docs/technical/12-reports-appendix.md` when you need one, and learn the
four patterns below.

## 11.1 The catalogue, grouped

| Group | Reports |
| --- | --- |
| **Statutory / IRD** | Materialized Report (VAT Annexure 7), Materialized Return Report, CBMS Activity Report |
| **Sales** | Sales Register, Sales Analysis (customer-wise summary & details, product-wise invoice details), Sales Stock Ledger, Invoice Activity |
| **Purchase / stock** | Purchase Register, Gas Purchase, Stock Balance (with Zero Values), Custom Supplier Quotation Comparison |
| **Finance** | Bank and Cash Book, Net Position of Cash and Bank, Party Ledger, Party Ledger Summary, Receipt Register, Consolidated Financial Statement Hierarchy, Profit and Loss Hierarchy, Advance Tax/TDS Details, Loan Summary, One Lakh Above Transactions |
| **HR / payroll** | Avinas Salary Statement, Monthly Attendance BS, Monthly Attendance Summary BS, Work on Holiday BS, Yearly Leave Details BS |
| **Audit** | User Audit Trail, User Daily Entry Summary |
| **Other** | Avinas Vehicle Expense |

## 11.2 Pattern 1 — reproduce the old software exactly

The **Materialized Report** is the IRD "VAT Annexure 7" sales book. Its
docstring states the goal plainly:

> The layout reproduces the annexure the old NGI billing software exported, so
> the group can retire that software: 21 columns in its order, BS dates with
> slashes, Yes/No instead of checkboxes, and (via `export_xlsx`) its letterhead
> block and Indian-grouped number formatting.

Including this:

> Three columns have no source and are always blank: Payment Method, VAT Refund
> Amount and Transaction Id. They are empty in every row of the software's own
> export too — placeholders kept so the column layout matches.

**Keeping three permanently blank columns is the right decision**, and a
comment saying why is what stops a future developer "cleaning them up". When
the deliverable is *"users and auditors must not notice the change"*, fidelity
beats tidiness — but write down which parts are fidelity.

Its row source is **CBMS Bill**, not Sales Invoice — one row per bill actually
reported to the IRD. That is what makes Chapter 12's legacy import necessary,
and it is why the report needed no changes to cover 79/80–82/83.

The **Materialized Return Report** was later laid out to match its sales
counterpart. Sibling reports should look like siblings.

## 11.3 Pattern 2 — Excel that carries a letterhead

`utils/report_excel.py`, three entry points and a deliberate non-merge:

| Function | Used by |
| --- | --- |
| `send_report_xlsx` | Script Reports (e.g. Materialized Return) — builds the workbook plus a totals row for numeric columns |
| `send_annexure7_xlsx` | the Materialized Report's own Annexure 7 layout |
| `export_query` | overrides `frappe.desk.reportview.export_query` — a **Sales Invoice list-view** export comes out as a fixed VAT REGISTER layout with the filtered company's letterhead, whatever columns the view shows; everything else passes through unchanged |

`send_annexure7_xlsx` is kept separate from `send_report_xlsx` **on purpose**:
that function also serves the list-view export, and "the two layouts agree on
almost anything" is false — they agree on almost nothing. Two clear functions
beat one with a mode flag.

## 11.4 Pattern 3 — printing and orientation

`report_print_orientation.js` injects `report_print_portrait.css`
**dynamically, only on query-report routes**. It used to be a global CSS
include, which changed every doctype print format too. If a stylesheet is meant
for one route, load it on that route.

`Override/query_report.py` overrides `get_data_for_custom_field` so the report
"Add Column" feature shows a Link field's **title instead of its id**.

## 11.5 Pattern 4 — what to check before you trust a report

1. **Which table are the rows from?** Materialized reads CBMS Bill; Sales
   Register reads Sales Invoice. They answer different questions and can
   legitimately differ.
2. **Is it fiscal-year filtered, and is the year resolved from the date or read
   from a column?** Old rows have empty year columns (Chapter 4.3).
3. **Is a multi-row child table joined?** Pick the row, then read its columns
   (Chapter 8.5).
4. **Is it hitting the replica?** Script Reports read from `:3307` — a few
   seconds stale is normal (Chapter 1.5).
5. **Are AD and BS dates being mixed?** Convert at the edge, once.

---

Next: **[Part VI — Legacy, lessons, and playbooks](06-legacy-and-lessons.md)**
