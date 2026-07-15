# Session handoff — 2026-07-15, Grishma printing + Windows QZ debugging

State of play when this session ended (laptop being rebooted into Windows).
Read together with `docs/claude_printing_handoff.md` (full architecture +
failure-mode reference).

## Where we are

### Grishma Enterprises invoice — DONE, calibrated, committed
- Two formats, both live on sites `avinas` + `nepalgas` and pushed:
  - **"Grishma Invoice Dot Matrix"** — raw ESC/P, the production path.
    Coordinates in `custom_code/printing/escp_grishma.py` (POS block; x =
    text START except r_qty/r_rate/r_amt = right edge; all mm from form
    top-left). Field-calibrated on the office LQ-310 through test jobs
    ~172-181 (commit f5ba987). Address line prints the customer's primary
    Address `address_line1`, blank if none (no fallback, per user).
  - **"Grishma Invoice Pre-Printed"** — chrome-PDF overlay clone of the
    Avinash format (`templates/print_formats/grishma_invoice_epson.html`),
    secondary path.
- Calibration loop: `./print_grishma_test.sh ['INV']` at the bench root
  (edits POS → prints first sheet raw via `lp -o raw`, no IRD counter bump).
- Last calibration action: printed NGK-SB-82/83-04162 (job 181) to check the
  PAN field position — **user never reported back on PAN placement; ask.**
- Dates note: form's date boxes are at 20.4cm but head reach ends 21.5cm, so
  dates print from 19.8cm (physical limit, wraps otherwise).

### Raw-print browser routing — FIXED, committed (d201825)
company_print.js v1.4 routes raw formats through QZ Tray instead of
/printview (that bug printed everything bunched at the top of the form).
Verified: get_rendered_raw_commands returns byte-identical, fully 7-bit
output on all paths.

### Server deploy — user pulled to the live server today
Steps given: migrate (watch for the hrms advance-patch crash), build,
clear-cache, restart; generate `sites/<site>/qz-*.pem` (openssl one-liner in
qz_security.py header); add Grishma row to Company Print Template (its row
was REMOVED from the avinas template today by a UI edit — re-add wherever
needed). Confirm which of these actually ran.

### Windows laptop printing — IN PROGRESS, this is the open problem
Symptom chain established:
- Browser: green "Print sent" ✓
- Correct queue receives job "QZ Tray Raw Print" (proved with paused queue) ✓
- Job status "printed", **printer never moves** ✗
- Windows test page prints fine ✓ ; port is USB002 (not WSD) ✓
- "Enable advanced printing features" already off
- Diagnosis: Epson driver's language monitor swallows RAW-datatype jobs.
- **Prescribed fix, not yet confirmed done:** add queue **LQ310-RAW**
  (Generic / Text Only driver, same USB002 port), remap the format in Print
  view → Printer Settings to it.
- **Next step = Test A** (bisects Windows raw path without QZ/browser):
  share LQ310-RAW as `RAW`, then from cmd:
  `copy /b C:\test.txt \\localhost\RAW`
  - prints → Windows raw OK; fix is only remapping QZ to LQ310-RAW; if still
    silent after remap, read QZ Tray log (Advanced → Diagnostic).
  - silent → USB/port level: replug/other cable/port, re-check USB00x.

## Loose ends
1. PAN position feedback (job 181) — possibly one more POS nudge.
2. Company Print Template rows: Grishma row missing on avinas (removed in a
   UI edit); NGI main row was set print_on_submit=0 during testing — restore
   intended values. Site rows are DATA, re-check on the live server too.
3. `263191a` (docs handoff) was unpushed when the session ended — push it.
4. User's unrelated pending work (report JS, naming_series.py, docs edits)
   is intentionally uncommitted — leave it alone.
5. Office Windows laptops: full checklist is in claude_printing_handoff.md
   (QZ Tray install, install-qz-cert.bat from the setup_bat endpoint, per-
   format printer mapping, tractor alignment ~12mm).

## SHIPPED (later on 2026-07-15): all-in-one print machine installer

The raw-queue deliverable above is superseded by a bigger one, now in the app:

- `qz_security.setup_print_machine_bat()` — logged-in download at
  `/api/method/avinashgroup_app.custom_code.printing.qz_security.setup_print_machine_bat`
  returns `setup-print-machine.bat`: self-elevates, installs QZ Tray v2.2.6 if
  missing (GitHub download, silent /S; skips gracefully offline), creates the
  LQ310-RAW Generic/Text Only queue on the Epson's auto-detected USB port
  (idempotent), writes the site cert as override.crt, restarts QZ Tray.
- `company_print.js` v1.5: `qz_raw_print()` falls back to LQ310-RAW when no
  explicit Print-view mapping exists (explicit mappings still win) — the
  per-browser mapping step is gone on machines set up by the installer.
- The older `setup_bat` (cert-only installer) still exists unchanged.
