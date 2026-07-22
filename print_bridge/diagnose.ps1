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
# -LiveTest sends ONE real slip to the printer (Part B test) — it will come out
# between the client's invoices, so it asks for confirmation first:
#   powershell -ExecutionPolicy Bypass -File diagnose.ps1 -LiveTest

param([switch]$LiveTest)

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
# Cross-check queue port against the port the Epson actually owns
if ($q -and $usb) {
    $usbPorts = Get-WmiObject Win32_Printer | Where-Object { $_.Name -ne 'LQ310-RAW' -and $_.DriverName -match 'Epson|EPSON' } | Select-Object -ExpandProperty PortName
    if ($usbPorts -and ($q.PortName -notin $usbPorts) -and ($q.PortName -like 'USB*')) {
        V 'F3?' "LQ310-RAW is on '$($q.PortName)' but the Epson driver queue uses '$($usbPorts -join ',')' — likely stale port; restart PC (v0.5.0 self-heals) or Set-Printer -Name LQ310-RAW -PortName <correct USBnnn>"
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

Write-Host "`n=== VERDICT ===" -ForegroundColor Green
if ($verdicts) { $verdicts | ForEach-Object { Write-Host $_ -ForegroundColor Yellow } }
else {
    Write-Host "Everything below the queue looks HEALTHY." -ForegroundColor Green
    Write-Host "Re-run with -LiveTest: paper moves => fault is browser/ERP side (origin D1, LNA prompt D2, stale JS D3/D4, routing E1)."
}
Write-Host "`nCollect for escalation: this output + C:\ProgramData\AvinashPrintBridge\print_bridge.log + config.json"
