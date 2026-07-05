# avinas1 Site Customization Inventory — Code + Database

> Chapter 14 of the technical documentation. A full audit of **every
> customization present on the avinas1 site**, from both sources:
> **(A) app code** (hooks, class overrides, JS files, shipped fields — version
> controlled) and **(B) the database** (Custom Fields, Property Setters, Client
> Scripts, custom Print Formats, Notifications, Custom DocPerm — created via the
> Customize/UI, **not in the repo**). Data pulled live from avinas1.
>
> This chapter answers "go doctype by doctype: is it customized, and how." For
> the mechanism behind each feature see chapters 2–8; for the by-doctype field
> detail see chapter 13.

## 1. Totals

| Customization type | Count | In repo? |
|--------------------|-------|----------|
| Custom Fields | 1,357 (across 379 doctypes) | partly — only 13 bundles exported to `custom/*.json`; the rest are DB-only or added by patches |
| Property Setters | 421 (across ~60 doctypes) | ❌ DB-only |
| Client Scripts | 7 | ❌ DB-only |
| Custom Print Formats | 8 (Jinja) | ❌ DB-only |
| Notifications | 6 | ❌ DB-only |
| Custom DocPerm (permission rows) | 490 | ❌ DB-only |
| Server Scripts | 0 | — |
| Workflows | 0 stored (Dynamic Approval creates them **on demand** at setup time) | code (chapter 2) |

**396 doctypes** carry at least one customization: **121** have meaningful
customization (property setters / client scripts / print formats / notifications
/ >3 fields); **275** carry only the audit block (`custom_created_by/on`,
`custom_modified_by`) plus standard permission rows.

> ⚠️ **Reproducibility gap.** The Property Setters, Client Scripts, Print
> Formats, Notifications and most Custom Fields live only in the avinas1
> database. A fresh `bench get-app avinashgroup_app` + `install-app` will
> **not** recreate them — they must be exported as fixtures or migrated with
> the site. Only the code-side customizations (hooks, class overrides, JS, the
> 13 exported field bundles, the 2 balance-confirmation templates) travel with
> the repo.

---

## 2. Database-only customizations (not in the app code)

These are the ones the earlier by-feature/by-file chapters did **not** cover
because they aren't in the repo.

### 2.1 Client Scripts (7)

DB-stored form scripts. Several **duplicate or predate** the app's file-based
JS; note the ON/OFF state — disabled ones are leftovers, enabled ones are live
and can **coexist/conflict** with the app scripts.

| Doctype / View | Name | State | What it does | Note |
|----------------|------|-------|--------------|------|
| Journal Entry / Form | *Journal Entry* | **ON** | vehicle picker: caches account→vehicle subtypes, filters `custom_subtype` per account row | **Duplicates** the app's `journal_entry.js` (chapter 4 §1). Two copies of the same behavior run — consolidate |
| Material Request / Form | *Fetch Approver of Request Creator* | OFF | auto-fills `custom_creator_employee` from the session user and builds an approver chain by walking Employee `reports_to` | disabled; an alternate approval approach superseded by Dynamic Approval |
| Payment Entry / Form | *Cheque/Reference date as of Posting Date* | **ON** | sets `reference_date = posting_date` on load and on posting-date change | **live, app-code has no equivalent** — a genuine DB-only behavior |
| Purchase Invoice / Form | *Purchase Invoice* | OFF | old VAT/TDS field toggles using the **stale `Percentage (%)`** default | disabled; superseded by `purchase_taxes_common.js`. Leftover of the pre-migration VAT scheme |
| Purchase Order / Form | *Test* | OFF | `custom_approver` change → calls `get_reviewer_managers` to fill `custom_po_request_approver` | disabled; builds the PO approver chain (references a `get_reviewer_managers` method) |
| Purchase Order / Form | *Take me To Supplier Quotation* | **ON** | adds a "View Supplier Quotation Comparison" button routing to that report with `purchase_order` prefilled | live, useful — not in app code |
| Sales Invoice / Form | *Sales Invoice* | OFF | `update_fiscal_year` sets `custom_fiscal_year` from posting date; commented-out return naming-series switch | disabled; the app now handles fiscal year server-side |

**Action items surfaced:** the JE script duplicates app JS (dedupe); the PE
reference-date and PO comparison-button scripts are live-only-in-DB (export as
fixtures or port to the app if they must survive a re-install); the OFF scripts
are stale leftovers (safe to delete).

### 2.2 Custom Print Formats (8, all Jinja)

Not in the repo — the actual printed layouts for the business documents.

| Doctype | Print Format | Note |
|---------|--------------|------|
| Sales Invoice | **Avinash Sales invoice** | main tax-invoice layout (reads `custom_print_count` for the IRD copy title — chapter 4 §5a) |
| Sales Invoice | **Avinash Sales/Return Invoice** | combined sale/return layout |
| Sales Invoice | **Avinash Sales Return** | credit-note layout |
| Purchase Invoice | **Avinash Purchase Invoice** | |
| Purchase Invoice | **A5 Avinash Purchase Invoice** | A5-size variant |
| Purchase Order | **Avinash Purchase Order** | |
| Journal Entry | **Avinash Journal Entry** | |
| Supplier | IRS 1099 Form | ERPNext-standard (not Avinash-specific) |

> These should be exported as fixtures (`Print Format` filtered to the
> `Avinash *` names) so they ship with the app — today they exist only on
> avinas1.

### 2.3 Notifications (6)

All email; mostly ERPNext/HRMS-standard, none Avinash-specific business logic:
Exit Interview Scheduled (Exit Interview), Training Scheduled (Training Event),
**Material Request Receipt Notification** (Material Request, on value change —
"{{ doc.name }} has been received"), Retention Bonus alert, New-Fiscal-Year
notification, Training Feedback. Only the Material Request one is workflow-
relevant to this business.

### 2.4 Property Setters (421) — form-layout & behavior overrides

These modify **existing ERPNext field properties** (not new fields). The
patterns across the customized transaction doctypes:

- **Naming series patterns** set here (complement the `naming_series.py`
  engine): e.g. Purchase Invoice `naming_series.options =
  .{custom_abbr}.-PUR-.#######.-.{custom_fiscal_year}`, Journal Entry
  `ACC-JV-.YYYY.-`, Item `autoname = naming_series:`.
- **Hiding standard fields/sections** to declutter the Nepali forms — e.g.
  Purchase Invoice hides `taxes_section`, `tax_category`, `shipping_rule`,
  `incoterm`, `is_paid`, `supplier_invoice_details`, `set_posting_time`,
  `named_place`… (17+ hides); Material Request Item hides 8 standard sections;
  Payment Entry hides `taxes_and_charges_section`, `accounting_dimensions`.
- **List-view columns** (`in_list_view`) retargeted to the custom fields — e.g.
  Payment Entry/Journal Entry show `custom_name`, `custom_document_no`,
  `custom_p_type`; Purchase/Sales Invoice show `title` + `posting_date`.
- **Mandatory/optional flips** — e.g. Item `item_code.reqd = 0`,
  `item_name.reqd = 1`, `naming_series.reqd = 0`; the two 0-field bundles
  (Packed Item `rate` read-only, Purchase Taxes and Charges `add_deduct_tax`
  default = Deduct) are pure property setters.
- **field_order** rewritten on the heavily-customized doctypes to interleave the
  custom fields.

Highest property-setter counts: Purchase Invoice (45), Sales Invoice (40),
Purchase Receipt (32), Supplier Quotation (21), Payment Entry (19), Item (17),
Supplier Quotation Item (15), Sales Invoice Item / Purchase Invoice Item (13),
Sales Order (13), Delivery Note (11).

### 2.5 Custom DocPerm (490)

Permission-row overrides across ~150 doctypes (e.g. Fiscal Year 15, Company 13,
Contact 13, Supplier 13, Item 12, Address 11, Customer 11, Material Request 11).
These adjust which roles can read/write/create/submit each doctype relative to
the ERPNext defaults. They are DB-only and should be exported if the role model
must be reproduced.

---

## 3. Complete per-doctype matrix (meaningful customization)

Counts: **CF** custom fields · **PS** property setters · **CS** client scripts ·
**PF** print formats · **N** notifications · **DP** custom docperm. Doctypes
with only the audit block are in §4.

| Doctype | CF | PS | CS | PF | N | DP |
|---------|----|----|----|----|---|----|
| Purchase Invoice | 40 | 45 | 1 | 2 | 0 | 0 |
| Sales Invoice | 33 | 40 | 1 | 3 | 0 | 6 |
| Purchase Receipt | 32 | 32 | 0 | 0 | 0 | 0 |
| Supplier Quotation | 15 | 21 | 0 | 0 | 0 | 8 |
| Payment Entry | 18 | 19 | 1 | 0 | 0 | 3 |
| Purchase Order | 16 | 12 | 2 | 1 | 0 | 9 |
| Journal Entry | 14 | 9 | 1 | 1 | 0 | 5 |
| Employee | 38 | 12 | 0 | 0 | 0 | 6 |
| Item | 13 | 17 | 0 | 0 | 0 | 12 |
| Sales Order | 10 | 13 | 0 | 0 | 0 | 0 |
| Quotation | 8 | 9 | 0 | 0 | 0 | 0 |
| Delivery Note | 10 | 11 | 0 | 0 | 0 | 0 |
| Request for Quotation | 8 | 8 | 0 | 0 | 0 | 0 |
| Material Request | 11 | 6 | 1 | 0 | 1 | 11 |
| Company | 14 | 4 | 0 | 0 | 0 | 13 |
| Customer | 11 | 9 | 0 | 0 | 0 | 11 |
| Supplier | 8 | 5 | 0 | 1 | 0 | 13 |
| Supplier Quotation Item | 12 | 15 | 0 | 0 | 0 | 0 |
| Sales Invoice Item | 8 | 13 | 0 | 0 | 0 | 0 |
| Purchase Invoice Item | 11 | 13 | 0 | 0 | 0 | 0 |
| Purchase Receipt Item | 10 | 3 | 0 | 0 | 0 | 0 |
| Purchase Order Item | 10 | 1 | 0 | 0 | 0 | 0 |
| Quotation Item | 8 | 1 | 0 | 0 | 0 | 0 |
| Sales Order Item | 8 | 1 | 0 | 0 | 0 | 0 |
| Delivery Note Item | 8 | 3 | 0 | 0 | 0 | 0 |
| Request for Quotation Item | 1 | 10 | 0 | 0 | 0 | 0 |
| Material Request Item | 0 | 9 | 0 | 0 | 0 | 0 |
| Supplier Group | 6 | 9 | 0 | 0 | 0 | 0 |
| Customer Group | 6 | 7 | 0 | 0 | 0 | 9 |
| Item Group | 6 | 6 | 0 | 0 | 0 | 0 |
| Price List | 6 | 6 | 0 | 0 | 0 | 6 |
| Asset Category | 6 | 7 | 0 | 0 | 0 | 0 |
| Attendance | 11 | 0 | 0 | 0 | 0 | 5 |
| Salary Component | 12 | 0 | 0 | 0 | 0 | 3 |
| Fiscal Year | 2 | 4 | 0 | 0 | 1 | 15 |
| Vehicle | 6 | 5 | 0 | 0 | 0 | 4 |
| Account | 6 | 1 | 0 | 0 | 0 | 7 |
| Stock Reconciliation | 6 | 2 | 0 | 0 | 0 | 1 |
| Leave Application | 4 | 2 | 0 | 0 | 0 | 9 |
| Salary Slip | 4 | 2 | 0 | 0 | 0 | 4 |
| Item Price | 7 | 1 | 0 | 0 | 0 | 3 |
| Contact | 7 | 3 | 0 | 0 | 0 | 13 |
| Address | 8 | 3 | 0 | 0 | 0 | 11 |
| Shift Type | 4 | 0 | 0 | 0 | 0 | 4 |
| Stock Entry | 4 | 1 | 0 | 0 | 0 | 0 |
| Landed Cost Voucher | 5 | 1 | 0 | 0 | 0 | 0 |
| Job Card | 4 | 1 | 0 | 0 | 0 | 0 |
| Pick List | 4 | 1 | 0 | 0 | 0 | 0 |
| POS Invoice | 4 | 1 | 0 | 0 | 0 | 0 |
| Purchase Taxes and Charges | 0 | 5 | 0 | 0 | 0 | 0 |
| Packed Item | 0 | 1 | 0 | 0 | 0 | 0 |
| Journal Entry Account | 1 | 1 | 0 | 0 | 0 | 0 |
| Communication | 6 | 3 | 0 | 0 | 0 | 0 |
| Department | 10 | 0 | 0 | 0 | 0 | 5 |
| Designation | 9 | 0 | 0 | 0 | 0 | 3 |
| Expense Claim | 4 | 0 | 0 | 0 | 0 | 9 |
| Expense Claim Type | 6 | 0 | 0 | 0 | 0 | 3 |
| Branch | 6 | 0 | 0 | 0 | 0 | 3 |
| Bank Account | 5 | 0 | 0 | 0 | 0 | 3 |
| Batch | 5 | 0 | 0 | 0 | 0 | — |
| Holiday List | 6 | 0 | 0 | 0 | 0 | 2 |
| Leave Type | 6 | 0 | 0 | 0 | 0 | 4 |
| Mode of Payment | 6 | 0 | 0 | 0 | 0 | 4 |
| Timesheet | 5 | 0 | 0 | 0 | 0 | 7 |
| Vehicle Log | 5 | 0 | 0 | 0 | 0 | 2 |
| Employee Tax Exemption Proof Submission | 11 | 0 | 0 | 0 | 0 | 5 |
| Employee Tax Exemption Declaration | 9 | 0 | 0 | 0 | 0 | 5 |
| Terms and Conditions | 3 | 0 | 0 | 0 | 0 | 7 |
| Exit Interview | 2 | 0 | 0 | 0 | 1 | 0 |
| Retention Bonus | 2 | 0 | 0 | 0 | 1 | 0 |
| Training Event | 4 | 0 | 0 | 0 | 1 | 2 |
| Training Result | 2 | 0 | 0 | 0 | 1 | 0 |

(Plus the 28 file-based + 13 DB-only custom doctypes from chapters 9 & 11, and
Employee Checkin CF3/DP9, Payroll Entry CF4, Salary Structure CF4, Warehouse
CF2/DP9, Cost Center CF2/DP7, Territory DP8, Currency DP8, Employee Referral
DP8 — all carrying audit fields + permission tweaks.)

---

## 4. The 275 audit-only doctypes

These carry **only** the audit block (created/modified tracking) plus, for some,
standard permission rows — no dedicated fields, property setters, scripts,
formats, or notifications. They inherit the cross-cutting behavior (audit
stamping, dynamic-approval short-circuit, and — for transaction types —
fiscal-year filtering) but the app does nothing else specific to them. They span
CRM (Lead, Opportunity, Prospect, Campaign, Competitor…), the many HR masters
(Appraisal, Interview*, Employee Onboarding/Separation/Promotion/Transfer, Leave
Policy/Period/Encashment, Gratuity, Job *…), manufacturing (BOM*, Work Order,
Operation, Routing, Workstation*, Production Plan, Job Card details), quality
(Quality *), projects (Project Template/Type, Task Type, Milestone*),
accounting masters (Tax Category/Rule, Payment Terms Template, Finance Book,
Cost Center Allocation, Period Closing Voucher, Repost *), stock masters (Bin,
Serial and Batch Bundle, Putaway Rule, Stock Entry Type, Stock Ledger Entry),
and platform doctypes (Email Account, Webhook*, OAuth*, Print Settings, Role*,
Workflow*). The full list is 275 names; representative coverage above.

---

## 5. Reproducing the site elsewhere (fixtures to add)

Only the code side ships today. To make another site match avinas1, export these
as fixtures in `hooks.py` (or migrate the DB):

```python
fixtures = [
    "Custom Field",           # or filter to name like "%custom_%" per doctype
    "Property Setter",
    {"dt": "Client Script", "filters": {"dt": ["in", [
        "Payment Entry","Purchase Order","Journal Entry"]]}},  # the live ones
    {"dt": "Print Format", "filters": {"name": ["like", "Avinash %"]}},
    {"dt": "Custom DocPerm"},  # if the role model must match
    # (Document Template balance-confirmation already exported)
]
```

Then the DB-only customizations become version-controlled. Until then, treat
this chapter as the source of truth for what exists on avinas1 beyond the repo.
