# The Avinash Group App Handbook

*Everything that was built, and the ideas you need in order to own it.*

---

## Why this book exists

Between late June and early August 2026 a large amount of code went into
`avinashgroup_app` — a numbering engine, an IRD e-billing integration, six
dot-matrix print pipelines, an SMS rules engine, a legacy-data import path, a
dozen reports. There is already good reference documentation for it
(`docs/technical/`, 14 chapters; `docs/user_guide/`, 8 chapters; plus ~50
feature and handoff notes). What did *not* exist was a **path through it** — a
single ordered read that takes you from "I know Frappe a little" to "I can
change any part of this system without breaking the tax office."

That is this book. It is a *learning* document, not a reference. It repeats
very little of what the reference chapters say; instead it explains the
**problem each subsystem solves**, the **decision that shaped it**, and the
**trap that decision was avoiding** — then points you at the file.

## How to read it

Read Parts I and II once, properly, before touching anything. They are short
and everything else depends on them.

| Part | Chapters | Read it when |
| --- | --- | --- |
| **I — Foundations** | 1. The ground you stand on<br>2. Frappe, as this app actually uses it | Before your first change. Non-negotiable. |
| **II — The domain** | 3. Nepal: BS dates, VAT, and what the IRD demands | Before touching invoices, dates, or tax. |
| **III — The transaction core** | 4. Numbering<br>5. The Sales Invoice pipeline<br>6. CBMS / IRD e-billing | Before touching Sales Invoice in any way. |
| **IV — Getting ink on paper** | 7. Why raw ESC/P exists<br>8. Delivery, copies and counting | When a print is wrong, shifted, or miscounted. |
| **V — Platform services** | 9. SMS, approvals, access control<br>10. Attendance & payroll<br>11. Reports | When you extend one of them. |
| **VI — Legacy & judgement** | 12. Importing the old software's history<br>13. The rules this app taught<br>14. Playbooks | Ch. 13 is the highest-value chapter in the book. Read it early anyway. |

If you have one hour: **Chapter 2, Chapter 13, and the playbook you need.**

## What is true as of when

Written 2026-08-06 against the code in the repo on that date. Where this book
and an older `docs/*.md` note disagree, check the code — the code has been
right more often than the notes, because most notes were written mid-problem
and the problem moved.

A convention used throughout:

> **The trap.** A short box like this marks something that has actually bitten
> this codebase, not a hypothetical. Every one of them cost real debugging time.

## The map — where everything lives

```
avinashgroup_app/
├── hooks.py                     ← the spine. Read it first, and re-read it
│                                  every time you wonder "what runs when?"
├── custom_code/
│   ├── Override/
│   │   ├── naming_series.py     ← the numbering engine (~3,000 lines)
│   │   ├── overrides.py         ← 9 doctype class overrides
│   │   └── …                    ← core-behaviour monkey patches
│   ├── SalesInvoice/
│   │   ├── salesinvoice_taxes.py  ← VAT/excise pipeline
│   │   ├── save_and_submit.py     ← save == submit, atomically
│   │   ├── credit_control.py      ← credit limit enforcement
│   │   └── print_count.py         ← IRD copy titles + sheet counting
│   ├── CBMS/                    ← IRD e-billing (client, hooks, retry, backfill)
│   ├── printing/                ← escp_*.py (6 forms), overlay.py, chrome_pdf.py
│   ├── document_generator/      ← templated document/PDF/email engine
│   ├── globalfilter/            ← company-scoped link filtering
│   ├── dynamic_approval.py      ← the multi-level approval engine
│   ├── fiscal_year_filter.py    ← per-user fiscal-year visibility
│   └── excise_ledger.py         ← GL entry rewriting for excise
├── sparrow_sms/                 ← rule-driven SMS dispatch
├── biometric/                   ← iclock/ADMS device protocol, attendance sync
├── payroll/                     ← attendance allowances
├── legacy_print_import/         ← old software's print counts
├── legacy_annexure_import/      ← old software's VAT Annexure 7 sheets
├── avinash_group_app/
│   ├── doctype/                 ← 40+ custom doctypes
│   ├── report/                  ← 30+ reports
│   └── print_format/
└── scripts/                     ← seeders and the number tracer

k40_bridge/      ← Windows service: biometric devices  → server
print_bridge/    ← Windows service: server → dot-matrix printers
docs/            ← reference documentation (see docs/README.md)
docs/book/       ← you are here
```

Two other apps share the bench and matter occasionally:

- **`rdp_common_app`** — shared Nepali-calendar infrastructure: BS payroll,
  BS-period financial reports, deferred revenue/expense in BS months, the
  Nepali datepicker, the global "Fit Columns" report option. Covered in
  Chapter 10.
- **`sarathi_app`** — a separate product on a separate live site. It appears in
  this story only as the source of a pattern worth copying (insert-then-submit)
  and for IRD/CBMS work on `sarathilive`.

---

Next: **[Part I, Chapter 1 — The ground you stand on](01-foundations.md)**
