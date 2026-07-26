# Using the A5 Overlay invoice formats — click by click

For the person at the billing desk and the person calibrating a printer.
What each screen does, in the order you touch it.

The overlay formats print **data only**, positioned to land in the boxes
already printed on the continuous form. Seven exist, one per pre-printed roll:

| Format | Roll |
| --- | --- |
| Grishma Invoice A5 Overlay | Grishma Enterprises |
| Nepal Gas Udyog Invoice A5 Overlay | Nepal Gas Udhyog |
| Nepal Gas Invoice A5 Overlay | Nepal Gas (original map) |
| Gandaki / Karnali / Narayani Invoice A5 Overlay | the three regional rolls |
| Avinash Invoice A5 Overlay | Avinash slip |

Pick the one that matches **the roll physically loaded in the printer**, not
the company name on the invoice. They differ only in where the boxes sit.

---

## A. Look at it on screen

1. Open the Sales Invoice.
2. Menu (⋯) → **Print**, or `Ctrl+P`. The Print view opens with a **Print
   Format** dropdown on the left.
3. Choose e.g. **Grishma Invoice A5 Overlay**.

**What happens:** the preview redraws as a mostly-empty page — values scattered
across white space. That is correct. The boxes, rules and headings are absent
because they are already on the paper. What you are looking at is only what the
printer will add.

The preview is a preview only. It does **not** count as a print and does not
move the IRD counter.

---

## B. Print it

4. Click **Print**.

**What happens:** instead of the browser's print dialog, a new tab opens with a
PDF, and an alert says *"PDF opened in a new tab — print it at 100% / Actual
size."*

That redirect is deliberate. These formats hold their millimetres only through
the Chrome PDF generator; the browser dialog would re-render the preview onto
whatever paper it defaults to (A4 portrait) and the whole layout would shift and
rotate. `public/js/ngi_print.js` intercepts the button for any format whose
`pdf_generator` is `chrome` and sends it down the PDF path instead.

5. In the PDF tab, press `Ctrl+P` and check three things before printing:

   - **Scale = 100%** (or "Actual size"). *Never* "Fit to page" — fitting
     shrinks everything a few percent and no value lands in its box again.
   - **Paper = the 241.3 × 139.7 mm form** (9.5 × 5.5 in). On the calibrated
     Linux box this is the `NGIForm` size on the `EPSON-LQ-310` queue.
   - **Margins = None.**

**Clicking Print here DOES count.** The PDF was produced by `download_pdf`,
which advances the IRD print counter and writes a Sales Invoice Print Log row.
Use a test invoice while calibrating.

---

## C. The sheets you get

The first print of an invoice produces **two sheets, two forms**:

    sheet 1  TAX INVOICE
    sheet 2  INVOICE

Reprint the same invoice and you get **one** sheet, titled `COPY OF INVOICE 1`,
then `COPY OF INVOICE 2`, and so on. A return prints a single `Sales Return`.

No roll carries a pre-printed title, so every one of those is typed by the
format. The series is decided in one place —
`custom_code/SalesInvoice/print_count.py` — and every format and both print
paths read it from there.

---

## D. It came out sideways / upside down

The PDF is already correct: wider than tall, no rotation flag. A sideways print
was turned by the **driver**, downstream of anything the format controls. Rather
than hunt driver settings on each machine, cancel it in the URL.

Take the PDF tab's address and add `&rot=`:

    ...&format=Grishma%20Invoice%20A5%20Overlay&rot=90

| Value | Use when |
| --- | --- |
| `rot=0` | default, no turn |
| `rot=90` | the print comes out sideways — driver locked to portrait, or the form feeds the short way |
| `rot=180` | upside down — form fed in reverse |
| `rot=270` | the other quarter turn |

Print one of each on a scrap form, keep whichever comes out upright. The page
box is swapped to match for 90 and 270, so nothing downstream has a reason to
rotate again.

---

## E. Everything is shifted a few mm

6. Add `&guide=1` to the URL and print that on a **real form**.

**What happens:** every field gets a red outline and the sheet edge a blue one.
Hold it against the pre-printed form and you can see exactly which boxes sit
high, low, left or right.

7. Correct the whole sheet at once with `&ox=` (horizontal) and `&oy=`
   (vertical), in millimetres, `+` = right / down:

    ...&guide=1&ox=1.5&oy=-2

8. Repeat until it sits right, then tell whoever maintains the app the final
   `ox`/`oy` so they can bake it into the format.

**Change only `ox`/`oy`.** They move everything together. Individual field
positions are calibrated ruler measurements of the form itself and live in
`custom_code/printing/escp_<form>.py`; editing one to fix a whole-sheet shift
breaks that field for everyone.

---

## F. Make it automatic

So far you have been choosing the format by hand. To have it happen on its own:

9. Go to **Company Print Template** → the **Sales Invoice** record.
10. Find the row for the company, or add one.
11. Set **Print Format** to the overlay, and **Return Print Format** to the same
    one. Tick **Print on Submit** if the desk should print straight from submit.
12. **Save.**

**What happens:** the printer icon on that company's invoices prints immediately
in this format, skipping the format chooser, and — if you ticked it — submitting
an invoice opens the print automatically.

Make this change **in the desk, not in SQL.** Saving fires the hook that clears
the cached routing map; a direct SQL update leaves stale routing in redis and
the desk keeps using the old format.

Two known gaps: an invoice submitted through **Workflow approval** fires neither
client event, so it will not auto-print; and the first auto-print of a session
may be caught by the **popup blocker** — allow popups for the site.

---

## G. Quick reference

Build the URL by hand when you need to:

    http://<host>/api/method/frappe.utils.print_format.download_pdf
      ?doctype=Sales%20Invoice
      &name=<INVOICE-NAME>            (URL-encode the / in 83/84 as %2F)
      &format=Grishma%20Invoice%20A5%20Overlay
      &no_letterhead=1

Then append any of:

| Param | Does |
| --- | --- |
| `&rot=90` | turn the print to cancel a rotating driver |
| `&guide=1` | outline every field box and the sheet edge |
| `&ox=1.5` | move everything right 1.5 mm (`-` for left) |
| `&oy=-2` | move everything up 2 mm (`+` for down) |

They combine. Every one of them counts as a print.

---

Related: `browser_print_setup.md` (per-machine printer setup),
`verification_guide_overlay_printing.md` (what was changed and how it was
proven).
