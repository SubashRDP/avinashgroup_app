# Reports catalog — avinashgroup_app

Every Script Report in the app (51), as read on 2026-11-19. Paths are relative to
`avinashgroup_app/`; `AGR/` = `avinash_group_app/report/`. Line refs are to each report's own `.py`.

## Shared plumbing

| Concern | Where |
| --- | --- |
| BS twin + month picker on every report Date filter | `rdp_common_app/public/js/report_nepali_date.js` (global, rdp hooks.py:33) |
| AD↔BS conversion, month names/ranges | `rdp_common_app.utils.bs_boundaries` (`ad_to_bs`, `bs_to_ad`, `BS_MONTH_NAMES`, `get_bs_month_range`) |
| BS strings, FY dates | `custom_code/CBMS/utils.py` (`bs_date_str`, `get_fiscal_year_dates`) |
| BS month periods honouring Nepal BS Period override | `hr/bs_calendar.py` (`month_period`, `get_default_month`) |
| Printed voucher numbers | `utils/voucher_numbers.py` (`resolve`, `link`) — only Posting Detail + Custom Ledger use it |
| Excel builders | `utils/report_excel.py` (`send_annexure7_xlsx`, `send_report_xlsx`) |
| Print orientation/footer | `public/js/report_print_orientation.js` |
| PDF | wkhtmltopdf `get_pdf` + `*_pdf.html` everywhere, except Chrome-first (`custom_code/printing/chrome_pdf.render`) in GL Posting Detail and SQ Comparison |

Copy-pasted, not shared: `_as_list()`, `get_company_customers/items/branches` (filter `custom_company IN (...) OR blank`, LIMIT 50).

Frappe quirks every report hits: `reqd` on a MultiSelectList never fires (empty `[]` is truthy) — guard on the server; an unticked Check never reaches the server — read with `cint()`.

## Ledgers & finance

| Report | What it is | Key facts |
| --- | --- | --- |
| **General Ledger Posting Detail** | Legacy DevExpress "Posting Detail" port. Categorized by Account / Party / Both / Vehicle | Raw SQL on GL Entry; BS period presets via `custom_ledger.get_period`; P&L opening floored at FY start (no PCVs); Vehicle mode reads PI Item + JE Account `custom_subtype` (`base_net_amount`); voucher_no filter applied in Python via `resolve()`; Chrome PDF with Legacy + Standard styles |
| **Custom Ledger** | One report for 4 legacy prints (GL / Normal Sub Ledger × Summary / Detail) via Format dropdown | Account `custom_sub_type_list` = vehicle sub-ledger; `DETAIL_ROW_LIMIT=20000`; vehicle path uses `pii.amount` with no P&L floor → can disagree with Posting Detail |
| **Party Ledger** | Customer/supplier statement, running balance | Also the engine of the customer portal statement (`templates/pages/customer_statement.py`); excludes JE `custom_p_type='Contract Form'` by default; zero-value SI/PI added as 0/0 rows; miti from stored fields; voucher numbers hardcoded (`custom_branch_name` / `custom_name`) |
| **Party Ledger Summary** | One row per party: Opening/Dr/Cr/Closing; Super Summary or Group Wise | Does NOT exclude Contract Form JVs → totals can differ from Party Ledger |
| **General Ledger Summary** | Tally-style TB | `FORCE INDEX (fin_stmt_agg_index)` perf fix; NO P&L opening floor; group accounts in filter ignored |
| **TDS Party Ledger Summary** | Party-wise sub-ledger of TDS accounts (legacy GL P03) | TDS accounts = name LIKE `%TDS%`/`%Tax Deduct%`; no PDF |
| **Ageing Report** | Bill-wise AR/AP ageing; "Merged" knocks advances off oldest bills FIFO | Wraps ERPNext `ReceivablePayableReport` |
| **Ageing Report Summary** | Ageing per party | Pure wrapper over Ageing Report's helpers |
| **Debtors Summary** | Customer Wise (Bulk/Dealer/Others/Cylinder blocks) or Monthly (all companies by day) | Hardwired accounts GAS 143101, CYLINDER 313101/313102; Monthly ignores company filter + permissions |
| **Bank and Cash Book** | Daybook per cash/bank account, day closings | Reuses Net Position helpers; voucher-number COALESCE skips SI `custom_branch_name` |
| **Net Position of Cash and Bank** | Opening/Receipts/Payments/Closing per cash/bank account | Accounts under "Cash and Cash Equivalent"; defaults to AD calendar year; currency label can lie |
| **Loan Summary** | Loan type × company matrix + ratio | Under Short/Long Term Borrowings; all cells are Data strings (Excel not numeric); `from_date` unused |
| **Profit and Loss Hierarchy** | ERPNext P&L + account-level cap + Total col | **Total overstated when accumulated_values=1 (the default)** |
| **Consolidated Financial Statement Hierarchy** | BS/P&L/CF across unrelated companies, common-accounts view | Monkeypatches ERPNext cfs module functions at runtime (process-global) |
| **Advance Tax TDS Details** | TDS schedule by khata no., Nepali labels | PI + JE sources; no `is_return` filter; N+1 party lookups |

Known disagreements: P&L opening floor (Posting Detail/Custom Ledger floor, GL Summary doesn't); `is_opening='Yes'` unbounded in Party Ledger(+Summary)/GL Summary; voucher-number source; BS from stored miti (Party Ledger) vs converted posting_date (rest).

## Sales

| Report | What it is | Key facts |
| --- | --- | --- |
| **Sales Register Report** | IRD VAT sales book / sales-return book (Rule 23(1)(ज)) | Bill No `COALESCE(custom_branch_name,name)`; buckets by `custom_vat_apply_on` + territory; custom openpyxl Excel; **SQL built from quoted strings (injection)** |
| **Sales Report Summary** | Item-wise totals; Summary / Branch Wise / Company-wise Comparison | "This Month" = BS month; Gas Qty in KG from `stock_qty` when UOM kg-like; one query per company |
| **Sales Bill Details** | Invoice list with PAN, vehicle, address, phone | Non-returns only; injection-prone SQL like Sales Register |
| **Sales Stock Ledger** | Sales lines of stock items, Detail / Summarized | **Not a stock ledger**: "Balance" = line amount, no running balance; totals mix UOMs |
| **Sales Analysis Customer wise Details** | customer → product, sales vs returns vs net | value = `amount + custom_excise_value` |
| **Sales Analysis Customer wise Summary** | one line per customer | returns always fetched, only hidden when unticked |
| **Sales Analysis Product wise Invoice Details** | product → customer → invoices | shows `si.name`, not printed number; fixed "No Agent" |
| **NG Sales Order Analysis** | SO item billed/pending/delay | `get_rows` reused by portal `sales_order_analysis.py` |
| **Sales Order Billing Capacity** | what each pending SO can bill today under credit limits (tree) | `credit_control.get_credit_position`; `billing_verdicts()` used by pending-orders popup |
| **Gas Dispatch (Quota)** | LP Gas qty per customer per BS month, last 12 months, quota = peak | Raw qty summed across UOMs (no kg conversion); `STRAIGHT_JOIN` perf fix |
| **One Lakh Above Transactions** | IRD annexure: parties ≥ 1,00,000 | uses `amount` WITHOUT excise → won't reconcile with Sales Analysis |
| **Invoice Activity Report** | IRD audit trail: Add / Printed / Modified | No date filters (FY window); drops invoices before CBMS `enable_from_date`; user from `custom_created_by` |
| **Receipt Register** | Customer receipts: Date Wise / Customer Wise / Summary | `custom_name`, `custom_posting_miti`, `custom_remark`; cheque "1" hidden |

Sales value basis differs: `custom_total` (Register, Summary) · header `custom_total_amount_including_excise` (Bill Details) · `amount + custom_excise_value` (Sales Analysis ×3) · plain `amount` (Sales Stock Ledger, One Lakh).

## Purchase, stock, tax, CBMS, audit

| Report | What it is | Key facts |
| --- | --- | --- |
| **Purchase Register Report** | IRD VAT purchase book / return book (Rule 23(1)(छ)) | buckets: tax-free / taxable / import / capitalised; **injection-prone SQL** |
| **Gas Purchase Report** | LPG purchase per Store Receipt with ICP/ICT/NA service charges | `custom_purchase_type='Gas Purchase Invoice'`, tanker fields (PDO, vehicle, IOC challan, transporter, refinery); service charges scanned with no date bound |
| **Avinas Vehicle Expense** | Fuel / R&M / other expense per vehicle | PII + JEA `custom_subtype`; no dates ⇒ all time |
| **Custom Supplier Quotation Comparison** | One column block per quotation, Quoted vs Ordered | Fork of ERPNext; local `set_default_supplier` has no perm check |
| **Material In Out Report** | Opening / Received / Delivered / Balance per item+UOM+branch+price list | Reads documents, not SLE; **Balance omits Opening**; full-history opening scans |
| **Inventory Report** | Stock summary + value + performance (turnover, days of cover, movement) + reorder need per company+item or warehouse, from SLE | standard in `docs/inventory-report-standard.md`; Rate = last purchase rate, not SLE valuation |
| **Stock Balance (With Zero Values)** | ERPNext Stock Balance + zero rows | NULL `custom_company` items dropped |
| **Materialized Report** | IRD Annexure-7 from `CBMS Bill` | matches both "83.84"/"83/84" FY spellings; Company User Permission scoping |
| **Materialized Return Report** | Annexure-7 credit notes from `CBMS Bill Return` | imports helpers from Materialized Report |
| **CBMS Activity Report** | CBMS Sync Log trail | **no company User Permission scoping** |
| **User Audit Trail** | one user's creates + field changes | `get_all` skips doc-level perms |
| **User Daily Entry Summary** | per-doctype Created/Submitted/Edited/... counts for a user | doctypes from "User Daily Entry Summary Settings"; `add_total_row` double-counts in export |
| LC Cost Sheet / Margin & Charges / Maturity / Register | Letter of Credit landed cost, margins, usance due buckets, register | totals add across currencies |
| PDC Bounce Analysis / Maturity / Register | post-dated cheque bounce rate, due buckets, register | bounce groups by party only |

## HR & payroll

| Report | What it is | Key facts |
| --- | --- | --- |
| **Monthly Attendance BS** | Detail (employee × day) or Summary; replaces HRMS Monthly Attendance Sheet | First IN/Last OUT = raw punches; late via `hr.shift_day.measure_day`; OT only from submitted Overtime Sheets; in-report actions (Give Leave, Close Shift Early, Import Punches, punch correction, late excuse); global unscoped CSS |
| **Work On Holiday BS** | holidays worked per BS month per employee | uses stored `custom_worked_on_holiday` (Monthly Attendance deliberately doesn't) |
| **Yearly Leave Details BS** | leave per BS month vs entitlement | company filter only on Attendance query |
| **Avinas Salary Statement** | client's Excel salary sheet from slips, journal check | grouped O/O, S/D, F/P; current department, not slip's; N+1 |
| **Salary Tax and SSF Deposit** | SSF 31%, SST, remuneration tax per employee with due dates | no payout-type filter (Dashain/encashment slips could add in) |

BS override inconsistency: only Monthly Attendance's main period, Salary Statement and Tax/SSF use `month_period`.

## Gaps

- **No real stock ledger exists.** Sales Stock Ledger is a sales-line list, Material In/Out is a period summary. See the stock findings in memory `gas-stock-ledger`.

## Top defects found while cataloguing

1. SQL injection via quoted-string filters: Sales Register, Sales Bill Details, Purchase Register.
2. Material In Out: Balance excludes Opening.
3. P&L Hierarchy: Total column overstated with accumulated values (default).
4. Permission gaps: CBMS Activity (no company scoping), User Audit Trail (`get_all`), Debtors Summary Monthly, Loan Summary.
5. SQ Comparison local `set_default_supplier` writes without a permission check.
