# Reports & Portal Pages — Technical Reference

> Chapter 8 of the technical documentation. Audience: developers.
> User-facing guide: [`../user_guide/07-reports.md`](../user_guide/07-reports.md)
> The HR/BS attendance reports are detailed in chapter 3 §7; this chapter
> catalogues the financial/sales/purchase suite and the portal pages.

All reports are **Script Reports** under `avinash_group_app/report/`, run
synchronously, and mostly build their own total rows. Company/party/item filter
dropdowns come from whitelisted `get_company_*` helpers scoped by
`custom_company`. Numbers use Indian lakh/crore grouping (`_fmt_inr`), NPR.

## 1. Cross-cutting print/PDF infrastructure

- **Shared BS-date filters**: reports with plain Date filters get a BS "Miti"
  twin input + "📅 Select Month" (whole-BS-month) from
  `rdp_common_app/public/js/report_nepali_date.js` (external app hook). Used
  by Gas Purchase, Sales Stock Ledger, Party Ledger Summary.
- **`public/js/report_print_orientation.js`** (global, query-report routes
  only): `window.askPrintOrientation` dialog; wraps every "Download PDF" inner
  button to append `&orientation=`; shims `window.open` to inject
  `report_print_portrait.css` + fit-to-width for print popups; shims
  `frappe.render_pdf` to inline black-grid styling plus an optional per-report
  footer (`window.__rdpPrintFooter`, used by Advance Tax TDS's
  Prepared/Checked/Verified signature block).
- **Three PDF patterns**: **A** — report-local `*_pdf.html` template with
  whitelisted `download_pdf` (re-runs execute, paginates in Python, in-body
  "Page X of Y"; Print calls the same PDF inline): Party Ledger, Party Ledger
  Summary, Sales/Purchase Register, Receipt Register, Loan Summary, One Lakh
  Above, the three Sales Analysis reports. **B** — shared helper only: Advance
  Tax TDS, Loan Summary dialogs. **C** — stock Frappe print.

## 2. Report catalogue

(Full field-level details are in the code; this is the authoritative summary.
"Miti" = BS date sourced from `custom_*_miti` custom fields.)

### Compliance (Nepal IRD)

| Report | Purpose | Source | Key filters |
|--------|---------|--------|-------------|
| **Advance Tax TDS Details** | अग्रिम कर TDS withholding statement per supplier per Tax Withholding Category, sectioned by IRD खाता नं with Nepali headers and signature footer | PI+items ⋈ Supplier; category parsed from `custom_tax_withholding_category_custom` via regex (rate/khata/title) | company*, dates* |
| **One Lakh Above Transactions** | parties whose taxable or exempt totals ≥ NPR 100,000 (IRD annexure); taxable = item amounts with `custom_vat_amount≠0`; returns subtract | SI+items ∪ PI+items | company*, dates* |
| **Sales Register** | खरिद/बिक्री VAT register: per SI, buckets tax-free / export / taxable / VAT via `custom_vat_apply_on` + territory | SI ⋈ SII ⋈ Customer | company, dates*, customer, is_return |
| **Purchase Register** | per PI: tax-free / taxable / import / capitalized buckets (`custom_vat_apply_on` × `is_fixed_asset` × supplier territory) + VATs + qty | PI ⋈ PII ⋈ Supplier ⋈ Item | company, dates*, supplier, purchase_type, is_return |

### Ledgers & treasury

| Report | Purpose |
|--------|---------|
| **Party Ledger** (1278 lines) | Tally-style party statement: opening → vouchers with running balance → closing; BS Miti per doctype; custom voucher display names (`custom_branch_name`/`custom_name`); optional item-level detailed mapping, remarks; JEs split per account; multi-party grouped mode; gated `exclude_account_patterns` (used by the Customer Statement portal to hide deposit/security accounts); Contract-Form JEs included by default. Landscape PDF pattern A. **Engine of the `/customer_statement` portal** |
| **Party Ledger Summary** | one line per party (opening/debit/credit/closing); Super Summary or Group Wise layouts; custom Excel export with Dr/Cr columns |
| **Net Position of Cash and Bank** | every leaf account under "Cash and Cash Equivalent": opening / receipts / payments / closing; PDC gating; multi-currency suppression |
| **Loan Summary** | borrowings matrix: loan types (children of Short/Long Term Borrowings) × company columns, subtotals, ratio row, Show Details expands sub-accounts. ⚠️ from_date collected but unused (cumulative to To Date) |
| **Receipt Register** | customer receipts (PE type Receive) in 3 views: Date Wise / Customer Wise (banner headers) / Summary; cheque no "1" suppressed |

### Financial statements

| Report | Purpose |
|--------|---------|
| **Consolidated Financial Statement Hierarchy** (734 lines) | consolidated BS/P&L/Cash-Flow across an **arbitrary company set** (no parent group company needed): monkey-patches ERPNext's consolidated engine, replaces per-root GL fetches with one aggregated SQL (needs the `fin_stmt_agg_index` from patch `add_gl_entry_fin_stmt_agg_index`), adds row Total column, common-accounts filtering, depth cap, fixes an ERPNext cash-flow bug. Has its own `USER_DOCS.md` |
| **Profit and Loss Hierarchy** | single-company ERPNext P&L + "Account Hierarchy Level" control that blanks group rows above depth N; Report/Growth/Margin views |

### Sales analysis & industry

| Report | Purpose |
|--------|---------|
| **SA — Customer wise Summary** | one row per customer: qty, gross (incl. excise), optional return/net columns |
| **SA — Customer wise Details** | Customer → product (UOM) drill-down with product/customer/grand totals |
| **SA — Product wise Invoice Details** | Product → customer → invoice/return rows; `build_rows(include_agent)` reused by the portal (agent rows dropped there). ⚠️ Frappe drops falsy filters — unchecked Include Return never reaches the server (treated OFF); JS default keeps it ON initially |
| **Gas Purchase Report** | LPG procurement register per Store Receipt combining gas PIs, PRs, Service Charge ICP/NA invoices; refinery/tanker/IOC-challan columns; BS-miti period filtering in Python; voucher-code parsing (`NGK-ICP-00218-82/83` → 218) |
| **Sales Stock Ledger** | sales-driven stock movement (submitted SIs of stock items), Detail/Summarized modes, BS dates via `nepali_datetime`, sales/return merge, colored voucher badges. Fix history: `docs/sales_stock_ledger_fixes.md` |
| **Avinas Vehicle Expense** | vehicle-wise Fuel/Repair/Others buckets from PI items + JE lines matched by account-name LIKE patterns; vehicle = `custom_subtype` shown as license plate. Doc: `docs/vehicle_expense_report.md` |
| **Custom Supplier Quotation Comparison** | pivoted item × supplier price comparison with net/VAT/discount/invoice-amount summary rows, near-expiry coloring, "Select Default Supplier" tool, PO→RFQ auto-fill |

### Missing

`customer_vendor_ledger_summary/` contains only a stale `__pycache__` — the
report has **no source** and is effectively deleted. (The Customer Ledger
Summary referenced by credit-control code is ERPNext's standard report.)

## 3. Common gotchas

- Sales/Purchase Register interpolate `company`/`customer` strings into SQL
  (dates are bound params) — keep filter values from link fields only.
- One row per voucher × party in Party Ledger → wide ranges get large;
  enrichment is batched in IN-chunks of 500.
- Reports stay under Frappe's 15 s prepared-report auto-switch by hitting
  indexed columns first; the daily-entry and fin-stmt indexes come from
  patches.

## 4. HR/BS reports

Monthly Attendance BS, Monthly Attendance Summary BS, Work On Holiday BS,
Yearly Leave Details BS, Avinas Salary Statement — see chapter 3 §7.

## 5. Portal pages (`templates/pages/`)

All require login; customer pages require the **Customer** role and resolve
the user's customers via `Portal User`, re-validating every AJAX request
(`_resolve_request` — companies/customers outside the user's set are rejected;
an empty party list is filled with the user's own customers, never "all").

| Route | Purpose |
|-------|---------|
| `/customer_statement` | the customer's own Party-Ledger statement + Portrait PDF; passes `exclude_account_patterns` so deposit/security accounts (313101/313102/313201 name patterns) never show or affect balances; dual AD+BS date pickers (AD is source of truth) |
| `/product_wise_invoice_details` | product → invoice drill-down for the customer's own accounts; reuses the report's `build_rows(include_agent=False)`; default company prefers Nepal Gas Udhyog (Karnali) |
| `/place_order` | LP Gas Sales Order placement: fixed LP Gas item, cylinder-size UOMs, rates via Item Price, client VAT math, `create_sales_order` re-validates server-side and submits with `ignore_permissions` |
| `/rfq/<name>` | supplier RFQ portal — see chapter 4 §9 |

Docs: `docs/product wise invoice customer portal.md`.
