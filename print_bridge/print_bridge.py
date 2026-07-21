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
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from urllib.parse import urlsplit

VERSION = "0.5.0"

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
	"""First WRITABLE data dir. Preference on Windows: ProgramData (one shared,
	machine-wide location whoever runs the agent — SYSTEM boot task or a user),
	then LocalAppData, then temp. The write-test matters: if the SYSTEM boot task
	created ProgramData\\AvinashPrintBridge, a plain-user launch of the agent may
	not be able to write the log there, and opening it would crash the agent at
	startup. Falling back keeps the agent alive rather than dying over a log path.
	"""
	if IS_WINDOWS:
		bases = [os.environ.get("PROGRAMDATA"), os.environ.get("LOCALAPPDATA")]
		candidates = [os.path.join(b, "AvinashPrintBridge") for b in bases if b]
		candidates.append(os.path.join(tempfile.gettempdir(), "AvinashPrintBridge"))
	else:
		candidates = [os.path.join(os.path.expanduser("~"), ".avinash_print_bridge")]
	for d in candidates:
		try:
			os.makedirs(d, exist_ok=True)
			probe = os.path.join(d, ".write_test")
			with open(probe, "w"):
				pass
			os.remove(probe)
			return d
		except OSError:
			continue
	return tempfile.gettempdir()  # last resort — always writable


APP_DIR = _app_dir()
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
LOG_FILE = os.path.join(APP_DIR, "print_bridge.log")
# Breadcrumb written when a FOREIGN program owns our port (see main). A support
# person who finds the agent "not running" looks in APP_DIR and this file tells
# them exactly what is wrong and how to fix it. Removed on every clean bind.
PORT_CONFLICT_FILE = os.path.join(APP_DIR, "PORT_CONFLICT.txt")

log = logging.getLogger("print_bridge")
log.setLevel(logging.INFO)
# Never let logging setup crash the agent: if the file handler can't open (log
# dir not writable in this security context), fall back to console-only. A bridge
# that can't write a log must still print.
try:
	_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
	_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
	log.addHandler(_handler)
except OSError:
	pass
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


def diagnose() -> dict:
	"""Everything the browser needs to explain a broken setup to a human.

	Only queried when something has already failed — the analysis lives here,
	the wording lives in print_bridge.js. Every field is best-effort: a
	diagnosis endpoint that can itself crash would be worse than none.
	"""
	printers, printer_error = [], ""
	try:
		printers = list_printers()
	except Exception as e:
		printer_error = str(e)
	elevated = None
	if IS_WINDOWS:
		try:
			import ctypes

			elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
		except Exception:
			pass
	return {
		"version": VERSION,
		"port": int(CONFIG["port"]),
		"default_printer": CONFIG["default_printer"],
		"queue_exists": CONFIG["default_printer"] in printers,
		# Name-based hint only (EnumPrinters level 1 has no driver info): is
		# anything that looks like the Epson visible to Windows at all?
		"epson_seen": any("lq-310" in p.lower() or "epson" in p.lower() for p in printers),
		"printers": printers,
		"printer_error": printer_error,
		"elevated": elevated,
		"allowed_origins": CONFIG["allowed_origins"],
		"config_file": CONFIG_FILE,
		"log_file": LOG_FILE,
		"dry_run": DRY_RUN,
	}


def _port_owner_is_bridge(port: int) -> bool:
	"""True if whatever is listening on 127.0.0.1:port identifies as this agent.

	Distinguishes 'another instance of us is already serving' (fine, exit
	quietly) from 'a foreign program squats on our port' (the browser would show
	"not installed" forever with no clue — see main). A 403 still counts as us:
	error responses carry the same Server header.
	"""
	import urllib.error
	import urllib.request

	req = urllib.request.Request(
		"http://127.0.0.1:%d/ping" % port, headers={"Origin": "http://localhost"}
	)
	try:
		with urllib.request.urlopen(req, timeout=3) as resp:
			if "AvinashPrintBridge" in (resp.headers.get("Server") or ""):
				return True
			return b'"version"' in resp.read(2048)
	except urllib.error.HTTPError as e:
		return "AvinashPrintBridge" in (e.headers.get("Server") or "")
	except Exception:
		return False


def _alert_user(title: str, text: str) -> None:
	"""Native dialog — but only when a person launched us (Start menu / double
	click). From the SYSTEM boot/logon task there is no visible desktop
	(session 0), so the box would block forever unseen; SESSIONNAME is only set
	in interactive sessions."""
	if not IS_WINDOWS or not os.environ.get("SESSIONNAME"):
		return
	try:
		import ctypes

		ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)  # MB_ICONERROR
	except Exception:
		pass


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
		elif self.path == "/diag":
			self._json(200, {"ok": True, "diag": diagnose()}, origin)
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

	  - Epson present, no queue   -> create the queue on the Epson's USB port
	  - Epson moved USB ports      -> repair the queue's port (Set-Printer)
	  - Epson offline, queue kept  -> leave the queue as-is (prints when it's back)
	  - Epson offline, no queue    -> throw (nothing to point a queue at yet)

	Port discovery does NOT require the Epson's own printer driver to be installed.
	Two things bit a fresh till and are handled here so nothing needs a manual
	PowerShell step:

	  1. The 'Generic / Text Only' driver may be absent from the driver store
	     (Add-PrinterDriver then fails with 0x80070032). Stage it from the Windows
	     inbox INF with pnputil and retry.
	  2. There may be NO Epson *printer* to copy a port from — Windows loaded only
	     the raw "USB Printing Support" function (usbprint.sys) and never installed
	     an EPSON LQ-310 queue. usbprint still assigns the connected device a USBnnn
	     port, recorded under its Enum key's `Device Parameters\\PortName`. Read that
	     for a currently-present USB printer (Epson VID 04B8) so a never-driver-
	     installed printer is bound automatically.

	-PresentOnly excludes stale USBnnn ports left by printers that were unplugged,
	so we pick the port the Epson is actually on, not an old one. Written as a real
	multi-line script (passed as one -Command arg); -ErrorAction Stop matters
	because Add-Printer raises NON-terminating errors that are otherwise invisible.
	"""
	ps = r"""
$ErrorActionPreference = 'Stop'

# 1) Ensure the Generic / Text Only driver is staged. Add-PrinterDriver fails with
#    0x80070032 if the inbox package was never added to the store; stage it first.
try {
  Add-PrinterDriver -Name 'Generic / Text Only' -ErrorAction Stop
} catch {
  $inf = Join-Path $env:windir 'inf\prnge001.inf'
  if (-not (Test-Path $inf)) { $inf = Join-Path $env:windir 'inf\ntprint.inf' }
  & pnputil.exe /add-driver $inf /install | Out-Null
  Add-PrinterDriver -Name 'Generic / Text Only' -ErrorAction Stop
}

$queue = Get-Printer -Name 'LQ310-RAW' -ErrorAction SilentlyContinue
$port = $null

# 2a) Preferred: an installed Epson printer — copy its port.
$epson = Get-Printer -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -like '*LQ-310*' -or $_.DriverName -like '*Epson*' } |
  Select-Object -First 1
if ($epson) { $port = $epson.PortName }

# 2b) No Epson printer installed: read the USBnnn port usbprint.sys assigned to a
#     currently-connected USB printer, whether or not a model driver was installed.
if (-not $port) {
  $devs = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.InstanceId -like 'USBPRINT\*' -or $_.InstanceId -like 'USB\VID_04B8*' }
  foreach ($d in $devs) {
    $k = 'HKLM:\SYSTEM\CurrentControlSet\Enum\' + $d.InstanceId + '\Device Parameters'
    $pn = (Get-ItemProperty -Path $k -Name PortName -ErrorAction SilentlyContinue).PortName
    if ($pn) { $port = $pn; break }
  }
}

# 3) Apply. Keep the exit-code contract: a message containing 'No Epson' means
#    "printer offline, not a real failure" (configure() maps it to exit code 3).
if (-not $port -and -not $queue) {
  throw 'No Epson dot-matrix printer found - attach it and switch it on.'
} elseif (-not $port) {
  Write-Output ('kept ' + $queue.PortName + ' - Epson offline')
} elseif (-not $queue) {
  Add-Printer -Name 'LQ310-RAW' -DriverName 'Generic / Text Only' -PortName $port -ErrorAction Stop
  Write-Output ('created on ' + $port)
} elseif ($queue.PortName -ne $port) {
  Set-Printer -Name 'LQ310-RAW' -PortName $port -ErrorAction Stop
  Write-Output ('repaired port -> ' + $port)
} else {
  Write-Output ('ok on ' + $port)
}
"""
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

	  0 = queue exists / was created
	  3 = only problem is that no Epson is attached right now — NOT a failure:
	      the agent creates the queue by itself on any later start or print with
	      the printer connected (_ensure_default_queue), so the installer shows
	      an informational note instead of an error.
	  1 = anything else (a real error worth reading the log for)
	"""
	if not IS_WINDOWS:
		print("--configure is Windows-only.")
		return 1
	results = []
	_step(results, f"{DEFAULT_PRINTER} print queue", _install_queue)
	failures = [detail for ok, _, detail in results if not ok]
	if not failures:
		return 0
	if all("No Epson" in detail for detail in failures):
		return 3
	return 1


def main() -> None:
	if "--configure" in sys.argv[1:]:
		sys.exit(configure())
	port = int(CONFIG["port"])
	# Bind loopback only — never 0.0.0.0. Nothing off this machine may print.
	# Bind FIRST (before the queue self-heal): if the port is taken, everything
	# else is moot and the answer must be diagnosed, not worked around.
	try:
		server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
	except OSError as e:
		if _port_owner_is_bridge(port):
			# Another instance of us (e.g. the boot task's agent is up and the
			# installer just launched one more post-install). It is serving —
			# exit quietly instead of crashing loud.
			log.info("127.0.0.1:%d already in use (%s); another instance is serving", port, e)
			return
		# A FOREIGN program owns the port. Without this branch the browser says
		# "Print Bridge not installed" forever and nobody learns why. Say what
		# is wrong everywhere we can: the log, a breadcrumb file beside it, and
		# a dialog when a person launched us by hand.
		msg = (
			"Avinash Print Bridge cannot start: another program is already "
			"using port %d on this computer (%s).\n\n"
			"To find and fix it:\n"
			"  1. Open Command Prompt as administrator.\n"
			"  2. Run:  netstat -ano | findstr :%d\n"
			"  3. Note the number in the last column (the PID).\n"
			"  4. Open Task Manager > Details and find that PID to see which "
			"program it is.\n"
			"  5. Close, reconfigure, or uninstall that program, then start "
			"Avinash Print Bridge from the Start menu (or restart the PC).\n\n"
			"If you are unsure which program it is, send a photo of the Task "
			"Manager row and this file to IT.\n" % (port, e, port)
		)
		log.error("port conflict on 127.0.0.1:%d — foreign owner. %s", port, msg)
		try:
			with open(PORT_CONFLICT_FILE, "w") as f:
				f.write(msg)
		except OSError:
			pass
		_alert_user("Avinash Print Bridge - port problem", msg)
		return
	# Clean bind: any earlier conflict breadcrumb is stale — remove it so the
	# diagnosis never outlives the problem.
	try:
		os.remove(PORT_CONFLICT_FILE)
	except OSError:
		pass
	# Self-heal the RAW queue on every launch, so a reboot that lost it — or an
	# install done with the Epson unplugged — still prints once the agent runs.
	# In a background thread: the PowerShell heal takes 5-10s, and a /ping that
	# arrives during it must answer instantly, not look like "not running". A
	# print racing the heal is fine — _resolve_target heals again if the queue
	# is still missing, and _install_queue tolerates an already-existing queue.
	import threading

	threading.Thread(target=_ensure_default_queue, daemon=True).start()
	log.info(
		"Avinash Print Bridge %s starting on 127.0.0.1:%d (dry_run=%s, origins=%s)",
		VERSION,
		port,
		DRY_RUN,
		", ".join(CONFIG["allowed_origins"]),
	)
	server.serve_forever()


if __name__ == "__main__":
	main()
