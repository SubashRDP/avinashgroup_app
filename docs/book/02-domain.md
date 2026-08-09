# Part II — The domain

---

# Chapter 3. Nepal: BS dates, VAT, and what the IRD demands

Most of the difficulty in this app is not technical. It is that a Nepali gas
distributor's books answer to a calendar ERPNext does not know, a tax structure
ERPNext does not model, and a tax authority that has opinions about your
*printer*. Get this chapter into your bones and three quarters of the code
stops looking strange.

## 3.1 Two calendars, permanently

The books run on **Bikram Sambat (BS)**. ERPNext stores **Gregorian (AD)**.
Both are true at once, and neither can be dropped:

- The database stores AD. Every `posting_date`, every GL entry, every report
  filter, internally, is AD. Do not fight this.
- Humans, invoices, and the IRD want BS. Every printed document and every
  statutory report shows BS.

So conversion happens **at the edges** — on print, on report render, on the
CBMS payload — never in the middle.

```python
# custom_code/CBMS/utils.py
import nepali_datetime

def to_bs_date(ad_date):
    return nepali_datetime.date.from_datetime_date(getdate(ad_date))

def bs_date_str(ad_date, sep="-"):
    bs = to_bs_date(ad_date)
    return f"{bs.year:04d}{sep}{bs.month:02d}{sep}{bs.day:02d}"
```

`bs_date_str` is registered as a Jinja method in `hooks.py`, which is how print
formats show BS dates without any template doing arithmetic.

The BS months, in order, index 0 = month 1:

> Baisakh, Jestha, Ashadh, Shrawan, Bhadra, Ashwin, Kartik, Mangsir, Poush,
> Magh, Falgun, Chaitra

> **The trap — two BS libraries on one bench.** `avinashgroup_app` converts with
> `nepali_datetime`. `rdp_common_app` has its own BS conversion sitting next to
> a *second, different* library. They do not always agree at month boundaries.
> `CBMS/utils.py` therefore keeps its own copy of the month names rather than
> importing rdp's, with a comment saying exactly why. **Never mix the two in one
> code path.** If you are in CBMS, use CBMS's converter; if you are in a BS
> payroll report, use rdp's. A date that is one day off in an IRD submission is
> a compliance problem, not a display bug.

Note also that `posting_date` and `custom_invoice_miti` are **read-only on the
Sales Invoice form** — the BS *miti* is derived from the posting date by
`SalesInvoice/posting_miti.py` on `before_validate`, so the two can never drift
apart by hand.

## 3.2 Fiscal years are BS, and they are load-bearing

Fiscal years are named `82/83`, `83/84` and start mid-July. They are not
cosmetic — they are a **scoping key** used all over the app:

- document numbers restart each fiscal year (Chapter 4),
- numbers are unique per **company + fiscal year**, not globally,
- per-user access is granted per fiscal year (Chapter 9),
- the IRD annexures are per fiscal year,
- legacy invoice numbers only resolve uniquely within a company *and* year.

`custom_code/Override/naming_series.py` looks up the Fiscal Year row spanning
the posting date and **throws if none exists**.

> **The operational trap.** Mid-July, if nobody created the new Fiscal Year —
> with a row for **all seven companies** — then on the first day of the new year
> *nobody can save an invoice at all*. This is a calendar event with a code
> consequence. Put it in a diary: create next year's Fiscal Year, all seven
> companies, before Ashadh ends.

The IRD API wants the year in its own format: the site's `82/83` is reformatted
to `2082.083` in the CBMS payload. One more reason conversions live at edges.

## 3.3 The tax structure: VAT on top of excise

ERPNext's tax templates could not express what these companies bill, so the app
computes tax itself, per item, and then writes the result into the standard
taxes table. The arithmetic is deliberately simple, and the *rules about what
is manual* matter more than the formulas.

Per item:

```
custom_total = base_net_amount + custom_excise_value
```

**Excise is always manual.** It is never recalculated by any code path, ever.
It is entered (or imported) and preserved.

VAT is driven by a per-item selector, `custom_vat_apply_on`, with three modes:

| `custom_vat_apply_on` | Rate | Amount |
| --- | --- | --- |
| `VAT 13%` (the default) | forced to 13 | **always recalculated** = `custom_total × 13 / 100` |
| `VAT 0%` | forced to 0 | always 0 |
| `Amount` | forced to 0 | **manual, never recalculated** |

Then the document totals are aggregations: `custom_total_excise_amount`,
`custom_total_vat_amount`, `custom_total_amount_including_excise`. Finally the
pipeline writes Excise and VAT rows into `doc.taxes` so the GL, the print
formats and every ERPNext report see normal ERPNext taxes.

The shape to remember: **excise is added to the base *before* VAT is taken.**
VAT is charged on the excise-inclusive amount, not on the net amount. If a
grand total is wrong by a suspiciously round proportion, check whether excise
made it into `custom_total`.

> **The trap — returns lose their manual taxes.** `custom_vat_amount`,
> `custom_excise_value` and `custom_total` are `no_copy` fields on Sales Invoice
> Item. ERPNext's *Create → Return* mapper therefore hands you a credit note
> with all three **zeroed**.
>
> `VAT 13%` rows self-heal (VAT is recomputed from the negative net amount).
> **Manual `Amount` VAT and all excise do not** — they are never recalculated by
> design. Without intervention the credit note is short by exactly the VAT and
> excise, and **no VAT reversal reaches the GL**: the company refunds the
> customer money it has already paid to the tax office.
>
> `restore_return_item_taxes()` (in `salesinvoice_taxes.py`) is the fix — it
> reads each row's `sales_invoice_item` link back to the original row, restores
> the values scaled to the returned quantity (partial returns), and applies the
> return sign. It must run **before** any total or the taxes table is built; a
> late sign flip leaves the taxes table built from the wrong numbers.
>
> The general lesson, which recurs: **`no_copy` + "never recalculated" is a
> silent-data-loss combination.** Any field that is both must be explicitly
> restored on every document-mapping path.

Purchase side has the same shape plus **TDS** — see
`custom_code/purchase_invoice/purchase_invoice_taxes_tds.py` and
`common/purchase_taxes_handler.py`. Sales has no TDS at all.

Excise also rewrites GL entries at `before_submit` via
`custom_code/excise_ledger.py`, so excise lands in its own account rather than
inside revenue.

## 3.4 What the IRD actually demands

Nepal's Inland Revenue Department runs **CBMS** — the Central Billing
Monitoring System. Billing software that is registered with it must obey rules
that are unusual for an ERP, and nearly every odd design decision in Parts III
and IV traces back to one of them:

**1. Report every sales bill to the IRD, in real time.**
Bills are POSTed to `https://cbapi.ird.gov.np/api/bill`, returns to
`/api/billreturn`. → Chapter 6.

**2. A reported bill is immutable.**
Once the IRD has it, the invoice can never be cancelled or deleted. The app
enforces this in `before_cancel` and `on_trash`, and hides those menu entries
on the form via `onload`. → Chapter 6.

**3. Invoice numbers must be gapless and sequential.**
A number is consumed the moment a draft is saved. A draft that later fails to
submit would leave a hole in the IRD's sequence. → Chapters 4 and 5, and this
is the entire reason Save-and-Submit is one atomic action.

**4. Count the prints, and label every reprint.**
The software must track how many times each invoice was printed and mark
reprints as copies of the original:

```
1st print → TAX INVOICE + INVOICE   (one event, two sheets)
2nd print → COPY OF INVOICE 1
3rd print → COPY OF INVOICE 2
```

→ Chapter 8.

**5. Produce the statutory annexures.**
The sales book the old software exported as *"VAT Annexure 7"* — 21 columns,
BS dates, Yes/No instead of checkboxes, a letterhead block, Indian-grouped
numbers. The Materialized Report reproduces it exactly, because reproducing it
exactly is what let the group retire the old software. → Chapters 11 and 12.

## 3.5 Why "the old software" keeps coming up

These branches ran **FACT**, and later an NGI-specific billing package, for
years. That history constrains the present in three ways you will keep meeting:

- **Printing.** FACT sent raw ESC/P to an LQ-310 with zero printer
  configuration, on pre-printed sprocket forms. Users' hands know those forms.
  Matching that output — to the millimetre — is Chapter 7.
- **Numbers.** The old invoice number for each migrated invoice lives in
  `custom_branch_name`. It is the join key for every legacy import, and it is
  only unique **within a company and a fiscal year**. Chapter 12.
- **History.** Print counts and years of annexure rows exist only in the old
  software's exports. They were imported so the new reports could reproduce the
  old ones for years the new system never saw. Chapter 12.

Whenever a piece of this app looks over-engineered, ask: *what did FACT do
here?* Usually the answer is the specification.

---

Next: **[Part III, Chapter 4 — Numbering](03-transaction-core.md)**
