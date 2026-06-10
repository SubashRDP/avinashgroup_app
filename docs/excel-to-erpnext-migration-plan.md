# Excel → ERPNext Migration — Design Plan

> Working notes for migrating 10 years of historical transactions from Excel into ERPNext.
> Status: **design agreed, not yet built.** Next step is a Sales Invoice pilot.

## Goal
Migrate **10 years of transactions** — Sales Invoices, Purchase Invoices, Journal Entries,
Stock Entries — from Excel into ERPNext as **full transactional history** (not just opening
balances). Requirements the user stated, in their words:

- **Check first** — validate whether each row *can* be posted before touching the API.
- **Prompt the user with errors** if validation fails; fix, then re-check.
- **Only hit the API if everything is clean** (all-or-nothing per batch).
- **Fast** and **automatic**.
- **"Data making"** — derive/transform fields conditionally ("for this, set this") and
  auto-create missing masters.
- **Queue / line-up** of multiple files, processed in order.
- Maximize **already-built open-source software**; build as little as possible.
- Keep cost low — **no AI in the per-row loop.**

## Core flow (the gate)
```
PHASE 1 — CHECK (no commit, nothing written)
  read sheet -> apply rules -> validate every row vs ERPNext
  any errors? -> STOP, show user the error report -> user fixes -> re-check
                 all rows pass ->
PHASE 2 — COMMIT (only now hit the API)
  insert + submit each row -> write Migration Map -> next file in queue
```
All-or-nothing per batch: if *any* row fails, **nothing** commits. Safest for financial data.

## The stack (≈90% reused open source)
| Layer | Tool | Build / Reuse |
|---|---|---|
| Pipeline spine: Excel input, conditional transforms, error routing, queue, scheduling, REST load | **Apache Hop** (Apache-licensed OSS) | Reuse — does most of the job, visual/low-code |
| Real business-rule validation (does it balance? stock available? period open?) | **ERPNext** Data Import / a small validate endpoint | Built-in — **only ERPNext can run these rules** |
| Clean messy text (names, dates) — one-time pass inside the pipeline | **Ollama** (local LLM, free) | Reuse — called via Hop's REST/HTTP transform |
| Deep interactive cleaning / reconciliation (optional) | **OpenRefine** (OSS) | Optional |
| Idempotency + reference remapping (old Excel IDs -> new ERPNext names) | **Migration Map** (small custom doctype) | Build — the only real custom piece |

## Why Apache Hop is the spine
Maps directly onto the requirements, no custom engine needed:
| Requirement | Hop feature (already built) |
|---|---|
| Read Excel | Microsoft Excel Input transform |
| "Data making — for this, this" | Conditional execution, mapping, merge/split, lookups |
| Check first, errors to user | Validation transforms + error routing (bad rows -> error file) |
| Only commit if all good | Workflow conditional logic gates the load on a clean check |
| Hit the API | REST / HTTP output transforms |
| Queue / line up files | Workflows + Hop Server (scheduling + REST trigger API) |
| Automatic | Scheduled, unattended pipelines |

## Where Ollama fits (and where it does NOT)
- ✅ **Inside the Hop pipeline**: a REST Client transform POSTs a messy field to the local
  Ollama API (`http://localhost:11434/api/generate`) and gets back a cleaned value.
  Example: `"M/s ABC Traders."` -> `"ABC Traders"`.
- ✅ Guardrail: run as a **one-time cleaning pass**, write result to a column, human reviews
  financial-adjacent values, then **freeze** it. Don't re-call per run (non-deterministic).
- ❌ **Never** in the per-row financial loop — no LLM decides amounts, accounts, debit/credit,
  or the commit. Those stay deterministic code. (Cost + audit + reproducibility.)
- ❌ "Chat to build mappings" — **dropped.** Hop's visual editor already does "put this here"
  by drag-drop, deterministically. Chat-to-pipeline would be a fiddly, low-value custom layer.

## The one thing no tool can do off-the-shelf (a law, not a gap)
ERPNext's real validation — does the invoice balance, is stock available, is the accounting
period open — **only exists inside ERPNext.** Any external tool (Hop included) must **call
ERPNext** to truly validate. Hop handles structure/ordering/cleaning/queue/error-routing;
ERPNext handles the accounting truth. That split is unavoidable when migrating into an ERP.

## Rejected options (and why)
- **Apache NiFi / Airbyte / Meltano / dlt** — no ERPNext connector, don't know ERPNext's
  business rules; add infrastructure for no payoff here.
- **Old Frappe Data Migration Tool** (Plan / Connector / Mapping) — **removed in v14**, not in v15.
- **Custom staging doctype + validate/commit endpoints** — superseded by Apache Hop +
  ERPNext's own Data Import log (don't rebuild what ships).
- **AI in the per-row loop** — expensive, non-deterministic, unauditable for financial books.

## Hard gotchas for a 10-year live migration
- **Stock valuation recompute**: load stock transactions **chronologically, oldest-first**;
  enable Allow Negative Stock during import, re-disable after; consider a controlled
  Repost Item Valuation at the end.
- **Fiscal Years** for all 10 years must exist before backdated posting.
- **GL / stock freeze dates** open across the historical range during import, then re-lock.
- **Load order**: masters (Company, CoA, Customers, Suppliers, Items, Warehouses) first, then
  Orders -> Receipts/Delivery -> Invoices -> Journal Entries -> Payments.
- **Preserve original invoice numbers** (audit/legal) via naming.
- **Idempotency** via Migration Map (`source_id -> erpnext_docname`) so re-runs never duplicate
  and cross-document references (SI -> SO/DN, Payment -> Invoice) resolve to new names.
- **Backdated submits** may need an approval/workflow bypass — see existing
  `custom_code/workflow_admin_bypass.py` in this app.

## Next step (pilot)
1. Stand up Apache Hop + a **test** ERPNext site + Ollama (test site, never production).
2. Build ONE Sales Invoice pipeline: Excel -> Ollama clean -> validate via ERPNext -> load.
3. Prove it on ~20 rows; inspect the error report.
4. Need: one sample Sales Invoice sheet (column headers + 2-3 rows) to write the real mapping.

## References
- Apache Hop: https://hop.apache.org/
- ERPNext Data Import: https://docs.frappe.io/erpnext/data-import
- Frappe Data Migration Tool (legacy, removed in v14): https://docs.frappe.io/framework/user/en/guides/data/using-data-migration-tool
- Ollama API: https://github.com/ollama/ollama/blob/main/docs/api.md
- OpenRefine: https://openrefine.org/
