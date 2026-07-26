# Verification guide — pre-printed invoice printing (Grishma & Nepal Gas Udyog)

**For an independent reviewer.** Everything below is written so you can check it
yourself rather than take it on trust. Every claim has a command next to it and
the output you should see. Where something is *not* proven, it says so.

- Work done: **2026-07-25**, on bench `/home/sijan/frappe-15`, branch `develop`,
  on top of commit `358dfc3`. **Not committed, not deployed to production.**
- Scope: the two formats in live use — **Grishma Invoice A5 Overlay** (`grishma`)
  and **Nepal Gas Udyog Invoice A5 Overlay** (`ngi_udyog`).
- Print path: **browser only** (see §1). Raw ESC/P and Print Bridge are parked
  by decision, not deleted.

---

## 1. Background — what we are printing and how

The branches print IRD VAT invoices onto **pre-printed continuous tractor forms,
9.5 × 5.5 inches = 241.3 × 139.7 mm**, on Epson dot-matrix printers. The paper
already carries all the boxes and headings; the software must print *only the
data*, landing inside boxes that are already there.

There were historically three ways to do this. As of 2026-07-25 only one is
supported:

| Path | How | Status |
| --- | --- | --- |
| **Browser / PDF** | server renders a mm-exact PDF with headless Chrome; the user prints it | **the only supported path** |
| Raw ESC/P | byte stream to a Generic/Text-Only queue via Print Bridge | parked — worked on one machine, never went fleet-wide |
| Browser print of the preview HTML | the stock Print button | never correct — the driver repaginates onto its own paper |

The decision to go browser-only is recorded in
`docs/handoff_2026-07-25_printing.md` §8a. The reason is that the raw path needs
five fragile things on every computer (a special queue, the right driver, port
discovery, elevation, a 24-pin printer), and the browser path needs only that the
machine can already print.

### How the format is built (worth understanding before reviewing)

The coordinates are **not** duplicated between the two renderers. Each
pre-printed form has one calibrated coordinate map, living in its ESC/P
generator (`custom_code/printing/escp_grishma.py`, `escp_ngi_udyog.py`, …) as a
`POS` dict of true millimetres from the paper's top-left. The HTML overlay reads
those same numbers through `custom_code/printing/overlay.py`, so the two cannot
drift. One shared template renders all seven companies'
overlays: `templates/print_formats/nepal_gas_invoice_a5_overlay.html`.

**This matters for review:** a bug in `overlay.py` mistranslates the calibrated
map into HTML, and looks fine in code review, because the numbers are right and
only their *meaning* is wrong. Two of the three defects below were exactly that.

---

## 2. What was wrong, and the evidence

### Defect 1 — the A5 width clamps were applied to the real form (largest, ~11 mm)

`overlay.py` defines `AMT_RIGHT = 207.0` and `DATE_RIGHT = 205.0`. Their comments
say they exist to squeeze the right-hand columns inside **A5's 210 mm width**.
They were applied on *every* render, including the 241.3 mm form. The result:
dates were right-aligned to 205 mm when the calibrated map puts them
**left-anchored at 198 mm** (Grishma) and **193 mm** (Udyog).

The template's own comment already claimed the opposite of what the code did:

> `page = 'form' (default) -> 241.3 x 139.7mm … every column lands in its real
> box (nothing clamped).`

**Measured before and after**, same invoice, real rendered PDFs:

```
OLD   date 2083-03-32   x 189.7 .. 205.0 mm
NEW   date 2083-03-32   x 198.0 .. 213.3 mm
```

**Fix:** `overlay_pos(form, page)` now takes the page mode and applies the clamps
only when `page == 'a5'`. On the form, every column keeps its calibrated value.

### Defect 2 — the copy-title anchor was wrong for Grishma

`overlay.py` exposed every form's `copy_label` x as `cx` — a **centre** — and the
template centred a 50 mm box on it. But the ESC/P maps disagree per form, and
each one says so in its own source:

| File | Its own comment | How its builder emits |
| --- | --- | --- |
| `escp_grishma.py:52` | `x = START of the label text` | left-anchored, no centring maths |
| `escp_ngi_udyog.py:66` | `x = CENTRE (label is centred at emit time)` | subtracts half the text width |

So Grishma's title was printing roughly half a label width left of its box;
Udyog was already correct.

**Fix:** each form module declares its own convention beside the coordinate it
describes — `COPY_LABEL_ANCHOR = "left"` in `escp_grishma.py`, `"center"` in
`escp_ngi_udyog.py` — and `overlay.py` reads it, exposing `x` + `align` for the
template to honour. Corrected: grishma, gandaki, narayani, avinash. Unchanged:
ngi, ngi_udyog, karnali.

`overlay.py` does not default the value: a form module that fails to declare it
throws. Defaulting is what caused this defect (every x was assumed a centre), so
a new form is required to state which it means rather than inherit a guess.

### Defect 3 — the first copy printed with no title

The overlay skipped typing `TAX INVOICE`, on the assumption the roll already
carried it. **No roll carries a pre-printed title, on any company's stationery**
(confirmed by Sijan). So sheet 1 went out untitled.

**Fix:** the guard is gone — the whole series is typed. The wording was also
corrected to the standard series, changed in one place so every format and both
renderers follow:

```
TAX INVOICE → INVOICE → COPY OF INVOICE 1 → COPY OF INVOICE 2 → COPY OF INVOICE 3
```

(previously `COPY OF ORIGINAL n`). Returns still print a single `Sales Return`.

### Defect 4 — the Print button routed some formats to the browser dialog

`public/js/ngi_print.js` decided which formats get the mm-exact PDF route from a
**hardcoded list of five** that was never updated when the seven A5 overlay
formats were added. Those formats fell through to the stock browser print → the
driver's own paper → the rotated / multi-page misprint. The printer-icon path
(`company_print.js`) routed correctly all along, which is why the same invoice
behaved differently depending on which button was used.

**Fix:** routing is now on the format's own `pdf_generator` field, the same rule
`company_print.js` uses, so the two can no longer drift.

### Added — orientation rescue (`&rot=`)

Not a defect in the PDF: the PDF is always 241.3 × 139.7 mm with no `/Rotate`.
But a **driver or PDF viewer** downstream can still rotate it, and that is the
recurring "it printed sideways" complaint. Rather than chase per-machine
settings, the overlay can now rotate the content itself to cancel it out —
`&rot=0|90|180|270` on the print URL, with the page box swapped for the quarter
turns. Same idea as the cheque format's existing rotation knob.

### Added — self-service calibration

`&guide=1` outlines every field box (red) and the sheet edge (blue) so one test
print over a real form shows exactly what sits where; `&ox=`/`&oy=` shift the
whole print in millimetres. Both combine with `&rot=`. This replaces the old
instruction to "print the proof format", which was impossible — no proof variant
exists for these two forms.

---

## 3. What changed, file by file

Six modified, one added (plus docs). `git diff --stat`:

```
 report/invoice_activity_report/invoice_activity_report.py   |   7 +-
 custom_code/SalesInvoice/print_count.py                     |  32 +++---
 custom_code/printing/overlay.py                             |  50 +++++++--
 hooks.py                                                    |   2 +-
 public/js/ngi_print.js                                      |  17 +++-
 templates/print_formats/nepal_gas_invoice_a5_overlay.html   | 104 ++++++++++++++---
```

| File | Change |
| --- | --- |
| `custom_code/printing/overlay.py` | `overlay_pos(form, page)`; clamps only on A5; per-form copy-label anchor |
| `templates/.../nepal_gas_invoice_a5_overlay.html` | always type the title; honour the anchor; left-anchored dates on the form; `&rot=`, `&ox/&oy`, `&guide=1` |
| `custom_code/SalesInvoice/print_count.py` | `COPY OF ORIGINAL n` → `COPY OF INVOICE n` (both series), docstrings corrected |
| `report/.../invoice_activity_report.py` | second copy of the wording, kept in sync |
| `public/js/ngi_print.js` | route on the format's own `pdf_generator` |
| `hooks.py` | asset cache-buster `?v=1.2` → `?v=1.3` |
| `avinashgroup_app/test_overlay_print.py` | **new** — the verification harness |

Nothing in the parked ESC/P builders was touched.

---

## 4. How to verify — run this yourself

### 4.1 The automated harness (the main check)

```bash
cd /home/sijan/frappe-15/sites
../env/bin/python ../apps/avinashgroup_app/avinashgroup_app/test_overlay_print.py
```

**Expected: `72/72 passed`.** It renders existing invoices and writes nothing —
it asserts the print counter is unchanged at the end, so it is safe to run
against live data. Artifacts land in `/tmp/overlay_print_test/` for inspection.

It checks five independent layers, for **both** formats:

| Layer | What it proves | Why it is not circular |
| --- | --- | --- |
| **A. HTML vs ESC/P map** | every field's mm position and anchor in the rendered HTML | the expectation table in the test was transcribed **by reading the ESC/P builders**, not `overlay.py`. If `overlay.py` is "fixed" wrongly, this disagrees. |
| **B. PDF page facts** | 241.3 × 139.7 mm, no `/Rotate`, pages == sheets, exactly one `.last` | catches the "one invoice ate two forms" trailing-blank-page bug |
| **C. Measured text positions** | pulls text back out of the finished PDF with `pdftotext -bbox` and compares to the declared mm | proves *Chrome put it there*, not just that the HTML asked. A silent shrink-to-fit passes A and B but fails here. |
| **D. Two line items** | 2 rows fit one form and clear the totals band | field requirement: every form must hold at least two items |
| **E. Rotation** | each `&rot=` value gives the right page shape, writes no `/Rotate`, actually transforms, and `ox/oy` still apply | the orientation knob does what it claims |

Sample of what a passing run looks like:

```
[PASS] grishma: copy_label @ 118.5,40.0 left
[PASS] grishma: trans_date left-anchored at 198.0
[PASS] grishma: grand total right edge @ 210.0
[PASS] grishma: page 241.3x139.7mm  — got {(241.3, 139.7)}
[PASS] grishma: invoice no measured at x=39.0  — measured 39.00mm want 39.0mm
[PASS] grishma: scale 1:1 (bar 200.0mm)  — measured 199.97mm
[PASS] grishma: 2 items stay on 1 sheet
[PASS] grishma: rot=90 page 139.7x241.3mm  — got {(139.7, 241.3)}
```

### 4.2 Check the claims against the source yourself

The two mistranslation bugs are visible in the source comments — you do not need
to trust the description:

```bash
cd /home/sijan/frappe-15/apps/avinashgroup_app/avinashgroup_app/custom_code/printing
grep -n "copy_label" escp_grishma.py escp_ngi_udyog.py     # "START of the label" vs "CENTRE"
grep -n "trans_date" escp_grishma.py escp_ngi_udyog.py     # 198.0 / 193.0
grep -n -A3 "AMT_RIGHT\|DATE_RIGHT" overlay.py             # the A5-only clamps
```

Confirm the ESC/P builders emit dates **without** `right=True` (so the map's x is
a left edge, and right-aligning to 205 mm was wrong):

```bash
grep -n '_el(el, P\["trans_date"\]' escp_grishma.py escp_ngi_udyog.py
```

### 4.3 Verify a PDF by hand

```bash
pdfinfo /tmp/overlay_print_test/grishma.pdf | grep -E "Pages|Page size"
# Pages: 2            (TAX INVOICE + INVOICE — the IRD pair, first print)
# Page size: 684 x 396 pts   (= 241.3 x 139.7 mm)

pdftotext -bbox -f 1 -l 1 /tmp/overlay_print_test/grishma.pdf - | head -20
# multiply any coordinate by 25.4/72 to get millimetres
```

### 4.4 Verify in the browser (the part the harness cannot do)

The harness renders through the same code the server uses, but it cannot press
the button. Someone must:

1. `cd /home/sijan/frappe-15 && bench start`, open `http://localhost:8000`
   (site names are not hostnames — `http://nepalgas:8000` resolves to nothing).
2. Open a **submitted** Sales Invoice → Print view → select **Grishma Invoice A5
   Overlay** → **Print**.
   - **Expected:** a PDF opens in a new tab, plus the alert *"Print it at 100% /
     Actual size … never Fit to page"*.
   - **If the OS print dialog appears instead**, the JS did not reload — check
     the Network tab shows `ngi_print.js?v=1.3` and hard-reload (Ctrl+Shift+R).
3. Repeat from the **form's printer icon**. Both must behave the same.
4. Repeat for **Nepal Gas Udyog Invoice A5 Overlay**.
5. Print the same invoice twice and confirm the titles run
   `TAX INVOICE` + `INVOICE`, then `COPY OF INVOICE 1`.

### 4.5 Verify on paper (needs the real stationery)

1. **Orientation first.** Print with `&rot=0`, `90`, `180`, `270` and keep
   whichever comes out upright. Sample PDFs of all four already exist.
2. **Then position.** Print with `&guide=1` over a real pre-printed form and
   photograph it; read how far the red boxes sit from the printed boxes; re-print
   with `&ox=<mm right>&oy=<mm down>` (negative = left/up) until they line up.
3. Confirm two line items land on one form, inside the ruled rows.
4. Confirm one print event consumes exactly as many forms as it has copies, with
   the perforation between them.

Full operator instructions: `docs/browser_print_setup.md`.

---

## 5. What is NOT proven

State these plainly to anyone reviewing; do not let the green test run imply more
than it covers.

1. **The coordinate maps have never been checked against these two
   stationeries.** This is the biggest gap. `escp_grishma.py`'s own header says
   its numbers *start from the Nepal Gas calibration*, and `escp_ngi_udyog.py`
   says its were measured off a rectified scan of a **Narayani** form. The
   harness proves the pipeline faithfully reproduces those maps — it cannot prove
   the maps match the paper. A single `ox`/`oy` pair fixes a uniform shift; it
   cannot fix a per-field error.
2. **Nothing has been tested on a physical printer in this work.** No Epson was
   attached.
3. **Anything downstream of the PDF** — queue paper size, driver orientation, and
   the operator choosing "Actual size" — is outside the code. `&rot=` exists to
   make orientation recoverable without those settings, but it has not been
   confirmed on paper.
4. **Which path the branches use today.** If Company Print Template still points
   these companies at the raw dot-matrix formats, the printer icon goes to the
   parked ESC/P path and none of this is visible to them. **Check this on
   production before concluding anything.** Logging the print format and route on
   `Sales Invoice Print Log` (~20 lines) would make it a SQL query instead of a
   phone call.
5. **Production state is inferred from the local bench.** Re-read it on
   `ng-group` before acting.
6. **Long values may be clipped.** Fields are `white-space:nowrap;
   overflow:hidden`, so an unusually long customer name or item name is silently
   cut at the box width rather than wrapped. Not exercised against realistic
   worst-case data.
7. `test_invoice_a5_print.py` (the *other*, plain-paper A5 format) currently
   **fails** its page-size and scale checks. This was verified to be
   **pre-existing** — it fails identically with all of this work stashed — and is
   a different format, out of scope here. It should be looked at separately.

---

## 6. Migrating to production (`ng-group`) — not yet done

### 6.0 The two things that make this migration unusual

**A. Do NOT run `bench migrate`.** Nothing in this change needs it — there are no
new doctypes, no new patches, and the print-format JSONs are untouched. Meanwhile
`patches.txt` carries a dozen unrun-on-some-sites patches, and a live migrate on
this bench has previously been flagged as crashing on an `hrms` advance patch.
Running migrate here buys nothing and risks an unrelated failure mid-deploy.
(If someone insists it is needed, make them say which patch requires it.)

**B. Code alone changes nothing for the branches.** This is the step every
previous handoff missed. `Company Print Template` decides which format the
printer icon and print-on-submit actually use, and on the dev site **not one
company points at an overlay** — everything routes to a Dot Matrix format, i.e.
the parked raw ESC/P path:

```
company                                  print_format
Grishma Enterprises Pvt. Ltd.            (NO ROW AT ALL)
Nepal Gas Udhyog Pvt. Ltd.               Grishma Invoice Dot Matrix     <- also looks wrong
Nepal Gas Udhyog (Gandaki/Karnali/…)     Nepal Gas Invoice Dot Matrix
```

Re-read this on production before doing anything else:

```bash
bench --site ng-group mariadb -e "select company, print_format, \
return_print_format, print_on_submit from \`tabCompany Print Template Company\` \
where parent='Sales Invoice' order by company;"
```

### 6.1 Order of operations

Code first, then data. Flipping the data first would point branches at the
overlay formats *before* the fixes land.

```bash
# 1 · dev machine — commit. Do NOT include print_bridge/* (parked path).
git add avinashgroup_app/ docs/
git commit -m "Invoice overlay: type all copy titles, honour per-form anchors, \
A5 clamps only on A5, orientation + calibration knobs, geometry test"
git push origin develop      # NOTE: develop is currently 2 commits ahead already
                             # (two cheque-print commits) — they ship too. Review them.

# 2 · server — code
cd ~/frappe-bench
git -C apps/avinashgroup_app pull origin develop
bench --site ng-group clear-cache    # hooks.py changed the ?v= asset version
bench restart                        # python modules + the jinja template cache
```

No `modified` bump is needed — the print-format JSONs are untouched; all geometry
lives in the shared template and `overlay.py`, both read from disk. No
`bench build` — `sites/assets/avinashgroup_app` is a symlink to the app's
`public/`.

```bash
# 3 · confirm the code is actually live BEFORE touching the data
curl -s https://ng-group.raindropinc.com/assets/avinashgroup_app/js/ngi_print.js \
  | grep -c is_chrome_format         # expect 3
```

Then run §4.4 in a browser on production — Print view *and* printer icon, both
formats. Only when that is green, do the data step.

### 6.2 The data step — switching the two companies to the overlays

In the **desk UI**, not SQL: `Company Print Template` → *Sales Invoice*. Saving
through the UI fires `on_update`, which invalidates the cached template map; a
raw SQL update leaves the old routing in redis.

| Company | Set `print_format` to | Note |
| --- | --- | --- |
| Grishma Enterprises Pvt. Ltd. | `Grishma Invoice A5 Overlay` | row may not exist — add it |
| Nepal Gas Udhyog Pvt. Ltd. | `Nepal Gas Udyog Invoice A5 Overlay` | currently `Grishma Invoice Dot Matrix` |

Leave `return_print_format` alone. Leave the other five companies alone — they
are out of scope and still on the parked path by choice.

**Confirm which company owns the `ngi_udyog` stationery before flipping it.**
The format name and the company name are not proof; ask the branch which roll
they load. Getting this wrong puts data in the wrong boxes on live invoices.

Do this **outside business hours** — `bench restart` briefly drops connections,
and the first branch print after the switch is the real test.

### 6.3 Rollback

Both halves are cheap to undo, which is why the data step goes last:

- **Data:** change the dropdown back to the Dot Matrix format and save. Instant,
  no deploy.
- **Code:** `git revert <sha> && bench --site ng-group clear-cache && bench restart`.

### 6.4 After the switch

- Print one real invoice per company, on the real stationery.
- Fix orientation with `&rot=` (§4.5) before worrying about position.
- Check `Error Log` for `chrome_pdf` entries — if Chrome is missing on the server
  the render silently falls back to wkhtmltopdf, which shrinks **every length to
  0.7688×**, and that log line is the only visible sign. If it appears, set
  `"chrome_path"` in `site_config.json`.
- Confirm the copy series on a second print: `COPY OF INVOICE 1`.

---

## 7. Open items after this

1. Print the four `&rot=` samples and fix the correct one as the default.
2. Calibrate `ox`/`oy` per form from a guide print, then make them permanent.
3. Persist `ox`/`oy`/`rot` per branch from the desk so no deploy is needed to
   adjust — the `Cheque Print Alignment` doctype already solves this exact shape;
   port the pattern (~1 hour).
4. Log `print_format` and route on `Sales Invoice Print Log` (§5.4).
5. Investigate the pre-existing `test_invoice_a5_print.py` failure (§5.7).
