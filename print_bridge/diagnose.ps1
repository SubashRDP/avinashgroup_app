# Print Bridge field diagnostic — paste whole file into PowerShell on the client PC.
#
# READ-ONLY: observation only (Get-*, netstat, GET /diag). It changes NOTHING and
# is safe to run while the client is actively printing.
#
# The VERDICT lines may SUGGEST fix commands (Remove-Printer, Remove-PrintJob,
# Restart-Service Spooler, reboot). Those are NOT run by this script — and you
# must NOT run them while invoices are flowing: they kill in-flight jobs.
# Wait for a pause between invoices, or do them off-hours.
#
# Codes (F2, F3, Q1, ...) map to docs/print_bridge_troubleshooting_handover.md.
# Since 0.5.2 this ships with the installer: double-click
#   C:\Program Files\AvinashPrintBridge\diagnose.bat  (also in the Start menu)
#
# Optional deeper tests — each prints ONE test line and asks for a typed YES
# first, so run them in a gap between the client's invoices:
#   -LiveTest      agent -> queue -> printer   (the path the ERP uses)
#   -WindowsTest   Windows -> queue -> printer (no agent; isolates the queue)

param([switch]$LiveTest, [switch]$WindowsTest)

$verdicts = @()
function V($code, $msg) { $script:verdicts += "[$code] $msg" }

Write-Host "=== 1. Agent (print_bridge.exe) ===" -ForegroundColor Cyan
$proc = Get-Process print_bridge -ErrorAction SilentlyContinue
if ($proc) { Write-Host "running, PID $($proc.Id)" }
else       { Write-Host "NOT RUNNING" -ForegroundColor Red }

$diag = $null
try {
    $diag = (Invoke-RestMethod 'http://127.0.0.1:8663/diag' -Headers @{Origin='http://localhost'} -TimeoutSec 5).diag
    $diag | ConvertTo-Json -Depth 4 | Write-Host
    if ([version]$diag.version -lt [version]'0.5.0') { V 'G5' "agent v$($diag.version) is old — reinstall v0.5.0" }
    if ($diag.default_printer -ne 'LQ310-RAW') { V 'A2' "default_printer is '$($diag.default_printer)', not LQ310-RAW — config.json was edited" }
    if (-not $diag.queue_exists) {
        if ($diag.epson_seen) { V 'Q1' "queue missing though Epson is seen — reboot so the SYSTEM task recreates it (elevated=$($diag.elevated))" }
        else                  { V 'Q2' "queue missing AND no Epson seen — check USB/power first" }
    }
} catch {
    if ($proc) { V 'G4' "agent runs but 8663 does not answer — check PORT_CONFLICT.txt / firewall (D5)" }
    else       { V 'G1/G2' "agent not installed or not started — Start menu > Avinash Print Bridge, then reboot" }
    $own = netstat -ano | Select-String ':8663.*LISTENING'
    if ($own) { Write-Host "port 8663 owner: $own" -ForegroundColor Yellow }
}

Write-Host "`n=== 1b. Config + log (the flight recorder) ===" -ForegroundColor Cyan
$cfgPath = 'C:\ProgramData\AvinashPrintBridge\config.json'
if (Test-Path $cfgPath) {
    $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
    Write-Host "config: default_printer='$($cfg.default_printer)' port=$($cfg.port)"
    if ($cfg.default_printer -and $cfg.default_printer -ne 'LQ310-RAW') {
        V 'A2' "config.json default_printer is '$($cfg.default_printer)' — if that queue uses the Epson driver, every job is SILENTLY SWALLOWED (green toast, no paper) while LQ310-RAW sits unused. Fix: edit $cfgPath to ""LQ310-RAW"", restart the agent"
    }
} else { Write-Host "no config.json — defaults in use (LQ310-RAW)" }
$logPath = 'C:\ProgramData\AvinashPrintBridge\print_bridge.log'
if (Test-Path $logPath) {
    # Every green toast in the ERP leaves exactly one of these lines: the queue
    # the job REALLY went to, and the Windows job id.
    $printed = Select-String -Path $logPath -Pattern 'printed \d+ bytes to' | Select-Object -Last 5
    if ($printed) {
        Write-Host "last raw jobs the agent handled:"
        $printed | ForEach-Object { Write-Host "  $($_.Line)" }
        if ($printed | Where-Object { $_.Line -notmatch "to 'LQ310-RAW'" }) {
            V 'A2' "the agent has been printing to a queue OTHER than LQ310-RAW (log lines above) — those jobs likely died in the Epson driver"
        }
    } else {
        Write-Host "no 'printed ... bytes' lines — NO raw print has ever reached this agent."
        Write-Host "If the ERP shows green toasts anyway, they are from a different machine/agent." -ForegroundColor Yellow
    }
    Write-Host "log tail:"
    Get-Content $logPath -Tail 8 | ForEach-Object { Write-Host "  $_" }
} else { Write-Host "no log file — the agent has never run on this machine" }

Write-Host "`n=== 2. Queue LQ310-RAW ===" -ForegroundColor Cyan
$q = Get-Printer -Name 'LQ310-RAW' -ErrorAction SilentlyContinue
if ($q) {
    $q | Select-Object Name, DriverName, PortName, PrinterStatus | Format-List | Out-String | Write-Host
    # THE prime suspect for "printer fine, software kills the job":
    if ($q.DriverName -ne 'Generic / Text Only') {
        V 'F2' "queue driver is '$($q.DriverName)' — the Epson driver SILENTLY SWALLOWS raw jobs. Fix (ONLY when printing is idle): Remove-Printer -Name LQ310-RAW ; restart PC (agent rebuilds it on Generic / Text Only)"
    }
    if ($q.PrinterStatus -in 'Paused','Offline') { V 'F4' "queue is $($q.PrinterStatus) — resume it (uncheck Pause Printing / Use Printer Offline)" }
    if ($q.PortName -match 'PORTPROMPT|FILE|XPS') { V 'F3' "queue port is '$($q.PortName)' — not a real printer port" }
} else { Write-Host "queue does not exist" -ForegroundColor Red }

Write-Host "`n=== 3. Stuck jobs ===" -ForegroundColor Cyan
$jobs = Get-PrintJob -PrinterName 'LQ310-RAW' -ErrorAction SilentlyContinue
if ($jobs) {
    $jobs | Select-Object Id, DocumentName, JobStatus, SubmittedTime | Format-Table | Out-String | Write-Host
    V 'F4/F1' "$(@($jobs).Count) job(s) in queue — stuck (printer offline/port dead) OR simply mid-print. Watch 30s: if the count never drops, they're stuck. Clearing (Remove-PrintJob) DELETES unprinted invoices — only when confirmed stuck and printing is idle"
} else { Write-Host "queue empty (jobs are draining — or never arriving)" }

Write-Host "`n=== 4. Epson on USB (VID_04B8) ===" -ForegroundColor Cyan
$usb = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object InstanceId -like 'USB\VID_04B8*'
if ($usb) { $usb | Select-Object FriendlyName, Status, InstanceId | Format-Table | Out-String | Write-Host }
else {
    Write-Host "no Epson USB device present" -ForegroundColor Red
    V 'F1c' "Windows does not see the Epson — reseat USB (direct port, no hub), power-cycle printer"
}
# Cross-check queue port against the port(s) a PRESENT USB printer actually owns
# (usbprint.sys records each connected device's USBnnn under its Enum key).
$presentPorts = @()
$pdevs = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.InstanceId -like 'USBPRINT\*' -or $_.InstanceId -like 'USB\VID_04B8*' }
foreach ($d in $pdevs) {
    $pn = (Get-ItemProperty -Path ('HKLM:\SYSTEM\CurrentControlSet\Enum\' + $d.InstanceId + '\Device Parameters') -Name PortName -ErrorAction SilentlyContinue).PortName
    if ($pn) { $presentPorts += $pn }
}
if ($presentPorts) {
    Write-Host "live USB printer port(s): $($presentPorts -join ', ')"
    if ($q -and $q.PortName -like 'USB*' -and $q.PortName -notin $presentPorts) {
        V 'F3' "LQ310-RAW is on '$($q.PortName)' but the live printer owns '$($presentPorts -join ',')' — stale port; restart PC (agent self-heals) or Set-Printer -Name LQ310-RAW -PortName $($presentPorts[0])"
    }
    # Stale Epson queues (dead USBnnn ports) don't block printing, but pre-0.5.2
    # agents copy the FIRST Epson queue's port — a stale one can hijack the heal.
    $stale = Get-Printer -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -ne 'LQ310-RAW' -and $_.DriverName -match 'EPSON|Epson' -and
        $_.PortName -like 'USB*' -and $_.PortName -notin $presentPorts }
    if ($stale) {
        V 'DEBRIS' "stale Epson queue(s) on dead ports: $(($stale | ForEach-Object { $_.Name + ' @ ' + $_.PortName }) -join ', ') — can mislead a pre-0.5.2 self-heal. When printing is idle AND the client app is confirmed NOT using these queue names: Remove-Printer -Name '<name>'"
    }
}

Write-Host "`n=== 5. Spooler ===" -ForegroundColor Cyan
$sp = Get-Service Spooler
Write-Host "Spooler: $($sp.Status)"
if ($sp.Status -ne 'Running') { V 'F5' "Print Spooler is $($sp.Status) — Restart-Service Spooler (as admin; note: a spooler restart drops queued jobs machine-wide)" }

if ($LiveTest -and $q) {
    Write-Host "`n=== 6. LIVE TEST — raw bytes straight to the queue (paper should move) ===" -ForegroundColor Cyan
    Write-Host "This prints ONE real test slip. If the client is mid-invoice, wait for a gap." -ForegroundColor Yellow
    $go = Read-Host "Type YES to send the test slip now"
    if ($go -ne 'YES') { Write-Host "skipped."; $LiveTest = $false }
}
if ($LiveTest -and $q) {
    try {
        $raw  = [Text.Encoding]::GetEncoding('ISO-8859-1').GetBytes("`e@PRINT BRIDGE OK`r`n`r`n`r`n")
        $body = @{ printer='LQ310-RAW'; data_b64=[Convert]::ToBase64String($raw) } | ConvertTo-Json
        $r = Invoke-RestMethod 'http://127.0.0.1:8663/print' -Method POST `
            -Headers @{Origin='https://ng-group.raindropinc.com'} -ContentType 'application/json' -Body $body
        Write-Host "agent replied: $($r | ConvertTo-Json -Compress)"
        Write-Host "LOOK AT THE PRINTER NOW. Slip printed => queue+printer fine, fault is browser/ERP (Part D). 'ok' but no paper => F2/F3/F4/F1." -ForegroundColor Yellow
    } catch { Write-Host "live test failed: $_" -ForegroundColor Red }
}

if ($WindowsTest -and $q) {
    Write-Host "`n=== 7. WINDOWS TEST — one line via Windows' own path (no agent) ===" -ForegroundColor Cyan
    Write-Host "This prints ONE test line. If the client is mid-invoice, wait for a gap." -ForegroundColor Yellow
    $go = Read-Host "Type YES to send the Windows test line now"
    if ($go -eq 'YES') {
        'PRINT TEST VIA WINDOWS' | Out-Printer -Name 'LQ310-RAW'
        Write-Host "sent. Paper moved => queue+port+printer are fine." -ForegroundColor Yellow
        Write-Host "Triangulate with -LiveTest: agent slip fails but this prints => agent-side; BOTH silent => queue/port/printer (F3/F4/F1)."
    } else { Write-Host "skipped." }
}

Write-Host "`n=== VERDICT ===" -ForegroundColor Green
if ($verdicts) { $verdicts | ForEach-Object { Write-Host $_ -ForegroundColor Yellow } }
else {
    Write-Host "Everything below the queue looks HEALTHY." -ForegroundColor Green
    Write-Host "Re-run with -LiveTest: paper moves => fault is browser/ERP side (origin D1, LNA prompt D2, stale JS D3/D4, routing E1)."
}
Write-Host "`nCollect for escalation: this output + C:\ProgramData\AvinashPrintBridge\print_bridge.log + config.json"
