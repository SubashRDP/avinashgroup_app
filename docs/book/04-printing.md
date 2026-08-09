# Part IV — Getting ink on paper

Printing consumed more time than any other area of this project. Not because
printing is hard, but because the target was not "a nice PDF" — it was
"**indistinguishable from what FACT printed on this exact pre-printed form,
on this exact printer, in this exact tractor**", and the tolerance was
millimetres.

---

# Chapter 7. Why raw ESC/P exists

## 7.1 The problem, stated fairly

The branches print invoices on **pre-printed carbonless sprocket forms** — the
boxes, headings and rules are already on the paper. The software only prints
the *data*, and each value must land inside its box.

FACT did this for years with no printer configuration at all, because it never
went through the Windows graphics driver. It sent the printer **plain text with
ESC/P control codes**. Paper size, orientation and scaling never entered the
picture: the printer used its own font and advanced exactly one form per
invoice.

The PDF path does go through the driver. The driver believes A4 is loaded, and
rotates the 9.5×5.5in page — producing the infamous "vertical print".

So the app restores the FACT mechanism: **the server renders raw ESC/P bytes,
a bridge carries them to the printer, the printer types.**

`custom_code/printing/escp_*.py` — one module per form:

| Module | Form |
| --- | --- |
| `escp_invoice.py` | Nepal Gas (NGI) continuous-form invoice |
| `escp_ngi_udyog.py` | NGI Udyog |
| `escp_gandaki.py` | Gandaki |
| `escp_narayani.py` | Narayani |
| `escp_karnali.py` | Karnali |
| `escp_grishma.py` | Grishma |
| `escp_avinash_slip.py` | Avinash slip |

Each is exposed as a Jinja method (`hooks.py`), so a print format is a thin
template calling `{{ gandaki_escp(doc) }}`.

## 7.2 Coordinates: how the calibration actually works

Read the docstring of `escp_invoice.py` — it is the reference. The essentials:

- Every field position is a **true millimetre distance from the paper's left
  edge / top perforation**, measured off a rectified scan of a real
  FACT-printed form.
- Horizontal placement uses **`ESC $`** — absolute positioning in **1/60 in**
  units, relative to the printer's column 0.
- Vertical placement uses **`ESC J`** — paper feeds in **1/180 in** units,
  relative to top-of-form.
- Form length is set to **33 lines × 1/6 in = 5.5 in exactly**, so a form feed
  always lands on the next form's top, no matter how much was printed.

The critical concept is **`X0`**: column 0 is not the paper edge. The tractor
holds the paper so that column 0 falls some distance in — measured as 12.0 mm
on the current rig (2026-07-14, with a centre-circle target).

```python
X0_MM = 12.0   # column 0 sits 12mm from the paper's left edge on this rig.
               # Every POS x is a TRUE ruler distance from the left paper edge.
               # Max reachable ink: X0 + 203.2mm head travel = 215.4mm.
```

> **The rule that keeps this maintainable:** `X0` and `Y0` are **the only
> calibration knobs**. If a whole print is shifted, adjust `X0`/`Y0`. If one
> field is in the wrong box, adjust that field. **Never fix a global shift by
> nudging every field** — you will destroy the measured map and the next
> adjustment becomes guesswork.
>
> The commit log shows both kinds, and they are labelled: *"narayani a5
> overlay: ox=-20 oy=-10 (2cm left, 1cm up)"* is a global shift;
> *"narayani escp: items +2mm down, qty/rate +4mm right"* is a field nudge.
> Keeping them distinct in the commit message is not decoration — it is how you
> later know which change to revert.

## 7.3 The HTML overlay, and one source of truth

Some sites need the same output as a PDF (plain paper, or a browser print) —
so there is an **HTML overlay** template that absolutely positions the same
values in millimetres.

The tempting implementation is to copy the coordinates into the template. The
implementation that survives is `custom_code/printing/overlay.py`:

> Every pre-printed sprocket form already has a calibrated coordinate map living
> in its raw-ESC/P generator (`escp_*.py`). Rather than re-measure or hand-copy
> those into the HTML overlay (which would drift), the overlay pulls them from
> here, and here re-uses the ESC/P module's own `POS` dict. **One source of
> truth.**

`overlay_pos(form, page)` loads the form's ESC/P module and reshapes its `POS`
dict for the template. It contains **no form-specific facts at all** — only two
numbers, and both are properties of the A5 *page*, not of any form.

This is the single most transferable idea in Part IV: **when two output paths
must agree about a measurement, one of them must read the other's numbers.**
Copies drift; imports cannot.

## 7.4 Two bugs that teach the same lesson

**Refusing to guess a convention.** Forms differ in what `POS["copy_label"]`'s
x means: some builders *centre* the label on it, some treat it as the *left
edge*. `overlay.py` requires each form module to declare
`COPY_LABEL_ANCHOR = "left" | "center"` and **throws if it is missing**:

> Deliberately NOT defaulted: this convention differs per form, and assuming one
> here is the exact bug found 2026-07-25 — every form's x was taken as a centre,
> so the forms that mean "left" printed their title about half a label width off.
> A new form must state which it is.

A default would have been *convenient* and would have silently produced wrong
output on half the forms. **Where a convention genuinely varies, make it
mandatory and fail loudly.**

**Clamps that belonged to one page mode leaking into the other.** The A5 page
is 210 mm; the real sprocket form is 241.3 mm. Two clamps (`AMT_RIGHT = 207.0`,
`DATE_RIGHT = 205.0`) exist *only* to squeeze right-hand columns inside A5.
Until 2026-07-25 they were applied on **every** page — dragging dates ~11 mm and
amounts 3 mm inboard of the boxes on the real form, contradicting the template's
own promise that the form page clamps nothing.

The fix was a `page` parameter (`"form"` | `"a5"`), defaulting to `"form"` so a
one-argument call is the real-form case. **A workaround for one mode must be
gated on that mode.**

## 7.5 wkhtmltopdf cannot render millimetres here

For the HTML overlay to work, 1 CSS mm must be 1 mm of paper. Frappe renders
PDFs with wkhtmltopdf, and Ubuntu's build (`0.12.6-2build2`) is compiled against
**unpatched Qt**, which makes smart shrinking impossible to disable:

```
The switch --disable-smart-shrinking, is not support using unpatched qt,
and will be ignored.
```

Measured on this machine: **every length renders at 0.7688×** — a 100 mm bar
comes out 76.88 mm, in mm, px, pt or in, on A4, Letter or a custom page, and
neither `--zoom` nor `--dpi` moves it. The form ends up shrunk into the
top-left corner of a correctly sized page.

Headless Chrome honours `@page { size: … }` and renders mm exactly (measured
1.0004×, 0.12 mm drift over a 241.3 mm page). Hence:

```python
pdf_generator     = ["…printing.chrome_pdf.render"]
after_migrate     = ["…printing.setup.ensure_chrome_generator"]
override_whitelisted_methods = {
    "frappe.utils.print_format.download_pdf": "…printing.chrome_pdf.download_pdf",
}
```

Only the affected formats go through Chrome; everything else still uses
wkhtmltopdf. And `ensure_chrome_generator` re-pins `pdf_generator="chrome"`
after every migrate, because re-importing a standard print format resets the
field to its default (Chapter 2.10 — the legitimate `after_migrate` case).

**The general lesson:** before spending days on CSS, *measure the renderer*.
Print a 100 mm calibration bar and put a ruler on it. The problem was never the
stylesheet.

---

# Chapter 8. Delivery, copies, and counting

## 8.1 Print Bridge — getting bytes to the printer

`print_bridge/` is a small Windows service that receives raw ESC/P from the
browser and hands it to the printer. It **replaced QZ Tray entirely** — no
certificate, no signing, no browser permission dance (`qz_sign.js` is no longer
loaded; `qz_security.py` remains for reference).

Three hard-won details from its README, each a genuine field bug:

1. **The Epson's own driver silently eats RAW jobs.** The installer creates an
   `LQ310-RAW` queue on the printer's port using the **Generic / Text Only**
   driver, which is a pure byte pipe. With the stock Epson ESC/P V4 driver, the
   spooler reports success and the print head never moves — the worst possible
   failure mode.
2. **A boot trigger is not enough on Windows 10/11.** With Fast Startup (the
   default), "Shut down" hibernates the kernel rather than truly booting, so a
   boot-only scheduled task never fires again — the v0.3.2 "works until the
   first shutdown" bug. The task now has **two triggers: at boot AND at any
   user's sign-in**, running as SYSTEM with no execution time limit. If both
   fire, the second instance finds the port taken and exits quietly.
3. **Pre-grant Chrome/Edge local-network access** for the ERP origin at install
   time, so no permission prompt ever appears in front of a clerk.

Browser side: `public/js/print_bridge.js` defines `avinash.print_bridge`, and it
must load **before** `ngi_print.js` (the Print-view button) and
`company_print.js` (the form printer icon) — `hooks.py` orders them explicitly,
and `company_print.js` chains `ngi_print.js`'s PrintView descriptor.

Which format each company prints is data, in the **Company Print Template**
doctype — not a branch in JavaScript.

## 8.2 Print counts and copy titles — the IRD requirement

`custom_code/SalesInvoice/print_count.py` is the single source of truth for
copy labelling. Both the Jinja templates and the ESC/P builders call
`invoice_copy_titles`.

**The counter counts SHEETS, not print events.** That distinction is the whole
design:

*Sheet-based series* (`pair=True` — Nepal Gas / Grishma / Avinash dot-matrix):

```
1st print → TAX INVOICE + INVOICE   (one print event, TWO sheets → count 2)
2nd print → COPY OF INVOICE 1
3rd print → COPY OF INVOICE 2
nth print → COPY OF INVOICE (n − 1)
```

*Single-sheet series* (`pair=False` — Grihalaxmi A4/Half, Nepal Gas Half)
follows the same order, one sheet per print:

```
1st → TAX INVOICE, 2nd → INVOICE, 3rd → COPY OF INVOICE 1, …
```

Returns print a single **Sales Return** sheet on every print, with no copy-of
prefix however many times printed.

Two rules that are easy to get wrong:

- **Every sheet's title is typed by the format.** No pre-printed roll carries a
  title on any company's stationery. Until 2026-07-25 the overlays skipped
  exactly `"TAX INVOICE"` on the assumption the roll said it — it does not.
- **The counter increments only on an *actual* print**: the browser Print button
  (`printview?trigger_print=1`), a PDF download, or raw/server printing.
  **Rendering the preview does not consume a sheet.** The preview shows the
  titles the *next* print will get. Get this wrong and merely looking at an
  invoice advances an IRD-visible counter.

## 8.3 Two records, deliberately

| Doctype | Grain | Purpose |
| --- | --- | --- |
| **Sales Invoice Print Count** | one row per invoice (`print_count`) | the running total that decides the next title |
| **Sales Invoice Print Log** | **one row per sheet** (`copy_number`, `printed_by`, timestamp) | the audit trail behind the Invoice Activity Report and the annexure |

A count would not tell you who reprinted an invoice at 11 pm; a log alone would
make the hot path a `COUNT(*)`. Keeping both is the right call — just remember
the log has **several rows per invoice**, which matters when you join to it
(§8.5).

And: **logging must never block the print.** A failure goes to the Error Log
and the print proceeds. Same discipline as CBMS (Chapter 6.2) — the audit trail
is important, but not more important than the clerk being able to hand the
customer an invoice.

## 8.4 Importing the legacy print history

`legacy_print_import/import_legacy_print_counts.py` loads the old software's
"Sale Invoice Register" so the counters continue rather than restart. It is a
model of how to write an import — Chapter 12 covers the discipline in general;
the specifics here:

- the join key is the old number stored in `custom_branch_name`,
- **it is only unique within a company AND a fiscal year** (NGK holds
  `NGK/000001` in both 77/78 and 79/80). Pass `company=` to narrow;
- rows still matching several invoices are reported under
  `ambiguous_register_rows` and imported for **none** of them — rather than
  credited to whichever invoice the scan happened to return last;
- the old software also counted the first print as 2 sheets, so the semantics
  line up with `print_count.py` exactly;
- existing rows are **added to**, not replaced (ERPNext prints happened after
  the legacy ones; the counter is total sheets);
- **dry run unless `commit=True`.**

## 8.5 The one-row-per-sheet join trap

The Materialized Report needs "when was this invoice first printed, and by
whom". Print Log has many rows per invoice, so the query collapses to the
**earliest sheet** and reads the timestamp *and* the printer **from that same
row**:

> taking them separately could pair a reprinter's name with the original
> print's time.

Two independent `MIN()`s over a multi-row group produce a person who never did
the thing at the time shown. Whenever you aggregate a group down to "the one
that matters", pick **the row** first, then read all its columns.

## 8.6 Cheque printing

A smaller pipeline with the same shape: **Cheque Print Alignment** holds
per-bank coordinates, and `payment_entry/` renders the cheque. The work here
was almost entirely about **amount in words**:

- drop the mid-number "And" (*"Twenty Five Thousand And Four Hundred"* → no),
- capitalise the paisa connector,
- **Indian digit grouping** (`12,34,567`, not `1,234,567`),
- align the words to the totals rows on the Gandaki and Karnali layouts.

Money-in-words is one of those problems that looks trivial and has a dozen
locale rules. It now lives in one place; extend it there rather than in a
template.

---

Next: **[Part V — Platform services](05-platform-services.md)**
