@echo off
rem Avinash Print Bridge — field diagnostic. Double-click to run. READ-ONLY:
rem it changes nothing and is safe while the client is printing invoices.
rem
rem Fix commands it SUGGESTS in the VERDICT are a different story — never run
rem those while invoices are flowing.
rem
rem Optional deeper tests (each prints ONE test line, asks for a typed YES):
rem   diagnose.bat -LiveTest      agent -> queue -> printer  (the ERP's path)
rem   diagnose.bat -WindowsTest   Windows -> queue -> printer (no agent)
rem
rem %~dp0 = this script's folder, so it works from the install dir, a USB
rem stick, or a Downloads folder alike — diagnose.ps1 must sit next to it.
rem Full path to powershell.exe: it is NOT in System32 itself, so the bare name
rem depends on PATH — and one till already shipped with a PATH that lost it.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnose.ps1" %*
echo.
pause
