# Claude handoff prompt — dot-matrix invoice printing (paste into Claude Code at the destination)

Copy everything below the line into Claude Code on the destination machine when
there is a printing problem. It contains the full system knowledge and every
failure mode we have already diagnosed, so start from it instead of rediscovering.

---

You are debugging invoice printing for the Avinash Group ERP (Frappe 15 bench,
app `avinashgroup_app`). Invoices print on **Epson LQ-310** dot-matrix printers
onto pre-printed continuous forms (9.5in × 5.5in, tractor feed). Read this
whole context before touching anything.

## Architecture — three print paths

1. **Raw ESC/P formats** (the production path for dot-matrix):
   - Print Formats: `"Nepal Gas Invoice Dot Matrix"` (built by
     `avinashgroup_app/custom_code/printing/escp_invoice.py`, jinja method
     `ngi_escp`) and `"Grishma Invoice Dot Matrix"`
     (`custom_code/printing/escp_grishma.py`, `grishma_escp`). Grishma form has
     NO HS Code column; otherwise same layout family.
   - `raw_printing=1`, `raw_commands = "{{ ngi_escp(doc) }}"` etc.
   - The byte stream is deliberately **100% 7-bit ASCII**: horizontal position
     is CR + spaces at 15cpi (NOT `ESC $` — its binary args >127 get UTF-8
     mangled in the browser→QZ path), vertical is `ESC J n` with n≤127, form
     length `ESC C 33` (33 × 1/6in = 5.5in), `ESC g` 15cpi. Never reintroduce
     bytes >127.
   - Coordinates: `POS` dict in each escp_*.py, **mm from the form's top-left
     corner** (x = where text STARTS, except r_qty/r_rate/r_amt = RIGHT edge).
     `X0_MM`/`Y0_MM` describe the printer rig (dev rig: 12.0 / -7.7, measured
     with a centre-circle target). Head travel limit: X0 + 203.2mm ≈ 215.4mm
     from the paper edge — fields further right WRAP to the next line; that is
     physics, not a bug.
2. **Chrome-PDF overlay formats** ("Nepal Gas Invoice Pre-Printed", "Avinash
   Invoice Pre-Printed", "Grishma Invoice Pre-Printed", …): mm-exact HTML
   rendered by headless chrome (`custom_code/printing/chrome_pdf.py`,
   `CHROME_PRINT_FORMATS` set; page exactly 241.3×139.7mm). Desk Print button
   is rerouted to the 1:1 PDF by `public/js/ngi_print.js`. Must print at 100% /
   Actual size, never fit-to-page.
3. **Company Print Template** (custom doctype, one record per doctype, child
   row per company: print_format, return_print_format, print_on_submit).
   Server API `get_print_templates` returns each rule with `pdf_generator` and
   `raw_printing` flags. `public/js/company_print.js` (v1.4+) routes the form
   Print button and print-on-submit: chrome → `download_pdf`; **raw →
   `qz_raw_print()` via QZ Tray** (calls
   `frappe.www.printview.get_rendered_raw_commands`, sends string via
   `qz.print`); everything else → `/printview?trigger_print=1`.
   KNOWN BUG (fixed in v1.4): raw formats previously went to /printview →
   the HTML fallback printed through the driver → **everything bunched at the
   top of the form**. If you see that symptom, the client is running old JS:
   check hooks `?v=` cache-busters, `bench build`, `bench clear-cache`, hard
   refresh.

## QZ Tray (browser → printer transport)

- Frappe's Print view raw path and our `qz_raw_print` both use QZ Tray with a
  per-browser printer mapping in `localStorage.print_format_printer_map`
  (set via Print view → Printer Settings, per print format).
- Requests are signed: `custom_code/printing/qz_security.py` +
  `public/js/qz_sign.js`. Site keys (NOT in git):
  `sites/<site>/qz-certificate.pem` + `qz-private-key.pem`; generate with
  `openssl req -x509 -newkey rsa:2048 -keyout qz-private-key.pem -out
  qz-certificate.pem -days 3650 -nodes -subj "/CN=Avinash Group ERP/O=Avinash Group"`.
  Without them qz_sign falls back to anonymous (QZ shows Allow prompt).
- One-click Windows cert install: logged-in users download
  `/api/method/avinashgroup_app.custom_code.printing.qz_security.setup_bat`
  → `install-qz-cert.bat` (self-elevates, writes
  `C:\Program Files\QZ Tray\override.crt`, restarts QZ Tray → no prompts).

## Verified diagnostics (run these before theorizing)

- Server render is correct if this is clean (bench console on the site):
  ```python
  from frappe.www.printview import get_rendered_raw_commands
  out = get_rendered_raw_commands(doc="Sales Invoice", name="<INV>", print_format="<raw format>")
  raw = out["raw_commands"]
  print(len(raw), raw.startswith("\x1b@"), all(ord(c) < 128 for c in raw))
  ```
  We proved this endpoint returns byte-identical output to the direct
  `build(doc)` call (only the copy-counter digit differs between renders).
- Linux reference transport that is KNOWN GOOD:
  `lp -d EPSON-LQ-310 -o raw file.prn` (plain `lp` also passes it raw —
  CUPS autotypes octet-stream).
- Calibration test scripts at the dev bench root: `print_ngi_test.sh`,
  `print_grishma_test.sh` (render fresh from the .py, print first sheet raw,
  do NOT bump the IRD counter — `print_count.before_print` increments only on
  `is_actual_print()` requests; browser prints DO increment: first print =
  Invoice + Tax Invoice pair, reprints = Copy of Original N).

## Windows failure modes already hit (and fixes)

Work through the chain: browser (green "Print sent" alert) → QZ Tray →
Windows spooler queue → driver/port → printer.

1. **Which queue?** Pause the printer queue (classic view `control printers` →
   See what's printing → Printer → Pause), print from browser: a job named
   "QZ Tray Raw Print" must appear. If not, the localStorage mapping points at
   a different/duplicate queue — re-map in Print view → Printer Settings.
2. **Job appears, says "printed", printer never moves, but the Windows test
   page prints fine** → the **Epson driver's language monitor swallows RAW
   datatype jobs**. THE FIX: add a second queue on the same USB port with
   driver **Generic / Text Only** (e.g. name `LQ310-RAW`), and map the raw
   formats to that queue. Generic/Text Only is a byte-pipe: no language
   monitor, no rendering — this is the definitive solution, don't fight the
   Epson driver. (Also reasonable: untick "Enable advanced printing features",
   Print processor = winprint/RAW, untick bidirectional support — but the
   Generic queue is what actually works.)
3. **WSD port** silently discards raw jobs — the printer must be on a
   `USB00x` virtual printer port.
4. Printer-side: Pause button/offline, no paper on tractor, cover open.
5. **Whole print shifted** on a new printer/rig: the tractor position differs
   from the dev rig. Align paper so column 0 ≈ 12mm from the paper's left
   edge and top-of-form at the perforation. X0_MM/Y0_MM are shared by ALL raw
   formats on that printer — prefer moving the tractor over editing them.
6. **Dates/rightmost fields wrap to a second line** → head-travel limit
   (215.4mm reach). Move the field left in POS or shorten the text; the head
   cannot go further right.

## Server deploy checklist (after git pull)

`bench --site <site> migrate` (syncs Print Format records; a live migrate
once crashed on an hrms advance patch — if it does, capture the traceback,
don't loop retries) → `bench build --app avinashgroup_app` →
`bench --site <site> clear-cache` → `bench restart`. Then browser hard
refresh (Ctrl+Shift+R) — desk caches JS+meta aggressively.

## Rules of engagement

- The Nepal Gas and Avinash formats are field-calibrated and in production:
  **never edit their POS values / templates while fixing another company's
  format** — each company has its own files precisely so they can't affect
  each other.
- Formats must coexist; changes to shared plumbing (company_print.js,
  chrome_pdf.py, qz_security.py, hooks) must stay additive.
- When a print is wrong, first decide WHICH path it took (raw QZ / chrome PDF
  / printview fallback) — the symptom "text at top of form" = HTML went
  through a driver; "fields shifted uniformly" = rig alignment; "single field
  off" = POS calibration; "right side wraps" = head limit; "sent but silent"
  = Windows driver/port swallow.
