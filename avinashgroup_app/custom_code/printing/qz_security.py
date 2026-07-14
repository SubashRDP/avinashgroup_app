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
