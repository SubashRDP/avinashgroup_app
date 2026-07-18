"""Avinash Print Bridge — loopback agent that pipes raw ESC/P to a Windows queue.

Replaces QZ Tray for raw printing. The ERP already renders the ESC/P byte
stream server-side (custom_code/printing/escp_*.py); QZ Tray was only carrying
those bytes the last hop from browser to printer, and charged a high price for
it: an Allow prompt on every session, a signing certificate, an override.crt to
install per machine, and a 90MB installer.

None of that applies here. QZ Tray prompts because it is a *generic* bridge —
any site on the internet may connect to it, so it must ask. This agent answers
to one origin (see ALLOWED_ORIGINS / config.json) and refuses every other, so
there is nothing to prompt about and no certificate to trust.

Browser rules for an HTTPS page talking to 127.0.0.1:
  - Mixed content: exempt. Chrome and Firefox 55+ both treat loopback as
    potentially trustworthy. Use the IP literal, NOT "localhost" — Firefox only
    exempted the localhost *name* in 84, but 127.0.0.1 works back to 55.
  - Chrome <=141: sends a Private Network Access preflight; we answer it with
    Access-Control-Allow-Private-Network.
  - Chrome 142+: Local Network Access permission. Pre-granted by registry policy
    (LocalNetworkAccessAllowedForUrls) at install; without it the user clicks
    once per origin and Chrome remembers.
  - Firefox: has not shipped LNA/PNA. Nothing to configure.

Transport is base64 of the exact bytes. QZ Tray UTF-8-encoded the command
string, which mangled any byte over 127 and forced escp_invoice.py to avoid
ESC $ positioning and cap ESC J feeds at 127 (see _h/_feed_to there). Exact
bytes lift that constraint.
"""

import base64
import json
import logging
import os
import platform
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler

VERSION = "0.1.0"

IS_WINDOWS = platform.system() == "Windows"
DEFAULT_PORT = 8663
DEFAULT_PRINTER = "LQ310-RAW"
DEFAULT_ORIGINS = ["https://ng-group.raindropinc.com"]

# --dry-run writes jobs to disk instead of a printer, so the HTTP/CORS layer can
# be exercised off-Windows.
DRY_RUN = "--dry-run" in sys.argv[1:]


def _app_dir() -> str:
	if IS_WINDOWS:
		base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
		d = os.path.join(base, "AvinashPrintBridge")
	else:
		d = os.path.join(os.path.expanduser("~"), ".avinash_print_bridge")
	os.makedirs(d, exist_ok=True)
	return d


APP_DIR = _app_dir()
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
LOG_FILE = os.path.join(APP_DIR, "print_bridge.log")

log = logging.getLogger("print_bridge")
log.setLevel(logging.INFO)
_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
log.addHandler(_handler)
# PyInstaller --noconsole leaves sys.stdout as None, and StreamHandler(None)
# blows up on the first log call — i.e. at startup, on every machine.
if sys.stdout is not None:
	log.addHandler(logging.StreamHandler(sys.stdout))


def load_config() -> dict:
	cfg = {
		"port": DEFAULT_PORT,
		"default_printer": DEFAULT_PRINTER,
		"allowed_origins": list(DEFAULT_ORIGINS),
	}
	try:
		with open(CONFIG_FILE) as f:
			cfg.update(json.load(f))
	except FileNotFoundError:
		with open(CONFIG_FILE, "w") as f:
			json.dump(cfg, f, indent=2)
		log.info("wrote default config to %s", CONFIG_FILE)
	except (OSError, ValueError) as e:
		log.warning("bad config %s (%s) — using defaults", CONFIG_FILE, e)
	return cfg


CONFIG = load_config()


def list_printers() -> list:
	if not IS_WINDOWS:
		return [DEFAULT_PRINTER] if DRY_RUN else []
	import win32print

	flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
	return [p[2] for p in win32print.EnumPrinters(flags, None, 1)]


def write_raw(printer: str, data: bytes) -> None:
	"""Send bytes to a print queue with the RAW datatype (no driver rendering).

	RAW matters: the stock Epson ESC/P V4 driver swallows RAW jobs — the spooler
	reports success and the head never moves — which is why the queue is a
	Generic / Text Only one. That queue is a pure byte pipe.
	"""
	if DRY_RUN:
		path = os.path.join(APP_DIR, "dryrun_last_job.bin")
		with open(path, "wb") as f:
			f.write(data)
		log.info("[dry-run] %d bytes for %r -> %s", len(data), printer, path)
		return

	import win32print

	h = win32print.OpenPrinter(printer)
	try:
		job = win32print.StartDocPrinter(h, 1, ("Avinash ERP invoice", None, "RAW"))
		try:
			win32print.StartPagePrinter(h)
			win32print.WritePrinter(h, data)
			win32print.EndPagePrinter(h)
		finally:
			win32print.EndDocPrinter(h)
		log.info("printed %d bytes to %r (job %s)", len(data), printer, job)
	finally:
		win32print.ClosePrinter(h)


class Handler(BaseHTTPRequestHandler):
	server_version = f"AvinashPrintBridge/{VERSION}"

	def log_message(self, fmt, *a):  # noqa: A002 - stdlib signature
		log.info("%s - %s", self.address_string(), fmt % a)

	def _origin_ok(self) -> str:
		"""Return the request Origin if allowed, else ''.

		This is the whole security model, so it is an exact match — no
		prefix/suffix matching that "https://ng-group.raindropinc.com.evil.com"
		could satisfy. Requests carrying a JSON content-type are preflighted by
		the browser, so a disallowed origin never reaches _print().
		"""
		origin = self.headers.get("Origin", "")
		return origin if origin in CONFIG["allowed_origins"] else ""

	def _cors(self, origin: str, preflight: bool = False) -> None:
		self.send_header("Access-Control-Allow-Origin", origin)
		self.send_header("Vary", "Origin")
		if preflight:
			self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
			self.send_header("Access-Control-Allow-Headers", "Content-Type")
			# Chrome <=141 PNA preflight. Harmless elsewhere; Chrome 142+ uses
			# the LNA permission instead.
			self.send_header("Access-Control-Allow-Private-Network", "true")
			self.send_header("Access-Control-Max-Age", "86400")

	def _json(self, code: int, payload: dict, origin: str = "") -> None:
		body = json.dumps(payload).encode()
		self.send_response(code)
		if origin:
			self._cors(origin)
		self.send_header("Content-Type", "application/json")
		self.send_header("Content-Length", str(len(body)))
		self.end_headers()
		self.wfile.write(body)

	def do_OPTIONS(self) -> None:
		origin = self._origin_ok()
		if not origin:
			self.send_response(403)
			self.end_headers()
			return
		self.send_response(204)
		self._cors(origin, preflight=True)
		self.send_header("Content-Length", "0")
		self.end_headers()

	def do_GET(self) -> None:
		origin = self._origin_ok()
		if not origin:
			self._json(403, {"ok": False, "error": "origin not allowed"})
			return
		if self.path == "/ping":
			self._json(
				200,
				{"ok": True, "version": VERSION, "default_printer": CONFIG["default_printer"]},
				origin,
			)
		elif self.path == "/printers":
			try:
				self._json(200, {"ok": True, "printers": list_printers()}, origin)
			except Exception as e:
				log.exception("printer enumeration failed")
				self._json(500, {"ok": False, "error": str(e)}, origin)
		else:
			self._json(404, {"ok": False, "error": "not found"}, origin)

	def do_POST(self) -> None:
		origin = self._origin_ok()
		if not origin:
			self._json(403, {"ok": False, "error": "origin not allowed"})
			return
		if self.path != "/print":
			self._json(404, {"ok": False, "error": "not found"}, origin)
			return
		try:
			length = int(self.headers.get("Content-Length") or 0)
			req = json.loads(self.rfile.read(length) or b"{}")
			data = base64.b64decode(req["data_b64"], validate=True)
		except (ValueError, KeyError, TypeError) as e:
			self._json(400, {"ok": False, "error": f"bad request: {e}"}, origin)
			return

		printer = req.get("printer") or CONFIG["default_printer"]
		try:
			write_raw(printer, data)
		except Exception as e:
			log.exception("print failed on %r", printer)
			self._json(500, {"ok": False, "error": str(e), "printer": printer}, origin)
			return
		self._json(200, {"ok": True, "bytes": len(data), "printer": printer}, origin)


# -------------------------------------------------------------- configure ----
# Machine setup that needs real logic: find the Epson, create the RAW queue.
# Everything static — installing the exe, the autostart task, shortcuts, the
# browser policy, uninstall — belongs to Inno Setup (installer.iss), which does
# it declaratively and reverses it on uninstall. Two owners for one step would
# only fight each other.
#
# Kept out of a base64 PowerShell blob on purpose: that is what made the old QZ
# installer impossible to debug, and it still printed "Done." when it failed.


def _run(args: list) -> tuple:
	import subprocess

	p = subprocess.run(args, capture_output=True, text=True, shell=False)
	return p.returncode, (p.stdout or "") + (p.stderr or "")


def _step(results: list, name: str, fn) -> None:
	try:
		detail = fn()
		results.append((True, name, detail or "ok"))
		log.info("[ok]   %s — %s", name, detail or "ok")
	except Exception as e:
		results.append((False, name, str(e)))
		log.error("[FAIL] %s — %s", name, e)


def _install_queue() -> str:
	"""Create the Generic / Text Only RAW queue on the Epson's port.

	-ErrorAction Stop matters: Add-Printer raises NON-terminating errors, so
	without it a failure is invisible and the caller reports success.
	"""
	if DEFAULT_PRINTER in list_printers():
		return f"{DEFAULT_PRINTER} already exists"
	ps = (
		"$ErrorActionPreference='Stop';"
		"try { Add-PrinterDriver -Name 'Generic / Text Only' -ErrorAction Stop } catch {};"
		"$p = Get-Printer | Where-Object { $_.Name -like '*LQ-310*' -or $_.DriverName -like '*Epson*' } | Select-Object -First 1;"
		"if (-not $p) { throw 'No Epson dot-matrix printer found — attach and power it on, then re-run.' };"
		f"Add-Printer -Name '{DEFAULT_PRINTER}' -DriverName 'Generic / Text Only' -PortName $p.PortName -ErrorAction Stop;"
		f"Write-Output ('created on ' + $p.PortName)"
	)
	rc, out = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps])
	if rc != 0:
		raise RuntimeError(out.strip() or "Add-Printer failed")
	return out.strip()


def configure() -> int:
	"""Create the RAW queue. Called by installer.iss at post-install.

	Exit code is the contract: installer.iss checks it and shows the user a real
	message pointing at the log, instead of claiming success regardless.
	"""
	if not IS_WINDOWS:
		print("--configure is Windows-only.")
		return 1
	results = []
	_step(results, f"{DEFAULT_PRINTER} print queue", _install_queue)
	return 0 if all(ok for ok, _, _ in results) else 1


def main() -> None:
	if "--configure" in sys.argv[1:]:
		sys.exit(configure())
	port = int(CONFIG["port"])
	log.info(
		"Avinash Print Bridge %s starting on 127.0.0.1:%d (dry_run=%s, origins=%s)",
		VERSION,
		port,
		DRY_RUN,
		", ".join(CONFIG["allowed_origins"]),
	)
	# Bind loopback only — never 0.0.0.0. Nothing off this machine may print.
	ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
	main()
