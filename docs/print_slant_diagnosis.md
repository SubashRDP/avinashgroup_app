# Slanted / thin print in a band — what it can be, and how to tell

**Symptom, 2026-07-28, Nepal Gas overlay on the Windows tills.** Some printed
values lean and look thin; others on the same sheet are upright and clean.

This is written down before testing so we stop re-arguing it. Each hypothesis
lists what supports it, what contradicts it, and the one test that settles it.

---

## The observation, precisely

Measured down the form (positions are where the render places them):

| mm | Field | How it prints |
| --- | --- | --- |
| 75.8 / 80.6 | item rows — qty, rate, amount | **clean, upright** |
| 88.8 | %Discount `0.00` | **clean, upright** |
| 90.9 – 101 | Amount in words (wraps 2–3 lines) | slanted, thin |
| 94.8 | Taxable Amount `1,41,937.60` | slanted, thin |
| 100.8 | 13% VAT `18,451.89` | slanted, thin |
| 108.8 | Grand Total `1,60,389.49` | **clean, upright** |

**The two facts that constrain everything:**

1. Discount, Taxable and VAT are rendered by **identical code** — same macro,
   same 8.5pt, same right alignment, same box width. Only the Grand Total
   differs (bold). So nothing in the layout distinguishes the three.
2. The affected rows form a **contiguous band, roughly 91–102 mm**. Everything
   above it and below it is clean.

A band on the paper that ignores what the code says is the shape of a
*mechanical* fault, not a rendering one. That is the starting assumption.

---

## Hypotheses, most likely first

### A. The paper is not held firmly in that band

Slanted characters on a dot matrix mean the paper moved while the head was
striking. In a fixed band, that means the paper is loose there.

- **Supports:** it is a band, not a set of fields; identical code prints
  differently inside and outside it.
- **Contradicts:** nothing yet.
- **Test:** print the same invoice with `&oy=10`. If the slant stays at the
  same height on the paper and now catches *different* fields, it is
  mechanical and no code change will fix it.
- **Fix if true:** check both tractor holders are locked and the paper is taut
  between them, not slack. Slack paper flutters exactly like this.

### B. The 10 mm downward shift moved content into a bad region

Today `oy` went from −11.2 to −1.2, so the whole layout sits 10 mm lower than
it ever has. The bottom block is now printing on paper that was never printed
on before.

- **Supports:** the complaint appeared the same day as the shift. Before it,
  the totals sat at 78.8 / 84.8 / 90.8 / 98.8 — all above the suspect band.
- **Contradicts:** nothing yet.
- **Test:** `&oy=-10` puts the layout back where it was this morning. If the
  bottom prints cleanly there, the shift is what exposed the bad region.
- **Fix if true:** either compact the bottom block upward (words + four totals)
  and leave the header alone, or move the printer's top-of-form 10 mm earlier
  and drop the `oy` back — the second is cleaner because it stops fighting the
  mechanism.

### C. The wrapped amount-in-words block disturbs the paper

The amount in words is the **only** field that wraps to several lines, and it
occupies 90.9–101 mm — straddling exactly the Taxable and VAT rows.

- **Supports:** it is the one thing structurally different about that band.
  More head passes over a stretch the tractor may not be gripping.
- **Contradicts:** a laser/PDF path renders the whole page at once, so this
  only bites if the driver prints line-by-line in text mode.
- **Test:** print the same invoice through a format that omits just that field
  (see *Test rig* below). If Taxable and VAT come out clean, this is it.
- **Fix if true:** shorten the box so it wraps to fewer lines, or move it clear
  of the totals rows.

### D. Ribbon worn in a horizontal stripe

Thin print is the classic ribbon symptom.

- **Supports:** the affected text is thin as well as slanted.
- **Contradicts:** the ribbon advances as it prints, so wear is usually even
  rather than a fixed stripe. And wear alone does not cause a *slant*.
- **Test:** advance or replace the ribbon and reprint the same sheet.

### E. Print head gap set too wide

- **Supports:** thin, faint output.
- **Contradicts:** it would affect the whole sheet, not a band.
- **Test:** move the gap lever one notch closer and reprint.

### F. Bold vs regular weight

The Grand Total is bold and clean; Taxable and VAT are regular and slanted.

- **Supports:** bold is double-strike, two passes, so it lands heavier and
  masks a small lean.
- **Contradicts, decisively:** the **item rows are regular weight and print
  clean**, and `%Discount` is regular weight and prints clean. Weight does not
  predict the fault. **Discounted as a primary cause.**

### G. String length makes the lean visible

`0.00` is 4 characters; `1,41,937.60` is 11.

- **Supports:** a small per-character lean is invisible on a short string.
- **Contradicts:** the item-row amounts are just as long and print clean.
- **Verdict:** may make the fault *more visible* in some rows, but does not
  cause it. Secondary at most.

---

## What has already been ruled out

- **Justify on the amount in words.** Real, and fixed in `49d2413` — it
  stretched spacing on every line but the last, which read as ragged. But it
  cannot explain Taxable and VAT, which never went near that code.
- **The `in_words` source.** Changed in `aa24e31` to use the document's stored
  wording. Unrelated to how characters are formed on paper.
- **Any per-field layout difference between the three totals.** Verified from
  the rendered HTML: identical style attributes apart from the Grand Total's
  `font-weight:bold`.

---

## Test rig

Do these on **one** invoice so the sheets are comparable, and change `_ts=` each
time or Chrome serves a cached PDF.

```
# 1. baseline — what we have now
...&format=Nepal%20Gas%20Invoice%20A5%20Overlay&no_letterhead=1&_ts=1

# 2. hypothesis A: does the band follow the fields, or stay on the paper?
...&no_letterhead=1&oy=10&_ts=2

# 3. hypothesis B: back to this morning's position
...&no_letterhead=1&oy=-10&_ts=3

# 4. hypothesis C: same sheet without the wrapped words block
#    (via the separate diagnostic format, so the production one is untouched)
```

**Reading the results**

| Result | Conclusion |
| --- | --- |
| Slant stays at the same height, catches different fields | **A** — mechanical, paper handling |
| Slant follows the fields down | rendering after all; re-open the layout |
| `&oy=-10` prints clean | **B** — the shift exposed a bad region |
| Clean without the words block | **C** — the wrapped block is the cause |
| Nothing changes anything | **D/E** — ribbon or head gap; try the printer's own self-test |

The printer's **self-test** (power off, hold LF/FF, power on) prints from its
own ROM with no computer involved. If that comes out slanted too, the fault is
entirely inside the printer and none of the above matters.

---

## Note

The diagnostic format must be a **separate print format record**, not a change
to `nepal_gas_invoice_a5_overlay.html` — that template is shared by all seven
overlay formats and is the live production path.
