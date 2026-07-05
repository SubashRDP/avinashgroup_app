# Avinash Group ERP — User Guide Overview

Welcome! This guide explains, in plain language, the custom features added on
top of ERPNext for the Avinash Group companies (Nepal Gas group and allied
businesses). It is written for the people who use the system every day —
accountants, HR staff, purchase/sales officers, and administrators.

For developers, the matching technical reference lives in
[`../technical/`](../technical/01-architecture.md).

## What's in this guide

| Chapter | Who it's for | What it covers |
|---------|-------------|----------------|
| [2. Approvals](02-approvals.md) | everyone who submits or approves documents | how the multi-level approval workflow works: submitting, approving, rejecting |
| [3. Attendance & HR](03-attendance-hr.md) | HR staff | biometric devices, check-ins, fixing attendance, allowances, HR reports |
| [4. Buying, Selling & VAT](04-buying-selling-vat.md) | accounts, purchase & sales staff | the VAT 13% / 0% / Amount scheme, excise, TDS, warehouses, voucher numbers, vehicles, cheque bounce |
| [5. CBMS / IRD e-Billing](05-cbms-billing.md) | accounts staff | how invoices are reported to IRD automatically and what to do when something fails |
| [6. Document Generator](06-document-generator.md) | accounts & admin staff | producing balance-confirmation letters and other formal documents |
| [7. Reports](07-reports.md) | accounts, sales, HR, management | every custom report: what it shows and how to use it |
| [8. Administrator Setup](08-admin-setup.md) | System Managers | fiscal-year access, company filters, audit trail, devices, templates — all setup checklists |

## The big ideas (read this once)

**Everything is company-scoped.** The group runs several companies in one
system. Master records (customers, suppliers, items) carry a Company, and the
system automatically limits dropdowns to the document's company and blocks
cross-company mistakes. If a value you expect is missing from a dropdown,
check the Company field first.

**Nepali dates everywhere.** Transactions store the English (AD) date, but
show and filter by the Nepali (BS) "Miti" too. Reports have BS month pickers;
attendance and payroll run on BS months; letters print BS dates.

**Approvals are configurable.** Any document type can be routed through a
multi-level approval chain without programming — see chapter 2.

**Invoices go to IRD automatically.** When you submit a Sales Invoice it is
reported to the IRD CBMS system in the background. You never wait for it, and
a synced invoice can no longer be cancelled — corrections go through a Sales
Return.

**Attendance comes from fingerprint devices.** Punches flow from the devices
(via the K40 Bridge or direct push) into Employee Checkins and then daily
Attendance, automatically flagged for lateness and holidays.

## Signing in

- Desk (staff): `http://<your-server>/app`
- Customer portal: `/customer_statement`, `/product_wise_invoice_details`,
  `/place_order` (requires a portal login with the Customer role)
- Supplier RFQ portal: link received by email

## Getting help

If a document refuses to save, read the error message carefully — most
messages in this system are specific ("Row #2: Vehicle is mandatory…",
"Company Mismatch…", "Only <user> may make changes…") and this guide's
chapters explain each one. When in doubt, contact your System Manager.
