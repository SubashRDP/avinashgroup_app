# Nepal Gas invoice printing — full context handoff (2026-07-12)

Read this to continue the print-calibration work from any device. Everything
below was established over 2026-07-11/12 on sijan's laptop.

## The system (already built, committed, pushed)

- 9.5"×5.5" (241.3×139.7mm) continuous-form Sales Invoice overlay. One Jinja
  template, absolute mm positioning:
  `avinashgroup_app/templates/print_formats/nepal_gas_invoice.html`
- 3 print formats (module records, synced by migrate):
  - **Nepal Gas Invoice Pre-Printed** — DATA ONLY, for the real pre-printed
    rolls. This is the production format.
  - **Nepal Gas Invoice Plain Paper** — draws form + data (blank paper,
    calibration).
  - **Nepal Gas Invoice A4 Proof** — crop-mark proof; user rejected it, ignore.
- PDFs render via headless Chrome (`custom_code/printing/chrome_pdf.py`)
  because distro wkhtmltopdf shrinks 0.7688×. Verified: PDF page is exactly
  684×396pts = 241.3×139.7mm (1:1 mm).
- **Fixed root cause of "prints portrait / lines off"**: the desk Print button
  browser-printed the preview on A4 portrait. `public/js/ngi_print.js`
  (app_include_js) now intercepts `PrintView.printit` for the 3 NGI formats
  and opens the Chrome PDF instead. Format list there must mirror
  `CHROME_PRINT_FORMATS` in `chrome_pdf.py`.

## Decisions made by the user

1. No A4 Proof format — calibrate with Plain Paper / Pre-Printed prints.
2. Always print at 100% / Actual size; clipping is acceptable; never fit-to-page.
3. **Straight (unrotated) print, sheet fed wide-edge-across the tray.**
   Rotated-90° variants were printed and rejected (2026-07-12).
4. Test prints go through `bench console` + `lp` (this does NOT bump the IRD
   `custom_print_count` — only trigger_print/download_pdf requests do).

## Calibration rig (on sijan's laptop only — printer is attached THERE)

- Canon LBP2900 (CAPT-only) on USB, driven by open-source captdriver
  (github.com/mounaiban/captdriver), compiled locally. CUPS queue `LBP2900`,
  filter `/usr/lib/cups/filter/rastertocapt` (root:root 755), device URI needs
  `?serial=`. "CAPT: no reply from printer" → power-cycle the printer.
  New machine setup: apt install autoconf automake libtool libcups2-dev
  libcupsimage2-dev cups-ppdc; clone repo; aclocal && autoconf &&
  automake --add-missing && ./configure && make && make ppd; install filter;
  lpadmin with ppd/CanonLBP-2900-3000.ppd.
- User cuts the sprocket strips off real forms at the perforations
  (−12.7mm each side → sheet 215.9×139.7mm) and feeds them to the Canon.

## Print recipes (run from `sites/` via `bench --site nepalgas console`)

```python
import frappe
pdf = frappe.get_print('Sales Invoice', 'NGK-SB-82/83-04316',
    'Nepal Gas Invoice Pre-Printed', as_pdf=True, pdf_generator='chrome')
open('/tmp/preprinted.pdf', 'wb').write(pdf)
```

Compose for the CUT sheet (shift 12.7mm=36pt left; page 612×396pt), then print:

```python
from pypdf import PdfReader, PdfWriter, Transformation
r = PdfReader('/tmp/preprinted.pdf'); w = PdfWriter()
p = w.add_blank_page(width=612, height=396)
p.merge_transformed_page(r.pages[0], Transformation().translate(tx=-36, ty=0))
w.write('/tmp/preprinted_cut.pdf')
```

```bash
lp -d LBP2900 -o media=Custom.215.9x139.7mm -o print-scaling=none /tmp/preprinted_cut.pdf
```

(The cut-sheet shift is a lab workaround only; production dot-matrix uses the
desk PDF as-is on the uncut roll.)

## CURRENT STATE / NEXT STEP

- Last test print: job 15, straight Pre-Printed data on a cut form. User says
  it's close; **"some scaling" still to adjust — not yet measured.**
- NEXT: user measures the straight print against the form boxes: per field,
  direction + mm. Uniform shift everywhere → set `ox`/`oy`
  (nepal_gas_invoice.html lines ~35-36, mm, + = right/down). Error growing
  across/down the page → scaling; fix by scaling the composed PDF (pypdf
  Transformation().scale()) for the Canon, but investigate before touching the
  template — the Chrome PDF itself is verified 1:1, so scale error is
  printer-side.
- ALSO PENDING: production Windows PC with the real dot-matrix — define custom
  form 24.13×13.97cm in Print server properties, tractor feed, print PDFs at
  100%, auto-rotate off. Then a first roll test; per-printer offset goes in
  `ox`/`oy`.

## To resume with Claude on another device

Clone/pull this repo, open Claude Code in the app directory, and say:
"Read NGI_PRINT_HANDOFF.md and continue the print calibration work."
Note the physical printer is on sijan's laptop — code/plan work is possible
anywhere, test prints only there (or attach the printer + redo rig setup).
