# Reports Appendix — Full Per-Report Reference

> Chapter 12 of the technical documentation. The complete reference for every
> report: purpose, source tables, all filters (with defaults), key columns,
> notable logic, PDF pattern, roles, and audience. Chapter 8 is the catalogue;
> this is the deep detail. The 5 HR/BS attendance reports + salary statement
> are in chapter 3 §7. All are Script Reports under
> `avinash_group_app/report/<name>/` with `.py` (query/rows), `.js` (filters +
> print), `.json` (config), and often `<name>_pdf.html` (PDF template).

## Shared infrastructure

- **BS-date filter twins** come from `rdp_common_app`'s
  `report_nepali_date.js`: any Date filter gets a BS "Miti" input + "📅 Select
  Month". Used by Gas Purchase, Sales Stock Ledger, Party Ledger Summary.
- **`report_print_orientation.js`** (global on query-report routes): the
  Portrait/Landscape dialog (`window.askPrintOrientation`), a wrapper that
  appends `&orientation=` to every "Download PDF" button, a `window.open` shim
  that injects `report_print_portrait.css` and fits wide tables, and a
  `frappe.render_pdf` shim that inlines black-grid styling + optional
  `window.__rdpPrintFooter` (Advance Tax TDS uses it for the signature block).
- **PDF patterns:** **A** = report-local `*_pdf.html` + whitelisted
  `download_pdf` (re-runs execute, paginates in Python, in-body "Page X of Y",
  Print calls the same PDF inline, "Pick Columns" support). **B** = shared
  helper only. **C** = stock Frappe print.
- **Number formatting:** `_fmt_inr` (Indian lakh/crore grouping, blanks zero),
  `_fmt_qty` (3 dp). Currency NPR.

---

## 1. Advance Tax TDS Details

- **Purpose:** Nepali IRD advance-tax (अग्रिम कर) withholding statement — per
  supplier, per Tax Withholding Category, the TDS-eligible turnover and TDS
  withheld, sectioned by IRD account number (खाता नं) with Nepali headers and a
  Prepared/Checked/Verified signature footer.
- **Source:** `Purchase Invoice ⋈ Purchase Invoice Item` (INNER) ⋈ `Supplier`
  (LEFT, for PAN). Category from `custom_tax_withholding_category_custom`.
- **Filters:** `company`* (default user default), `from_date`* (month start),
  `to_date`* (today), `Fit Columns` (view toggle, default 1, excluded from
  print).
- **Columns:** क्र.सं. / नाम / कारोबार रकम (turnover) / खाता नं / अग्रिम कर रकम
  (TDS) / पान नम्बर / रेट.
- **Logic:** category strings like `"2.5% -11124 TDS-Other Entities"` are
  regex-parsed into rate/khata/title. Turnover = `SUM(item amount WHERE
  apply_tds=1)`; TDS = `SUM(custom_tds_amount)`; grouped by supplier + category.
  Section header/total + grand total rows bolded. `custom_tds_apply_on='Amount'`
  shows rate as "amount".
- **PDF:** B (shared helper + signature footer). **Roles:** Accounts Manager/User.
- **Audience:** accountant/auditor — IRD TDS return.

## 2. Avinas Vehicle Expense ("Nepal Gas Vehicle Expense")

- **Purpose:** vehicle-wise operating expense (Fuel / Repair / Others) across
  both Purchase Invoices and Journal Entries, one row per vehicle + grand total.
  Company-agnostic — buckets keyed by account-name LIKE patterns.
- **Source:** `PI ⋈ PII` (amount `pic.amount`, vehicle `pic.custom_subtype`,
  account `pic.expense_account`) UNION ALL `JE ⋈ JEA` (amount `jea.debit −
  jea.credit`, vehicle `jea.custom_subtype`, account `jea.account`), both ⋈
  `Account`, LEFT ⋈ `Vehicle` for the license plate.
- **Bucket mapping:** Fuel `%Fuel Expenses%`; Repair `%R & M - Vehicles%`;
  Others `%Other Vehicle Expenses%`.
- **Filters:** `company`* (user default), `Vehicle No` (Link), `Filter By`
  (Fiscal Year / Date Range, default Fiscal Year), `Fiscal Year`,
  `Start/End Date`. Company applies to `acc.company`.
- **Columns:** Vehicle No / Fuel / Repair / Others (Currency).
- **Logic:** blank vehicles excluded; grouped by `COALESCE(license_plate,
  vehicle)`; Vehicle No renders as a link to the Vehicle. Doc:
  `docs/vehicle_expense_report.md` (notes open items: filter label mismatch, BS
  filter not yet done, stale test).
- **Roles:** Accounts User/Manager, System Manager. **Audience:** management/
  accountant (fleet cost).

## 3. Consolidated Financial Statement Hierarchy

- **Purpose:** consolidated Balance Sheet / P&L / Cash Flow across **any**
  arbitrary set of companies — no shared parent group company required (unlike
  ERPNext's built-in). Adds a per-row Total column, hides accounts not common
  to all selected companies, caps tree depth.
- **Source:** `GL Entry` (aggregated), `Account`, Company, Fiscal Year, Finance
  Book.
- **Filters:** `Companies` (MultiSelect, empty = all), `Filter Based On`
  (Fiscal Year / Date Range), `Start/End Date`, `Start/End Year`,
  `Finance Book`, `Report` (P&L / Balance Sheet / Cash Flow, default Balance
  Sheet), `Common Accounts scope` (Selected / All), `Currency`,
  `Accumulated Values in Group Company`, `Include Default FB Entries` (1),
  `Show zero values`, `Account Hierarchy Level` (1..max depth).
- **Logic:** monkey-patches ERPNext's consolidated engine
  (`get_companies`, `set_gl_entries_by_account`,
  `get_account_type_based_gl_data`, `get_accounts`) to accept an explicit
  company list and replace per-root GL fetches with **one aggregated SQL**
  producing two synthetic opening/period entries per account/company (with
  presentation-currency conversion + finance-book scope). Fixes an ERPNext Cash
  Flow bug. `add_row_total_column` sums the row; `filter_shared_accounts` drops
  accounts absent from any company (with orphan re-parenting);
  `apply_account_level_filter` caps depth. **Needs** the `fin_stmt_agg_index`
  (patch `add_gl_entry_fin_stmt_agg_index`) for speed. Has `USER_DOCS.md`.
- **Roles:** Accounts User/Manager, **Auditor**. **Audience:** management/auditor.

## 4. Profit and Loss Hierarchy

- **Purpose:** single-company ERPNext P&L extended with an "Account Hierarchy
  Level" control that blanks group-account rows above a chosen indent level;
  Report/Growth/Margin views.
- **Source:** `GL Entry` via `erpnext.financial_statements`.
- **Filters:** base financial-statement filters + `Select View` (Report/Growth/
  Margin), `Accumulated Values` (1), `Include Default FB Entries` (1),
  `Show zero values`, `Account Hierarchy Level` (1–6, default 3).
- **Logic:** Income (Credit) + Expense (Debit) with `ignore_closing_entries`;
  net profit/loss appended; group rows with indent < level are cleared while
  leaves + "Profit for the year" stay.
- **Roles:** Accounts User/Manager, Auditor. **Audience:** management/auditor.

## 5. Custom Supplier Quotation Comparison

- **Purpose:** pivoted procurement comparison — items as rows, suppliers as
  dynamic columns, per-item price + summary rows (Net Total, discount, Taxable,
  VAT, Invoice Amount). Includes a "Select Default Supplier" tool.
- **Source:** `Supplier Quotation ⋈ Supplier Quotation Item`, optionally driven
  from a PO → RFQ link.
- **Filters:** `company`*, `from_date` (−1 month), `to_date` (today), `Item`
  (scoped), `Supplier` (MultiSelect, company-scoped `get_company_suppliers`),
  `Supplier Quotation` (MultiSelect docstatus<2), `Request for Quotation`,
  `Categorize by` (Supplier/Item), `Include Expired` (0), `Preferred Quotation`
  (1 → `custom_preferred_quotation=1`), `Purchase Order` (auto-fills RFQ).
- **Logic:** price field default `base_amount`; keeps the lowest price when
  multiple quotes; summary rows from quotation-level discount/tax
  (`apply_discount_on` splits Net-Total vs Grand-Total discount); Invoice
  Amount from `base_grand_total`; supplier columns generated via
  `frappe.scrub`; near-expiry `valid_till` colored.
- **Roles:** Manufacturing/Purchase Manager, Purchase/Stock User.
  **Audience:** procurement.

## 6. Gas Purchase Report

- **Purpose:** LPG procurement register — one row per Store Receipt combining
  gas PIs, PRs, and Service Charge (ICP/NA) invoices into refinery/tanker/IOC-
  challan/qty/rate/price/VAT/ICP/ICT-VAT/N.A./total columns, by BS month.
- **Source:** `PI(+Item)`, `PR(+Item)` keyed by custom fields
  (`custom_purchase_type`, `custom_receipt_type`, `custom_store_receipt_*`,
  `custom_refinery`, `custom_pdo_no`, `custom_vehicle_no`,
  `custom_ioc_challan_*`, `custom_name_of_transportor`). Type constants: "Gas
  Purchase Invoice", "Gas Purchase Receipt", "Service Charge ICP", "Service
  Charge NA".
- **Filters:** `company` (MultiSelect), `from_date`/`to_date` (BS twins),
  `Refinery` (MultiSelect from the field's own options via `get_refineries`).
- **Logic:** an invoiced receipt is represented by its invoice
  (`pii.purchase_receipt`), else by the receipt; period filtered in Python on
  BS miti (From/To Miti or BS Year+Month + optional AD range); service charges
  mapped by document number parsed from `custom_store_receipt_no` or a coded
  voucher name (`NGK-ICP-00218-82/83` → 218). Rate = Price/Qty; Total = Price +
  other_expense − ICT VAT. Total row appended.
- **Roles:** Accounts Manager/User. **Audience:** accountant/management (NOC gas
  procurement, excise/ICP/VAT).

## 7. Loan Summary

- **Purpose:** borrowings matrix — each loan type (children of "Short/Long Term
  Borrowings") × company columns, subtotals, grand total, per-company ratio;
  "Show Details" expands sub-accounts.
- **Source:** `Account` (tree under the two group names) + `GL Entry`
  (`SUM(credit − debit) WHERE posting_date <= to_date`).
- **Filters:** `Company` (MultiSelect, empty = all), `from_date` (year start),
  `to_date`* (today), `Show Details` (0).
- **Logic:** `_normalize` collapses label variants ("Short Term Loan (STL)");
  Cr/Dr suffix with accounting dash for zero; Ratio = company grand / all-company
  grand. Standalone PDF (Landscape) with in-body pagination; header falls back
  to "Nepal Gas Group". ⚠️ `from_date` collected but **unused** (cumulative to
  To Date).
- **PDF:** A. **Roles:** Accounts Manager/User. **Audience:** management/accountant.

## 8. Net Position of Cash and Bank

- **Purpose:** treasury cash-position — every leaf account under "Cash and Cash
  Equivalent": Opening / Receipts / Payments / Closing over the period + a
  consolidated total.
- **Source:** `Account` (group matched by name, `&`→`and`) + `GL Entry`
  (opening = balance before from_date + in-period is_opening; movements =
  debit/credit sums).
- **Filters:** `company`* (user default), `from_date`* (year start), `to_date`*
  (year end), `Cash/Bank Codes` (MultiSelect), `Suppress Local Currency
  Equivalents`, `Consider Post Dated Cheques` (gates the `is_pdc` clause via
  `_gl_has_pdc_column`), `Show Zero Balance`.
- **Columns:** Cash/Bank Code / Description (Link Account) / Cash Book / Currency
  Code / Opening / Receipts / Payments / Closing.
- **Logic:** Closing = Opening + Receipts − Payments; zero-movement accounts
  skipped unless Show Zero; multi-currency optionally forced to company
  currency; totals in company currency.
- **Roles:** Accounts Manager/User, System Manager. **Audience:** treasury/
  management.

## 9. One Lakh Above Transactions

- **Purpose:** Nepal IRD annexure — every customer (Sale) and supplier
  (Purchase) whose taxable OR exempt total ≥ ₨100,000 in the period.
  `THRESHOLD = 100000`.
- **Source:** `SI+Item ⋈ Customer` and `PI+Item ⋈ Supplier`.
- **Filters:** `company`* (MultiSelect), `from_date`* (month start), `to_date`*
  (today), `Fit Columns` (1).
- **Columns:** PAN / Name of Tax Payer / Trade Name Type (constant 'E') /
  Purchase-Sale ('S'/'P') / Taxable Amount / Exempted Amount.
- **Logic:** taxable = `SUM(ABS(amount) WHERE custom_vat_amount≠0)`, exempt =
  VAT-0 lines; returns subtract as negative ABS; `HAVING ≥ threshold` +
  Python re-filter; sorted by name.
- **PDF:** C (standalone HTML/PDF, Portrait). **Roles:** Accounts Manager/User.
  **Audience:** auditor/accountant — IRD filing. ⚠️ `trade_name_type` hardcoded
  'E'; no totals row.

## 10. Party Ledger (1278 lines)

- **Purpose:** full customer/supplier statement — Opening → each voucher (with
  running balance) → "For the Periods" → Closing, with BS Miti dates, custom
  voucher display names, optional item-level detail, remarks, Contract-Form
  handling. Multi-party = one section per party. **Engine of the
  `/customer_statement` portal.**
- **Source:** `GL Entry` (`is_cancelled=0`, company, party_type) LEFT ⋈ SI/PI
  for return detection; enrichment from SI/PI Items, Payment Entry (+refs),
  Journal Entry, Customer/Supplier.
- **Filters:** `company`* (user default), `Party Type` (Customer/Supplier,
  default Customer), `Party` (MultiSelect; 1 → flat, 0/2+ → grouped),
  `Account` (MultiSelect scoped to ledger accounts), `from_date`* (month start),
  `to_date`* (today), `Voucher No` (LIKE), `Show Remarks`, `Show Balance`
  (default 1 — blanks running balance on transaction rows), `Detailed Mapping`
  (item sub-rows), `Show Contract Form` (**default 1** — includes JE
  `custom_p_type='Contract Form'`), `Fit Columns`.
- **Columns:** S.No / Date / Miti / Voucher No / Description / [detail qty/uom/
  rate/amount] / Debit / Credit / Balance / [Remarks].
- **Logic:** Opening = pre-period balance + in-period is_opening; merge collapses
  multi-line vouchers per voucher but splits JEs per account (contras shown
  separately); BS miti from `custom_invoice_miti`/`custom_posting_miti`/
  `custom_nepali_miti`; display names from `custom_branch_name`/`custom_name`
  (real docname kept for links); remarks from `custom_narration`/`memo`/
  `remarks`/`user_remark`; detailed mapping adds indented item + VAT + payment-
  reference/advance rows. Two gated WHERE conditions applied to opening+period
  alike: Contract-Form exclusion and `exclude_account_patterns` (the portal uses
  it to hide deposit/security accounts). Enrichment batched in IN-chunks of 500.
- **PDF:** A (Landscape, `party_ledger_pdf.html`). **Roles:** Accounts Manager/
  User, Employee Self Service, Sales person, Account Team.
  **Audience:** accountant/management + customers (portal). ⚠️ One row per
  voucher × party → large for wide ranges.

## 11. Party Ledger Summary (526 lines)

- **Purpose:** one aggregate line per party (Opening / Debit / Credit / Closing)
  — "Super Summary" (flat + grand total) or "Group Wise" (per-group subtotals).
  Custom Excel export with Dr/Cr columns.
- **Source:** `GL Entry GROUP BY party` ⋈ Customer/Supplier + their Groups.
- **Filters:** `Report Type`* (Super Summary/Group Wise), `company`*,
  `Party Type`*, `Party Group` (MultiSelect, `get_company_party_groups`),
  `Party` (MultiSelect), `from_date`* (month start), `to_date`* (today),
  `Show Zero Balance`, `Closing DB/CR` (blank/DB/CR), `Fit Columns`.
- **Columns:** Customer/Vendor Code / Name / VAT-PAN / Opening / Debit / Credit
  / Closing.
- **Logic:** company-scoped via party `custom_company` EXISTS; opening =
  pre-period + is_opening; net-zero hidden unless Show Zero; Closing DB/CR keeps
  debit(>0)/credit(<0) closings. Super Summary appends "Closing Totals (N
  Customers/Vendors)"; Group Wise emits group header → parties → "Group Total
  for: X". Excel export shows Opening/Closing magnitude + Dr/Cr columns
  (standard Export overridden). BS month picker repositioned next to Fit
  Columns.
- **PDF:** A (default Portrait). **Roles:** Accounts Manager/User, Account Team.
  **Audience:** accountant/management.

## 12. Purchase Register Report

- **Purpose:** Nepal VAT purchase register (खरिद खाता) — per PI, value split
  into Tax-Free / Taxable (domestic) / Taxable Import / Capitalized
  (fixed-asset) with their VATs + Total VAT + qty. "Is Return" mode shows
  returns as positives.
- **Source:** `PI+Item ⋈ Supplier` (tax_id, `custom_territory`) ⋈ `Item`
  (`is_fixed_asset`), `GROUP BY pi.name`.
- **Filters:** `company` (MultiSelect), `from_date`* (month start), `to_date`*
  (today), `Supplier` (MultiSelect, `get_company_suppliers`), `Purchase Type`
  (MultiSelect → filters `custom_purchase_type`), `Is Return`, `Fit Columns` (1).
- **Columns:** Date / Miti / Purchase Type / Voucher No / Supplier Invoice
  No/Date/Miti / Supplier Name / VAT Number / Purchase / Tax Free / Taxable /
  VAT / Taxable Import / Import VAT / Capitalized / Capitalized VAT / Total VAT
  / QTY.
- **Logic:** bucketing by `custom_vat_apply_on` × `is_fixed_asset` ×
  `custom_territory` (Nepal / non-Nepal). Purchase =
  `custom_total_amount_including_excise`. Miti first token. Returns → abs().
  Voucher No encoded `custom_name::docname`. Shares the Pick-Columns patch with
  Sales Register.
- **PDF:** A (Landscape). **Roles:** Accounts Manager/User. **Audience:**
  accountant/auditor — IRD VAT register.

## 13. Sales Register Report

- **Purpose:** VAT sales register — per submitted SI, split tax-free / export /
  taxable / VAT. Returns view (abs).
- **Source:** `SI ⋈ SII ⋈ Customer`, `GROUP BY si.name`. Buckets = conditional
  SUM over `custom_vat_apply_on` + territory.
- **Filters:** `company`, `from_date`*/`to_date`*, `customer`, `is_return`,
  `Fit Columns`.
- **PDF:** A (Landscape, Pick-Columns). ⚠️ `company`/`customer` string-
  interpolated into SQL; dates are bound params.
- **Roles:** Accounts Manager/User. **Audience:** accountant/auditor — VAT return.

## 14. Receipt Register (451 lines)

- **Purpose:** customer receipts (Payment Entry, Receive) in 3 views — Date-Wise
  / Customer-Wise (merged banner) / Summary. Shows cheque no + remarks.
- **Source:** `Payment Entry` (`docstatus=1`, `party_type='Customer'`,
  `payment_type='Receive'`); fields incl. `custom_posting_miti`, `custom_name`,
  `paid_to`, `reference_no`, `received_amount`, `custom_remark`.
- **Filters:** `View`* (3, default Date Wise), `company`* (user default),
  `from_date`* (month start), `to_date`* (today), `Customer` (MultiSelect,
  `get_company_customers`), `Bank/Cash Account` (MultiSelect of company
  Bank/Cash via `get_company_bank_accounts`, filters `paid_to`), `Fit Columns`.
- **Columns:** vary by view; all views total per group + grand total.
- **Logic:** cheque "1" placeholder suppressed; Miti first token of
  `custom_posting_miti`; customer-header rows render as full-width grey banners
  (re-tagged on scroll due to datatable virtualization). Own PDF: Date-Wise →
  Landscape, others → Portrait.
- **PDF:** A. **Roles:** Accounts Manager/User. **Audience:** accountant/cashier.
  ⚠️ "GL Code" column is an unfinalized placeholder.

## 15. Sales Analysis — Customer wise Summary (391 lines)

- **Purpose:** one row per customer — Sales Qty + Gross Value (incl. excise);
  with Include Return: Return Qty/Value + Net Sales; grand total row.
- **Source:** `SI+Item ⋈ Customer`, `GROUP BY customer`.
- **Filters:** `company` (MultiSelect), `from_date`*/`to_date`*, `Customer`
  (`get_company_customers`), `Customer Group` (`get_company_customer_groups`),
  `Item` (`get_company_items`), `Include Return` (default 1), `Fit Columns`.
- **Columns:** Customer Code (Link) / Name / VAT-PAN / Sales Qty / Gross Value;
  +Return Qty/Value, Net Sales Qty/Value when Include Return.
- **Logic:** Gross = `amount + custom_excise_value`; returns negated to positive;
  Net = Sales − Return in Python; Return/Net columns only generated when Include
  Return on.
- **PDF:** A (Landscape). **Roles:** Accounts Manager/User. **Audience:** sales
  management. ⚠️ `item_code` narrows lines but grouping stays per customer.

## 16. Sales Analysis — Customer wise Details (360 lines)

- **Purpose:** Customer → Product (UOM) drill-down: qty / value / VAT / total-
  incl-VAT + per-customer and grand rollups.
- **Source:** `SII ⋈ SI ⋈ Item ⋈ Customer`, `GROUP BY customer, item, uom,
  is_return`.
- **Filters:** `company`, `from_date`*/`to_date`*, `Customer`, `Product`
  (`get_company_items`), `Include Return` (default 1), `Fit Columns`.
- **Logic:** Value = `amount + custom_excise_value`; VAT = `custom_vat_amount`;
  returns flipped positive; UOM suffix only when an item sold in >1 UOM. ⚠️
  Frappe drops falsy filters → unchecked Include Return never reaches the server
  (`cint(None)=0` = OFF); JS default 1 keeps it on at first load.
- **PDF:** A (Portrait). **Roles:** Accounts Manager/User. **Audience:** sales.
  ⚠️ Granularity customer × item × UOM → large.

## 17. Sales Analysis — Product wise Invoice Details (424 lines)

- **Purpose:** Product → (No Agent) → Customer → invoice-level rows (Invoice then
  Return sections), with Customer/Agent/Product totals + grand totals.
  `build_rows` is reused by the `/product_wise_invoice_details` portal (agent
  rows dropped there).
- **Source:** `SII ⋈ SI`; item/customer names via small IN-lookups (deliberately
  not joined, to keep the heavy query lean), sorted in Python.
- **Filters:** `company`, `from_date`*/`to_date`*, `Customer`, `Product`,
  `Include Return` (default 1), `Fit Columns`.
- **Logic:** same Value/VAT/return-flip + Include-Return quirk. `include_agent`
  toggles the No-Agent/Agent rows (portal passes False). Per-customer order
  (2026-06-28): Invoice rows → Return rows → summary (Customer Sales above
  Customer Returns); section labels bold. Miti from `custom_invoice_miti`.
- **PDF:** A (Landscape). **Roles:** Accounts Manager/User. **Audience:** sales +
  customers (portal).

## 18. Sales Stock Ledger (500 lines)

- **Purpose:** sales-driven stock movement from submitted SIs of stock items —
  Detail (per line) or Summarized (per item/UOM, optional sales/return merge).
  BS posting date per row.
- **Source:** `SI ⋈ SII ⋈ Item` (`is_stock_item=1`).
- **Filters:** `Report Type`* (Detail/Summarized), `company` (user default;
  on-change clears/refreshes dependents), `Branch` (company-scoped),
  `from_date`* (month start), `to_date`* (month end) — BS twins, `Warehouse`
  (company-scoped), `Item` (via Item Default.company), `Item Group`
  (custom_company), `Price List`, `UOM`, `Voucher No` (SI, scoped),
  `Voucher Type` (Sales Invoice/Sales Return), `Fit Columns` (1), `Sales/Return
  Merge`.
- **Columns:** Detail — Date / Nepali Date / Voucher Type / Voucher No / Item /
  Sales Qty / UOM / Sales Rate (5 dp) / Stock Qty / Stock UOM / Rate of Stock
  UOM NPR (5 dp) / Balance. Summarized — Item / Type / Sales Qty / UOM / Stock
  Qty / Stock UOM / Balance. Bold Total row.
- **Logic:** `nepali_datetime` for BS conversion; `_resolve_period` returns
  empty (no error) for an incomplete period, throws only From>To; stock rate =
  `COALESCE(NULLIF(stock_uom_rate,0), rate/conversion_factor)`; merge nets
  returns (`ELSE -ABS(qty)`); 5-dp rate precision. JS: colored Sales
  Invoice/Return pill badges, zebra striping, drag-scroll, "₨"→"Rs".
- **Fix history:** `docs/sales_stock_ledger_fixes.md` (item-group column,
  missing SLE join, return sign in merge, float precision, company scoping,
  company-change refresh; + 2026-06-04 Nepali-month + UI polish).
- **Roles:** Accounts/Sales User & Manager, System Manager. **Audience:** sales +
  stock.

## Missing report

`customer_vendor_ledger_summary/` contains only a stale `__pycache__` — **no
source** (`.json`/`.py`/`.js`). The report is effectively deleted. (The
"Customer Ledger Summary" referenced by credit-control code is ERPNext's
standard report, not this.)

---

## Audit / access reports (chapter 6)

- **User Audit Trail** — everything a user created/changed in a range, per
  field, old→new value, incl. child-row add/remove; only doctypes the running
  user can read. Roles: System Manager, Auditor, Accounts Manager, HR Manager.
- **User Daily Entry Summary** — per user + day, document counts by type and
  docstatus, each a drill-down link. Always runs fresh.

## HR / BS reports (chapter 3 §7)

Monthly Attendance BS, Monthly Attendance Summary BS, Work On Holiday BS,
Yearly Leave Details BS, Avinas Salary Statement.
