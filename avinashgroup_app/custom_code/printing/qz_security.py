# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""QZ Tray request signing.

Frappe's raw-print integration sends UNSIGNED (anonymous) requests to QZ
Tray, so QZ prompts "Allow?" on every connection and the "Remember this
decision" checkbox has no identity to remember. These endpoints give the
site a signing certificate; public/js/qz_sign.js wires them into qz-tray.js.

Once requests are signed:
- QZ's "Remember this decision" works (identity = this certificate), and
- installing the certificate as QZ's override cert removes the prompt
  entirely:  sudo cp sites/<site>/qz-certificate.pem /opt/qz-tray/override.crt
  (Windows:  copy to "C:\\Program Files\\QZ Tray\\override.crt")

Setup per site (files live in the site folder, NOT in git):
  cd sites/<site> && openssl req -x509 -newkey rsa:2048 \
    -keyout qz-private-key.pem -out qz-certificate.pem -days 3650 -nodes \
    -subj "/CN=Avinash Group ERP/O=Avinash Group"
"""

import base64

import frappe


@frappe.whitelist()
def certificate() -> str:
	"""Public certificate PEM the browser hands to QZ Tray."""
	try:
		with open(frappe.get_site_path("qz-certificate.pem")) as f:
			return f.read()
	except FileNotFoundError:
		return ""


@frappe.whitelist()
def setup_bat():
	"""Downloadable Windows installer for the QZ override certificate.

	Give office users this URL (logged in):
	  /api/method/avinashgroup_app.custom_code.printing.qz_security.setup_bat
	They download install-qz-cert.bat and double-click it: the script
	re-launches itself as administrator, writes the site certificate to
	"C:\\Program Files\\QZ Tray\\override.crt" and restarts QZ Tray, after
	which prints from this site run with no Allow prompt.
	"""
	pem = certificate().strip()
	if not pem:
		frappe.throw("No qz-certificate.pem on this site — generate it first (see qz_security.py header).")

	echo_lines = "\r\n".join(f"echo {line}" for line in pem.splitlines())
	script = (
		"@echo off\r\n"
		f":: QZ Tray override certificate installer — {frappe.local.site}\r\n"
		":: Writes the ERP's signing certificate as QZ Tray's override cert so\r\n"
		":: prints from the site run without an Allow prompt.\r\n"
		"net session >nul 2>&1\r\n"
		"if %errorlevel% neq 0 (\r\n"
		"    echo Requesting administrator rights...\r\n"
		"    powershell -Command \"Start-Process -FilePath '%~f0' -Verb RunAs\"\r\n"
		"    exit /b\r\n"
		")\r\n"
		"set \"QZDIR=%ProgramFiles%\\QZ Tray\"\r\n"
		"if not exist \"%QZDIR%\" (\r\n"
		"    echo QZ Tray is not installed. Install it from https://qz.io/download first, then run this again.\r\n"
		"    pause\r\n"
		"    exit /b 1\r\n"
		")\r\n"
		"(\r\n"
		f"{echo_lines}\r\n"
		") > \"%QZDIR%\\override.crt\"\r\n"
		"taskkill /f /im qz-tray.exe >nul 2>&1\r\n"
		"start \"\" \"%QZDIR%\\qz-tray.exe\"\r\n"
		"echo.\r\n"
		"echo Done. QZ Tray restarted with the site certificate installed.\r\n"
		"pause\r\n"
	)

	frappe.response["type"] = "download"
	frappe.response["filename"] = "install-qz-cert.bat"
	frappe.response["filecontent"] = script
	frappe.response["content_type"] = "application/octet-stream"


@frappe.whitelist()
def setup_print_machine_bat():
	"""Downloadable ALL-IN-ONE Windows print-machine installer.

	Give office users this URL (logged in):
	  /api/method/avinashgroup_app.custom_code.printing.qz_security.setup_print_machine_bat
	They download setup-print-machine.bat and double-click it. The script
	re-launches itself as administrator and then:

	1. Installs QZ Tray (pinned v2.2.6, silent) if it is not installed —
	   downloaded from GitHub at run time; if the machine has no internet it
	   says so and continues with the remaining steps.
	2. Creates the LQ310-RAW printer queue (Generic / Text Only driver on the
	   Epson's own USB port). The stock Epson ESC/P V4 driver SWALLOWS
	   RAW-datatype jobs (spooler says "printed", head never moves) — the
	   Generic/Text Only queue is a pure byte-pipe, proven on the office
	   print machine 2026-07-15. Idempotent: skipped when the queue exists.
	3. Writes this site's signing certificate as QZ Tray's override.crt so
	   prints run with no Allow prompt (same as install-qz-cert.bat).
	4. Restarts QZ Tray so it sees both the certificate and the new printer
	   (it caches the printer list).

	After this, no per-browser step is needed: company_print.js falls back to
	the LQ310-RAW queue for raw formats when no explicit printer mapping is
	set in the Print view.
	"""
	pem = certificate().strip()
	if not pem:
		frappe.throw("No qz-certificate.pem on this site — generate it first (see qz_security.py header).")

	# PowerShell does the download/install/queue work; shipped -EncodedCommand
	# (base64 of UTF-16LE) so no quoting survives batch mangling.
	ps = (
		"$ErrorActionPreference='Continue';\n"
		"$qzDir = Join-Path $env:ProgramFiles 'QZ Tray';\n"
		"if (-not (Test-Path $qzDir)) {\n"
		"  Write-Host 'QZ Tray not found - downloading v2.2.6 (~90MB)...';\n"
		"  $exe = Join-Path $env:TEMP 'qz-tray-setup.exe';\n"
		"  try {\n"
		"    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;\n"
		"    Invoke-WebRequest -Uri 'https://github.com/qzind/tray/releases/download/v2.2.6/qz-tray-2.2.6-x86_64.exe' -OutFile $exe -UseBasicParsing;\n"
		"    Write-Host 'Installing QZ Tray silently...';\n"
		"    Start-Process -FilePath $exe -ArgumentList '/S' -Wait;\n"
		"    Write-Host 'QZ Tray installed.';\n"
		"  } catch {\n"
		"    Write-Host ('QZ Tray download/install FAILED: ' + $_.Exception.Message);\n"
		"    Write-Host 'Install it manually from https://qz.io/download then re-run this script.';\n"
		"  }\n"
		"} else { Write-Host 'QZ Tray already installed.' }\n"
		"$rawName = 'LQ310-RAW';\n"
		"try { Add-PrinterDriver -Name 'Generic / Text Only' } catch {}\n"
		"$epson = Get-Printer | Where-Object { $_.Name -like '*LQ-310*' -or $_.DriverName -like '*Epson*ESC/P*' } | Select-Object -First 1;\n"
		"$port = if ($epson) { $epson.PortName } else { 'USB002' };\n"
		"if (-not (Get-Printer -Name $rawName -ErrorAction SilentlyContinue)) {\n"
		"  try {\n"
		"    Add-Printer -Name $rawName -DriverName 'Generic / Text Only' -PortName $port;\n"
		"    Write-Host ('Created printer ' + $rawName + ' on port ' + $port);\n"
		"  } catch { Write-Host ('Could not create ' + $rawName + ': ' + $_.Exception.Message) }\n"
		"} else { Write-Host ($rawName + ' queue already exists.') }\n"
		"Get-Printer -Name $rawName -ErrorAction SilentlyContinue | Format-Table Name,DriverName,PortName -AutoSize | Out-String | Write-Host;\n"
	)
	encoded = base64.b64encode(ps.encode("utf-16-le")).decode()

	echo_lines = "\r\n".join(f"echo {line}" for line in pem.splitlines())
	script = (
		"@echo off\r\n"
		f":: All-in-one print machine setup — {frappe.local.site}\r\n"
		":: QZ Tray (if missing) + LQ310-RAW raw queue + QZ override certificate.\r\n"
		"net session >nul 2>&1\r\n"
		"if %errorlevel% neq 0 (\r\n"
		"    echo Requesting administrator rights...\r\n"
		"    powershell -Command \"Start-Process -FilePath '%~f0' -Verb RunAs\"\r\n"
		"    exit /b\r\n"
		")\r\n"
		"echo === Step 1-2: QZ Tray + LQ310-RAW queue ===\r\n"
		f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}\r\n"
		"set \"QZDIR=%ProgramFiles%\\QZ Tray\"\r\n"
		"if not exist \"%QZDIR%\" (\r\n"
		"    echo QZ Tray still missing - skipping certificate install. Re-run after installing QZ Tray.\r\n"
		"    pause\r\n"
		"    exit /b 1\r\n"
		")\r\n"
		"echo === Step 3: site certificate as override.crt ===\r\n"
		"(\r\n"
		f"{echo_lines}\r\n"
		") > \"%QZDIR%\\override.crt\"\r\n"
		"echo === Step 4: restarting QZ Tray ===\r\n"
		"taskkill /f /im qz-tray.exe >nul 2>&1\r\n"
		"start \"\" \"%QZDIR%\\qz-tray.exe\"\r\n"
		"echo.\r\n"
		"echo Done. This machine can now print invoices: QZ Tray trusted, LQ310-RAW queue ready.\r\n"
		"echo No browser setup needed - raw invoice formats print via LQ310-RAW automatically.\r\n"
		"pause\r\n"
	)

	frappe.response["type"] = "download"
	frappe.response["filename"] = "setup-print-machine.bat"
	frappe.response["filecontent"] = script
	frappe.response["content_type"] = "application/octet-stream"


@frappe.whitelist()
def sign(request: str) -> str:
	"""SHA512-RSA signature (base64) of QZ's to-sign payload."""
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import padding

	try:
		with open(frappe.get_site_path("qz-private-key.pem"), "rb") as f:
			key = serialization.load_pem_private_key(f.read(), password=None)
	except FileNotFoundError:
		return ""
	signature = key.sign(request.encode(), padding.PKCS1v15(), hashes.SHA512())
	return base64.b64encode(signature).decode()
