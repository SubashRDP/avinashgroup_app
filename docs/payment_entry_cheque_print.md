# Payment Entry — Cheque Overlay Print Format

Print format **`Payment Entry Cheque`** (Doctype: *Payment Entry*, custom Jinja format,
module *Avinash Group App*). It overlays the payment details — date, payee, amount in words,
and amount in figures — onto a pre-printed bank cheque.

File: `avinashgroup_app/avinash_group_app/print_format/payment_entry_cheque/payment_entry_cheque.json`

## Method — A4 carrier, VERTICAL feed

The format prints a full **A4 portrait** page. The cheque is rotated **90°** and sits as a
**tall strip** near the top-left of the A4, so the cheque is fed **standing up (vertical)**.
Rotation is controlled by `ROTATE` (`90` or `270`).

Every field is placed in millimetres measured from the **cheque's own top-left corner**, so the
numbers match how you measure directly on a physical cheque — the rotation does not change them.

Default cheque size: **190.5 × 88.9 mm** (`CHEQUE_W` × `CHEQUE_H`).

## Where the cheque goes on the A4 (tray guide)

The cheque footprint on the A4 is fixed by `MX`/`MY`:

| From the A4 sheet edge | Distance |
| --- | --- |
| Left edge → left edge of cheque | **1.0 cm** (`MX = 10 mm`) |
| Top edge → top edge of cheque | **1.5 cm** (`MY = 15 mm`) |
| Cheque width (across the sheet) | **8.9 cm** |
| Cheque height (down the sheet) | **19.05 cm** |

**Placing the physical cheque** (portrait A4 held upright, dashed box near the top-left):

- Turn the cheque a **quarter-turn clockwise** — the bank logo (normally top-left) moves to the
  **top-right**.
- **Bank logo → TOP-RIGHT** corner of the dashed box.
- **Date boxes → BOTTOM-RIGHT** corner.
- The cheque's long top edge runs down the **right** side of the box; the account-number / MICR
  edge runs down the **left** side.
- Tape the top short edge (logo side) to the A4.

**Loading the tray / printing:** feed plain **A4 portrait** into the **LBP2900**. Print at
**100% / Actual Size, margins NONE**. In the Chrome print dialog make sure the destination is
**LBP2900** (Chrome tends to remember an old/dead printer) and scale is **Actual size**, not
"Fit to page".

## Two-pass workflow (same A4 sheet)

1. **Print with the guide.** Add `&cheque_guide=1` to the print URL. A dashed box with red corner
   marks and a field preview shows exactly where the cheque goes. Print on a **blank A4** sheet.
2. **Lay the cheque** inside the dashed box (orientation above). Tape the top edge down.
3. **Print again without the guide** (drop `&cheque_guide=1`). The text lands on the cheque.

## Calibration parameters (current = Global IME Bank cheque)

All are Jinja `set` variables at the top of the template — edit and reprint to nudge.

| Variable | Value | Meaning |
| --- | --- | --- |
| `MX`, `MY` | `10.0`, `15.0` | Cheque top-left position on the A4 (mm) |
| `ROTATE` | `90` | Vertical feed rotation; use `270` if text prints upside down |
| `FONT` | `11` | Base font size (pt) |
| `USE_BS` | `0` | `1` = Nepali BS date, `0` = `posting_date` as-is |
| `DATE_X`, `DATE_Y` | `138.0`, `10.0` | Date block position (mm from cheque top-left) |
| `DATE_GAP` | `3.8` | Letter spacing between date digits (mm) — align to the DDMMYYYY boxes |
| `PAYEE_X`, `PAYEE_Y` | `40.0`, `22.0` | Payee name position |
| `WORDS_X`, `WORDS_Y` | `23.0`, `28.5` | Amount-in-words start position (first ruled line ≈ 33 mm) |
| `WORDS_W`, `WORDS_LH` | `100.0`, `7.0` | Wrap width; line height (2nd ruled line ≈ 40 mm) |
| `FIG_X`, `FIG_Y`, `FIG_W` | `138.0`, `33.0`, `50.0` | Amount-in-figures position and width |

> **Different bank?** These positions are measured for the **Global IME Bank** cheque. A cheque
> from another bank has different box positions — re-measure each field (mm from the cheque's
> top-left) and update the variables.

## Field sourcing

- **Date** → `doc.posting_date`, rendered as `DDMMYYYY` digits. With `USE_BS=1` it converts to the
  Nepali BS date via `bs_date_str()`.
- **Payee** → `doc.party_name or doc.party` (blank for party-less entries such as internal transfers).
- **Amount in words** → `frappe.utils.money_in_words(doc.paid_amount, currency)`, currency from
  `doc.paid_from_account_currency` (fallback `NPR`).
- **Amount in figures** → `doc.paid_amount`, formatted `{:,.2f}`.

## How to print

1. Open the Payment Entry.
2. Menu → **Print**, select the **Payment Entry Cheque** format, tick **No Letterhead**.
3. For the first calibration pass append `&cheque_guide=1` to the URL; drop it for the real run.

## Deploying to another site

The format auto-imports on `bench migrate`. It only re-imports if the JSON's `modified` timestamp
is **newer** than the DB record — so **bump `modified`** whenever you edit the HTML, otherwise
migrate silently skips it. To apply immediately without migrate:

```bash
bench --site <SITE> execute frappe.modules.import_file.import_file_by_path \
  --kwargs "{'path': 'apps/avinashgroup_app/avinashgroup_app/avinash_group_app/print_format/payment_entry_cheque/payment_entry_cheque.json', 'force': True}"
bench --site <SITE> clear-cache
```

## Troubleshooting

- **Printer stops, nothing comes out, queue backs up** — the Canon **CAPT** backend has wedged
  (`lpstat -p LBP2900` shows *disabled … CAPT: bad reply from printer*). **Power-cycle the
  LBP2900** (off/on at the printer), then `cupsenable LBP2900` and reprint. Clear stuck jobs with
  `cancel -a LBP2900`.
- **Text upside down on the cheque** — set `ROTATE = 270`, re-import, reprint.
- **A long amount wraps to 3 lines** — the cheque has 2 ruled lines. Lower `FONT` a point so it
  fits on two, or widen `WORDS_W` if the cheque has room.
- **A field lands off** — nudge its `_X`/`_Y` and reprint the guide pass to re-check.
- **wkhtmltopdf** strips the CSS `transform`, so server-side PDF via wkhtmltopdf will **not** show
  the rotation. Print from the browser dialog (Chrome), which honours it.
