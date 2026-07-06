# Reports — User Guide

Every custom report, grouped by who uses it. Open any report from the
awesomebar by name. General tips:

- **Company** filters accept multiple companies where shown as a multi-select.
- **Dates**: reports with date filters usually show a Nepali (BS) "Miti" twin
  and a **📅 Select Month** button — pick a BS month and both dates fill
  themselves.
- **Printing**: most reports have their own **Download PDF** / Print buttons
  that produce a properly paginated PDF (with page numbers); some ask
  Portrait/Landscape first. "Fit Columns" is a screen-view toggle and doesn't
  affect the print.

## For accountants — compliance (IRD)

| Report | What it gives you |
|--------|------------------|
| **Sales Register** | the VAT sales register: one row per invoice, values split into tax-free / export / taxable / VAT — ready for the VAT return. Returns mode shows credit notes |
| **Purchase Register** | the VAT purchase register: tax-free / taxable / import / capitalized buckets with their VAT amounts and quantity |
| **Advance Tax TDS Details** | the TDS (अग्रिम कर) withholding statement per supplier and category, in IRD format with Nepali headers; print includes the Prepared/Checked/Verified signature block |
| **One Lakh Above Transactions** | all customers & suppliers whose taxable or exempt turnover in the period is NPR 100,000 or more — the IRD annexure |

## For accountants — ledgers & cash

| Report | What it gives you |
|--------|------------------|
| **Party Ledger** | a full statement for one party (or grouped statements for many): opening balance, every voucher with running balance, closing. BS Miti dates, remarks, optional item-level detail. This is also what customers see on their portal |
| **Party Ledger Summary** | one line per party: opening / debit / credit / closing. "Super Summary" (flat) or "Group Wise" (per customer/supplier group). Excel export shows Dr/Cr columns |
| **Receipt Register** | customer receipts in three layouts: by date, by customer, or one line per customer |
| **Net Position of Cash and Bank** | every cash/bank account's opening, receipts, payments and closing for the period |
| **Loan Summary** | short- and long-term borrowings per loan type across companies, with a ratio row; "Show Details" expands sub-accounts. Balances are cumulative up to the To Date |

## For management

| Report | What it gives you |
|--------|------------------|
| **Consolidated Financial Statement Hierarchy** | Balance Sheet / P&L / Cash Flow consolidated across any set of group companies, with a Total column and a depth control to collapse the account tree |
| **Profit and Loss Hierarchy** | a single company P&L collapsed to the account level you choose (1–6) |
| **Sales Analysis — Customer wise Summary** | per-customer quantity and value, with optional returns and net columns |
| **Sales Analysis — Customer wise Details** | customer → product drill-down with VAT and totals |
| **Sales Analysis — Product wise Invoice Details** | product → customer → individual invoices and returns, with product and grand totals |
| **Avinas Vehicle Expense** | per-vehicle Fuel / Repair / Others expense totals (from purchase invoices and journal entries) for a fiscal year or date range |
| **Custom Supplier Quotation Comparison** | items as rows, suppliers as columns — compare quoted prices, discounts, VAT and invoice totals side by side and pick a default supplier |
| **Gas Purchase Report** | the LPG procurement register per store receipt: refinery, tanker, IOC challan, quantity, rate, VAT, ICP/NA service charges, totals — filtered by BS month |
| **Sales Stock Ledger** | stock movement driven by sales invoices, detail or summarized, with BS dates and an optional sales/returns merge |

## For HR

See [chapter 3 §5](03-attendance-hr.md#5-hr-reports-all-in-nepali-bs-months):
Monthly Attendance BS, Monthly Attendance Summary BS, Work On Holiday BS,
Yearly Leave Details BS, Avinas Salary Statement.

## For auditors / System Managers

| Report | What it gives you |
|--------|------------------|
| **User Audit Trail** | everything one user created or changed in a date range — per field, old value → new value, including child-table rows. Pick the user, dates, optionally document types |
| **User Daily Entry Summary** | how many documents a user created on a given day, by type and status (draft/submitted/cancelled); every count is a click-through to the underlying list |

<a id="portals"></a>
## Customer portals

Customers with a portal login (Customer role) can self-serve:

| Page | What the customer sees |
|------|------------------------|
| `/customer_statement` | their own account statement (same data as Party Ledger), with AD + BS date pickers and a PDF download. Deposit/security accounts are excluded automatically |
| `/product_wise_invoice_details` | their own product-wise invoice details, including returns |
| `/place_order` | place an LP Gas order online (cylinder sizes, live rates, VAT); it arrives as a Sales Order |

Customers only ever see their own companies and accounts — every request is
re-checked on the server.
