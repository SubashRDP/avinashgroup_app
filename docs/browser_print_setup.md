# Invoice printing — browser way, branch setup sheet

This is the ONLY supported invoice print path (decision 2026-07-25, see
`handoff_2026-07-25_printing.md` §8a). One-time setup per computer, then daily
printing is just: **Print → it prints**. No preview, no dialog — that is
deliberate, and the reason is the IRD copy counter; see "Silent printing" below.

Works with any Epson dot-matrix on the till — LQ-310, LQ-350, or 9-pin LX-310
(LX prints coarser but lands in the boxes).

## How printing works (tell the operator this much)

1. Open the invoice → Print (the Print view button or the form's printer icon).
2. The invoice **prints. That is the whole thing** — no preview, no dialog, no
   second click. See "Silent printing" below; on a till that has not had the
   silent-print shortcut applied yet, a print dialog appears instead and the
   operator must confirm it.
3. Nothing to choose. Paper size, orientation and scale all come from the
   printer's own defaults, set once by step 1–2 of the setup below.

Each print event consumes exactly as many forms as it has copies (first print:
TAX INVOICE + INVOICE = 2 forms). The tear-off perforation must land between
copies — if it creeps, the paper was loaded off the top-of-form, not a software
problem: re-load the tractor paper with the perforation at the tear bar.

## Silent printing — why the dialog has to go

Not cosmetic. The IRD copy counter (`custom_code/SalesInvoice/print_count.py`)
increments when the server **renders** the PDF, and commits it there and then
(`before_print`, the `frappe.db.commit()` at the end). That is before Chrome's
print dialog is even on screen. So today:

- operator presses Print, then **cancels** the dialog → the count went up and no
  paper exists. The next real print is labelled `COPY OF INVOICE 2` for a
  customer who never received an original.
- the machine loses power while the dialog is open → same.

And it cannot be fixed by counting later instead: `window.onafterprint` fires
**identically** for Print and for Cancel, and no other browser API distinguishes
them. As long as a dialog exists, nothing on the client or the server can tell a
cancelled print from a real one. A sales invoice cannot be cancelled in Nepal,
so the burnt copy number is permanent.

Removing the dialog removes the cancel. That is the fix.

### Applying it (per till, one line)

Chrome's `--kiosk-printing` sends `window.print()` straight to the default
printer with no preview and no dialog. Use it **without** `--kiosk` — plain
`--kiosk` would lock the till into one full-screen page with no tabs or address
bar, which is not wanted for the desk.

Edit the Chrome shortcut the till uses for the ERP: right-click → Properties →
**Target**, and append the flag after the `.exe`:

```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk-printing
```

Then **close Chrome completely** (check Task Manager → Details for stray
`chrome.exe`) and reopen from that shortcut. A Chrome that is already running
reuses the existing process and silently ignores the new flag — this is the
single most common reason "it didn't work".

Two things to know before rolling it out:

- The flag is **per Chrome instance, not per site**. Every print from that
  browser becomes silent, including Ctrl+P on any other page. Fine on a
  dedicated till; surprising on a shared office PC.
- Any *other* way into Chrome (pinned taskbar icon, a desktop link, Start menu)
  launches without the flag and the dialog comes back. Replace or remove those
  so the shortcut above is the only entry point.

### Proving it prints exactly like today — do this before rolling out

The requirement is that the paper comes out **identical**, only without the
dialog. The render does not change (same server, same PDF, same printer, same
driver defaults), so the only thing that can move is whether silent print uses
the driver's defaults or the per-printer settings Chrome remembered from past
dialogs. Prove it on one till rather than assume it:

1. Pick a **throwaway invoice** — these test prints advance the IRD copy
   counter like any other print.
2. **Before** applying the flag, print it with `&guide=1` on the URL, on a real
   pre-printed form. Every field box outlines in red and the sheet edge in blue.
   Keep that sheet.
3. Apply the flag, restart Chrome, print the **same invoice** with the same
   `&guide=1`, same printer, same stationery.
4. Lay the two sheets on top of each other against a window. **The red boxes
   must coincide exactly.**

Coincide → silent printing changed nothing; roll it out. Offset or visibly
scaled → Chrome is silently printing with different settings than the dialog
was using; remove the flag from the shortcut (that alone reverts it) and treat
it as a calibration problem before trying again.

`guide`, `ox`, `oy` and `rot` are read straight off `frappe.form_dict` by the
overlay template, not passed as handler arguments, so they work identically on
the silent-print route and the old dialog route. That is what makes the two
sheets comparable.

Record the Chrome version you verified against. The flag is undocumented and
unsupported by Google, and has broken across browser updates before — so
re-run this comparison after a major Chrome update rather than assuming it
still holds.

### Pinning the destination printer

Silent printing has no dialog to pick a printer in, so it uses the Windows
default — and Windows reassigns that on its own unless step 3 of the setup
turns that behaviour off. On a till where that is not reliable, Chrome's
supported `DefaultPrinterSelection` enterprise policy pins the destination by
name regardless of the Windows default. It goes in the same HKLM policy area
`installer.iss` already writes to.

Nothing changes in the ERP. `avinash.print_pdf` (`public/js/ngi_print.js`)
already loads the PDF into a hidden iframe and calls `contentWindow.print()` —
there is no tab and nothing to preview, only the dialog, and the flag removes
it. This covers every `chrome`-generator format: Nepal Gas, Grishma, Gandaki,
Karnali and Narayani.

**GLMI is the exception.** It renders with wkhtmltopdf, so it goes through
`/printview?trigger_print=1` in a real tab that prints and then closes itself
after 5 seconds. With the flag it prints silently too, but the tab still
flashes up. Making it tab-free means moving `GLMI Sales` / `GLMI Return` to the
`chrome` generator like the others — worth doing, but it changes the render
engine for an mm-positioned A4 layout, so it needs a test print on real
stationery first, not a blind switch.

### What this does not fix

The count still commits when the PDF is rendered, so a power cut in the moment
between rendering and the spooler taking the job, or a printer that is offline
or out of paper, still counts a sheet that never printed. Closing that last gap
needs the printer to report back that it accepted the job, which is what the
Print Bridge `pdf` job type in `requirement_print_bridge_driver_mode.md` was
for. Silent printing shrinks the window from "however long a dialog sits open"
to a fraction of a second; it does not reach zero.

## One-time setup — Windows till

2 minutes, admin rights, does not affect any other printing on the machine.

1. **Create the form size** (once per machine):
   Control Panel → Devices and Printers → click the Epson printer →
   **Print Server Properties** (toolbar) → tick *Create a new form* →
   Name: `NGIForm` — Width: **24.13 cm** — Height: **13.97 cm** → Save Form.
   (Width first. If the dialog is in inches: 9.50 × 5.50 in.)
2. **Make it the printer's default**:
   Right-click the Epson printer → Printer properties → **Advanced** tab →
   **Printing Defaults…** → Paper Size: `NGIForm` — Orientation: **Portrait**
   → OK. (Printing *Defaults*, not *Preferences* — Defaults cover every user.)
3. **Make the Epson the Windows default printer**: Settings → Bluetooth &
   devices → Printers & scanners → the Epson → **Set as default**, and turn
   **off** "Let Windows manage my default printer" (it silently reassigns the
   default to whatever was used last). Silent printing has no dialog to pick a
   printer in, so it always uses this one.
4. **Apply the silent-print shortcut** — see "Silent printing" above. Do this
   last, after 1–3, so the first silent print already has the right paper.

Orientation stays **Portrait** even though the form is wider than tall —
"Landscape" would rotate the already-landscape page a further 90° (this is the
classic cause of the sideways/up-down misprint).

## One-time setup — Linux (reference: the dev laptop)

The laptop's `EPSON-LQ-310` CUPS queue is the reference implementation:

- Queue default paper `NGIForm` (684 × 396 pt).
- `/usr/lib/cups/filter/rastertoepson-lq310` installed (root-owned, from
  `custom_code/printing/rastertoepson-lq310`) — strips the stock driver's
  double page-feed so one page = one form, not two.

Byte-level verified 2026-07-25 with no printer attached: the job stream
declares form length 139.7 mm (`ESC C 33`) and sends exactly one form-feed per
copy.

## Troubleshooting, in order

| Symptom | Cause | Fix |
| --- | --- | --- |
| A print dialog appears instead of printing straight away | Chrome was not started from the `--kiosk-printing` shortcut | close Chrome **completely** (Task Manager → Details → no `chrome.exe`), reopen from that shortcut; check no other icon launches Chrome without the flag |
| Prints silently to the wrong printer | Windows default printer is wrong, or "Let Windows manage my default printer" is on | setup step 3 |
| Print button opens the OS dialog, not a PDF | stale ERP JS | hard-reload (Ctrl+Shift+R); check Network shows `ngi_print.js?v=1.3+` |
| Content rotated 90° / upside down on paper | driver Orientation = Landscape, or paper size not NGIForm | setup steps 1–2 — **or just use `&rot=`, see "If the orientation is wrong" below** |
| Every copy eats two forms / blank form between copies | driver paper is A4 (297 mm feed), or (Linux) double-feed wrapper missing | setup step 2 / install the wrapper |
| Everything shifted by a constant amount | ox/oy calibration | see "Calibrating a form" below |
| Each sheet prints higher (or lower) than the last | page height ≠ the form's real pitch | see "If the print CREEPS" below — **not** an ox/oy job |
| Whole form printed small (~77%) | PDF was rendered by wkhtmltopdf, not Chrome | check the format's `pdf_generator` = chrome on the site |
| Values in wrong boxes entirely | wrong overlay format for that company's stationery | pick the overlay matching the pre-printed roll (each company has its own) |

## If the orientation is wrong — `&rot=`

**This is the fix that needs nothing from the computer.** The PDF the server
makes is always correct: 241.3 × 139.7 mm, wider than tall, with no rotation
stored in it. So a print that comes out sideways or upside down was rotated by
the **driver or the PDF viewer**, after the ERP is done. Instead of chasing that
machine by machine, rotate the content to cancel it out — add `&rot=` to the
print URL:

| Value | What it does | Try it when |
| --- | --- | --- |
| `&rot=0` | default, form as-is on a 241.3 × 139.7 mm page | normal |
| `&rot=90` | quarter turn, page becomes **portrait** 139.7 × 241.3 mm | the print comes out sideways — usually a driver locked to portrait |
| `&rot=180` | same page, upside down | the form feeds in reverse |
| `&rot=270` | the other quarter turn | if 90 is upside down |

Print one invoice at each value, keep whichever comes out upright on the form.
It combines with `&ox`/`&oy`/`&guide`, so position calibration is unaffected.

Why `rot=90` usually fixes "sideways": a driver that believes portrait paper is
loaded will rotate a landscape page to make it fit. `rot=90` hands it a portrait
page with the form already turned inside it, so the driver has no reason to
rotate anything and the paper comes out right.

## If the print CREEPS — every sheet a little higher than the last

Different from "everything is 2mm off". Here sheet 1 looks fine, sheet 5 is
visibly high, sheet 10 is off the boxes. **`ox`/`oy` cannot fix this** — they
shift every sheet by the same amount, they do not stop a walk.

The cause is always the same: the paper advance per sheet does not equal the
form's real perforation-to-perforation distance. The printer does not see the
perforation; it feeds the page height it was given and starts the next sheet.
Feed 0.3mm short and the error adds up — sheet 5 prints 1.5mm high.

> Because it accumulates, the SAME machine prints differently at sheet 1 and
> sheet 6. Two tills compared at different points in their roll look like "every
> laptop prints differently" when there is really one fault. Before blaming a
> machine, always ask **which sheet since the paper was loaded**.

Direction:

| What you see | Meaning | Do |
| --- | --- | --- |
| creeps **up** the form | feeding too little | **raise** the height |
| creeps **down** the form | feeding too much | **lower** the height |

Measure it — a single sheet cannot resolve 0.3mm, ten can:

1. Load the paper with the perforation at the tear bar and print **10 forms**.
2. Measure how far the 10th print sits off its boxes, in mm.
3. Per-sheet error = that ÷ 10. New height = 139.7 + it (creeping up), or
   139.7 − it (creeping down). E.g. 3mm high over 10 sheets → 139.7 + 0.3 =
   **140.0**.
4. Trial it with **`&fh=140`** on the print URL — no deploy, that machine only.
5. It must also be set on the DRIVER, which is what actually feeds the paper:
   `windows_setup_form.ps1 -HeightMm 140` (Linux: the PPD's `NGIForm`). If only
   one of the two changes, the walk stays.
6. When it holds over 10 sheets, send the number to the developer to bake into
   that stationery's format.

If the creep is large and jumpy rather than a slow walk (a whole blank form now
and then), that is the double-feed fault instead — see the Troubleshooting
table.

## Calibrating a form (the "print one sheet and send a photo" step)

Needed once per stationery per printer, when the values land in the right
pattern but the whole print sits a few mm off. It moves EVERYTHING together —
never adjust individual field positions.

1. Open the invoice's print URL and add **`&guide=1`**, e.g.
   `/printview?doctype=Sales%20Invoice&name=<INV>&format=Grishma%20Invoice%20A5%20Overlay&guide=1`
   Every field box outlines in red and the sheet edge in blue.
2. Print that on a **real pre-printed form** and photograph it (or lay a plain
   print over a real form against a light). The red boxes show exactly which way
   and how far the data sits off its printed box.
3. Re-print with the offset in the URL: **`&ox=<mm right>&oy=<mm down>`**
   (negative = left / up), e.g. `&ox=-1.5&oy=2`. Repeat until it lands.
   `guide` and `ox`/`oy` combine, so you can keep the outlines on while dialling.
4. When the numbers are right, they are made permanent in the format wrapper —
   send them to the developer. (Making these settable per branch from the desk,
   with no deploy, is the next planned step.)

`guide` never appears in a normal print: it is off unless the URL asks for it.
