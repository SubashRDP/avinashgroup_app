# Print Bridge — Windows install & verification handover

**Read this on the Windows print machine (the till with the Epson LQ-310).**
It is written so a person *or* a Claude Code session on that machine can run it
end-to-end and report a pass/fail for each of the four sites.

## Goal being verified

> With **one** installation, all **4** ERP sites print raw dot-matrix invoices,
> with **no other software** installed, and printing is **fast**.

The four sites (already baked into the agent's allow-list and the browser policy
in v0.2.0 — nothing to configure):

| # | Site URL |
|---|---|
| 1 | https://ng-group.raindropinc.com  (production, all 7 companies) |
| 2 | https://avinaslive1.raindropinc.com |
| 3 | https://sandboxavinas-demo.raindropinc.com |
| 4 | https://avinasdemo.raindropinc.com |

## What is already proven (so you can trust the parts below)

On a real Windows runner in CI, the built `print_bridge.exe` was verified to:
start, accept all 4 origins (HTTP 200), encode a print job **byte-exact**
(including a `0xB0` byte QZ Tray used to mangle), and refuse foreign origins
(403). The **only** thing CI could not do is move a physical printer head — that
is what this handover confirms.

---

## Step 1 — Install (once)

1. **Attach the Epson LQ-310 and switch it ON first.** The installer creates the
   print queue on the printer's own port and will warn if it can't find it.
2. Download **`PrintBridgeSetup.exe`** (v0.2.0 or newer) from the release page:
   https://github.com/SubashRDP/avinashgroup_app/releases/tag/print-bridge-v0.2.0
3. Run it, accept the UAC (admin) prompt. Finish the wizard.

That is the whole install. **No QZ Tray, no certificate, no browser setup.**

## Step 2 — Automated self-check (PowerShell)

Open **PowerShell** and paste this whole block. It checks the agent, the print
queue, the browser policy for all 4 origins, and does a live loopback print test.
It prints `PASS`/`FAIL` per check.

```powershell
$ErrorActionPreference = 'Continue'
$origins = @(
  'https://ng-group.raindropinc.com',
  'https://avinaslive1.raindropinc.com',
  'https://sandboxavinas-demo.raindropinc.com',
  'https://avinasdemo.raindropinc.com'
)
function Ok($b,$m){ if($b){Write-Host "PASS  $m" -f Green}else{Write-Host "FAIL  $m" -f Red} }

# 1. Agent process / login task
$task = schtasks /Query /TN "Avinash Print Bridge" 2>$null
Ok ($LASTEXITCODE -eq 0) "login task 'Avinash Print Bridge' registered"

# 2. Agent answering on the loopback port
try { $p = Invoke-RestMethod 'http://127.0.0.1:8663/ping' -Headers @{Origin=$origins[0]} }
catch { $p = $null }
Ok ($p -and $p.ok) "agent answers on 127.0.0.1:8663 (version $($p.version))"

# 3. LQ310-RAW queue exists (Generic / Text Only)
$q = Get-Printer -Name 'LQ310-RAW' -ErrorAction SilentlyContinue
Ok ($q -ne $null) "LQ310-RAW queue exists (driver: $($q.DriverName), port: $($q.PortName))"

# 4. Every origin accepted by the agent
foreach ($o in $origins) {
  try { $r = Invoke-WebRequest "http://127.0.0.1:8663/ping" -Headers @{Origin=$o} -UseBasicParsing; $code=$r.StatusCode }
  catch { $code = $_.Exception.Response.StatusCode.value__ }
  Ok ($code -eq 200) "origin accepted: $o"
}

# 5. Browser policy pre-grants each origin (Chrome + Edge)
foreach ($br in 'Google\Chrome','Microsoft\Edge') {
  $key = "HKLM:\SOFTWARE\Policies\$br\LocalNetworkAccessAllowedForUrls"
  $vals = @()
  if (Test-Path $key) { $p2 = Get-ItemProperty $key; $vals = $p2.PSObject.Properties | ? {$_.Name -match '^\d+$'} | % {$_.Value} }
  foreach ($o in $origins) { Ok ($vals -contains $o) "$br policy has $o" }
}

# 6. LIVE PHYSICAL PRINT — this actually moves the Epson head
$raw   = [Text.Encoding]::GetEncoding('ISO-8859-1').GetBytes("`e@PRINT BRIDGE OK - all 4 sites`r`n`r`n`r`n")
$body  = @{ printer='LQ310-RAW'; data_b64=[Convert]::ToBase64String($raw) } | ConvertTo-Json
try { $pr = Invoke-RestMethod 'http://127.0.0.1:8663/print' -Method POST -Headers @{Origin=$origins[0]} -ContentType 'application/json' -Body $body }
catch { $pr = $null }
Ok ($pr -and $pr.ok) "live print sent to Epson ($($pr.bytes) bytes) — CHECK THAT PAPER MOVED"
```

**The last check is the real one:** a slip should physically come out of the
Epson. If the checks are green but no paper moves, see Troubleshooting.

## Step 3 — Per-site browser print (the actual user workflow)

For **each** of the 4 URLs:

1. Open it in Chrome or Edge, log in.
2. Open an invoice → **Print** → pick a raw / dot-matrix format.
3. Expect a green toast **"Printing via LQ310-RAW"**, the Epson prints, and
   **no "Allow local network" prompt** appears.

Tick each one:

- [ ] https://ng-group.raindropinc.com prints
- [ ] https://avinaslive1.raindropinc.com prints
- [ ] https://sandboxavinas-demo.raindropinc.com prints
- [ ] https://avinasdemo.raindropinc.com prints

If all four print from the single install → **goal met.**

## Step 4 — Report back

Send back:
1. The PASS/FAIL output from Step 2.
2. Whether paper physically moved on the Step 2 live print.
3. The 4 tick-boxes from Step 3 (which sites printed, which didn't).
4. If anything failed: the log file
   **`%LOCALAPPDATA%\AvinashPrintBridge\print_bridge.log`**.

---

## Troubleshooting

Log: `%LOCALAPPDATA%\AvinashPrintBridge\print_bridge.log`

| Symptom | Cause / fix |
|---|---|
| Installer said the queue couldn't be created | Epson not attached / powered off during install. Connect + power on, re-run `PrintBridgeSetup.exe`. |
| Step 2 check 3 (LQ310-RAW) FAIL | Same as above — the queue was never made. Re-run installer with the printer on. |
| Live print PASS but no paper | Job reached the queue but not the printer: check the Epson is online/has paper; confirm `LQ310-RAW` port matches the Epson's USB port (`Get-Printer LQ310-RAW`). |
| A site shows "Allow local network" prompt | Policy key missing for that origin (Step 5 FAIL). Click **Allow** once (Chrome remembers), or re-run the installer. |
| A site does nothing / old QZ behaviour | Agent not running: start **Avinash Print Bridge** from the Start menu, or sign out/in to trigger the login task. |
| Need a NEW site to print later | Edit `%LOCALAPPDATA%\AvinashPrintBridge\config.json` → add its `https://…` origin to `allowed_origins`, restart the agent. No reinstall. |

## Config reference

`%LOCALAPPDATA%\AvinashPrintBridge\config.json` (created on first run):

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

- `["*"]` in `allowed_origins` = allow **any** site (only for a dedicated till).
- `allow_local_test_origins: true` = also auto-accept `localhost` / `127.*` /
  private-IP dev sites without listing them.

See also `print_bridge/README.md` (design) and `docs/print_bridge_deployment.md`.
