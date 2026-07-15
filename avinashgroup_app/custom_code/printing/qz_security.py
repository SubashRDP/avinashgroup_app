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
