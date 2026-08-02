# Print Bridge — Complete User Guide

Raw dot-matrix invoice printing for the Avinash Group ERP, on Epson LQ-310
printers, from any of the four ERP sites — with **one** small program installed
per till and **no** QZ Tray, certificates, or browser prompts.

**Who this is for**
- **Till operators** — read *Everyday use* and *When printing fails* (they are short).
- **IT / field support** — the whole document; *Install*, *Troubleshooting*, and
  *Diagnostics* are your working sections.
- **Developers** — *How it works*, *Config*, and *Deploying updates*.

Current version: **Print Bridge v0.5.0**.

---

## 1. What Print Bridge is (and why it exists)

Invoices are printed as **raw ESC/P** byte streams so they land exactly on the
pre-printed continuous-form stationery. Browsers cannot send raw bytes to a USB
printer on their own. Print Bridge is a tiny background agent that listens only on
`http://127.0.0.1:8663` (this computer only — nothing off the machine can reach
it) and forwards the ERP's print job straight to the Epson.

It **replaces QZ Tray**. There is no certificate, no Java, no per-site pairing.

```
Browser (ERP site) ──HTTP──> Print Bridge agent (127.0.0.1:8663) ──raw──> LQ310-RAW queue ──USB──> Epson LQ-310
```

The queue named **`LQ310-RAW`** uses the Windows **"Generic / Text Only"** driver —
a pure byte pipe. (The Epson's *own* driver silently swallows raw ESC/P jobs, which
is why we never print through it.)

---

## 2. The four ERP sites

The agent and the browser policy already trust these four out of the box — nothing
to configure per site:

| # | Site URL | Role |
|---|----------|------|
| 1 | `https://ng-group.raindropinc.com` | production (all 7 companies) |
| 2 | `https://avinaslive1.raindropinc.com` | test |
| 3 | `https://sandboxavinas-demo.raindropinc.com` | test |
| 4 | `https://avinasdemo.raindropinc.com` | test |

One install on a till makes **all four** print. Adding a *new* site later needs one
config edit — see §10.

---

## 3. Install — once per till

> **Before you start: connect the Epson LQ-310 by USB and switch it ON.** v0.5.0
> can install without it, but with the printer on, the `LQ310-RAW` queue is created
> immediately and you can test right away.

1. On the till, open this link and download **`PrintBridgeSetup.exe`**:
   `https://github.com/SubashRDP/avinashgroup_app/releases/download/print-bridge-v0.5.0/PrintBridgeSetup.exe`

   ⚠️ Do **not** use the repo's generic *"latest release"* page — that slot belongs
   to a different product (K40 Bridge). Use the direct link above, or pick the
   newest release named **"Print Bridge vX.Y.Z"**.

2. Run it and accept the **admin (UAC)** prompt. Finish the wizard.

3. That's all — no QZ Tray, no certificate, no browser setup.

**What the installer does:** drops `print_bridge.exe`, creates the `LQ310-RAW`
queue on the Epson's USB port (now, or automatically on the first print if the
printer was off during install), pre-grants all four sites in the Chrome/Edge
local-network policy, and registers an autostart task that runs the agent as
SYSTEM **at boot and at every sign-in**.

### If Windows blocks the installer

It is unsigned, so Windows/antivirus may block a freshly-downloaded copy
(*"Windows protected your PC"* or *"cannot access the specified device, path, or
file"*). It is not broken — clear the block:

1. Right-click `PrintBridgeSetup.exe` → **Properties** → tick **Unblock** → Apply.
2. Right-click → **Run as administrator**.
3. SmartScreen blue box → **More info → Run anyway**.
4. Still blocked → **Windows Security → Virus & threat protection → Protection
   history** → find it → **Restore / Allow** (or add a File exclusion), then re-run.

---

## 4. Verify it works (right after install)

1. Open any of the four sites in Chrome/Edge and log in.
2. Open an invoice → **Print** → choose a raw / dot-matrix format.
3. Expect: a green toast **"Printing via LQ310-RAW"**, the Epson prints, and **no
   "Allow local network" prompt**.

For a full self-check without the browser, IT can run the PowerShell block in §7.

Tick off each site once (they all use the single install):

- [ ] `ng-group.raindropinc.com` prints
- [ ] `avinaslive1.raindropinc.com` prints
- [ ] `sandboxavinas-demo.raindropinc.com` prints
- [ ] `avinasdemo.raindropinc.com` prints

---

## 5. Everyday use (operators)

- Just print normally: open the invoice → **Print** → the dot-matrix format → done.
- The agent starts by itself when the computer boots or you sign in. You never have
  to launch anything.
- If nothing prints, first look at the printer: **is it on, online, and does it have
  paper?** Then see §6.

---

## 6. When printing fails — troubleshooting

Log file (IT): `%PROGRAMDATA%\AvinashPrintBridge\print_bridge.log`

| What you see | What it means | Fix |
|---|---|---|
| Dialog **"Print Bridge not installed on this computer"** | The browser can't reach the agent on `127.0.0.1:8663` — it isn't running (or isn't installed). | See §6.1. |
| Green toast but **nothing prints** | Job reached the agent, but the `LQ310-RAW` queue is missing or on the wrong USB port. | See §6.2. |
| Popup **"Allow local network"** | Browser policy didn't pre-grant this site. | Click **Allow** once (Chrome remembers), or re-run the installer. |
| Old message **"signal is aborted without reason"** | This browser is running an **old cached** script. | Hard-reload the page (`Ctrl+Shift+R`); if still old, clear the site's cache. The server also needs the current app JS deployed (§11). |
| Dialog about **another program using port 8663** | A foreign program squats on the agent's port. | Follow the on-screen steps (it names the port and how to find the program), or read `%PROGRAMDATA%\AvinashPrintBridge\PORT_CONFLICT.txt`. |
| Installer said **the queue couldn't be created** | Epson was off/unplugged during install. | Connect + power on the Epson, then just **restart the PC** (the agent recreates the queue on startup) or re-run the installer. |
| Nothing prints **after a full shutdown** | Old versions (before v0.3.4) died on Fast-Startup shutdown. | Install **v0.5.0** over the old one. |

### 6.1 "Print Bridge not installed" — agent not running

Fastest fix: **restart the computer** — the autostart task relaunches the agent as
SYSTEM, and (v0.5.0) it recreates the `LQ310-RAW` queue on the way up. Then reload
the browser.

If you don't want to reboot, IT can start it from the Start menu (**Avinash Print
Bridge**) or run the diagnostic in §7 to confirm whether it's installed at all. If
it was never installed on this machine, do §3.

### 6.2 Prints "sent" but no paper — queue / port

Almost always the `LQ310-RAW` queue is missing or aimed at the wrong USB port.

**On v0.5.0 this heals itself:** with the Epson plugged in and on, **restart the
PC** (or reinstall over the top). The agent finds the Epson's USB port on startup —
even if Windows never installed the Epson's own driver — and creates/repairs the
queue automatically. No manual PowerShell.

If it still doesn't print after that, run the diagnostics in §7 and send IT the
`/diag` output plus the log file.

---

## 7. Diagnostics toolbox (IT)

### One-shot self-check (PowerShell)

Paste this whole block into **PowerShell** on the till. It checks the autostart
task, the agent, the queue, all four origins, the browser policy, and does a **live
physical print**:

```powershell
$origins = @(
  'https://ng-group.raindropinc.com',
  'https://avinaslive1.raindropinc.com',
  'https://sandboxavinas-demo.raindropinc.com',
  'https://avinasdemo.raindropinc.com'
)
function Ok($b,$m){ if($b){Write-Host "PASS  $m" -f Green}else{Write-Host "FAIL  $m" -f Red} }

$task = schtasks /Query /TN "Avinash Print Bridge" /V /FO LIST 2>$null
Ok ($LASTEXITCODE -eq 0) "autostart task registered"
Ok ([bool]($task -match 'At system start up|At startup')) "  boot trigger present"
Ok ([bool]($task -match 'At logon time|At log on')) "  sign-in trigger present (survives Fast Startup shutdown)"
Ok ([bool]($task -match 'SYSTEM')) "  runs as SYSTEM"

try { $p = Invoke-RestMethod 'http://127.0.0.1:8663/ping' -Headers @{Origin=$origins[0]} } catch { $p = $null }
Ok ($p -and $p.ok) "agent answers on 127.0.0.1:8663 (version $($p.version))"

$q = Get-Printer -Name 'LQ310-RAW' -ErrorAction SilentlyContinue
Ok ($q -ne $null) "LQ310-RAW queue exists (driver $($q.DriverName), port $($q.PortName))"

foreach ($o in $origins) {
  try { $r = Invoke-WebRequest 'http://127.0.0.1:8663/ping' -Headers @{Origin=$o} -UseBasicParsing; $code=$r.StatusCode }
  catch { $code = $_.Exception.Response.StatusCode.value__ }
  Ok ($code -eq 200) "origin accepted: $o"
}

$raw  = [Text.Encoding]::GetEncoding('ISO-8859-1').GetBytes("`e@PRINT BRIDGE OK`r`n`r`n`r`n")
$body = @{ printer='LQ310-RAW'; data_b64=[Convert]::ToBase64String($raw) } | ConvertTo-Json
try { $pr = Invoke-RestMethod 'http://127.0.0.1:8663/print' -Method POST -Headers @{Origin=$origins[0]} -ContentType 'application/json' -Body $body } catch { $pr = $null }
Ok ($pr -and $pr.ok) "live print sent ($($pr.bytes) bytes) — CHECK THAT PAPER MOVED"
```

**The last check is the real one:** a slip must physically come out of the Epson.
Green checks with no paper = the queue is on the wrong USB port (see §6.2).

### The agent's own health report

- `http://127.0.0.1:8663/ping` — quick "am I alive", returns the version.
- `http://127.0.0.1:8663/diag` — full structured report: version, whether the queue
  exists, whether Windows even sees an Epson, admin status, the allowed origins, and
  the config/log paths. This is the first thing to capture when a machine misbehaves.

  ```powershell
  Invoke-RestMethod 'http://127.0.0.1:8663/diag' -Headers @{Origin='http://localhost'}
  ```

### Confirm the v0.5.0 port auto-detect can see the Epson

If a machine has the Epson connected but no Epson driver installed, confirm the
agent will find its USB port (should print a `USB00x`):

```powershell
Get-PnpDevice -PresentOnly |
  Where-Object { $_.InstanceId -like "USBPRINT\*" -or $_.InstanceId -like "USB\VID_04B8*" } |
  ForEach-Object { (Get-ItemProperty ("HKLM:\SYSTEM\CurrentControlSet\Enum\" + $_.InstanceId + "\Device Parameters") -Name PortName -ErrorAction SilentlyContinue).PortName }
```

### Log file

`%PROGRAMDATA%\AvinashPrintBridge\print_bridge.log` (rotates). Every print, every
queue create/repair, and every startup heal is logged here.

---

## 8. How it works (developers)

- **Agent:** `print_bridge/print_bridge.py` (shipped as `print_bridge.exe`). A
  loopback-only HTTP server. Endpoints: `GET /ping`, `GET /printers`, `GET /diag`,
  `POST /print` (JSON `{printer, data_b64}`). It refuses any origin not in the
  allow-list (403) and binds `127.0.0.1` only.
- **Queue self-heal:** `_install_queue()` runs at every startup and on any print
  that hits a missing queue. It (1) stages the *Generic / Text Only* driver from the
  Windows inbox INF via `pnputil` if it's missing, and (2) finds the Epson's USB
  port — from an installed Epson printer if one exists, otherwise from the USBnnn
  port `usbprint.sys` assigned to the connected device (read from its registry Enum
  key, `-PresentOnly` so stale ports are ignored). This is what makes a fresh till
  work with no manual steps.
- **Raw datatype:** `write_raw()` opens the queue with the `RAW` datatype so no
  driver rendering touches the bytes.
- **Browser side:** `avinashgroup_app/public/js/print_bridge.js` probes the agent,
  routes raw formats to it (2 s timeout on probes, 60 s on a print so a first-print
  queue-heal isn't aborted), and shows a case-specific dialog when something is
  wrong instead of a generic error.
- **ESC/P generators:** `custom_code/printing/escp_*.py` build the byte streams,
  calibrated to the LQ-310's 8-inch head travel and the pre-printed forms.
- **Installer:** `print_bridge/installer.iss` (Inno Setup). CI
  (`.github/workflows/build-print-bridge.yml`) builds `PrintBridgeSetup.exe` on a
  Windows runner when a `print-bridge-vX.Y.Z` tag is pushed, and publishes a release
  with `make_latest: false`.

**Model note:** the layout is calibrated to the **LQ-310**. The transport (queue +
agent + raw ESC/P) works with any Epson dot-matrix on any till, but a *different
model* or *different stationery* may need position re-calibration in the ESC/P
generators.

---

## 9. Config reference

`%PROGRAMDATA%\AvinashPrintBridge\config.json` (created on first run):

```json
{
  "port": 8663,
  "default_printer": "LQ310-RAW",
  "allowed_origins": [
    "https://ng-group.raindropinc.com",
    "https://avinaslive1.raindropinc.com",
    "https://sandboxavinas-demo.raindropinc.com",
    "https://avinasdemo.raindropinc.com"
  ],
  "allow_local_test_origins": true
}
```

- `allowed_origins` — exact-match list of sites allowed to print. `["*"]` allows
  **any** site (use only on a dedicated single-purpose till).
- `allow_local_test_origins` — `true` also auto-accepts `localhost` / `127.*` /
  private-IP dev sites without listing them.

---

## 10. Adding a NEW site later

No reinstall needed:

1. Edit `%PROGRAMDATA%\AvinashPrintBridge\config.json` → add the `https://…` origin
   to `allowed_origins`.
2. Restart the agent (reboot, or start **Avinash Print Bridge** from the Start menu).
3. First print from that site, Chrome may ask **Allow local network** once.

To bake a new site into the installer for all future machines, add it to the
defaults in `print_bridge.py` and the browser-policy list in `installer.iss`, then
cut a new release.

---

## 11. Deploying an app / JS update (ERP server, developers)

The browser-side code (the routing, the error dialogs, the installer download link)
lives on the **ERP server**, not the till. After merging a change:

```bash
cd /path/to/frappe-bench/apps/avinashgroup_app
git pull
cd /path/to/frappe-bench
bench build --app avinashgroup_app
bench --site all clear-cache
bench restart
```

Then **hard-reload** (`Ctrl+Shift+R`) the browser on each till. Until this is done,
tills may keep running the old cached script (the *"signal is aborted"* symptom).

**Cutting a new agent/installer release:** bump `VERSION` in `print_bridge.py` and
`MyAppVersion` in `installer.iss`, update the download URL in `print_bridge.js` and
the docs, commit, then `git tag print-bridge-vX.Y.Z && git push <remote> vX.Y.Z`.
CI builds and publishes `PrintBridgeSetup.exe`.

---

## 12. Remote support via AnyDesk

Everything except the physical checks is doable over AnyDesk.

- **You can** drive all the PowerShell, the installer, browser printing, and read
  the logs remotely.
- **You cannot** confirm paper physically moved, or fix power/cable/paper — keep a
  person at the printer (any non-technical person) as your eyes and hands.
- **Set up first:** install AnyDesk as a service / enable **Request elevation** so
  UAC prompts (driver + printer install) are clickable remotely; set an
  **unattended-access** password so you can reconnect if the session drops.

---

## 13. Quick reference card

| Thing | Value |
|---|---|
| Agent address | `http://127.0.0.1:8663` (loopback only) |
| Queue name | `LQ310-RAW` (Generic / Text Only) |
| Autostart task | `Avinash Print Bridge` (boot + sign-in, SYSTEM) |
| Log | `%PROGRAMDATA%\AvinashPrintBridge\print_bridge.log` |
| Config | `%PROGRAMDATA%\AvinashPrintBridge\config.json` |
| Port-conflict note | `%PROGRAMDATA%\AvinashPrintBridge\PORT_CONFLICT.txt` |
| Health | `GET /ping`, full report `GET /diag` |
| Installer | Release **Print Bridge vX.Y.Z** → `PrintBridgeSetup.exe` (NOT "latest") |
| Fix most things | Epson on → **restart the PC** → reload the browser |

---

## Appendix — version history (highlights)

| Version | Change |
|---|---|
| **0.5.0** | Auto-creates `LQ310-RAW` even when the Epson's own driver was never installed: stages the Generic/Text Only driver via `pnputil`, and finds the USB port from the connected device. No manual PowerShell on a fresh till. |
| 0.4.1 | Don't abort a print that is still setting up the queue (60 s print timeout). |
| 0.4.0 | Self-diagnosis (`/diag`, `PORT_CONFLICT.txt`, case-specific browser dialogs). |
| 0.3.5 | Install without the Epson attached; queue creates itself on first print. |
| 0.3.4 | Autostart registered via `schtasks /XML` with boot **and** sign-in triggers (survives Fast-Startup shutdown). |

See also: `print_bridge/README.md` (design), `docs/print_bridge_deployment.md`,
`docs/print_bridge_windows_handover.md`, `docs/print_bridge_till_setup.md`.
