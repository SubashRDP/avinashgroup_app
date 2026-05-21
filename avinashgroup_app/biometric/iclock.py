"""ZKTeco ADMS push protocol handler.

Devices configured with Server Mode = ADMS push to /iclock/* on this server.
This module implements the subset needed to receive attendance:

    GET  /iclock/cdata?SN=<sn>&options=all   -> server config block
    POST /iclock/cdata?SN=<sn>&table=ATTLOG  -> tab-separated attendance rows
    GET  /iclock/getrequest?SN=<sn>          -> pending commands (none for now)
    GET  /iclock/ping?SN=<sn>                -> keepalive

Always returns plain-text 200 so a misbehaving device does not retry-storm.

Logs go to bench's logs/iclock.log — tail with:
    tail -f /home/dell/frappe-v15/logs/iclock.log
"""

import frappe
from werkzeug.wrappers import Response

from frappe.website.page_renderers.base_renderer import BaseRenderer
from avinashgroup_app.biometric.utils import (
	assert_known_device,
	process_attendance_records,
)

def _log():
	import logging

	logger = frappe.logger("iclock", allow_site=True, file_count=20)
	logger.setLevel(logging.INFO)
	return logger


class IclockRenderer(BaseRenderer):
	def can_render(self):
		return self.path == "iclock" or self.path.startswith("iclock/")

	def render(self):
		endpoint = self.path[len("iclock/"):] if self.path.startswith("iclock/") else ""
		method = frappe.local.request.method
		qs = frappe.local.request.query_string.decode("utf-8", errors="replace")
		sn = frappe.form_dict.get("SN", "-")

		log = _log()
		log.info("HIT %s /iclock/%s SN=%s qs=%s", method, endpoint, sn, qs)

		try:
			if endpoint == "cdata":
				return _handle_cdata(method, log)
			if endpoint == "getrequest":
				log.info("getrequest SN=%s -> OK (no pending commands)", sn)
				return _text("OK")
			if endpoint == "ping":
				log.info("ping SN=%s -> OK", sn)
				return _text("OK")
			if endpoint == "devicecmd":
				body = frappe.local.request.get_data(as_text=True)[:500]
				log.info("devicecmd SN=%s body=%r -> OK", sn, body)
				return _text("OK")
			if endpoint == "fdata":
				log.info("fdata SN=%s -> OK", sn)
				return _text("OK")
			log.warning("unknown endpoint /iclock/%s SN=%s -> OK", endpoint, sn)
			return _text("OK")
		except Exception:
			log.exception("handler error endpoint=%s SN=%s", endpoint, sn)
			frappe.log_error(
				title="ZKTeco ADMS handler error",
				message="endpoint={} qs={} body={}\n{}".format(
					endpoint,
					qs,
					frappe.local.request.get_data(as_text=True)[:2000],
					frappe.get_traceback(),
				),
			)
			# Acknowledge so the device clears its queue; we have the traceback in Error Log.
			return _text("OK")


def _text(body, status=200):
	if isinstance(body, str):
		body = body.encode("utf-8")
	return Response(body, status=status, mimetype="text/plain")


def _handle_cdata(method, log):
	sn = frappe.form_dict.get("SN", "")

	if method == "GET":
		log.info("cdata handshake SN=%s -> sending config block", sn)
		return _text(_config_block(sn))

	table = (frappe.form_dict.get("table") or frappe.form_dict.get("Table") or "").upper()
	raw = frappe.local.request.get_data(as_text=True) or ""

	log.info("cdata POST SN=%s table=%s body_bytes=%d", sn, table, len(raw))
	if raw:
		log.debug("cdata POST SN=%s raw=%r", sn, raw[:2000])

	if table == "ATTLOG":
		count = _process_attlog(raw, sn, log)
		frappe.db.commit()
		log.info("ATTLOG SN=%s synced=%d", sn, count)
		return _text("OK: {}".format(count))

	# OPERLOG, BIODATA, USER, FINGERPRINT, etc. — ack only for now.
	log.info("cdata SN=%s table=%s ignored (ack only)", sn, table)
	return _text("OK")


def _config_block(sn):
	# Stamp=9999 tells the device to upload everything it has on next push.
	return (
		"GET OPTION FROM: {sn}\n"
		"ATTLOGStamp=9999\n"
		"OperLogStamp=9999\n"
		"AttPhotoStamp=None\n"
		"ErrorDelay=30\n"
		"Delay=10\n"
		"TransTimes=00:00;14:05\n"
		"TransInterval=1\n"
		"TransFlag=TransData AttLog OpLog\n"
		"Realtime=1\n"
		"Encrypt=None\n"
	).format(sn=sn)


def _process_attlog(raw, sn, log):
	try:
		assert_known_device(sn)
	except frappe.PermissionError:
		log.warning("ATTLOG SN=%s rejected: device not registered or disabled", sn)
		return 0

	records = []
	skipped = 0
	for line in raw.splitlines():
		if not line.strip():
			continue
		parts = line.split("\t")
		if len(parts) < 2:
			skipped += 1
			continue
		user_id = parts[0].strip()
		timestamp = parts[1].strip()
		if not user_id or not timestamp:
			skipped += 1
			continue
		records.append({"user_id": user_id, "timestamp": timestamp})

	log.info("parsed ATTLOG SN=%s records=%d skipped=%d", sn, len(records), skipped)
	for r in records:
		log.info("  punch SN=%s user_id=%s ts=%s", sn, r["user_id"], r["timestamp"])

	if not records:
		return 0



	result = process_attendance_records(records, device_identifier=sn) or {}
	log.info(
		"process_attendance_records SN=%s synced=%s errors=%s details=%s",
		sn,
		result.get("synced"),
		result.get("errors"),
		(result.get("error_details") or [])[:5],
	)
	return result.get("synced", len(records))
