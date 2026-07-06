# Buying, Selling, VAT & Vouchers — User Guide

For accounts, purchase and sales staff. Covers the custom tax fields on every
buying/selling document, warehouses, voucher numbers, vehicles, credit terms,
and cheque bounce.

## 1. VAT on every line — the "Apply On" selector

Every item row on Purchase Invoice / Order / Receipt / Supplier Quotation and
Sales Invoice / Quotation / Sales Order / Delivery Note has:

| Field | What to do |
|-------|-----------|
| **VAT Apply On** | `VAT 13%` (default — VAT is calculated for you), `VAT 0%` (tax-free line), or `Amount` (you type the VAT amount yourself) |
| **Excise Value** | type the excise duty for the line if any — it is never auto-calculated |
| **Total** | shown automatically = line amount + excise. VAT is charged on this |
| **VAT Amount** | calculated (read-only) except in `Amount` mode |

The system automatically writes the matching **Excise Duty** and **VAT** rows
into the taxes table and recalculates the grand total — don't add those tax
rows by hand.

**Returns**: on a Purchase/Sales Return, quantities and VAT are automatically
made negative — just enter positive numbers as usual.

## 2. TDS on Purchase Invoices

1. Pick the **Tax Withholding Category** in the invoice's custom TDS field
   (this is separate from ERPNext's standard TDS field — use the custom one).
2. Tick **Apply TDS** on the item rows it applies to.
3. Per row choose `Percentage (%)` (rate comes from the category) or `Amount`
   (type it). The TDS total is deducted in the taxes table automatically and,
   on submit, the TDS ledger entry is tagged with the supplier so the TDS
   ledger reconciles per party.

## 3. Warehouses pick themselves

Items can have different warehouses per **branch** (and buying vs selling).
The mapping lives on the Item (*Branch Wise Warehouse* table, with item-level
defaults as fallback). When you pick an item on a document, the correct
branch warehouse is filled in automatically. If you choose a warehouse
manually and no mapping exists, your choice is kept.

## 4. Voucher numbers

- Document names are generated as `{company}-{prefix}-{fiscal year}-{number}`
  (e.g. a Sales Invoice `NGK-SB-82/83-0000123`; returns get their own prefix).
- Some documents also carry a human **Voucher No** (`custom_name`, e.g.
  `SGU-RC-000006-82/83`) built from the company, type code, document number
  and fiscal year.
- For certain types (Other Purchase Receipts, Purchase Returns, Bank/Journal
  voucher types, bank receipts), the **Document No** field fills itself with
  the next number when you open a new form. If you type a number yourself, it
  is kept — the letter suffix ("65" vs "65A") distinguishes duplicates.
- Duplicate voucher numbers are blocked (cancelled documents excluded, so an
  amended document reuses its number).

## 5. Vehicles on expense lines

Any Purchase Invoice item or Journal Entry line booked to a vehicle expense
account (**Fuel Expenses**, **R & M - Vehicles**, **Other Vehicle Expenses**)
must have a **Vehicle** selected. The dropdown only offers the vehicles
configured on that account (Account → Vehicle List). If you get "Row #N:
Vehicle is mandatory…", pick the vehicle; if the dropdown is empty, ask your
admin to configure the account's vehicle list. These expenses feed the
Vehicle Expense report.

## 6. Master-data helpers

- **Duplicate warning**: saving a Customer/Supplier whose name or VAT/PAN
  already exists in the same company asks "Do you want to create it again?" —
  choose No and use the existing record (its ID is a clickable link).
- **Default accounts row**: Customers, Suppliers and Items automatically get
  one default accounting row with the right Company filled in.
- **Company is locked after saving** — you cannot change a record's company
  once created (the number series embeds the company). Create a new record
  instead.
- **Company Mismatch errors** mean you picked a record belonging to a
  different company — the dropdowns filter for you, but pasted values are
  checked on save.

## 7. Customer credit & due dates

- The invoice **due date** fills automatically from the customer's payment-day
  terms (Customer → days limit); supplier invoices likewise from the
  supplier's payment term days.
- Credit-limit blocking (bill count / overdue days / amount) exists in the
  system but is **currently not active** — ask your administrator about its
  status before relying on it.

## 8. Cheque bounce

If a customer's cheque bounces after you submitted the Payment Entry:
open the submitted Payment Entry → **Actions → Cheque Bounce** → confirm.
The system posts a reversing ledger entry (the invoice becomes outstanding
again) and marks the Payment Entry "Cheque Bounced" in red. The original
entry is *not* cancelled — the reversal sits alongside it, which keeps the
audit trail intact.

## 9. Stock Adjustment (quantity-only correction)

For pure quantity corrections (found/lost cylinders etc.) use **Stock
Adjustment**: date, company, Loss/Gain, reason, and item rows with warehouse
and quantity. **Rate must stay 0** — if value must move, use a Stock Entry
instead. On submit the stock quantity changes but the stock *value* is
preserved, and this survives later revaluations.

Backdated purchase invoices that update stock show an orange notice that
valuation will be reposted overnight — that is informational, not an error.

## 10. Invoice print copies (IRD rule)

The system counts how many times each Sales Invoice is actually printed or
downloaded as PDF and labels the output accordingly, as IRD requires:

- **1st print** → *Tax Invoice*
- **2nd print** → *Copy of Original*
- **3rd print** → *Copy of Original 2*, and so on.

Only a real print or PDF download counts — opening the Print **preview** does
not use up a copy number (the preview shows the title the next print will
carry). You don't do anything for this; it is automatic.

## 11. Portals

- **/place_order** — customers order LP Gas online; orders arrive as submitted
  Sales Orders.
- **/rfq/<id>** — suppliers answer a Request for Quotation online, including
  VAT, discounts and attachments; a Supplier Quotation is created
  automatically.
- Customer statement and product-wise invoice portals: see
  [chapter 7](07-reports.md#portals).
