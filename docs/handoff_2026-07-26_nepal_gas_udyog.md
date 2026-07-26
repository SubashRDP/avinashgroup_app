# Handover — 2026-07-26 — Nepal Gas Udyog pre-printed invoice

**Scope of this document is one company.** Everything below is about
**Nepal Gas Udhyog Pvt. Ltd.** printing onto its 9.5″ × 5.5″ pre-printed
continuous form. The other six companies are deliberately untouched and are not
discussed here.

Session ended mid-deploy: the live server was reached, the read-only survey was
about to run, and work was paused to fix layout. Nothing on production was
changed. **Live is exactly as it was this morning.**

---

## 1. The chain — what talks to what

Know this before touching anything; every question below resolves to one link in
it.

| Link | Value |
| --- | --- |
| Company | `Nepal Gas Udhyog Pvt. Ltd.` |
| Routing record | `Company Print Template` → *Sales Invoice* → that company's row |
| Print format | `Nepal Gas Udyog Invoice A5 Overlay` |
| Form key it passes | `ngi_udyog` |
| Measurements module | `custom_code/printing/escp_ngi_udyog.py` (`POS`) |
| Shared renderer | `templates/print_formats/nepal_gas_invoice_a5_overlay.html` |
| Generator | `chrome` (pinned in the format's own JSON) |
| Paper | 241.3 × 139.7 mm = **684 × 396 pt** |

The format record is a one-liner — it sets `form = 'ngi_udyog'` and includes the
shared template. **All seven overlay formats share that one template**; only the
`POS` map differs. So a change to the template affects every company, and a
change to `escp_ngi_udyog.py` affects only this one.

---

## 2. Status

**Done:**

- Code committed as **`6fea0fc`** ("overlay") and pushed to `origin/develop`.
- **Working on `avinasdemo.raindropinc.com`.** Verified by the only check that
  actually proves it: the rendered PDF measures **684 × 396 pt**. A page near
  595 × 842 means Chrome did not render it and wkhtmltopdf did.
- Windows branch-PC blocker root-caused (§6).
- Runbooks written: `docs/live_server_overlay_deploy.md` (server),
  `docs/branch_pc_setup.md` (the billing PC).

**Not done:**

- **Nothing is deployed to `ng-group.raindropinc.com`.** Not the per-site steps,
  not the routing row. The branch still prints exactly what it printed yesterday.
- Layout / coordinate work — the reason this session stopped.
- `ox` / `oy` / `rot` have never been measured against the real stationery.
- `docs/branch_pc_setup.md` and `docs/windows_setup_form.ps1` are still
  **untracked in git**. Commit them or they never reach the server.

---

## 3. Resume here — the live deploy

Site name is the full domain: **`ng-group.raindropinc.com`**, not `ng-group`.

### 3.1 Survey first (read-only, changes nothing)

From the bench root:

```bash
cd apps/avinashgroup_app && git log --oneline -3 && git status --short | head && cd ../..

for b in google-chrome-stable google-chrome chromium chromium-browser; do command -v $b; done
ls -1 /home/frappe/bin/google-chrome /opt/google/chrome/chrome 2>/dev/null
grep -i chrome sites/common_site_config.json

bench --site ng-group.raindropinc.com mariadb -e "select company, print_format, \
return_print_format, print_on_submit from \`tabCompany Print Template Company\` \
where parent='Sales Invoice' order by company;"
```

Read it like this:

- **`git log` top line is `6fea0fc`** → the code is already on this disk (demo
  and production are served by the **same bench**), so skip the pull. Older →
  `git pull origin develop`.
- **All the Chrome probes come back empty** → **stop.** Deploying without Chrome
  puts shrunk invoices on real VAT forms and raises no error.
- **The routing row for `Nepal Gas Udhyog Pvt. Ltd.` is your rollback.**
  Write down what it says today before changing it.

### 3.2 Per-site steps (these are owed regardless of the git state)

```bash
bench --site ng-group.raindropinc.com reload-doc avinash_group_app page overlay_print_test
bench set-config -g chrome_path /home/frappe/bin/google-chrome   # use the path found above
bench --site ng-group.raindropinc.com clear-cache
bench restart
```

Outside business hours — `bench restart` drops in-flight requests.

### 3.3 Prove the code is live *before* touching routing

```bash
curl -s https://ng-group.raindropinc.com/assets/avinashgroup_app/js/ngi_print.js | grep -c is_chrome_format   # expect 3
```

Then open `https://ng-group.raindropinc.com/app/overlay-print-test` **in Chrome**,
press **PDF** on the `Nepal Gas Udyog Invoice A5 Overlay` row, and check the saved
file:

```bash
pdfinfo <saved>.pdf | grep "Page size"     # expect 684 x 396 pts
```

The page's **Print** button will be **disabled on live** — it prints to a CUPS
queue on the *server*, and the server has no printer. That is correct. The branch
uses **PDF**.

### 3.4 Only then, the routing row

Desk UI: `Company Print Template` → *Sales Invoice* → set
`Nepal Gas Udhyog Pvt. Ltd.` → `print_format` = **`Nepal Gas Udyog Invoice A5 Overlay`**.
Leave `return_print_format` alone.

**UI, not SQL.** The desk save fires `on_update`, which clears the cached routing
map. A raw `UPDATE` leaves stale routing in redis and looks like the change did
nothing.

**Confirm with the branch which roll they actually load before flipping this.**
The format name is not proof. Wrong roll = data in the wrong pre-printed boxes on
live VAT invoices.

Full detail: `docs/live_server_overlay_deploy.md`.

---

## 4. The layout work

### Where the numbers live

`custom_code/printing/escp_ngi_udyog.py` → the `POS` dict. Every value is a
**true ruler distance in mm from the paper's top-left corner**. That module's
header explains the derivation; read it before editing.

### The rule that matters

- **Whole sheet shifted in one direction** → that is `ox` / `oy`. Do **not**
  touch `POS`.
- **One field wrong, the rest fine** → that field's entry in `POS`.

Editing a `POS` value to correct a whole-sheet shift breaks that field for
everyone and hides the real problem. This has bitten this codebase before.

### How to measure it

Use `/app/overlay-print-test`, on a **throwaway invoice**, on the **real
stationery**. Order matters — orientation first, position second; a sideways
print tells you nothing about millimetres.

1. **Guide** → prints outlines instead of an invoice. Blue = sheet edge,
   red = each field's box.
   - Blue lands on the form's own edges → paper size is right.
2. **Sideways?** Set **Rotate** to 90 / 180 / 270, print again, keep whichever
   comes out upright. That becomes this branch's permanent `rot`.
3. **A few mm out, all the same direction?** Type millimetres into **Shift
   right** / **Shift down**, press Guide again, repeat until it lines up.
4. Print a normal invoice (no guide) and check the copy titles:
   TAX INVOICE → INVOICE, and `COPY OF INVOICE 1` on a second print.

`ox` / `oy` / `rot` are **URL knobs, not stored settings.** Whatever comes out of
this has to be made permanent by someone — today it is not persisted anywhere.

---

## 5. Known gaps — say these out loud

1. **The `ngi_udyog` coordinate map has never been checked against this
   stationery.** Its numbers were measured off a rectified scan of a
   ***Narayani*** form. `ox`/`oy` fix a uniform shift; they cannot fix a
   per-field error. The guide sheet is where this surfaces, and it is the single
   most likely thing to go wrong.
2. **Long values are clipped, not wrapped** — fields are `nowrap;
   overflow:hidden`, so an unusually long customer or item name is silently cut
   at the box width.
3. **Returns are out of scope.** `return_print_format` is untouched, so credit
   notes keep whatever path they use today.
4. **Chrome's absence fails silently** — wkhtmltopdf renders every length at
   **0.7688×**. Nothing raises; the only sign is an `Error Log` entry for
   `chrome_pdf`. This is why §3.3 exists.

---

## 6. The billing PC (one-time, per machine)

Root-caused 2026-07-26. **Symptom: Chrome offers only A4 and Letter.**

A PC ends up with several queues for one printer. Chrome was pointed at the one
running `Epson ESC/P V4 Class Driver`. **V4 drivers ignore Windows Forms
entirely** and publish a fixed media list, so the 241.3 × 139.7 form can never
appear on that queue — no setting, script, or registry edit adds it.

Use a queue whose driver is the real Epson one at **MajorVersion 3**, on the
**USB** port. On the machine we looked at, `EPSON LQ-310 ESC/P2 (Copy 1)` /
USB005 already existed.

Three traps that cost time:

- The form must be set in **Printing Defaults**, not just Preferences — Defaults
  is what Chrome reads.
- `Set-PrintConfiguration -PaperSize` **cannot** take a custom form name; it only
  accepts Windows' built-in enum. Use
  `rundll32 printui.dll,PrintUIEntry /p /n "<queue>"`.
- Chrome caches the paper list at startup. `taskkill /F /IM chrome.exe` —
  closing the window is not enough.

**Chrome, not Firefox.** Firefox rasterises PDFs before printing and loses the
exact millimetres.

Full runbook: `docs/branch_pc_setup.md`.

---

## 7. Rollback

- **Data** — set the `Nepal Gas Udhyog Pvt. Ltd.` row back to the value recorded
  in §3.1 and save. Instant, no deploy, no restart. This alone makes the overlay
  invisible to the branch again.
- **Code** — `git revert 6fea0fc`, then `clear-cache` and `bench restart`. Only
  needed if something outside the overlay breaks.

---

## 8. Do not

- **Do not run `bench migrate` on this bench.** Known crash in
  `hrms.patches.v15_0.update_advance_payment_ledger_amount` ("Column 'amount' in
  SET is ambiguous"). Nothing in `6fea0fc` needs it — the one new record is a desk
  Page, and `reload-doc` installs that directly.
- **Do not change routing by SQL** (§3.4).
- **Do not edit `POS` to fix a whole-sheet shift** (§4).
- **Do not bump the other six companies** while this one is being proven.

---

## 9. Next session, in order

1. Finish the layout fixes.
2. Run §3.1, paste the output, decide pull-or-not.
3. §3.2 → §3.3. Stop if the PDF is not 684 × 396 pt.
4. §3.4 routing, after confirming the roll with the branch.
5. Branch PC per §6.
6. Guide print per §4, report `rot` and `ox`/`oy`.
7. Make those permanent — ideally the way `Cheque Print Alignment` already does
   it, so future adjustments need no deploy.
8. Commit `docs/branch_pc_setup.md` and `docs/windows_setup_form.ps1`.
