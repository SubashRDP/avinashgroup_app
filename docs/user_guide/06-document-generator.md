# Document Generator — User Guide

For accounts and admin staff. The Document Generator produces formal letters
— today mainly the **Customer / Vendor Balance Confirmation** letters — from
ready-made templates, filled with live data, editable before printing or
emailing.

You need one of these roles: *Document Template User* (generate documents),
*Document Template Manager* (also author templates), or System Manager.

## Generating a letter

1. Open the **Document Generator** page (search "Document Generator" in the
   awesomebar).
2. **Choose a template** — e.g. *Customer Balance Confirmation*.
3. **Choose the company** the letter is from.
4. **Fill the inputs.** For the balance-confirmation letters:
   - the **Customer** (or Vendor) — the dropdown only shows parties of the
     chosen company;
   - **either** a **Fiscal Year or** a **From/To date range** — they are
     mutually exclusive; filling one clears the other. Every date field has a
     paired Nepali (BS) picker that stays in sync.
5. The letter **builds itself** as soon as the inputs are complete — there is
   no Generate button. The rendered letter appears in an editable page.
6. **Edit if needed** — the letter is directly editable (bold, lists,
   alignment, even inserting an image from the toolbar).
7. From the **Actions** menu choose:
   - **Print (letterhead paper)** — the PDF leaves the letterhead area blank,
     for printing on pre-printed company paper;
   - **Print (with letterhead)** — the PDF includes the drawn header/footer
     (logo, company name, VAT no, contacts) — use this for digital copies;
   - **Email** — enter recipients (or leave blank to use the party's email on
     file); the letter is emailed as a PDF.

Every print or email automatically saves a **Generated Document** record —
your archive copy, with the exact inputs used, the final text, and the email
status. Open one later and click **Edit in Generator** to revise and re-issue
it.

## What the balance-confirmation letters contain

A dated (BS) letter addressed to the party, showing for the period: opening
balance, taxable sales/purchases, VAT @13%, (TDS for vendors), total, and
closing balance — followed by a request to confirm within 7 days and a
signature block with your signature image, name, designation and the company
stamp.

For your signature and the stamp to appear, the admin must have set up: your
Employee record's *signature image* and *Document User* link, and the
Company's *document stamp* image ([chapter 8](08-admin-setup.md)).

## Authoring or changing templates (managers)

Templates are **Document Template** records (name, target companies, inputs,
data sources, letter body in HTML, header/footer, email subject). Saving
validates the template; the **Preview** button renders it with sample data.
Authoring is a semi-technical task (HTML + query writing) — the full authoring
guide is in the technical documentation:
[`../technical/07-document-generator.md`](../technical/07-document-generator.md)
§7.
