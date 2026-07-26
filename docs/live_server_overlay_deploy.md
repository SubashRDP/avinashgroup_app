# Deploying the A5 Overlay invoice to the live server

**Status:** proven on `avinasdemo.raindropinc.com` on **2026-07-26**. This is the
runbook for repeating it on **`ng-group.raindropinc.com`**.

**Scope of this deploy: `Nepal Gas Udhyog Pvt. Ltd.` only.** One company, one
format — `Nepal Gas Udyog Invoice A5 Overlay`. The other six companies stay on
whatever they use today. Narrow scope is deliberate: if the calibration is off
on the real stationery, exactly one branch is affected and the rollback is one
dropdown.

Code being deployed: commit **`6fea0fc`** on `develop` (and the two cheque-print
commits below it, which ship along with it).

---

## 0. The thing to check first

`ng-group` and `avinasdemo` are on the **same bench** (see
`print_bridge_deployment.md` — one ERP server serves all four sites). If that is
still true, **the code is already on live's disk from the demo deploy** and most
of this document is already done.

Confirm before doing anything else:

```bash
cd <bench>/apps/avinashgroup_app
git log --oneline -1
```

| Result | What it means |
| --- | --- |
| `6fea0fc overlay` | Code is there. **Skip step 1**, go to step 2. |
| anything older | Separate bench, or not pulled. Do step 1. |

Everything after step 1 is **per-site** and must be run for `ng-group`
regardless — the demo deploy did not touch it.

---

## 1. Code onto the server

```bash
cd <bench>/apps/avinashgroup_app
git pull origin develop
git log --oneline -1          # expect 6fea0fc
```

No `bench build` — `sites/assets/avinashgroup_app` is a symlink to the app's
`public/`, so the JS is live the moment it is on disk.

> **Do not run `bench migrate`.** Nothing here needs it, and this bench has a
> known crash in `hrms.patches.v15_0.update_advance_payment_ledger_amount`
> ("Column 'amount' in SET is ambiguous"). The one schema-ish thing this commit
> adds is a desk Page, and step 2 installs that directly.
>
> No print-format JSON changed in `6fea0fc`, so no `modified` bump is needed
> either. (If you ever *do* edit one, read
> `print_format_modified_bump` in `docs/` — an unbumped `modified` is skipped
> **silently** and the site keeps rendering the old template.)

---

## 2. Install the test page on `ng-group`

`6fea0fc` adds a desk Page, `overlay-print-test`. It is a file-backed standard
record, so the site needs to import it. Without this, `/app/overlay-print-test`
is a 404:

```bash
bench --site ng-group reload-doc avinash_group_app page overlay_print_test
```

---

## 3. Tell the server where Chrome is

The overlay renders through headless Chrome. If Chrome is not found, the render
**silently falls back to wkhtmltopdf**, which draws every length at **0.7688×** —
the invoice comes out visibly shrunk and nothing errors. The only sign is an
`Error Log` entry.

`chrome_pdf.find_chrome()` searches `PATH`, but web workers under supervisor
inherit a bare `PATH` that misses `/home/frappe/bin`. So pin it explicitly.

Find the binary:

```bash
for b in google-chrome-stable google-chrome chromium chromium-browser; do \
  command -v $b; done
ls -1 /home/frappe/bin/google-chrome /opt/google/chrome/chrome 2>/dev/null
```

On the demo server it is `/home/frappe/bin/google-chrome`. Set it bench-wide
(one bench, four sites — they all want it):

```bash
bench set-config -g chrome_path /home/frappe/bin/google-chrome
grep chrome <bench>/sites/common_site_config.json
```

If nothing is found at all, Chrome is not installed and **stop here** — deploying
further would put shrunk invoices on real forms.

---

## 4. Restart

```bash
bench --site ng-group clear-cache     # hooks.py bumped ngi_print.js to ?v=1.3
bench restart
```

Do this **outside business hours** — `bench restart` drops in-flight requests.

---

## 5. Verify the code is live — before touching any routing

Three checks, in order. Each one fails differently, so do not skip ahead.

**5a — the JS actually shipped:**

```bash
curl -s https://ng-group.raindropinc.com/assets/avinashgroup_app/js/ngi_print.js \
  | grep -c is_chrome_format          # expect 3
```

**5b — the page exists.** Open
`https://ng-group.raindropinc.com/app/overlay-print-test` in **Chrome**. You
should get the bench with a format table. Then:

- Every overlay row must show `pdf_generator: chrome` with **no red ⚠ line**.
  A ⚠ saying *"pdf_generator is 'wkhtmltopdf'"* means the format record on this
  site was reset — fix it before going further (see Troubleshooting).
- The **Print** button will be **disabled**. That is correct: it prints to a
  queue on the *server*, and the live server has no printer attached. The branch
  PC uses **PDF**.

**5c — the page really is 241.3 × 139.7 mm.** Press **PDF** on the
`Nepal Gas Udyog Invoice A5 Overlay` row, save the file, and:

```bash
pdfinfo <saved>.pdf | grep "Page size"
```

Expect **`684 x 396 pts`** (= 241.3 × 139.7 mm). Anything else — especially
something near `595 x 842` — means the render did not go through Chrome. Go back
to step 3.

> **Chrome, not Firefox.** Firefox's PDF viewer rasterises before printing and
> loses the exact millimetres. This is a hard requirement for anyone who prints.

---

## 6. The data step — route the company at the overlay

**Nothing above changes what a branch sees.** `Company Print Template` decides
which format the printer icon and print-on-submit use, and today every company
routes to a Dot Matrix format (the parked raw ESC/P path).

Read the current state first, so you can put it back:

```bash
bench --site ng-group mariadb -e "select company, print_format, \
return_print_format, print_on_submit from \`tabCompany Print Template Company\` \
where parent='Sales Invoice' order by company;"
```

**Write down what `Nepal Gas Udhyog Pvt. Ltd.` says now.** That value is your
rollback.

Then, in the **desk UI** — `Company Print Template` → *Sales Invoice*:

| Company | Set `print_format` to |
| --- | --- |
| Nepal Gas Udhyog Pvt. Ltd. | `Nepal Gas Udyog Invoice A5 Overlay` |

Leave `return_print_format` alone. Leave the other six companies alone.

> **UI, not SQL.** Saving through the desk fires `on_update`, which invalidates
> the cached template map. A raw `UPDATE` leaves the old routing in redis and the
> change appears not to have worked.

> **Confirm the stationery before you flip it.** The format name is not proof of
> which roll the branch loads. Ask them. Getting this wrong prints data into the
> wrong pre-printed boxes on live VAT invoices.

---

## 7. First print, then calibrate

Do this on **one throwaway invoice**, on the **real stationery**, at the branch.

Order matters — orientation first, position second. A sideways print tells you
nothing about millimetres.

1. **Guide sheet.** On `/app/overlay-print-test`, pick the invoice, press
   **Guide**. Print that PDF at **Actual size**, paper `NGIForm`.
   - Blue outline on the form's own edges → paper size is right.
   - Red boxes = where each value lands.
2. **Sideways?** Set **Rotate** to 90 / 180 / 270 and print again. Keep whichever
   comes out upright. That value becomes this branch's permanent `rot`.
3. **A few mm out, all in the same direction?** Type millimetres into **Shift
   right** / **Shift down** and press Guide again until it lines up.
4. Print a normal invoice with no `guide`, and check the copy titles:
   TAX INVOICE → INVOICE, and on a second print `COPY OF INVOICE 1`.

> Only ever change the shift values. Per-field positions are ruler measurements
> of the form and live in `custom_code/printing/escp_ngi_udyog.py` — editing one
> to fix a whole-sheet shift breaks that field for everybody.

Once `ox` / `oy` / `rot` are settled, report them. Making them permanent is a
code change (or, better, the `Cheque Print Alignment` pattern — see Open items).

**The branch PC needs its own one-time setup** — the paper size, the right print
queue, Chrome. That is a separate document: `docs/branch_pc_setup.md`. Do it
before step 7, or step 7 will just produce blank sheets.

---

## 8. Rollback

Cheap, which is why the data step went last.

- **Data (undoes everything a branch sees):** `Company Print Template` → set
  `Nepal Gas Udhyog Pvt. Ltd.` back to the value you wrote down in step 6, save.
  Instant, no deploy, no restart.
- **Code:** `git revert 6fea0fc && bench --site ng-group clear-cache && bench restart`.
  Only needed if something outside the overlay broke — the routing rollback alone
  makes the overlay invisible again.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Invoice prints visibly small, everything shrunk | Chrome not found; wkhtmltopdf rendered it at 0.7688× | Step 3. Check `Error Log` for `chrome_pdf`. |
| `pdfinfo` shows a page near 595 × 842 | Same as above | Step 3 |
| ⚠ *"pdf_generator is 'wkhtmltopdf'"* on the test page | The Print Format record on this site lost its generator | `bench --site ng-group execute frappe.modules.import_file.import_file_by_path --kwargs "{'path': '<bench>/apps/avinashgroup_app/avinashgroup_app/avinash_group_app/print_format/nepal_gas_udyog_invoice_a5_overlay/nepal_gas_udyog_invoice_a5_overlay.json', 'force': True}"` then `clear-cache` |
| `/app/overlay-print-test` is 404 | Page not imported | Step 2 |
| Branch presses Print, gets the browser dialog not a PDF | Stale JS in their browser | Ctrl+Shift+R. Then check 5a. |
| Branch still gets the old dot-matrix behaviour | Routing not changed, or changed by SQL | Step 6, via the desk UI |
| Blank sheet out of the printer | Paper size on the PC does not match the page, and scaling is off | `docs/branch_pc_setup.md` |
| Correct in Chrome, wrong in Firefox | Firefox rasterises PDFs | Use Chrome |

---

## 10. Known gaps — say these out loud

Do not let a green deploy imply more than it covers.

1. **The `ngi_udyog` coordinate map has never been checked against this
   stationery.** Its numbers were measured off a rectified scan of a *Narayani*
   form. A single `ox`/`oy` pair fixes a uniform shift; it cannot fix a per-field
   error. Step 7 is where this gets found.
2. `ox` / `oy` / `rot` are **URL knobs, not stored settings**. Whatever the branch
   settles on has to be made permanent by someone; today it is not persisted.
3. **Long values are clipped, not wrapped** — fields are `nowrap; overflow:hidden`.
   An unusually long customer or item name is silently cut at the box width.
4. **Returns are out of scope.** `return_print_format` is untouched, so credit
   notes keep whatever path they use today.
5. The other six companies are untouched **by choice**, not by oversight.

---

## Open items after this

1. Fix `rot` and `ox`/`oy` as defaults once the branch reports them.
2. Persist alignment per branch from the desk, so adjusting it needs no deploy —
   the `Cheque Print Alignment` doctype already solves this exact shape.
3. Log `print_format` on `Sales Invoice Print Log`, so "which path did that
   branch actually use" becomes a SQL query instead of a phone call.
4. Roll out to the remaining companies, one at a time, same procedure.

Background reading: `docs/how_overlay_print_works.md` (the code path),
`docs/verification_guide_overlay_printing.md` (what changed and how it was
proven), `docs/branch_pc_setup.md` (the Windows PC).
