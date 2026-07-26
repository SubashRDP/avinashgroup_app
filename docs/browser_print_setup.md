# Invoice printing — browser way, branch setup sheet

This is the ONLY supported invoice print path (decision 2026-07-25, see
`handoff_2026-07-25_printing.md` §8a). One-time setup per computer, then daily
printing is just: **Print → PDF opens → print it**.

Works with any Epson dot-matrix on the till — LQ-310, LQ-350, or 9-pin LX-310
(LX prints coarser but lands in the boxes).

## How printing works (tell the operator this much)

1. Open the invoice → Print (the Print view button or the form's printer icon).
2. A **PDF opens in a new tab** — this is correct. If a print dialog opens
   instead of a PDF, the setup or the ERP JS is stale; see Troubleshooting.
3. Print the PDF at **100% / Actual size**. Never "Fit to page", never
   "Shrink". (After the one-time setup below, even a forgotten "Fit" changes
   nothing, because paper size = page size.)

Each print event consumes exactly as many forms as it has copies (first print:
TAX INVOICE + INVOICE = 2 forms). The tear-off perforation must land between
copies — if it creeps, the paper was loaded off the top-of-form, not a software
problem: re-load the tractor paper with the perforation at the tear bar.

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
3. **Browser print dialog**: first print, choose the Epson, More settings →
   Scale: **100** (or open the PDF in Adobe/SumatraPDF and pick Actual size).
   The browser remembers per printer.

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
| Print button opens the OS dialog, not a PDF | stale ERP JS | hard-reload (Ctrl+Shift+R); check Network shows `ngi_print.js?v=1.3+` |
| Content rotated 90° / upside down on paper | driver Orientation = Landscape, or paper size not NGIForm | setup steps 1–2 — **or just use `&rot=`, see "If the orientation is wrong" below** |
| Every copy eats two forms / blank form between copies | driver paper is A4 (297 mm feed), or (Linux) double-feed wrapper missing | setup step 2 / install the wrapper |
| Everything shifted by a constant amount | ox/oy calibration | see "Calibrating a form" below |
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
