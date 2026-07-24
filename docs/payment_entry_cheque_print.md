# Payment Entry — Cheque Overlay Print Format

Print format **`Payment Entry Cheque`** (Doctype: *Payment Entry*, custom Jinja format,
module *Avinash Group App*). It overlays the payment details — date, payee, amount in words,
and amount in figures — onto a pre-printed bank cheque.

File: `avinashgroup_app/avinash_group_app/print_format/payment_entry_cheque/payment_entry_cheque.json`

## Method — print DIRECTLY onto the bare cheque

The cheque leaf itself is the paper. It goes into the tray **alone**, **logo edge first**.
The page is therefore **88.9 × 190.5 mm** — the cheque stood on its short edge — and the cheque's
own corner *is* the page corner, so `MX = MY = 0`.

The cheque content is rotated **90°** (`ROTATE`, `90` or `270`) so it lands correctly on that
portrait page. Every field is placed in millimetres from the **cheque's own top-left corner**, so
the numbers match how you measure directly on a physical cheque — the rotation does not change them.

Default cheque size: **190.5 × 88.9 mm** (`CHEQUE_W` × `CHEQUE_H`).

How the cheque's own coordinates map onto the fed page:

| Cheque feature | Where it ends up |
| --- | --- |
| Left (logo) edge, `cx = 0` | **Leading edge** — goes into the printer first |
| Right (date) edge, `cx = 190.5` | Trailing edge |
| Top edge, `cy = 0` | Right-hand side as the sheet feeds |
| Bottom (MICR) edge, `cy = 88.9` | Left-hand side |

Mapping (relative to the cheque's own corner): `x = MX + 88.9 − cy`, `y = MY + cx`.

## Leave the print dialog on A4 — the page exploits centre registration

The page is declared a **normal A4**, and the cheque content is placed where a bare cheque
*physically sits in the tray*. The LBP2900 is **centre-fed**: a narrow sheet registers to the
middle of the tray, not the left edge. So:

| Offset | Value | Why |
| --- | --- | --- |
| `MX` | **60.55 mm** | `(210 − 88.9) / 2` — where a centre-registered 88.9 mm sheet actually lies |
| `MY` | **0 mm** | The cheque's leading edge *is* the top of the page |

This is **not** cosmetic centring. 60.55 is the measured position of the paper, so no custom paper
size and no dedicated CUPS queue are needed — **A4 in the dialog is correct**.

`MY = 0` matters: the cheque's leading edge enters first and the printer begins imaging at the top
of the page, so any `MY > 0` pushes every field that far down the cheque. The nearest field is
`WORDS_X = 29 mm`, comfortably past the printer's ~5 mm unprintable top band.

**`&align=left`** — if a printer registers narrow paper to the *left* edge of the tray instead of
the centre, add this to the URL and `MX` becomes 0.

**`&sheet=cheque`** — emits a true 88.9 × 190.5 mm page with `MX = MY = 0`. Only use this if a
matching custom paper size is genuinely selected in the dialog; otherwise the print path re-centres
the small page and every field misses.

## Printer alignment — moving the print left/right/up/down

If the print lands off the cheque, **do not touch the field coordinates.** Those are measured from
the cheque itself and are the same on every printer. What differs per printer is where it grips the
paper — so move the *whole block* instead.

Set it in the UI — **Cheque Print Alignment** (a Settings single, at `/app/cheque-print-alignment`).
No code, no re-import, no `modified` bump:

| Field | Effect |
| --- | --- |
| **Move Right (mm)** | `+` moves everything **right**, `−` moves it **left** |
| **Move Down (mm)** | `+` moves everything **down**, `−` moves it **up** |
| **Rotation** | `90`, or `270` if the text prints upside down |
| **Tray Alignment** | `centre` (LBP2900) or `left` for left-registering printers |
| **Page Size** | `a4` (recommended) or `cheque` for a true 88.9 × 190.5 mm page |

Permissions: System Manager (full) and Accounts Manager (read/write), so the accounts team can
correct alignment without a developer.

The print format reads these at render time, guarded by an `exists()` check — on a site where the
doctype hasn't been migrated in yet, the format still renders using its built-in defaults.

### Trying values without saving

```
...&format=Payment%20Entry%20Cheque&no_letterhead=1&dx=2.5&dy=-1
```

- `dx` = same as **Move Right** (right positive, left negative)
- `dy` = same as **Move Down** (down positive, up negative)
- `rotate=270` = same as the **Rotation** field

Decimals and negatives both work. Reprint, measure, adjust, repeat. Once a pair of values is
right, type them into the form and Save so every print picks them up.

> **They are additive.** `&dx=` is applied *on top of* the saved **Move Right**. With `Move Right = 2`
> saved, `&dx=1` prints at 3 mm. Handy for fine-tuning, easy to confuse — when hunting for a value
> from scratch, leave the form at 0 and use `dx` alone.

Resolution order for every setting: **URL parameter → saved form value → built-in default.**

## Alignment guide

Add **`&cheque_guide=1`** to the print URL for a dashed outline plus red corner marks, so you can
check registration before committing a real cheque. Drop the flag for the real run.

## Calibration parameters (current = Global IME Bank cheque)

All are Jinja `set` variables at the top of the template — edit and reprint to nudge.

| Variable | Value | Meaning |
| --- | --- | --- |
| `SHEET` | `a4` | `a4` = A4 page, cheque placed at the centre-fed position; `cheque` = true 88.9×190.5 page |
| `ALIGN` | `centre` | Tray registration for narrow paper; `&align=left` sets `MX = 0` |
| `MX`, `MY` | `60.55`, `0` | Where the bare cheque sits in the tray (`MX`); leading edge = page top (`MY`) |
| `ROTATE` | `90` | Vertical feed rotation; use `270` if text prints upside down |
| `FONT` | `11` | Base font size (pt) |
| `USE_BS` | `0` | `1` = Nepali BS date, `0` = `posting_date` as-is |
| `DATE_X`, `DATE_Y` | `138.0`, `10.0` | Date block position (mm from cheque top-left) |
| `DATE_GAP` | `3.8` | Letter spacing between date digits (mm) — align to the DDMMYYYY boxes |
| `PAYEE_X`, `PAYEE_Y` | `44.0`, `22.0` | Payee name position |
| `WORDS_X`, `WORDS_Y` | `29.0`, `28.5` | Amount-in-words start position (first ruled line ≈ 33 mm) |
| `WORDS_W`, `WORDS_LH` | `100.0`, `7.0` | Wrap width; line height (2nd ruled line ≈ 40 mm) |
| `FIG_X`, `FIG_Y`, `FIG_W` | `142.6`, `31.0`, `50.0` | Amount-in-figures position and width |

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

> ### ⚠ ALWAYS bump `modified` when you edit the HTML
>
> The format auto-imports on `bench migrate`, but `import_file_by_path` only re-imports when the
> JSON's `modified` is **strictly newer** than the DB record's. Equal timestamps are **skipped
> silently** — no error, no warning, and the site keeps serving the *old* template while git shows
> your edit sitting there looking applied.
>
> This has already cost two debugging sessions:
> - `ec6aeaa` — "bump modified so migrate re-imports the format"
> - `68fa46d` — changed `MX` 10 → 60.5 to centre the cheque, but left `modified` at
>   `2026-07-19 15:30:00` (same as `8a8d771`). Every migrate skipped it, so the site printed at
>   `MX=10` for days. It surfaced as "the cheque doesn't print in the centre" and was only pinned
>   down by diffing a saved PDF against a local render: every field was off by exactly
>   143.25 pt = 50.56 mm on X and 0.000 pt on Y. A rigid, single-axis, exactly-constant offset is
>   the signature of a stale template — not a printer, margin, scaling, or calibration problem.
>
> If a change to this file doesn't seem to take effect, **check `modified` first**, before touching
> any coordinate.

To apply immediately without migrate:

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
