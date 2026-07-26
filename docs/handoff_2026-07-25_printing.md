# Handover — Invoice printing (2026-07-25)

Hand-off for the **pre-printed IRD VAT invoice printing** thread. Written from the laptop
bench `/home/sijan/frappe-15`, branch `develop`, on top of commit `25fd3c6`.

Supersedes the printing sections of `handoff_2026-07-22.md` for the *invoice overlay*
path. Print Bridge (the Windows raw-print agent) is unchanged — for that, start at
`print_bridge_troubleshooting_handover.md`.

> **Read `## Deploy debt` first.** There is an unreleased bug fix sitting uncommitted in
> the working tree, and it has **not** been tested in a browser.

---

## 1. The problem this thread exists to solve

Print IRD VAT invoices onto **pre-printed 9.5″ × 5.5″ continuous tractor forms** on Epson
LQ-310 dot-matrix printers, across 7 companies and several remote branches, so that every
value lands inside a box that is already printed on the paper. Replaces FACT ERP, which did
this for years by bypassing the Windows graphics driver entirely.

## 2. The mental model — there are three print paths, not one

This is the single most important thing to understand before touching anything. The same
invoice and the same print format behave completely differently depending on how the user
triggered the print.

| Path | Trigger | Renderer | mm-exact? |
| --- | --- | --- | --- |
| **PDF** | "Get PDF", or Print view → Print *for chrome formats* | `chrome_pdf.render` server-side | **Yes** |
| **Browser print** | Print view → Print for any other format; Ctrl+P | The user's browser, onto the **driver's** paper | **No** — driver says A4, form rotates/repaginates |
| **Raw ESC/P** | Raw formats via Print Bridge | `escp_*.py` → bytes → `LQ310-RAW` queue | Yes (bypasses driver) |

Almost every "the print is wrong" report in this project has turned out to be *the right
template rendered through the wrong path*, not a bad template.

## 3. What is proven, by measurement (2026-07-25)

Do not re-litigate these; they were measured, not reasoned about. Scripts used are
throwaway, but trivially reproducible (render → `pypdf` MediaBox → `pdftoppm` → pixel extents).

- **The PDF geometry is exact.** Real invoices through `frappe.get_print(..., as_pdf=True)`:

      Nepal Gas Invoice A5 Overlay   pages: 1   page 1: 241.30 x 139.70 mm  rotate=0
      Nepal Gas Invoice Pre-Printed  pages: 1   page 1: 241.30 x 139.70 mm  rotate=0

- **Chrome honours `@page` exactly.** A minimal 241.3 × 139.7 mm red-box page rendered
  through the same Chrome flags: 1 page, `241.30 x 139.70 mm`, `rotate=0`, red rect
  measured at **241.30 × 139.70 mm starting at (0.00, 0.00)**.
- **Multi-page output is by design, not a pagination fault.** `NGG-SB-82/83-00141`,
  2 items, `invoice_copy_titles` → `['TAX INVOICE', 'INVOICE']` → 2 copies × 1 item-page
  = 2 pages, each full form size. A single-item invoice already printed 11 times returns
  `['COPY OF ORIGINAL 11']` → 1 page. This is the IRD copy requirement.
- **`pdf_generator` is correctly pinned.** On `avinas1` the field is a visible Select with
  options `wkhtmltopdf\nchrome`; all seven A5 overlays and the pre-printed formats read
  `'chrome'`.

**Corollary: the overlay templates' CSS and coordinates are correct.** Proposals to change
`page-width`/`page-height`, remove `contain: strict`, or add `page-break-before: always`
address a defect that is not in the output. (`page-width` is a *wkhtmltopdf CLI option*
name — see `frappe/utils/pdf.py` — not CSS. Chrome ignores it; it is dead code, not a bug.
`page-break-before: always` would have injected a blank leading page.)

## 4. The bug found and fixed today

**Symptom:** printing an A5 Overlay format produced content flowing top-to-bottom across
multiple A4-ish pages instead of one tractor form.

**Root cause:** `public/js/ngi_print.js` patches `PrintView.printit` to route mm-exact
formats to `download_pdf`. It decided which formats those were from a **hardcoded list of
five**, with the comment *"Must mirror CHROME_PRINT_FORMATS in chrome_pdf.py"*. The seven
A5 Overlay formats were added later (`d5f0dea`, `4b20c29`) and **the list was never
updated** — so they fell through to stock `printit()` → browser print → driver's paper.
The list had also drifted from the set it claimed to mirror (`Nepal Gas Invoice A4
Portrait` was missing).

Meanwhile `company_print.js` (the form printer icon / print-on-submit path) routes on
`sel.generator === "chrome"` — the format's own field — and was always correct. So the
same invoice printed correctly from the printer icon and incorrectly from the Print view.

**Fix:** `ngi_print.js` now routes on the format's own `pdf_generator`, the same rule
`company_print.js` uses, with the list demoted to a fallback:

```js
function is_chrome_format(view) {
    const format = view.selected_format();
    const doc = view.get_print_format ? view.get_print_format(format) : null;
    if (doc && doc.pdf_generator) return doc.pdf_generator === "chrome";
    return NGI_FORMATS.includes(format);
}
```

The two print paths can no longer drift: a new overlay format needs no edit in either file.

## 5. Deploy debt — do this next

**Uncommitted in the working tree** (branch is also 1 commit ahead of `origin/develop`):

| File | Why |
| --- | --- |
| `avinashgroup_app/public/js/ngi_print.js` | the fix above |
| `avinashgroup_app/hooks.py` | asset cache-buster `?v=1.2` → `?v=1.3` |
| `CLAUDE.md` | stale env facts, see §8 |

(`payment_entry_cheque_v1_adjusted.json` and the untracked
`payment_entry_cheque_lq_240x140/` directory were already modified before this session and
are **not** part of this work.)

To deploy:

```bash
cd /home/sijan/frappe-15
bench --site avinas1 clear-cache     # hooks.py changed the asset version
bench start                          # dev server is not always running
```

Assets are symlinked (`sites/assets/avinashgroup_app` → the app's `public/`), so **no
`bench build` is needed** — but the `?v=` bump plus `clear-cache` is mandatory or browsers
keep the old JS.

### ⚠ Not yet verified in a browser

The fix is verified only at the file level:

```
$ grep -c is_chrome_format /home/sijan/frappe-15/sites/assets/avinashgroup_app/js/ngi_print.js
3
$ node --check avinashgroup_app/public/js/ngi_print.js   # passes
```

**The end-to-end browser test was never run** — the bench dev server was not running during
this session. Whoever picks this up must do it:

1. `bench start`, open `http://localhost:8000` (site names are **not** hostnames —
   `curl http://avinas1:8000/...` resolves to nothing).
2. Open a submitted Sales Invoice → Print view → select an **A5 Overlay** format → **Print**.
3. **Expected:** a PDF opens in a new tab, plus the alert *"Print it at 100% / Actual size
   on the 9.5″ × 5.5″ form — never Fit to page."*
   **If instead the OS print dialog appears immediately**, the JS did not reload — check
   `frappe.boot.app_include_js` shows `ngi_print.js?v=1.3`.
4. In the PDF dialog choose **Actual size / 100%**, never "Fit to page". This is the last
   place scaling can be reintroduced and it is outside anything the code controls.

## 6. The system, for someone new

**Print formats** (~40 across the 7 companies) live in
`avinashgroup_app/avinash_group_app/print_format/`; most are thin JSON wrappers that
`{% include %}` a template from `avinashgroup_app/templates/print_formats/`.

**ESC/P generators** — `custom_code/printing/escp_*.py`, one per pre-printed form
(`escp_invoice` = NGI, plus `ngi_udyog`, `gandaki`, `karnali`, `narayani`, `grishma`,
`avinash_slip`). Coordinates were measured off sprocket-rectified scans (homography fit to
all 22 sprocket-hole centres, 0.39 mm mean / 0.99 mm max residual). **Two calibration
constants per rig** — `X0_MM`, `Y0_MM` — shift the whole form; every `POS` entry is a true
ruler mm from the paper edge. *Adjust X0/Y0, never individual fields.*

**`custom_code/printing/overlay.py`** — the HTML overlay reads its coordinates out of the
ESC/P `POS` dicts rather than duplicating them. One source of truth, two renderers; they
cannot drift. `overlay_pos(form)` is exposed to Jinja via `hooks.py`.

**`custom_code/printing/chrome_pdf.py`** — renders through headless Chrome instead of
wkhtmltopdf. Non-negotiable: the shipped wkhtmltopdf is built against unpatched Qt and
renders **every length at 0.7688×**, un-disableable. Chrome measures 1.0004×.
`printing/setup.py` re-pins `pdf_generator = chrome` from `after_migrate`, because
re-importing a standard print format resets the field.

**Print Bridge** — `print_bridge/`, the Windows agent that carries raw ESC/P bytes to the
`LQ310-RAW` (Generic / Text Only) queue. The stock Epson ESC/P V4 driver silently swallows
RAW jobs. QZ Tray is fully removed.

**IRD copy tracking** — `custom_code/SalesInvoice/print_count.py`. `invoice_copy_titles` is
the single source of truth for the Tax Invoice / Invoice / Copy of Original N series; both
Jinja and ESC/P call it. Only *actual* prints consume sheets — previews do not.

## 7. Calibrating a branch without touching their machine

You do not need the client's printer.

1. Have them print the **proof format** (`draw_form = true`, e.g. `Nepal Gas Invoice A4
   Proof`) on plain paper. It draws the form furniture itself.
2. They lay it over a real pre-printed form against a light and photograph it.
3. You read the offset and set **`ox` / `oy`** (mm, + = right / down) — URL params on the
   overlay template. Nothing else moves.

Framed to the client this is *"print one sheet and send a photo"*, a one-time setup — the
same thing FACT/Tally/Busy have always required for dot-matrix stationery.

## 8. Traps that have each cost real time

- **wkhtmltopdf shrinks everything 0.7688×.** If a form suddenly prints small, check
  `pdf_generator` didn't revert to `wkhtmltopdf`.
- **Print format edits silently never reach the site unless `modified` is bumped** in the
  JSON. The tell is a constant single-axis PDF offset.
- **JS edits need the `?v=` bump in `hooks.py` + `clear-cache`**, or browsers keep the old file.
- **`developer_mode` and `server_script_enabled` are OFF on this bench** (verified — `frappe.conf`
  returns `None`). UI edits to doctypes/print formats **will not export to disk**. Edit files, migrate.
- **There is no DB replica here** despite `docs/db-master-slave-replication.md`; only
  MariaDB `:3306` is listening and `read_from_replica` is unset.
- **Two lists must agree** when a format's generator is *not* in its JSON: `CHROME_PRINT_FORMATS`
  in `chrome_pdf.py` and the `after_migrate` pin. Formats carrying `"pdf_generator": "chrome"`
  in their own JSON (all seven overlays) need neither.
- **ESC/P feed units are hardcoded to 1/180 in** (`_feed_to` in `escp_invoice.py`). That is
  24-pin ESC/P2. A **9-pin Epson LX** feeds in **1/216 in**, so every vertical position would
  land at 83 % of target — cumulative down the form, header nearly right, totals badly out.
  **Keep the fleet 24-pin (LQ-310, or LQ-350 as the direct replacement)** until this is
  parameterised. Note this affects the *raw* path only: the overlay path renders a PDF
  through the graphics driver and is printer-model-agnostic.

## 8a. DECISION 2026-07-25 (evening): browser way ONLY

Sijan: *"i need only browser way.. no need any other way."* The supported path is
Print view / printer icon → server-side Chrome PDF → user prints the PDF through
the machine's own driver queue at 100%. Raw ESC/P, Print Bridge raw carrying, and
the driver-mode bridge idea (`docs/requirement_print_bridge_driver_mode.md`) are
**parked, not deleted** — do not spend time on them unless this decision is
reversed. What browser-way-only needs per machine is exactly three things:
queue default paper = the 24.13 × 13.97 cm form, Orientation = Portrait, print at
100%. Reference implementation: this laptop's `EPSON-LQ-310` CUPS queue (NGIForm
default + `rastertoepson-lq310` double-feed wrapper), byte-level verified
2026-07-25 without a printer. A 9-pin LX-310 is fully supported on this path
(coarser output); it was only the raw path that excluded it.

## 8b. Grishma + Nepal Gas Udyog hardening (2026-07-25 evening)

Scope narrowed by Sijan to the two formats actually in use: **Grishma Invoice A5
Overlay** and **Nepal Gas Udyog Invoice A5 Overlay**. Three real defects found
and fixed, all verified by `avinashgroup_app/test_overlay_print.py` (46/46):

1. **Copy titles.** The overlay skipped typing "TAX INVOICE" (assuming the roll
   carried it — no roll does). Guard dropped; wording is now
   TAX INVOICE → INVOICE → COPY OF INVOICE n, changed once in `_titles_for()`
   so every format and both renderers follow. `invoice_activity_report.py`
   carries a second copy of the wording and was updated to match.
2. **Copy-label anchor.** `overlay.py` called every form's `copy_label` x a
   CENTRE, but the ESC/P maps say otherwise per form — grishma's own POS comment
   reads *"x = START of the label text"*, ngi_udyog's reads *"x = CENTRE"*. The
   HTML put Grishma's title ~half a label width left of its box. `overlay.py`
   now reads the convention from the form module itself (`COPY_LABEL_ANCHOR`,
   declared next to the coordinate, no default — a module that omits it throws);
   ngi_udyog, ngi and karnali are unchanged, grishma/gandaki/narayani/avinash
   corrected.
3. **A5 clamps applied on the real form** (the largest error, ~11mm). `AMT_RIGHT
   =207` / `DATE_RIGHT=205` exist only to fit A5's 210mm width, but ran on the
   241.3mm form too, right-aligning dates to 205mm when the calibrated map puts
   them left-anchored at 198 (grishma) / 193 (ngi_udyog). Measured before/after
   on a real invoice: date x moved 189.7mm → 198.0mm. `overlay_pos(form, page)`
   now applies the clamps only when `page == 'a5'`.

**Orientation is now fixable without touching the machine** — Sijan's priority
("by anyhow the paper orientation should come good"): `&rot=0|90|180|270` on the
print URL rotates the content inside the page and swaps the page box for the
quarter turns, so a driver that would have rotated a landscape page is handed a
portrait one with the form already turned inside it and has no reason to rotate.
Same idea as the cheque format's rotation knob. All four modes are asserted in
`test_overlay_print.py` (page box shape, no `/Rotate` in the PDF, the transform
actually present, and ox/oy still applying under rotation).

**Calibration is now self-service**: `&guide=1` outlines every field box and the
sheet edge (never shown in a normal print), and `&ox=`/`&oy=` nudge the whole
print in mm — same shape as the cheque format's `&dx/&dy`. See
`docs/browser_print_setup.md`. This replaces the "print the proof format"
instruction, which was impossible: no proof variant exists for these two forms.

**Not yet done:** persisting ox/oy per branch from the desk (a doctype, ~1h,
pattern already exists in `Cheque Print Alignment`), and deploying any of this
to `ng-group` — see §9.

## 9. Open items, roughly by value

1. **Run the browser test in §5.** Nothing else matters until this is confirmed.
2. **Persist `ox`/`oy`.** They are URL params today, so per-branch calibration means
   hand-maintained URLs. `Cheque Print Alignment` (fields `move_right`, `move_down`,
   `rotation`, `tray_align`, `sheet_mode`) already solves exactly this shape for cheques —
   port the pattern to invoices, keyed by company or branch. Turns "I'll set it remotely"
   into "the branch sets it themselves". ~1 hour.
3. **Log `print_format` and `route` on `Sales Invoice Print Log`.** It currently stores
   `sales_invoice`, `customer`, `customer_name`, `branch_name`, `company`, `copy_number` —
   so *there is no way to tell from history which print path a branch used*, which is
   exactly the question that blocked diagnosis today. Both values are already in hand in
   `before_print` (`_current_print_format()` and `is_actual_print()`). ~20 lines, and it
   makes "is any branch still on the browser-print path?" a SQL query.
4. **Make the ESC/P feed divisor per-printer**, so a 9-pin LX is a supported option.
5. **Per-branch calibration still pending for Grishma and NGI** (carried over from earlier
   handoffs).
6. **Copy titles: skip is wrong for ALL companies, and the series wording is wrong**
   (clarified by Sijan during browser testing 2026-07-25). No roll has a pre-printed
   title; the standard series must be TYPED on every sheet, for every company:
   *TAX INVOICE → INVOICE → COPY OF INVOICE 1 → COPY OF INVOICE 2 → COPY OF INVOICE 3*.
   Two edits when picked up (deferred — "this is for later"):
   - drop the `copy_label != 'TAX INVOICE'` guard in
     `templates/print_formats/nepal_gas_invoice_a5_overlay.html` (always type the title);
   - change `COPY OF ORIGINAL {n}` → `COPY OF INVOICE {n}` in `_titles_for()`
     (`custom_code/SalesInvoice/print_count.py`) — single source feeding overlays,
     ESC/P builders, and the Grihalaxmi/Half formats alike. Check the ESC/P builders
     don't also carry their own skip of TAX INVOICE.

## 10. What was *not* verified

Stated plainly so nobody inherits false confidence:

- The browser end-to-end test (§5). File-level only.
- **Which path the branches actually use.** If they print from the form's printer icon they
  were on the already-correct `company_print.js` route, in which case today's fix is real but
  may not be *their* symptom — and something else is in play. Item 3 above exists to make
  this answerable.
- Nothing was tested against a physical LQ-310 in this session.
