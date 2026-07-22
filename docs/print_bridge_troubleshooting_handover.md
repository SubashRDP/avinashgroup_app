# Print Bridge — Troubleshooting Catalogue & Field Handover

Everything that can stop a raw invoice from printing, how to **confirm** each one
(exact command / exact thing to look at), how to **fix** it, and what to **hand
over** to a field tech. Grounded in Print Bridge **v0.5.0**
(`print_bridge/print_bridge.py`, `installer.iss`, `public/js/print_bridge.js`).

> **The one fact that splits every problem in half:** the green toast
> **"Printing via LQ310-RAW"** only appears *after the agent replies `ok`* — i.e.
> the bytes were **successfully written into the `LQ310-RAW` queue**. So:
>
> - **Green toast, nothing prints** → the problem is **downstream of the queue
>   write**: the queue's port, its driver, a paused/offline queue, or the printer
>   itself. The browser and the agent are fine. **(This is the current client-PC
>   symptom.)**
> - **Red toast / a problem dialog / nothing happens** → the problem is **at or
>   above the queue write**: agent not running, origin blocked, queue missing,
>   print format not routed to raw.
>
> Decide which half you're in first, then jump to that section.

---

## Part A — 30-second triage for "says printing but nothing comes out"

Run these two lines in **PowerShell on the affected computer**. They answer 90%
of cases without touching the browser.

```powershell
Get-Printer -Name 'LQ310-RAW' | Select-Object Name, DriverName, PortName, PrinterStatus
Get-PrintJob -PrinterName 'LQ310-RAW'
```

Read the result against this:

| What you see | It means | Go to |
|---|---|---|
| `DriverName` is **not** `Generic / Text Only` (e.g. an Epson name) | Wrong driver — the Epson driver **silently swallows RAW ESC/P** | **F2** |
| `PortName` is a `USBnnn` but the Epson is on a *different* port, or a `PORTPROMPT`/`FILE`/`XPS` port | Queue aimed at the wrong place | **F3** |
| `PrinterStatus` = `Paused` or `Offline` | Queue is paused / marked "Use Printer Offline" | **F4** |
| `Get-PrintJob` shows **stuck jobs** piling up | Jobs spool but never drain (printer offline / port dead) | **F4 / F1** |
| Everything looks right (`Generic / Text Only`, correct `USBnnn`, `Normal`, no stuck jobs) | Queue is healthy — problem is the **printer hardware** or you're printing to the **wrong queue** | **F1 / A2** |
| `Get-Printer` errors "printer name is not valid" | The queue **does not exist** — but then you'd get a *dialog*, not a green toast. Re-check the symptom. | **Q1** |

### A2 — Confirm you're actually printing to the Epson's queue

The agent prints to whatever `default_printer` is in its config (normally
`LQ310-RAW`). If someone edited the config, a green "success" can go to a
different, wrong queue.

```powershell
Get-Content C:\ProgramData\AvinashPrintBridge\config.json
# Look at "default_printer" — it must be "LQ310-RAW".
Invoke-RestMethod 'http://127.0.0.1:8663/diag' -Headers @{Origin='http://localhost'}
# The reply lists default_printer, queue_exists, epson_seen, and every printer Windows sees.
```

---

## Part B — The definitive live test (bypasses the browser entirely)

This sends raw bytes **straight to the queue**, skipping the ERP and the browser.
It isolates "is the queue→printer path alive?" from everything above it.

```powershell
$raw  = [Text.Encoding]::GetEncoding('ISO-8859-1').GetBytes("`e@PRINT BRIDGE OK`r`n`r`n`r`n")
$body = @{ printer='LQ310-RAW'; data_b64=[Convert]::ToBase64String($raw) } | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:8663/print' -Method POST `
  -Headers @{Origin='https://ng-group.raindropinc.com'} -ContentType 'application/json' -Body $body
```

- **A slip comes out** → the queue and printer are fine. The fault is **above**
  the queue: browser routing, origin, wrong print format, or old cached JS →
  Part D.
- **`ok` reply but no paper** → the fault is the **queue/driver/port/printer** →
  Part C (Q/F/P rows).
- **Error reply** → read the message; it usually names the missing queue → **Q1**.

---

## Part C — Full failure catalogue (every layer)

Ordered printer-outward → browser. Each row: how it looks, how to **confirm**,
how to **fix**, and the underlying spec.

### P — Printer hardware (job spools, nothing prints → green toast possible)

| Code | Cause | Confirm | Fix | Spec |
|---|---|---|---|---|
| **F1** | Printer **off / offline / no paper / cover open / error light** | Look at the Epson (power + error LEDs, paper). `Get-PrintJob -PrinterName LQ310-RAW` shows jobs stuck at "Spooling/Error" | Power on, load paper, clear the error, close the cover. Then clear stuck jobs: `Get-PrintJob -PrinterName LQ310-RAW \| Remove-PrintJob` and reprint | A queue accepts `WritePrinter` bytes even when the device is offline; the job just waits. That's why the toast is green. |
| **F1b** | **Dead/dry ribbon or head** | Paper *moves* but is blank/faint | Replace ribbon; this is the one "prints but empty" case — different from "nothing at all" | — |
| **F1c** | **USB cable / hub** not delivering the device | `Get-PnpDevice -PresentOnly \| ? InstanceId -like 'USB\VID_04B8*'` returns nothing | Reseat USB (prefer a **direct** port, not a hub), try another port, power-cycle printer | Epson USB vendor id is `04B8`; the agent finds the port from this device. |

### F — The `LQ310-RAW` queue exists but is wrong (green toast, no paper)

| Code | Cause | Confirm | Fix | Spec |
|---|---|---|---|---|
| **F2** | Queue built on the **Epson driver**, not Generic/Text Only | `Get-Printer -Name LQ310-RAW \| select DriverName` ≠ `Generic / Text Only` | Delete the bad queue and let the agent rebuild it clean: `Remove-Printer -Name LQ310-RAW` then **restart the PC** (or re-run the installer). The agent recreates it on the correct driver | The Epson ESC/P V4 driver **swallows RAW jobs** — spooler reports success, head never moves. `write_raw()` uses the `RAW` datatype; only a "Generic / Text Only" byte-pipe queue passes it through (`print_bridge.py` docstrings). |
| **F3** | Queue points at the **wrong / stale USB port** | `Get-Printer -Name LQ310-RAW \| select PortName` vs the real port from `Get-PnpDevice -PresentOnly … VID_04B8` (see the §7 PowerShell in the user guide) | With Epson **on**, **restart the PC** — the agent's `_install_queue()` runs `Set-Printer` to repair the port on startup. Manual: `Set-Printer -Name LQ310-RAW -PortName USBnnn` | v0.5.0 self-heals the port at every launch, using `-PresentOnly` so stale ports left by a moved/unplugged printer are ignored. |
| **F4** | Queue is **Paused** or **"Use Printer Offline"** | `Get-Printer -Name LQ310-RAW \| select PrinterStatus` = `Paused`/`Offline`; or jobs stuck in `Get-PrintJob` | Resume: right-click the printer → uncheck **Pause Printing** and **Use Printer Offline**; or `Get-Printer … ; (Get-WmiObject Win32_Printer -Filter "Name='LQ310-RAW'").Resume()`. Clear stuck jobs and reprint | A paused/offline queue still returns success to `WritePrinter`; the job just never leaves the spooler. |
| **F5** | **Spooler service** stopped or wedged | `Get-Service Spooler` not `Running`; jobs won't clear | `Restart-Service Spooler` (as admin), clear jobs, reprint | All queue I/O goes through the Windows Print Spooler. |

### Q — The queue is missing (usually a *dialog*, not a green toast)

| Code | Cause | Confirm | Fix | Spec |
|---|---|---|---|---|
| **Q1** | `LQ310-RAW` **queue absent**, agent couldn't recreate it | ERP shows **"Print queue missing"** dialog; `/diag` → `queue_exists:false`, `epson_seen:true` | **Restart the PC** with the Epson attached — the SYSTEM boot task runs the agent **elevated**, which lets `Add-Printer` succeed. If still failing, re-run the installer with the printer on | `_resolve_target()` heals a missing queue on demand, but `Add-Printer` needs elevation; the boot/logon task runs as SYSTEM for exactly this. |
| **Q2** | Queue missing **and** printer not seen | ERP shows **"Printer not connected"**; `/diag` → `queue_exists:false`, `epson_seen:false` | Fix the physical connection (F1/F1c), then just print again — the queue builds itself once Windows sees the printer. No reinstall | `_install_queue()` throws the "No Epson" case → the agent leaves the queue for the next print. |
| **Q3** | Agent running but **not elevated**, so it can't create the queue | `/diag` → `elevated:false` and `queue_exists:false` | Don't rely on a hand-started agent — reboot so the **SYSTEM task** owns it. Confirm the autostart task exists (A-row below) | A user-launched `print_bridge.exe` lacks rights for `Add-Printer`; only the SYSTEM task can self-heal. |
| **Q4** | **Generic/Text Only driver** absent from the driver store | Agent log shows `0x80070032`; `/diag` `printer_error` set | v0.5.0 stages it automatically via `pnputil` from `prnge001.inf`/`ntprint.inf`. If that failed, add the "Generic / Text Only" printer once by hand, then reboot | `_install_queue()` step 1 stages the inbox driver before `Add-Printer`. |

### G — The agent itself (ERP shows "not running" / "blocked")

| Code | Cause | Confirm | Fix | Spec |
|---|---|---|---|---|
| **G1** | **Not installed** on this PC | Task Manager → Details has no `print_bridge.exe`; `Invoke-RestMethod http://127.0.0.1:8663/ping` refuses | Install `PrintBridgeSetup.exe` **v0.5.0** (direct release link, **not** "latest") | — |
| **G2** | Installed but **not running** (autostart task missing/failed) | `schtasks /Query /TN "Avinash Print Bridge"` errors; no `print_bridge.exe` | Start from **Start menu → Avinash Print Bridge**, then reboot to confirm autostart. Check `task_register.log` in ProgramData | Autostart is a `schtasks /XML` task with **boot + sign-in** triggers as SYSTEM; sign-in trigger is what survives Fast-Startup shutdowns. |
| **G3** | **Only starts after Restart, dies after Shutdown** | Works after "Restart", dead after "Shut down" + power-on | Reinstall v0.5.0 (has the sign-in trigger). Test with **Shut down**, not Restart | Fast Startup makes a shutdown a kernel hibernate → no boot trigger fires; the logon trigger covers it. Pre-0.3.4 bug. |
| **G4** | **Port 8663 taken by a foreign program** | ERP shows **"Something is blocking…"**; `C:\ProgramData\AvinashPrintBridge\PORT_CONFLICT.txt` exists; `netstat -ano \| findstr :8663` → a non-`print_bridge` PID | Identify the PID in Task Manager → Details; close/reconfigure/uninstall it; start the agent | The agent binds `127.0.0.1:8663` only; if a foreign owner holds it, it writes `PORT_CONFLICT.txt` and refuses rather than fighting. |
| **G5** | **Old agent version** (< 0.5.0) | `/ping` or `/diag` → `version` below `0.5.0` | Reinstall v0.5.0 over the top | Only 0.5.0 auto-creates the queue with no Epson driver present. |
| **G6** | Agent **crash-looping** (e.g. unwritable log dir) | Appears then vanishes in Task Manager; no log growth | Send `print_bridge.log`; check ProgramData permissions | `_app_dir()` falls back ProgramData→LocalAppData→temp; a crash loop is usually something else. |

### D — Browser ↔ agent / ERP routing (the live test in Part B prints, but the ERP doesn't)

| Code | Cause | Confirm | Fix | Spec |
|---|---|---|---|---|
| **D1** | **This site is not on the allow-list** — the classic "works in office, not on a new machine/URL" | ERP shows **"blocked"** dialog cause B; `/diag` `allowed_origins` doesn't include the site's URL; agent returns **403** | Add the exact `https://…` origin to `allowed_origins` in `config.json`, **restart the agent**. To bake in for all machines, add to `DEFAULT_ORIGINS` + `installer.iss` and cut a release | Origin match is **exact** (`_origin_allowed`); only the 4 built-in sites + loopback/LAN are trusted out of the box. **Check the site the client PC actually opens.** |
| **D2** | **Chrome 142+ Local Network Access** prompt not granted | Browser shows an "Allow local network" prompt, or the request is blocked pre-flight | Click **Allow** once (Chrome remembers), or (re)run the installer which pre-grants via HKLM policy | `installer.iss` writes `LocalNetworkAccessAllowedForUrls` for Chrome+Edge for all 4 origins. Firefox needs nothing. |
| **D3** | **Old cached JS** — "signal is aborted without reason" | That exact old message; page running a stale bundle | Hard-reload `Ctrl+Shift+R`; if still old, clear the site cache. **Server must have the current JS deployed** (build + restart, see below) | Old build aborted prints at 2s; current code allows **60s** so a first-print queue-heal isn't killed. |
| **D4** | **Server hasn't deployed the current app JS** | Tills keep showing old behaviour after a hard reload | On the ERP server: `git pull && bench build --app avinashgroup_app && bench --site all clear-cache && bench restart`, then hard-reload tills | The routing/dialog/download-link code lives on the ERP server, not the till. |
| **D5** | **Firewall / AV** blocks loopback | Even `no-cors` probe fails though `print_bridge.exe` runs | Allow loopback / add an AV exception for `print_bridge.exe` | Rare; loopback is normally exempt. |

### E — ERP-side print routing (nothing raw happens at all)

| Code | Cause | Confirm | Fix | Spec |
|---|---|---|---|---|
| **E1** | Company has **no Company Print Template rule** → prints via normal PDF/dialog, not the agent | Print opens the browser PDF/format picker instead of going raw; company is **GLMI or SGU** (currently unconfigured) | Add a row for that company to the **Company Print Template** (doctype "Sales Invoice") pointing at its dot-matrix format | Only 5 of 7 companies are wired (NGI/NGG/NGK/NGN/GEPL). GLMI + SGU fall back to stock printing. |
| **E2** | **Empty ESC/P** from the server → silent no-op | Clicking print does **nothing at all** (no toast, no dialog) | Check the print format renders; look for a server error in the Frappe error log | `print_raw_doc` bails silently on `!r.message` (empty `get_rendered_raw_commands`). |
| **E3** | **Non-byte print data** | Red toast "Print data is not a byte stream" | Bug in the ESC/P generator (`escp_*.py`) emitting a char > 255 — escalate to dev | `btoa()` rejects any char > 255. |
| **E4** | **Duplicate copy risk** after a slow print | Toast "No answer after 60 seconds… may still print" | **Wait and check the printer before reprinting** — the job usually completed; aborting the HTTP request does **not** cancel it server-side | 60s client timeout; the agent finishes the spool regardless. |

---

## Part D — Diagnostics reference (the specification)

### `/ping` — quick "is it alive"
`GET http://127.0.0.1:8663/ping` → `{ ok, version, default_printer }`. Needs an
allowed `Origin` header. Use it to read the **version** and default queue.

### `/diag` — the full structured report (capture this first on any bad machine)
`GET http://127.0.0.1:8663/diag` → `{ ok, diag: { … } }`:

| Field | Meaning | What "bad" looks like |
|---|---|---|
| `version` | agent version | below `0.5.0` → G5 |
| `default_printer` | queue the agent prints to | not `LQ310-RAW` → A2 |
| `queue_exists` | is that queue present | `false` → Q1/Q2/Q3 |
| `epson_seen` | any Epson/LQ-310 visible to Windows (name hint only) | `false` with `queue_exists:false` → Q2 (printer not connected) |
| `printers` | every queue Windows enumerates | confirms what's really installed |
| `printer_error` | error while enumerating | non-empty → spooler/driver problem |
| `elevated` | is the agent admin | `false` + missing queue → Q3 |
| `allowed_origins` | sites allowed to print | site missing → D1 |
| `config_file` / `log_file` | where config & log live | paths to collect |

```powershell
Invoke-RestMethod 'http://127.0.0.1:8663/diag' -Headers @{Origin='http://localhost'}
```

### Configure exit codes (installer contract, `configure()` in print_bridge.py)
`0` = queue created/exists · `3` = **no Epson attached right now (NOT a failure**,
heals on first print) · `1` = a real error worth reading the log.

### Key paths (memorise these — everything to collect lives here)
| Thing | Path / value |
|---|---|
| Agent address | `http://127.0.0.1:8663` (loopback only) |
| Queue | `LQ310-RAW`, driver **Generic / Text Only** |
| Autostart task | `Avinash Print Bridge` (boot + sign-in, SYSTEM) |
| Log | `C:\ProgramData\AvinashPrintBridge\print_bridge.log` |
| Config | `C:\ProgramData\AvinashPrintBridge\config.json` |
| Port-conflict note | `C:\ProgramData\AvinashPrintBridge\PORT_CONFLICT.txt` |
| Task-register log | `C:\ProgramData\AvinashPrintBridge\task_register.log` |
| Installer (v0.5.0) | `https://github.com/SubashRDP/avinashgroup_app/releases/download/print-bridge-v0.5.0/PrintBridgeSetup.exe` |

### The four trusted sites (out of the box)
`https://ng-group.raindropinc.com` (production) ·
`https://avinaslive1.raindropinc.com` · `https://sandboxavinas-demo.raindropinc.com` ·
`https://avinasdemo.raindropinc.com`. Any **other** URL a client PC opens must be
added to `allowed_origins` (D1).

---

## Part E — Handover: what a field tech needs

**Golden rule of first response:** *Epson on + paper in → restart the PC → reload
the browser.* v0.5.0 rebuilds the queue and repairs the port on boot; this alone
fixes most F3/Q1/G2 cases.

### Before you escalate, collect (2 minutes):
1. The `/diag` output (paste of the `Invoke-RestMethod …/diag` line).
2. `Get-Printer -Name LQ310-RAW | select Name,DriverName,PortName,PrinterStatus`.
3. The log file `C:\ProgramData\AvinashPrintBridge\print_bridge.log`.
4. `PORT_CONFLICT.txt` **if it exists**.
5. **Which site URL** the PC prints from, and **which company** the invoice is for.
6. Whether the **Part B live test** produced paper (this is the single most useful
   fact — it splits "queue/printer" from "browser/ERP").

### Escalate to a developer when:
- Part B prints but the ERP won't, **and** the origin is already allowed (D1
  ruled out) and JS is current (D3/D4 ruled out) → likely a print-format/routing
  bug.
- `btoa`/byte-stream error (E3) → ESC/P generator bug.
- Repeated crash-loop with a clean environment (G6).
- A **different printer model or stationery** is in use → the ESC/P layout is
  calibrated to the LQ-310 and needs re-calibration in `escp_*.py`.

### Remote support (AnyDesk)
You can drive **all** of the above remotely — PowerShell, installer, browser,
logs. You **cannot** confirm paper physically moved or fix power/cable/paper, so
keep a person at the printer as your eyes/hands. Set AnyDesk to allow **elevation**
(UAC for driver/printer installs) and set an **unattended-access** password.

### New site / new company checklist
- **New URL** that must print raw → add to `allowed_origins` (D1); for a permanent
  rollout, add to `DEFAULT_ORIGINS` + `installer.iss` and cut a release.
- **New company** invoices not auto-routing → add its row to **Company Print
  Template** (E1). GLMI and SGU are currently unconfigured.

---

## Quick decision tree

```
Print clicked
│
├─ Nothing happens (no toast, no dialog) ─────────► E1 (wrong/no routing) or E2 (empty ESC/P)
│
├─ Dialog "not running" ──────────────────────────► G1/G2  (agent absent/stopped)
├─ Dialog "something is blocking" ────────────────► G4 (port) or D1 (origin) or D2 (LNA)
├─ Dialog "printer not connected" ────────────────► Q2/F1c
├─ Dialog "print queue missing" ──────────────────► Q1/Q3
├─ Red toast "not a byte stream" ─────────────────► E3
├─ Toast "no answer after 60s" ───────────────────► E4 (check printer before reprint!)
│
└─ GREEN toast "Printing via LQ310-RAW", no paper ► run Part A:
      ├─ wrong DriverName ───────────────────────► F2
      ├─ wrong PortName ─────────────────────────► F3
      ├─ Paused/Offline / stuck jobs ────────────► F4 / F1
      ├─ all correct ────────────────────────────► F1 (hardware) / A2 (wrong queue)
      └─ still unsure ───────────────────────────► Part B live test
```

See also: `docs/print_bridge_user_guide.md` (operator/IT guide),
`print_bridge/README.md` (design), `docs/print_bridge_deployment.md`.
