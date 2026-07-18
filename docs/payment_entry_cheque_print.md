# Payment Entry — Cheque Overlay Print Format

Print format **`Payment Entry Cheque`** (Doctype: *Payment Entry*, custom Jinja format,
module *Avinash Group App*). It overlays the payment details — date, payee, amount in words,
and amount in figures — onto a pre-printed Nepal bank cheque.

File: `avinashgroup_app/avinash_group_app/print_format/payment_entry_cheque/payment_entry_cheque.json`

## Method — A4 carrier (no rotation)

The format prints a full **A4 portrait** page. The cheque lies **flat (landscape)** near the
top-left of that A4; there is **no rotation**, so you feed plain A4 through the printer normally.

The cheque is positioned on the A4 by `MX`/`MY` (top-left offset in mm). Every field is placed in
millimetres measured from the **cheque's own top-left corner**, so the numbers match how you
measure directly on a physical cheque.

Default cheque size: **190.5 × 88.9 mm** (`CHEQUE_W` × `CHEQUE_H`).

## Two-pass workflow (same A4 sheet)

1. **Print with the guide.** Add `&cheque_guide=1` to the print URL. A dashed box with red
   L-shaped corner marks shows exactly where the cheque goes. Print this on a **blank A4** sheet.
2. **Lay the cheque** inside the dashed box — **bank logo at the TOP-LEFT corner, date boxes at
   the TOP-RIGHT.** Tape the top edge of the cheque down to the A4.
3. **Print again without the guide** (normal print, no `&cheque_guide=1`). The text now lands on
   the cheque.

Always print at **100% / Actual Size, margins NONE**, to the **LBP2900**.

## Calibration parameters

All are Jinja `set` variables at the top of the template — edit and reprint to nudge.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MX`, `MY` | `10.0`, `15.0` | Cheque top-left position on the A4 (mm) |
| `FONT` | `11` | Base font size (pt) |
| `USE_BS` | `0` | `1` = Nepali BS date, `0` = `posting_date` as-is |
| `DATE_X`, `DATE_Y` | `138.8`, `11.0` | Date block position (mm from cheque top-left) |
| `DATE_GAP` | `3.7` | Letter spacing between date digits (mm) — align to the DDMMYYYY boxes |
| `PAYEE_X`, `PAYEE_Y` | `40.0`, `21.0` | Payee name position |
| `WORDS_X`, `WORDS_Y` | `20.0`, `27.0` | Amount-in-words start position |
| `WORDS_W`, `WORDS_LH` | `120.0`, `6.0` | Amount-in-words wrap width and line height (mm) |
| `FIG_X`, `FIG_Y`, `FIG_W` | `145.0`, `31.0`, `40.0` | Amount-in-figures position and width |

## Field sourcing

- **Date** → `doc.posting_date`, rendered as `DDMMYYYY` digits. With `USE_BS=1` it converts to the
  Nepali BS date via `bs_date_str()`.
- **Payee** → `doc.party_name or doc.party` (blank for party-less entries such as internal transfers).
- **Amount in words** → `frappe.utils.money_in_words(doc.paid_amount, currency)`, currency from
  `doc.paid_from_account_currency` (fallback `NPR`).
- **Amount in figures** → `doc.paid_amount`, formatted `{:,.2f}`.

## How to print

1. Open the Payment Entry.
2. Menu → **Print**, select the **Payment Entry Cheque** format.
3. For the first calibration pass append `&cheque_guide=1` to the URL; drop it for the real run.

## Notes

- `pdf_generator` is `wkhtmltopdf`.
- If a field lands off-position, adjust its `_X`/`_Y` and reprint the guide pass to re-check.
- Keep `MX`/`MY` fixed once the printer feed is calibrated; then only per-field nudges are needed.
