# Requirement — Print Bridge "driver mode" (PDF through the existing Windows driver)

Status: **accepted as a future requirement, not yet built** (decided 2026-07-25).
Owner of the decision: Sijan. Target version: print-bridge 0.6.0.

## The problem this solves

The raw ESC/P path is deterministic on the paper but fragile on the computer: it
needs the `LQ310-RAW` Generic/Text-Only queue, the RAW datatype, port discovery,
elevation, and PowerShell — five per-machine things that can each fail (and have:
see the bare-`powershell` PATH bug fixed in 0.5.3). The browser/PDF path needs no
setup but hands the last step to a human print dialog, where "Fit to page",
auto-rotate, and wrong paper sizes are born — the source of the recurring
"printed 90° rotated / up-down" reports.

Principle the requirement encodes: **if Windows can already print a test page to
the Epson, the invoice must print correctly with zero extra setup.**

## The design

Add a `pdf` job type to Print Bridge alongside `raw`:

1. ERP renders the overlay PDF exactly as today (server-side headless Chrome —
   geometry proven: 241.30 × 139.70 mm, rotate=0).
2. Browser posts the PDF (base64, same transport as raw jobs) to the bridge.
3. The bridge prints it **programmatically through the Epson's own existing
   queue** (the one Word/Excel already use):
   - render PDF pages to pixels with PyMuPDF at the printer's DPI;
   - open a GDI printer DC with an exact DEVMODE set in code: custom paper
     241.3 × 139.7 mm (`dmPaperWidth`/`dmPaperLength` are in 0.1 mm — no
     pre-defined Windows form needed), `dmScale = 100`, orientation fixed;
   - `StretchDIBits` the pixels onto the page. No viewer, no dialog, no human
     choices.

Target queue selection: default to the installed Epson queue (the `epson_seen`
logic in `diagnose()` already finds it); overridable in `config.json`.

## What it eliminates, per machine

| Today's failure source | Driver mode |
| --- | --- |
| RAW queue missing / wrong driver / port moved | Gone — uses the queue that already works |
| Generic/Text driver staging, PowerShell, elevation | Gone — no queue creation at all |
| Human picks "Fit to page" / auto-rotate in the PDF dialog | Gone — no dialog; no-scale is set in code |
| Driver paper size defined wrong → 90° rotation | Gone — paper size passed per job; if a driver refuses width > length, the bridge rotates the raster itself (handled once in code, not per machine) |
| 9-pin LX-310 vertical drift on raw (1/216 vs 1/180 feed units) | Gone — the driver handles motion; LX becomes fully supported |

Remaining per-machine dependency: the bridge agent itself (installer, autostart,
diagnostics all already exist).

## Tradeoffs accepted

- Driver printing on a dot-matrix is graphics-band printing: slower, noisier,
  text as rendered dots rather than the printer's own font. **Raw stays the
  preferred path where it is set up; driver mode is the automatic fallback.**
- One assumption to verify per driver family (not per machine): the Epson ESC/P
  driver accepts a custom 241.3 × 139.7 mm page via DEVMODE. Dot-matrix drivers
  generally allow user-defined sizes up to the 254 mm carriage; the raster-rotate
  fallback covers a driver that refuses width > length.

## Test strategy (no physical printer needed)

The GitHub CI runner is real Windows with a **"Microsoft Print to PDF"** queue.
The smoke test prints through the actual GDI path to that queue, then measures
the produced PDF's page size and content position — end-to-end proof of the
pipeline on every push, before any till is touched.

## Effort estimate

~150–200 lines in `print_bridge.py` (job type + GDI print function), PyMuPDF in
the PyInstaller bundle (~30 MB installer growth), a small change in
`company_print.js` / `print_bridge.js` to send the PDF to the bridge instead of
opening a viewer tab, plus the CI smoke test.

## Related

- `docs/handoff_2026-07-25_printing.md` — the three-print-paths model, the
  ngi_print.js routing bug, and what is measured vs. assumed.
- `print_bridge/print_bridge.py` — 0.5.3 fixed queue creation failing on
  machines whose PATH cannot find `powershell` (now invoked by absolute path).
