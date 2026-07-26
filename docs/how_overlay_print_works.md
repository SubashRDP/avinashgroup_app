# How the A5 Overlay invoice printing works — the code

End-to-end walkthrough for a developer. Every claim below is a file and line
you can open. Companion to `how_to_use_overlay_print.md` (which is the operator
view of the same machinery).

## The one-sentence version

A Print Format renders absolutely-positioned `<div>`s whose `left`/`top` are
true millimetres read from the form's calibrated ESC/P map, headless Chrome
turns that into a 241.3 × 139.7 mm PDF at exactly 1:1, and the printer adds
those values to a form that already has the boxes printed on it.

Two things make it work, and both are load-bearing:

1. **Absolute mm, no layout.** Nothing flows. Every value is placed.
2. **Chrome, not wkhtmltopdf.** The distro's wkhtmltopdf is built against
   unpatched Qt and renders every length at **0.7688×**, un-disableable
   (`chrome_pdf.py` header documents the measurement). One wrong generator and
   the entire form shrinks into the top-left corner.

---

## The chain, in order

```
   desk Print button
        │  ngi_print.js  ── patches PrintView.printit
        ▼
   /api/method/frappe.utils.print_format.download_pdf
        │  hooks.py override_whitelisted_methods → chrome_pdf.download_pdf
        ▼
   frappe.utils.print_utils.get_print
        │  reads Print Format .pdf_generator  ("chrome")
        │  before_print hook → print_count.before_print   ← counter + titles
        ▼
   Jinja renders the Print Format's html
        │  {% set form = 'grishma' %}{% include overlay template %}
        │      ├── overlay_pos(form, page)  → overlay.py
        │      │        └── escp_grishma.POS + COPY_LABEL_ANCHOR
        │      └── invoice_copy_titles(doc) → print_count.py
        ▼
   pdf_generator hook → chrome_pdf.render
        │  headless chrome --print-to-pdf
        ▼
   684 × 396 pt PDF  (= 241.3 × 139.7 mm, /Rotate absent)
```

### Stage 0 — the Print Format record

`avinash_group_app/print_format/grishma_invoice_a5_overlay/*.json`

The whole record is three fields that matter:

```json
"pdf_generator": "chrome",
"print_format_type": "Jinja",
"html": "{% set form = 'grishma' %}{% include \"avinashgroup_app/templates/print_formats/nepal_gas_invoice_a5_overlay.html\" %}"
```

All seven overlays are this same two-line wrapper differing only in the `form`
key. There is **one** template; there are **no** per-format templates.

`pdf_generator` living on the record is what makes *every* path exact — not
just the buttons, but `attach_print` (emailed invoices) and `print_by_server`
(CUPS). `frappe/utils/print_utils.py:43` reads it when the caller passes
nothing.

### Stage 1 — the click

`public/js/ngi_print.js`

`print/print.js` is lazy-loaded, so the class does not exist at boot. The file
intercepts the *assignment* with `Object.defineProperty(frappe.ui.form,
"PrintView", …)` (`:79`) and patches whatever gets assigned, whenever.

The patch replaces `printit()` (`:37`). The routing decision is
`is_chrome_format()` (`:27`):

```js
const doc = view.get_print_format ? view.get_print_format(format) : null;
if (doc && doc.pdf_generator) return doc.pdf_generator === "chrome";
return NGI_FORMATS.includes(format);       // fallback only
```

It asks the format itself, so a new chrome format needs no edit here. The
hardcoded `NGI_FORMATS` list is a fallback for a format doc not yet in
`locals`. **That list used to be the rule**, it drifted, and the seven overlays
fell through it to the browser print dialog — the defect fixed 2026-07-25.

A chrome format is sent to `download_pdf` instead of the browser dialog,
because the dialog re-renders the preview HTML onto the dialog's paper (A4
portrait) and every millimetre is lost.

Same decision exists a second time for the form's printer icon, in
`company_print.js`, driven by `Company Print Template` rules.

### Stage 2 — endpoint and generator resolution

`hooks.py:360` overrides the whitelisted `download_pdf` with
`chrome_pdf.download_pdf`, which forces `pdf_generator="chrome"` for names in
`CHROME_PRINT_FORMATS` (`chrome_pdf.py:198`).

**The overlays are deliberately NOT in that set.** They carry `pdf_generator`
in their own JSON, so `print_utils.py:43` resolves it without help. The set is
better read as *"formats that need re-pinning"*: those six JSONs have no
`pdf_generator` field, so a migrate re-import blanks it, and
`setup.ensure_chrome_generator` (`after_migrate`, `hooks.py:358`) writes it
back. The overlays survive a migrate on their own.

`ensure_chrome_generator` also widens the `pdf_generator` Select via a Property
Setter — stock Frappe offers only `wkhtmltopdf`, so the field could not legally
hold `chrome` otherwise.

### Stage 3 — HTML generation

`templates/print_formats/nepal_gas_invoice_a5_overlay.html`, §1–7.

Three helpers are reachable from print Jinja because `hooks.py jinja.methods`
exports them: `overlay_pos`, `invoice_copy_titles`, `bs_date_str`.

**Knobs** (§1) come from two places that *add*: the wrapper (`{% set ox = 1.5
%}`) and the URL (`&ox=1.5`). The URL half works because `frappe.form_dict` is
in Jinja's safe globals — the same trick the cheque format uses:

```jinja
{%- set ox = (ox | default(0)) + (frappe.form_dict.get('ox') | float) -%}
```

⚠️ `get_safe_globals` binds the **object** into the Jinja env when the env is
first built. Mutate `frappe.local.form_dict` in place; *replacing* it is
invisible to later renders in the same process. This cost real debugging time
and is documented in `test_overlay_print.py`'s `render()`.

**Geometry** (§2) separates two things that used to be one:

```jinja
{%- set fw = 210.0 if is_a5 else 241.3 -%}   {# the FORM  — coordinate space #}
{%- set pw = fh if quarter else fw -%}       {# the PAGE  — swapped by rot #}
```

`rot` is whitelisted to the four right angles and applied as a single CSS
transform on `.ov-rot`, with `transform-origin: 0 0`, so no field coordinate
changes when the print is turned.

**Coordinates** (§3) — one call:

```jinja
{%- set P = overlay_pos(form, page) -%}
```

**Macros** (§5) are the only things that emit a positioned box. `at()` puts a
box's LEFT edge at x; `atr()` puts its RIGHT edge at xr, reproducing the ESC/P
`right=True` behaviour so digits line up on the column rule. `ox`/`oy` are
added inside the macros, which is why they move everything and why nothing else
in the file needs to know about them.

**Sheets** (§7) is a double loop: for each copy title, for each page of items.

### Stage 3a — where the numbers come from

`custom_code/printing/overlay.py`

This module holds **no form measurements**. It resolves the form key to its
module and reshapes:

```python
mod = _form_module(form)          # 'grishma' → escp_grishma
P = mod.POS
```

`escp_grishma.py` is the single source of truth for Grishma: `X0_MM`/`Y0_MM`,
the `POS` dict in true mm from the form's top-left, and `COPY_LABEL_ANCHOR`.
The ESC/P path and the browser path read the *same* numbers, which is why they
cannot drift.

Two per-form subtleties overlay.py carries across, both of which were bugs:

- **`COPY_LABEL_ANCHOR`** — some builders centre the label on `POS["copy_label"]`
  x, others treat it as the left edge. `_copy_label_anchor()` reads the form
  module's declaration and **throws if absent**; it deliberately does not
  default, because defaulting to "centre" is exactly what printed Grishma's
  title half a label width off.
- **`page`** — `AMT_RIGHT`/`DATE_RIGHT` exist only to squeeze columns inside
  A5's 210 mm and now apply only when `page == 'a5'`. They previously ran on
  the 241.3 mm form too, dragging the dates ~11 mm inboard (measured
  189.7 → 198.0 mm).

Those two constants are the only numbers in the file, and they describe the A5
**page**, not any form.

### Stage 3b — the copy titles

`custom_code/SalesInvoice/print_count.py`

`_titles_for(prev_sheets, pair, is_return)` (`:76`) is the only definition of
the IRD series:

```
prev 0  → ["TAX INVOICE", "INVOICE"]      (one print event, TWO sheets)
prev 2  → ["COPY OF INVOICE 1"]
prev n  → ["COPY OF INVOICE n-1"]
is_return → ["Sales Return"]
```

The counter counts **sheets**, not events, which is why the pair advances it by
2. Formats that print one sheet per event (Grihalaxmi) pass `pair=False` and
get the same order spread one per print.

Every format and both renderers call `invoice_copy_titles(doc)`, so the wording
is defined once. (`invoice_activity_report.py:321` holds a second copy of the
*label* for stored sheet numbers — a different job, deliberately duplicated,
kept in sync by hand.)

### Stage 3c — what counts as a print

`before_print` (`hooks.py:127` → `print_count.py:133`) runs on every render,
preview included, and always stamps `doc.flags.print_prev_sheets` so the
template shows the titles the *next* print will use.

It only advances the stored counter when `doc.docstatus == 1 and
is_actual_print()`. `is_actual_print()` (`:126`) is true for
`trigger_print=1` or a `cmd` in `PRINT_OUTPUT_CMDS` (`:50`) — `download_pdf`,
`download_multi_pdf`, `print_by_server`, weasyprint, and
`get_rendered_raw_commands`.

So: **previewing is free, opening the PDF costs a sheet.** These are GET
requests, hence the explicit `frappe.db.commit()` (`:156`) — otherwise the
increment dies in the request-end rollback. The count lives in its own doctype
(`Sales Invoice Print Count`, autonamed by the invoice), never on the invoice,
and the increment is an atomic `UPDATE … SET print_count = print_count + %s`
(`:180`). A logging failure is swallowed: it must never block a print.

### Stage 4 — HTML to PDF

`chrome_pdf.render()` is the `pdf_generator` hook (`hooks.py:354`). It returns
`None` for any generator other than `"chrome"` so the next hook — finally
wkhtmltopdf — gets a turn.

It strips the desk's screen chrome, localises assets, writes the HTML to a temp
dir and shells out:

```
chrome --headless --disable-gpu --no-pdf-header-footer
       --run-all-compositor-stages-before-draw --virtual-time-budget=10000
       --print-to-pdf=… file://…
```

`--run-all-compositor-stages-before-draw` and the virtual time budget are what
stop a half-laid-out page being captured. If Chrome is missing it logs and
returns `None` — which means a **silently shrunk** print, so that Error Log
entry is the thing to check when a form suddenly comes out tiny.

Result: `@page { size: 241.3mm 139.7mm; margin: 0 }` becomes a **684 × 396 pt**
MediaBox with no `/Rotate`. Measured accuracy 1.0004×, 0.12 mm over the page.

---

## What breaks if you touch the wrong thing

| Symptom | Cause |
| --- | --- |
| Whole form shrunk into the top-left | wkhtmltopdf got it — check `pdf_generator` on the record, and the `chrome_pdf` Error Log |
| Print rotated / sideways | driver, not the format — the PDF has no `/Rotate`. Use `&rot=` |
| Everything a few mm off | `ox`/`oy`, never a field number |
| One field off | that form's `escp_*.py` POS entry |
| Format edits never reach the site | bump `modified` in the JSON — a standard format is only re-imported when its timestamp moves |
| Right-hand columns pulled inboard on the real form | the A5 clamps — check `page` is not `'a5'` |
| Title half a label width off | `COPY_LABEL_ANCHOR` disagrees with the builder's emit site |
| Nothing changes for a branch | `Company Print Template` still routes to a Dot Matrix format |

## Registration points for a new overlay form

1. `escp_<form>.py` — `POS`, `X0_MM`/`Y0_MM`, `COPY_LABEL_ANCHOR`
2. `overlay.py:_FORMS` — form key → module name
3. a Print Format JSON — the two-line wrapper, `pdf_generator: "chrome"`
4. a `Company Print Template` row — otherwise nothing routes to it
5. `test_overlay_print.py` — transcribe expectations from the **ESC/P builder**,
   not from `overlay.py`; that is what makes the harness non-circular

## Verification

`avinashgroup_app/test_overlay_print.py`, 72 checks, run from `sites/`:

```bash
cd /home/sijan/frappe-15/sites
../env/bin/python ../apps/avinashgroup_app/avinashgroup_app/test_overlay_print.py
```

Five layers: (A) HTML vs an independent transcription of the ESC/P map,
(B) PDF page facts, (C) positions measured back out of the PDF with
`pdftotext -bbox`, (D) two line items fit and clear the totals band,
(E) rotation and offsets. It renders real invoices, writes nothing, and asserts
the print counter did not move.
