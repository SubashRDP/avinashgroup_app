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
import ipaddress
import json
import logging
import os
import platform
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from urllib.parse import urlsplit

VERSION = "0.3.1"

IS_WINDOWS = platform.system() == "Windows"
DEFAULT_PORT = 8663
DEFAULT_PRINTER = "LQ310-RAW"
# Origins allowed to print out of the box: the production site plus the three
# public test sites. All are https subdomains of raindropinc.com — PUBLIC
# origins, so the allow_local_test_origins rule below does NOT cover them; a
# public origin must be listed here (and mirrored in installer.iss's browser
# policy so Chrome 142+ doesn't prompt). One install therefore prints from all
# four with no per-machine config. Add more by editing allowed_origins in
# config.json — no reinstall, just restart the agent.
DEFAULT_ORIGINS = [
	"https://ng-group.raindropinc.com",             # production — all 7 companies
	"https://avinaslive1.raindropinc.com",          # test
	"https://sandboxavinas-demo.raindropinc.com",   # test
	"https://avinasdemo.raindropinc.com",           # test
]
# Also auto-accept loopback / LAN origins (any scheme, any port) so an ad-hoc
# test site at http://localhost:8000, http://127.0.0.1, or http://192.168.x.y
# prints from the same install with no config edit. Public internet is still
# refused unless listed above. Set false in config.json to lock down to
# allowed_origins only.
DEFAULT_ALLOW_LOCAL_TEST = True

# --dry-run writes jobs to disk instead of a printer, so the HTTP/CORS layer can
# be exercised off-Windows.
DRY_RUN = "--dry-run" in sys.argv[1:]


def _app_dir() -> str:
	if IS_WINDOWS:
		# ProgramData, not LocalAppData: the agent runs as SYSTEM (boot task), and
		# %LOCALAPPDATA% under SYSTEM is the hidden systemprofile — config and log
		# would be unfindable and differ from a user-context run. ProgramData is one
		# machine-wide location whoever runs the agent.
		base = (
			os.environ.get("PROGRAMDATA")
			or os.environ.get("LOCALAPPDATA")
			or os.path.expanduser("~")
		)
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
		# ["*"] means allow any origin (max convenience, dedicated till only);
		# otherwise list the exact site URLs that may print.
		"allowed_origins": list(DEFAULT_ORIGINS),
		"allow_local_test_origins": DEFAULT_ALLOW_LOCAL_TEST,
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


def _is_local_origin(origin: str) -> bool:
	"""True for loopback / LAN origins — a test site on this machine or the
	office network, reached at localhost, 127.x, or a private IP (any port)."""
	host = urlsplit(origin).hostname or ""
	if host == "localhost" or host.endswith(".localhost"):
		return True
	try:
		ip = ipaddress.ip_address(host)
	except ValueError:
		return False
	return ip.is_loopback or ip.is_private


def _origin_allowed(origin: str) -> bool:
	"""The whole security model. Three ways an origin may print:

	  1. allowed_origins contains "*"      -> allow any site (opt-in wildcard)
	  2. allowed_origins lists it exactly  -> the production / named test sites
	  3. it is loopback/LAN and enabled    -> ad-hoc test sites, no config edit

	Matching in (2) is exact — no prefix/suffix that
	"https://ng-group.raindropinc.com.evil.com" could satisfy.
	"""
	allowed = CONFIG["allowed_origins"]
	if "*" in allowed:
		return True
	if origin in allowed:
		return True
	if CONFIG.get("allow_local_test_origins", DEFAULT_ALLOW_LOCAL_TEST) and _is_local_origin(origin):
		return True
	return False


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
		return printer

	import win32print

	target = _resolve_target(printer)
	h = win32print.OpenPrinter(target)
	try:
		job = win32print.StartDocPrinter(h, 1, ("Avinash ERP invoice", None, "RAW"))
		try:
			win32print.StartPagePrinter(h)
			win32print.WritePrinter(h, data)
			win32print.EndPagePrinter(h)
		finally:
			win32print.EndDocPrinter(h)
		log.info("printed %d bytes to %r (job %s)", len(data), target, job)
	finally:
		win32print.ClosePrinter(h)
	return target


def _resolve_target(printer: str) -> str:
	"""Return an existing queue to open, self-healing a missing LQ310-RAW.

	Windows error 1801 (invalid printer name) means the queue isn't there —
	usually the installer ran with the Epson unplugged so the RAW queue was
	never created, or it was removed. Recreate it (the agent must run elevated;
	see installer.iss) before giving up. We never silently fall back to the
	Epson's own driver queue: it swallows RAW ESC/P and the head never moves, so
	a 'success' there would print nothing.
	"""
	printers = list_printers()
	if printer in printers:
		return printer
	log.warning("printer %r not found; (re)creating %s", printer, DEFAULT_PRINTER)
	_ensure_default_queue()
	printers = list_printers()
	if DEFAULT_PRINTER in printers:
		return DEFAULT_PRINTER
	raise RuntimeError(
		"Print queue '%s' is not installed, and the %s queue could not be "
		"created. Attach the Epson LQ-310 and switch it on, then try again — or "
		"re-run PrintBridgeSetup.exe. Installed printers: %s"
		% (printer, DEFAULT_PRINTER, ", ".join(printers) or "none")
	)


class Handler(BaseHTTPRequestHandler):
	server_version = f"AvinashPrintBridge/{VERSION}"

	def log_message(self, fmt, *a):  # noqa: A002 - stdlib signature
		log.info("%s - %s", self.address_string(), fmt % a)

	def _origin_ok(self) -> str:
		"""Return the request Origin if allowed, else ''.

		Delegates to _origin_allowed (wildcard / exact list / loopback-LAN).
		Requests carrying a JSON content-type are preflighted by the browser, so
		a disallowed origin never reaches _print().
		"""
		origin = self.headers.get("Origin", "")
		return origin if origin and _origin_allowed(origin) else ""

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
			used = write_raw(printer, data)
		except Exception as e:
			log.exception("print failed on %r", printer)
			self._json(500, {"ok": False, "error": str(e), "printer": printer}, origin)
			return
		self._json(200, {"ok": True, "bytes": len(data), "printer": used or printer}, origin)


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
	"""Create OR repair the Generic / Text Only LQ310-RAW queue. Idempotent, and
	tolerant of a printer that isn't connected right now:

	  - Epson present, no queue   -> create the queue on the Epson's port
	  - Epson moved USB ports      -> repair the queue's port (Set-Printer)
	  - Epson offline, queue kept  -> leave the queue as-is (prints when it's back)
	  - Epson offline, no queue    -> throw (nothing to point a queue at yet)

	Kept as ONE PowerShell statement chain (no newline before elseif — PowerShell
	would treat that as a parse error). -ErrorAction Stop matters: Add-Printer
	raises NON-terminating errors, so without it a failure is invisible.
	"""
	ps = (
		"$ErrorActionPreference='Stop';"
		"try { Add-PrinterDriver -Name 'Generic / Text Only' -ErrorAction Stop } catch {};"
		"$e = Get-Printer | Where-Object { $_.Name -like '*LQ-310*' -or $_.DriverName -like '*Epson*' } | Select-Object -First 1;"
		"$r = Get-Printer -Name 'LQ310-RAW' -ErrorAction SilentlyContinue;"
		"if (-not $e -and -not $r) { throw 'No Epson dot-matrix printer found - attach it and switch it on.' }"
		" elseif (-not $e) { Write-Output ('kept ' + $r.PortName + ' - Epson offline') }"
		" elseif (-not $r) { Add-Printer -Name 'LQ310-RAW' -DriverName 'Generic / Text Only' -PortName $e.PortName -ErrorAction Stop; Write-Output ('created on ' + $e.PortName) }"
		" elseif ($r.PortName -ne $e.PortName) { Set-Printer -Name 'LQ310-RAW' -PortName $e.PortName -ErrorAction Stop; Write-Output ('repaired port -> ' + $e.PortName) }"
		" else { Write-Output ('ok on ' + $r.PortName) }"
	)
	rc, out = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps])
	if rc != 0:
		raise RuntimeError(out.strip() or "Add-Printer failed")
	return out.strip()


def _ensure_default_queue() -> None:
	"""Best-effort create/repair LQ310-RAW. Safe to call every launch — runs at
	startup (heal after a reboot: queue lost, Epson on a different USB port, or an
	install done with the Epson unplugged) and on a print that hit a missing queue.
	Always runs _install_queue (which is idempotent and also repairs the port);
	needs the agent elevated to succeed. Failures are logged, never raised."""
	if not IS_WINDOWS or DRY_RUN:
		return
	try:
		log.info("queue: %s", _install_queue())
	except Exception as e:
		log.warning("could not create/repair %s: %s", DEFAULT_PRINTER, e)


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
	# Self-heal the RAW queue on every launch, so a reboot that lost it — or an
	# install done with the Epson unplugged — still prints once the agent runs.
	_ensure_default_queue()
	log.info(
		"Avinash Print Bridge %s starting on 127.0.0.1:%d (dry_run=%s, origins=%s)",
		VERSION,
		port,
		DRY_RUN,
		", ".join(CONFIG["allowed_origins"]),
	)
	# Bind loopback only — never 0.0.0.0. Nothing off this machine may print.
	try:
		ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
	except OSError as e:
		# Port already owned by another instance (e.g. the boot task's agent is up
		# and the installer just launched a second one post-install). That instance
		# is serving — exit quietly instead of crashing loud.
		log.info("127.0.0.1:%d already in use (%s); another instance is serving", port, e)


if __name__ == "__main__":
	main()
