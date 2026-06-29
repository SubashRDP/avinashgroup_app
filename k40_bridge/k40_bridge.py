

import json
import logging
import logging.handlers
import os
import platform
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, datetime, timedelta as _timedelta
from tkinter import StringVar, Tk, Toplevel, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import requests
from zk import ZK

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

IS_WINDOWS = platform.system() == "Windows"
TASK_NAME = "K40 Bridge"

# Suppress the brief black console window that pops up when this --noconsole
# GUI build shells out to schtasks/taskkill on Windows. Without this flag, a
# cmd window flashes on screen every time a subprocess runs (e.g. the
# schtasks /Query that fires at every startup). 0 on non-Windows = no-op.
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

# Set when launched by the scheduler / auto-start with --background (or
# --hidden): start with the window withdrawn to the tray so a boot-time
# launch never pops the GUI to the foreground.
START_HIDDEN = any(a in ("--background", "--hidden") for a in sys.argv[1:])

# ============================================
# CONSTANTS
# ============================================
VERSION = "1.3.0"

# The only endpoint the bridge uses to deliver punches.
# Takes a JSON list of {user_id, timestamp} dicts. A batch of size 1 is
# valid — there is no separate single-record endpoint.
BATCH_WEBHOOK_PATH = (
    "/api/method/avinashgroup_app.biometric.api.receive_attendance"
)
# Heartbeat ping — bridge calls this every sync cycle so the server knows the
# bridge is alive even when no new punches were found.
HEARTBEAT_PATH = "/api/method/avinashgroup_app.biometric.heartbeat.ping"
# Command tunnel — bridge polls this, runs the returned commands, reports back.
POLL_COMMANDS_PATH = (
    "/api/method/avinashgroup_app.biometric.bridge_commands.poll_commands"
)
REPORT_COMMAND_PATH = (
    "/api/method/avinashgroup_app.biometric.bridge_commands.report_command_result"
)
# How many punches per batch POST. The server processes one (employee, date)
# group at a time, so a batch that's too big has no advantage; a batch that's
# too small still pays HTTP overhead per call.
BATCH_SIZE = 100
# How often the command poller checks the server (independent of sync cycle).
COMMAND_POLL_INTERVAL_SEC = 30
# Prune dedup entries whose punch date is older than this many days.
DEDUP_RETENTION_DAYS = 90
# Re-check GitHub for new bridge versions this often, in addition to the
# one-shot check at startup. 24h keeps long-running installs current
# without hammering the update URL.
UPDATE_CHECK_INTERVAL_HOURS = 24

# URL to the version-tracker file in the repo. Bumped on each release.
UPDATE_CHECK_URL = (
    "https://raw.githubusercontent.com/SubashRDP/avinashgroup_app/"
    "develop/k40_bridge/latest_version.txt"
)
# Direct download URL — Releases on public repos work WITHOUT GitHub login.
DOWNLOAD_PAGE_URL = "https://github.com/SubashRDP/avinashgroup_app/releases/latest"
# Fallback only. Prefer the version-explicit URL from installer_download_url()
# below: GitHub's "latest" pointer can drift to an OLDER release (e.g. if an old
# release's assets get re-uploaded), which would make the self-updater download a
# version that doesn't match latest_version.txt and loop forever. Pinning the URL
# to the exact advertised version removes that whole failure mode.
INSTALLER_DOWNLOAD_URL = (
    "https://github.com/SubashRDP/avinashgroup_app/releases/latest/download/K40BridgeSetup.exe"
)


def installer_download_url(version):
    """Build the version-explicit installer URL for a given version string.

    The release tag is `k40-v{version}` (see build-k40-bridge.yml), so the asset
    lives at releases/download/k40-v{version}/K40BridgeSetup.exe. This always
    fetches exactly the version latest_version.txt advertises, independent of
    which release GitHub currently flags as "latest"."""
    v = version.strip().lstrip("v")
    return (
        "https://github.com/SubashRDP/avinashgroup_app/"
        f"releases/download/k40-v{v}/K40BridgeSetup.exe"
    )

def _data_dir():
    """Return a stable per-user data directory that survives exe moves/replacements."""
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "K40Bridge")
    elif platform.system() == "Darwin":
        path = os.path.expanduser("~/Library/Application Support/K40Bridge")
    else:
        path = os.path.join(
            os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
            "K40Bridge",
        )
    os.makedirs(path, exist_ok=True)
    return path


# Folder where the exe was launched (for backwards compat — old config.json was here)
EXE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

# Stable per-user data directory (survives exe being moved/replaced)
APP_DIR = _data_dir()

CONFIG_FILE = os.path.join(APP_DIR, "config.json")
SYNCED_RECORDS_FILE = os.path.join(APP_DIR, "k40_synced.json")
NEXT_SYNC_FILE = os.path.join(APP_DIR, "next_sync.json")
LAST_SYNC_DATES_FILE = os.path.join(APP_DIR, "last_sync_dates.json")
LOG_FILE = os.path.join(APP_DIR, "k40_bridge.log")

# One-time migration: if old config sits next to the exe, copy it into APP_DIR
def _migrate_old_config():
    for fname in ("config.json", "k40_synced.json", "next_sync.json"):
        old = os.path.join(EXE_DIR, fname)
        new = os.path.join(APP_DIR, fname)
        if os.path.exists(old) and not os.path.exists(new):
            try:
                import shutil
                shutil.copy2(old, new)
            except Exception:
                pass

_migrate_old_config()

DEFAULT_CONFIG = {
    "sync_interval_minutes": 1440,
    "log_level": "INFO",
    "log_max_size_mb": 10,
    "log_backup_count": 5,
    "device_timeout_seconds": 5,
    "network_probe_retries": 3,
    "devices": [],
}

INTERVAL_OPTIONS = [
    ("1 day", 1440),
    ("1 hour", 60),
    ("30 minutes", 30),
    ("15 minutes", 15),
    ("10 minutes", 10),
    ("5 minutes", 5),
    ("2 minutes", 2),
]


# ============================================
# WINDOWS AUTO-START (Task Scheduler integration)
# ============================================
def _is_admin():
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def autostart_status():
    """Return True if the K40 Bridge scheduled task exists."""
    if not IS_WINDOWS:
        return False
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME],
            capture_output=True, text=True, timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except Exception:
        return False


def autostart_install():
    """Register the bridge as a Windows scheduled task.
    Auto-start at boot, restart on failure, highest privilege.
    Returns (ok, message)."""
    if not IS_WINDOWS:
        return False, "Auto-start is only supported on Windows."
    if not _is_admin():
        return False, (
            "Administrator rights required.\n\n"
            "Close the bridge, then right-click k40_bridge.exe → "
            "Run as administrator, then click Enable Auto-Start again."
        )

    from xml.sax.saxutils import escape

    exe_path = os.path.abspath(sys.argv[0])
    work_dir = os.path.dirname(exe_path)
    # Escape so paths containing &, <, > (e.g. a user folder named "A & B")
    # don't produce malformed XML that schtasks rejects.
    exe_path_x = escape(exe_path)
    work_dir_x = escape(work_dir)

    xml = (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        '  <Triggers>\n'
        '    <BootTrigger><Enabled>true</Enabled></BootTrigger>\n'
        '    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>\n'
        '  </Triggers>\n'
        '  <Principals>\n'
        '    <Principal id="Author">\n'
        '      <RunLevel>HighestAvailable</RunLevel>\n'
        '      <LogonType>InteractiveToken</LogonType>\n'
        '    </Principal>\n'
        '  </Principals>\n'
        '  <Settings>\n'
        '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
        '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
        '    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>\n'
        '    <RestartOnFailure>\n'
        '      <Interval>PT1M</Interval>\n'
        '      <Count>999</Count>\n'
        '    </RestartOnFailure>\n'
        '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
        '    <AllowHardTerminate>true</AllowHardTerminate>\n'
        '    <StartWhenAvailable>true</StartWhenAvailable>\n'
        '    <Hidden>true</Hidden>\n'
        '  </Settings>\n'
        '  <Actions>\n'
        f'    <Exec>\n'
        f'      <Command>{exe_path_x}</Command>\n'
        f'      <Arguments>--background</Arguments>\n'
        f'      <WorkingDirectory>{work_dir_x}</WorkingDirectory>\n'
        '    </Exec>\n'
        '  </Actions>\n'
        '</Task>\n'
    )

    fd, xml_path = tempfile.mkstemp(suffix=".xml")
    try:
        os.close(fd)
        with open(xml_path, "w", encoding="utf-16") as f:
            f.write(xml)
        result = subprocess.run(
            ["schtasks", "/Create", "/XML", xml_path, "/TN", TASK_NAME, "/F"],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return True, "Auto-start enabled. Bridge will launch at every boot."
        return False, (result.stderr or result.stdout or "Unknown error").strip()
    except Exception as e:
        return False, str(e)
    finally:
        try:
            os.remove(xml_path)
        except Exception:
            pass


def autostart_uninstall():
    """Remove the K40 Bridge scheduled task."""
    if not IS_WINDOWS:
        return False, "Auto-start is only supported on Windows."
    if not _is_admin():
        return False, "Administrator rights required."
    try:
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
            capture_output=True, text=True, timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return True, "Auto-start disabled."
        return False, (result.stderr or result.stdout or "Unknown error").strip()
    except Exception as e:
        return False, str(e)


# ============================================
# UPDATE CHECK
# ============================================
def _version_tuple(s):
    """Convert '1.2.3' → (1, 2, 3) for comparison."""
    try:
        return tuple(int(x) for x in s.strip().lstrip("v").split("."))
    except Exception:
        return (0,)


def check_for_update():
    """Fetch latest version string from GitHub. Returns (latest, is_newer).
    Returns (None, False) on failure (no network, etc.)."""
    try:
        r = requests.get(UPDATE_CHECK_URL, timeout=8)
        if r.status_code != 200:
            return None, False
        latest = r.text.strip().split("\n")[0].strip()
        if not latest:
            return None, False
        is_newer = _version_tuple(latest) > _version_tuple(VERSION)
        return latest, is_newer
    except Exception:
        return None, False


# ============================================
# CONFIG I/O
# ============================================
def _atomic_write_json(path, obj, indent=None):
    """Write JSON to `path` atomically: serialize to a temp file in the same
    directory, fsync, then os.replace over the target. A crash or power loss
    mid-write leaves the old file intact instead of a half-written (corrupt)
    one — important for config.json, whose loss drops the user back into the
    setup wizard."""
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception as e:
        # A corrupt/unreadable config would otherwise be silently discarded,
        # dropping the user back into the setup wizard with all their devices
        # and credentials gone. Preserve the bad file and leave a breadcrumb so
        # it can be recovered. Logging isn't configured yet (it's built FROM the
        # config), so write directly to the log file.
        try:
            import shutil
            backup = CONFIG_FILE + ".corrupt"
            shutil.copy2(CONFIG_FILE, backup)
        except Exception:
            backup = "(backup failed)"
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as lf:
                lf.write(
                    f"{datetime.now():%Y-%m-%d %H:%M:%S} ERROR config.json "
                    f"unreadable ({e}); preserved a copy at {backup}\n"
                )
        except Exception:
            pass
        return None


def save_config(config):
    _atomic_write_json(CONFIG_FILE, config, indent=2)


# ============================================
# LOGGING
# ============================================
class GuiLogHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        try:
            self.callback(self.format(record))
        except Exception:
            pass


def setup_logging(config, gui_callback=None):
    logger = logging.getLogger("k40_bridge")
    logger.setLevel(getattr(logging, config.get("log_level", "INFO"), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    max_bytes = int(config.get("log_max_size_mb", 10)) * 1024 * 1024
    backup_count = int(config.get("log_backup_count", 5))
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    if gui_callback:
        gh = GuiLogHandler(gui_callback)
        gh.setFormatter(fmt)
        logger.addHandler(gh)

    return logger


# ============================================
# DEDUP STATE (one file shared across all devices)
# ============================================
class DedupStore:
    """In-memory set of {serial}_{user_id}_{YYYY-MM-DD HH:MM:SS} keys.

    Prevents the bridge from re-POSTing a punch the server already accepted.
    Persisted to k40_synced.json. Pruned on load + on save so the file does
    not grow without bound — keys whose date is older than
    DEDUP_RETENTION_DAYS are dropped (the server-side time-exact merge in
    _reconcile_day_checkins is the long-term backstop, not this file).
    """

    def __init__(self):
        # Guards self.synced so the (serialized) sync path and any future
        # caller can mutate/iterate it without "set changed size during
        # iteration". Non-reentrant: _prune() assumes the lock is already held.
        self._lock = threading.Lock()
        self.synced = set()
        if os.path.exists(SYNCED_RECORDS_FILE):
            try:
                with open(SYNCED_RECORDS_FILE) as f:
                    self.synced = set(json.load(f))
            except Exception:
                self.synced = set()
        self._prune()  # construction is single-threaded; no lock needed

    def is_synced(self, key):
        with self._lock:
            return key in self.synced

    def mark(self, key):
        with self._lock:
            self.synced.add(key)

    def save(self):
        with self._lock:
            self._prune()
            data = list(self.synced)
        # Write outside the lock; an atomic replace can't corrupt the file.
        try:
            _atomic_write_json(SYNCED_RECORDS_FILE, data)
        except Exception:
            pass

    def _prune(self):
        """Drop entries whose embedded date is older than DEDUP_RETENTION_DAYS.
        Keys we don't recognize (malformed / older format) are kept so a bad
        parser change does not silently delete valid history.
        Assumes self._lock is held (or single-threaded construction)."""
        cutoff = datetime.now() - _timedelta(days=DEDUP_RETENTION_DAYS)
        pruned = set()
        for k in self.synced:
            ts = _parse_key_timestamp(k)
            if ts is None or ts >= cutoff:
                pruned.add(k)
        self.synced = pruned


def _parse_key_timestamp(key):
    """Best-effort: extract the trailing 'YYYY-MM-DD HH:MM:SS' from a dedup key.
    Returns a datetime, or None if the key format isn't recognized."""
    if not key or len(key) < 19:
        return None
    tail = key[-19:]
    try:
        return datetime.strptime(tail, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


# ============================================
# DEVICE CLIENTS
# ============================================
class _AttRecord:
    """Lightweight record matching pyzk's Attendance shape (.user_id, .timestamp)."""
    __slots__ = ("user_id", "timestamp")

    def __init__(self, user_id, timestamp):
        self.user_id = user_id
        self.timestamp = timestamp


class _BaseClient:
    """Common probe_network + interface for device-specific clients."""

    def __init__(self, device, timeout=5, retries=3):
        self.device = device
        self.timeout = timeout
        self.retries = retries

    def probe_network(self):
        host = self.device["ip"]
        port = int(self.device.get("port", self._default_port()))
        for attempt in range(self.retries):
            try:
                sock = socket.create_connection((host, port), timeout=self.timeout)
                sock.close()
                return True
            except (socket.timeout, socket.error, OSError):
                if attempt < self.retries - 1:
                    time.sleep(min(2 ** attempt, 4))
        return False

    def _default_port(self):
        return 4370

    def fetch_attendance(self, date_filter=None):
        raise NotImplementedError


class ZKTecoClient(_BaseClient):
    """ZK protocol over port 4370 (K20, K40, F18, MB360, eSSL, etc.)."""

    def _default_port(self):
        return 4370

    def fetch_attendance(self, date_from=None, date_to=None):
        """Fetch attendance records.

        - date_from=None, date_to=None → return ALL records on the device.
        - date_from set → keep records on/after that date.
        - date_to set → keep records on/before that date.
        """
        if not self.probe_network():
            return [], "UNREACHABLE"

        comm_key = self.device.get("comm_key", 0) or 0
        try:
            comm_key = int(comm_key)
        except (TypeError, ValueError):
            comm_key = 0

        try:
            conn = ZK(
                self.device["ip"],
                port=int(self.device.get("port", 4370)),
                timeout=self.timeout,
                password=comm_key,
            )
            zk = conn.connect()
            zk.disable_device()
            try:
                attendances = zk.get_attendance()
            finally:
                try:
                    zk.enable_device()
                except Exception:
                    pass
                try:
                    zk.disconnect()
                except Exception:
                    pass

            if date_from or date_to:
                def _in_range(a):
                    d = a.timestamp.date()
                    if date_from and d < date_from:
                        return False
                    if date_to and d > date_to:
                        return False
                    return True
                attendances = [a for a in attendances if _in_range(a)]
            return attendances, "OK"
        except Exception as e:
            return [], f"ERROR: {e}"


class HikvisionClient(_BaseClient):
    """Hikvision ISAPI HTTP API. Requires username/password (Digest auth).
    Default port 80 (HTTP). Set port=443 in config and use HTTPS for secure devices.
    """

    def _default_port(self):
        return 80

    def fetch_attendance(self, date_from=None, date_to=None):
        if not self.probe_network():
            return [], "UNREACHABLE"

        try:
            from requests.auth import HTTPDigestAuth
            import uuid

            user = self.device.get("username", "")
            pw = self.device.get("password", "")
            if not user:
                return [], "ERROR: Hikvision device requires username"

            ip = self.device["ip"]
            port = int(self.device.get("port", 80))
            scheme = "https" if port == 443 else "http"
            base = f"{scheme}://{ip}:{port}"

            # Default window: last 30 days → today. If no bounds passed,
            # use a wide window since Hikvision REQUIRES a startTime/endTime.
            today = date.today()
            if date_from is None:
                date_from = today.replace(year=today.year - 1) if today.month > 1 else date(today.year - 1, today.month, today.day)
            if date_to is None:
                date_to = today

            # ISO 8601 day window. Hikvision wants TZ offset; use local.
            from datetime import time as _time, timezone, timedelta
            tz_offset_sec = -time.timezone if time.daylight == 0 else -time.altzone
            tz = timezone(timedelta(seconds=tz_offset_sec))
            start = datetime.combine(date_from, _time.min).replace(tzinfo=tz).isoformat()
            end = datetime.combine(date_to, _time.max).replace(tzinfo=tz).isoformat()

            auth = HTTPDigestAuth(user, pw)
            records = []
            position = 0
            page = 100
            max_pages = 50  # safety cap (5000 events/day)

            for _ in range(max_pages):
                payload = {
                    "AcsEventCond": {
                        "searchID": str(uuid.uuid4()),
                        "searchResultPosition": position,
                        "maxResults": page,
                        "major": 0,
                        "minor": 0,
                        "startTime": start,
                        "endTime": end,
                    }
                }
                try:
                    r = requests.post(
                        f"{base}/ISAPI/AccessControl/AcsEvent?format=json",
                        json=payload, auth=auth, timeout=15, verify=False,
                    )
                except Exception as e:
                    return [], f"ERROR: {e}"

                if r.status_code in (401, 403):
                    return [], "AUTH_FAIL"
                if r.status_code != 200:
                    return [], f"ERROR: HTTP {r.status_code}: {r.text[:160]}"

                try:
                    data = r.json()
                except Exception:
                    return [], f"ERROR: non-JSON response: {r.text[:160]}"

                acs = data.get("AcsEvent", {})
                events = acs.get("InfoList") or []
                for e in events:
                    emp = e.get("employeeNoString") or e.get("employeeNo")
                    ts = e.get("time")
                    if not emp or not ts:
                        continue
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        # store naive local time to match pyzk shape
                        dt = dt.replace(tzinfo=None)
                    except Exception:
                        continue
                    records.append(_AttRecord(str(emp), dt))

                status = (acs.get("responseStatusStrg") or "").upper()
                if status != "MORE":
                    break
                position += page

            return records, "OK"
        except Exception as e:
            return [], f"ERROR: {e}"


class HtmsClient(_BaseClient):
    """HTMS-86 / HAMS access-control software (HUNDURE/Chiyu HTA controllers).

    These controllers don't speak the ZK protocol, so there's nothing to poll
    over port 4370. Instead HTMS-86 writes every punch into Microsoft Access
    (.mdb) databases, and we read those directly:

      • Punch rows live in table ``PubEvent`` inside per-year files
        ``HAMS_<year>.mdb`` (e.g. HAMS_2026.mdb). Each row carries
        ``personID`` (HTMS internal, zero-padded), ``eventDate`` and
        ``eventTime``.
      • The human work-number lives in the master ``HAMS.mdb`` ``Emp`` table:
        ``Emp_Id`` (== PubEvent.personID) maps to ``Emp_no``.

    We send ``Emp_no`` as the user_id so it matches Employee.attendance_device_id
    in ERPNext (the same convention the ZK path relies on).

    The config row uses ``db_folder`` (the HTMS-86 install folder) in place of
    ip/port. Reading is done through ADO/OLEDB on Windows — the same Jet
    provider HTMS itself uses — so no extra database driver is required on a
    32-bit build.
    """

    # OLEDB providers tried in order. ACE matches modern (often 64-bit) Office
    # installs; Jet 4.0 ships with every 32-bit Windows and is what HTMS uses.
    _PROVIDERS = (
        "Microsoft.ACE.OLEDB.16.0",
        "Microsoft.ACE.OLEDB.12.0",
        "Microsoft.Jet.OLEDB.4.0",
    )

    def _folder(self):
        return (self.device.get("db_folder") or self.device.get("ip") or "").strip()

    def _master_db(self):
        return os.path.join(self._folder(), "HAMS.mdb")

    def probe_network(self):
        # "Reachable" == the HTMS folder and its master DB exist on disk.
        folder = self._folder()
        return bool(folder) and os.path.isdir(folder) and os.path.isfile(self._master_db())

    def _connect(self, db_path):
        try:
            import win32com.client
        except ImportError as e:
            raise RuntimeError(
                "pywin32 is not installed — HTMS/HAMS sources need the win32com "
                "package to read Access .mdb files. Install pywin32, or use the "
                "official Windows build of the bridge."
            ) from e

        # NOTE: COM is initialized once per fetch in fetch_attendance() (and
        # balanced with CoUninitialize there), not here — so this can be called
        # repeatedly (master DB + each year file) without nesting init counts.
        last_err = None
        for prov in self._PROVIDERS:
            try:
                conn = win32com.client.Dispatch("ADODB.Connection")
                conn.Open(f"Provider={prov};Data Source={db_path};")
                return conn
            except Exception as e:
                last_err = e
        raise RuntimeError(
            f"no usable Access OLEDB provider (tried {', '.join(self._PROVIDERS)}); "
            f"install the Microsoft Access Database Engine redistributable matching "
            f"this app's bitness — last error: {last_err}"
        )

    # Substrings that mark a *transient* Access/Jet failure — the .mdb is
    # momentarily locked or held exclusively (often by HTMS-86 itself writing a
    # punch). These are worth retrying; anything else (missing table, bad SQL,
    # no provider) is a hard error and re-raised immediately.
    _TRANSIENT_HINTS = ("lock", "in use", "being used", "share", "denied", "exclusively")

    def _query(self, db_path, sql, retries=3):
        last_err = None
        for attempt in range(retries):
            try:
                conn = self._connect(db_path)
                try:
                    rs = conn.Execute(sql)[0]
                    ncols = rs.Fields.Count
                    rows = []
                    while not rs.EOF:
                        rows.append([rs.Fields.Item(i).Value for i in range(ncols)])
                        rs.MoveNext()
                    rs.Close()
                    return rows
                finally:
                    conn.Close()
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if any(h in msg for h in self._TRANSIENT_HINTS) and attempt < retries - 1:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                raise
        raise last_err

    def _emp_map(self):
        """Emp_Id (== PubEvent.personID) -> Emp_no, from the master HAMS.mdb.

        Also warns when several employees share one Emp_no. That work-number is
        what we send to ERPNext as the user_id, so a shared value silently
        collapses those people's punches onto a single Employee. A log warning is
        the only place ops can catch a HAMS data-entry mistake before it skews
        attendance (the value may legitimately repeat across active + deleted
        re-enrollments of the same person, so this is a heads-up, not a hard
        error)."""
        rows = self._query(self._master_db(), "SELECT Emp_Id, Emp_no FROM Emp")
        mp = {}
        ids_by_no = {}
        for emp_id, emp_no in rows:
            key = ("" if emp_id is None else str(emp_id)).strip()
            no = ("" if emp_no is None else str(emp_no)).strip()
            if key and no:
                mp[key] = no
                ids_by_no.setdefault(no, []).append(key)
        shared = {no: ids for no, ids in ids_by_no.items() if len(ids) > 1}
        if shared:
            preview = "; ".join(f"{no}->{ids}" for no, ids in list(shared.items())[:8])
            logging.getLogger("k40_bridge").warning(
                "HTMS HAMS.mdb has %d Emp_no value(s) shared by multiple employees; "
                "their punches collapse onto one ERPNext employee — fix in HAMS. "
                "Examples (Emp_no->Emp_Ids): %s", len(shared), preview
            )
        return mp

    def _year_files(self, date_from, date_to):
        """HAMS_<year>.mdb paths covering [date_from..date_to]. With no
        date_from, return every yearly file present (first/full sync)."""
        folder = self._folder()
        present = {}
        for fn in os.listdir(folder):
            m = re.match(r"^HAMS_(\d{4})\.mdb$", fn, re.IGNORECASE)
            if m:
                present[int(m.group(1))] = os.path.join(folder, fn)
        if not present:
            return []
        if date_from is None:
            years = set(present)
        else:
            y1 = (date_to.year if date_to else max(present))
            years = {y for y in range(date_from.year, y1 + 1) if y in present}
            # Always include the newest file: a device clock running into the
            # next year must not be silently dropped.
            years.add(max(present))
        return [present[y] for y in sorted(years)]

    def fetch_attendance(self, date_from=None, date_to=None):
        if not self.probe_network():
            return [], "UNREACHABLE"

        # COM must be initialized on the calling (sync) thread before any ADODB
        # call, and balanced with CoUninitialize so repeated daily syncs don't
        # leak apartment-init counts. Wrap the whole read once, not per query.
        try:
            import pythoncom
        except ImportError:
            return [], (
                "ERROR: pywin32 not installed — HTMS sources need win32com/"
                "pythoncom to read Access .mdb files"
            )
        pythoncom.CoInitialize()
        try:
            return self._fetch_attendance(date_from, date_to)
        finally:
            pythoncom.CoUninitialize()

    def _fetch_attendance(self, date_from=None, date_to=None):
        try:
            emp_map = self._emp_map()
        except Exception as e:
            return [], f"ERROR: reading Emp table: {e}"

        records = []
        for db_path in self._year_files(date_from, date_to):
            try:
                rows = self._query(
                    db_path, "SELECT personID, eventDate, eventTime FROM PubEvent"
                )
            except Exception as e:
                return [], f"ERROR: reading {os.path.basename(db_path)}: {e}"

            for person_id, ev_date, ev_time in rows:
                pid = ("" if person_id is None else str(person_id)).strip()
                # Skip non-person rows (door/alarm events have empty/zero personID)
                # and punches whose employee has no work-number / was removed.
                if not pid or not pid.strip("0"):
                    continue
                emp_no = emp_map.get(pid)
                if not emp_no:
                    continue
                ts = self._parse_dt(ev_date, ev_time)
                if ts is None:
                    continue
                d = ts.date()
                if date_from and d < date_from:
                    continue
                if date_to and d > date_to:
                    continue
                records.append(_AttRecord(emp_no, ts))

        return records, "OK"

    @staticmethod
    def _parse_dt(ev_date, ev_time):
        """Combine HTMS eventDate + eventTime into a naive datetime. ADO returns
        text columns as str and date/time columns as datetime-like objects, so
        handle both."""
        if ev_date is None:
            return None
        if hasattr(ev_date, "year") and not isinstance(ev_date, str):
            d = datetime(ev_date.year, ev_date.month, ev_date.day)
        else:
            ds = str(ev_date).strip().replace("-", "/").split(" ")[0]
            try:
                d = datetime.strptime(ds, "%Y/%m/%d")
            except ValueError:
                return None

        if ev_time is not None and hasattr(ev_time, "hour") and not isinstance(ev_time, str):
            return d.replace(hour=ev_time.hour, minute=ev_time.minute, second=ev_time.second)

        ts_str = ("" if ev_time is None else str(ev_time).strip()).split(" ")[-1]
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                t = datetime.strptime(ts_str, fmt)
                return d.replace(hour=t.hour, minute=t.minute, second=t.second)
            except ValueError:
                continue
        return d


# ============================================
# INTEGRATION REGISTRY
# ============================================
# Single source of truth for every punch source the bridge supports. Each entry
# declares:
#   category : "device"   → a physical unit polled over the network
#              "software"  → attendance software we read a database/export from
#   client   : the _BaseClient subclass that does the fetching
#   label    : human name shown in the wizard dropdown
#   help     : one-line hint shown under the row's section
#   fields   : the per-source inputs the wizard renders automatically. Each
#              field spec: {key, label, width, default, secret, kind, optional,
#              browse}. "kind":"int" stores an int; "secret" masks input;
#              "optional" makes it non-required; "browse":"dir" adds a folder
#              picker button.
#
# Adding a NEW software integration is therefore: write a _BaseClient subclass
# that returns _AttRecord objects from its data store, then add one entry here.
# The wizard, save/load, testing, logging and control panel all adapt with no
# further GUI code.
INTEGRATIONS = {
    "zkteco": {
        "category": "device",
        "client": ZKTecoClient,
        "label": "ZKTeco (K40 / K20 / F18 / eSSL…)",
        "help": "Biometric device's LAN IP (Menu → Comm. → Ethernet). Comm Key is 0 unless set on the device.",
        "fields": [
            {"key": "ip", "label": "Device IP", "width": 15},
            {"key": "port", "label": "Port", "width": 6, "default": "4370", "kind": "int", "optional": True},
            {"key": "comm_key", "label": "Comm Key", "width": 9, "default": "0", "kind": "int", "secret": True, "optional": True},
        ],
    },
    "hikvision": {
        "category": "device",
        "client": HikvisionClient,
        "label": "Hikvision (ISAPI HTTP)",
        "help": "Device IP and the ISAPI HTTP port (usually 80). Username/password are the device admin login.",
        "fields": [
            {"key": "ip", "label": "Device IP", "width": 15},
            {"key": "port", "label": "Port", "width": 6, "default": "80", "kind": "int", "optional": True},
            {"key": "username", "label": "Username", "width": 12},
            {"key": "password", "label": "Password", "width": 12, "secret": True},
        ],
    },
    "htms": {
        "category": "software",
        "client": HtmsClient,
        "label": "HTMS-86 / HAMS (Access DB)",
        "help": r"Folder containing HAMS.mdb and HAMS_<year>.mdb (the HTMS-86 install folder, e.g. E:\HTMS-86).",
        "fields": [
            {"key": "db_folder", "label": "HTMS-86 Folder", "width": 38, "browse": "dir"},
        ],
    },
}

# type → client map (kept for make_device_client and any older callers).
DEVICE_TYPES = {key: meta["client"] for key, meta in INTEGRATIONS.items()}


def integration_meta(dtype):
    return INTEGRATIONS.get((dtype or "").lower())


def integrations_in(category):
    """[(type_key, meta), …] for one category, in registry order."""
    return [(k, m) for k, m in INTEGRATIONS.items() if m["category"] == category]


def make_device_client(device, timeout=5, retries=3):
    dtype = (device.get("type") or "zkteco").lower()
    cls = DEVICE_TYPES.get(dtype, ZKTecoClient)
    return cls(device, timeout=timeout, retries=retries)


def device_address(device):
    """Human-readable source address for logs and the control-panel table:
    the primary configured field (e.g. DB folder) for software sources,
    host:port for network devices."""
    meta = integration_meta(device.get("type"))
    if meta and meta["category"] == "software":
        for f in meta["fields"]:
            val = device.get(f["key"])
            if val:
                return str(val)
        return "(not configured)"
    return f"{device.get('ip', '')}:{device.get('port', 4370)}"


# Backwards-compat alias (old code used DeviceClient directly)
DeviceClient = ZKTecoClient


# ============================================
# ERPNEXT CLIENT (with API token auth)
# ============================================
class ErpnextClient:
    def __init__(self, device):
        self.device = device
        base = device["erpnext_url"].rstrip("/")
        self.base = base
        self.batch_url = base + BATCH_WEBHOOK_PATH
        self.heartbeat_url = base + HEARTBEAT_PATH
        self.poll_url = base + POLL_COMMANDS_PATH
        self.report_url = base + REPORT_COMMAND_PATH
        self.auth_header = f"token {device['api_key']}:{device['api_secret']}"

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": self.auth_header,
        }

    def test_connection(self):
        """Verify auth using a built-in Frappe method. Returns (ok, message)."""
        try:
            r = requests.get(
                self.base + "/api/method/frappe.auth.get_logged_user",
                headers={"Authorization": self.auth_header},
                timeout=10,
            )
            if r.status_code == 200:
                user = r.json().get("message", "?")
                return True, f"authenticated as {user}"
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return False, str(e)

    # ── Heartbeat ──────────────────────────────────────────────────────
    def heartbeat(self):
        """Tell the server the bridge is alive (updates last_contact_time).
        Returns (ok, message). Network failures are non-fatal — they just
        mean the server will eventually trip the disconnect alert."""
        serial = self.device.get("serial", "")
        if not serial:
            return False, "no serial configured"
        try:
            r = requests.post(
                self.heartbeat_url,
                json={"device_serial": serial},
                headers=self._headers(),
                timeout=10,
            )
        except Exception as e:
            return False, str(e)
        if r.status_code in (401, 403):
            return False, f"auth/whitelist: HTTP {r.status_code}"
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text[:160]}"
        return True, None

    # ── Batch push ─────────────────────────────────────────────────────
    def push_batch(self, records):
        """Send a list of {user_id, timestamp_str} dicts in one POST.

        Returns (per_record_results, message). per_record_results is a list
        the same length as `records`, each entry one of:
            'synced'    — accepted by server
            'skipped'   — already existed
            'error'     — record-level error (employee not found, etc.)
        On full-request failure (network, 5xx, auth) returns ([], message)
        with an empty list and the caller treats every record as errored.
        On auth_fail returns ('auth_fail', message).
        """
        if not records:
            return [], None

        payload_records = [
            {"user_id": str(r["user_id"]), "timestamp": r["timestamp_str"]}
            for r in records
        ]
        payload = {
            "attendance_data": payload_records,
            "device_identifier": self.device.get("serial", ""),
        }

        try:
            r = requests.post(
                self.batch_url,
                json=payload,
                headers=self._headers(),
                timeout=60,
            )
        except Exception as e:
            return [], f"network: {e}"

        if r.status_code in (401, 403):
            return "auth_fail", f"HTTP {r.status_code}: {r.text[:160]}"
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}: {r.text[:200]}"

        try:
            msg = r.json().get("message", {}) or {}
        except Exception:
            return [], f"non-JSON response: {r.text[:160]}"

        # receive_attendance returns process_attendance_records output:
        #   { success, synced, errors, skipped, message,
        #     synced_punches, failed_punches, skipped_punches }
        # Each *_punches list holds "{user_id}_{timestamp}" identifiers so we
        # can resolve every record to a definite outcome.
        synced_set = set(msg.get("synced_punches") or [])
        skipped_set = set(msg.get("skipped_punches") or [])
        failed_set = set(msg.get("failed_punches") or [])
        error_details = msg.get("error_details") or []

        results = []
        for rec in records:
            rid = f"{rec['user_id']}_{rec['timestamp_str']}"
            if rid in synced_set:
                results.append("synced")
            elif rid in skipped_set:
                results.append("skipped")
            elif rid in failed_set:
                results.append("error")
            else:
                # Not individually enumerated (e.g. an older server build).
                # Infer from totals: clean run → synced, otherwise retry it.
                if msg.get("errors", 0) == 0 and msg.get("synced", 0) >= len(records):
                    results.append("synced")
                else:
                    results.append("error")

        return results, "; ".join(str(d) for d in error_details[:3]) or None

    # ── Command tunnel ─────────────────────────────────────────────────
    def poll_commands(self):
        """Ask the server for any Pending commands for this device.
        Returns a list of {name, command_type, payload} dicts, or [] on failure."""
        serial = self.device.get("serial", "")
        if not serial:
            return []
        try:
            r = requests.post(
                self.poll_url,
                json={"device_serial": serial, "max_commands": 5},
                headers=self._headers(),
                timeout=10,
            )
        except Exception:
            return []
        if r.status_code != 200:
            return []
        try:
            msg = r.json().get("message", {}) or {}
        except Exception:
            return []
        return msg.get("commands") or []

    def report_command(self, command_name, status, result_text=""):
        """Tell the server a command finished. status in ('Done','Failed')."""
        serial = self.device.get("serial", "")
        try:
            requests.post(
                self.report_url,
                json={
                    "device_serial": serial,
                    "command": command_name,
                    "status": status,
                    "result": result_text[:4000],
                },
                headers=self._headers(),
                timeout=10,
            )
        except Exception:
            pass


# ============================================
# SYNC ENGINE (background thread)
# ============================================
class SyncEngine:
    def __init__(self, config, logger, status_callback):
        self.config = config
        self.logger = logger
        self.status_callback = status_callback  # fn(device_name, state, msg)
        self.dedup = DedupStore()
        self.paused = False
        self.stop_event = threading.Event()
        self.force_event = threading.Event()
        self.force_subset = None  # None=all, list=specific
        self.force_from_date = None  # if set, used as date_from for the next sync
        self.thread = None
        self.command_thread = None
        self.last_sync_per_device = {}
        self.next_sync_at = None
        self.reschedule_event = threading.Event()
        # Serializes run_sync across the scheduled loop and the command-tunnel
        # thread so they can never sync the same device at once (which would
        # race on the dedup set / state files and double-POST punches).
        self._sync_lock = threading.Lock()

    def start(self):
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        # Command poller — separate thread so it can react to admin-issued
        # Force Sync within COMMAND_POLL_INTERVAL_SEC, independent of how long
        # the sync cycle is set to.
        self.command_thread = threading.Thread(
            target=self._command_poll_loop, daemon=True
        )
        self.command_thread.start()

    def stop(self):
        self.stop_event.set()
        self.force_event.set()

    def force_sync(self, device_names=None, from_date=None):
        """Trigger immediate sync.
        device_names: list to sync only those (None = all).
        from_date: pull records starting this date (None = use saved last_sync_date)."""
        self.force_subset = device_names
        self.force_from_date = from_date
        self.force_event.set()

    def reschedule(self):
        """Called when the user changes sync_interval_minutes.
        Wakes the sleeping thread so the new interval takes effect immediately."""
        interval = int(self.config.get("sync_interval_minutes", 1440)) * 60
        self.next_sync_at = time.time() + interval
        self._save_next_sync(self.next_sync_at)
        self.reschedule_event.set()
        self.force_event.set()  # wakes the thread without triggering a sync

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def _load_next_sync(self):
        if not os.path.exists(NEXT_SYNC_FILE):
            return None
        try:
            with open(NEXT_SYNC_FILE) as f:
                return float(json.load(f).get("next_sync_at", 0))
        except Exception:
            return None

    def _save_next_sync(self, ts):
        try:
            _atomic_write_json(NEXT_SYNC_FILE, {"next_sync_at": ts, "saved_at": time.time()})
        except Exception:
            pass

    def _load_last_sync_dates(self):
        if not os.path.exists(LAST_SYNC_DATES_FILE):
            return {}
        try:
            with open(LAST_SYNC_DATES_FILE) as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _get_last_sync_date(self, device_name):
        """Returns a date or None if never synced before."""
        s = self._load_last_sync_dates().get(device_name)
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None

    def _set_last_sync_date(self, device_name, d):
        dates = self._load_last_sync_dates()
        dates[device_name] = d.strftime("%Y-%m-%d")
        try:
            _atomic_write_json(LAST_SYNC_DATES_FILE, dates, indent=2)
        except Exception:
            pass

    def _loop(self):
        try:
            interval = int(self.config.get("sync_interval_minutes", 1440)) * 60
        except (TypeError, ValueError):
            interval = 1440 * 60
        saved_next = self._load_next_sync()
        now = time.time()

        # If we have a previously scheduled time and it's in the past
        # (computer was off when sync was due) → catch up immediately.
        # If it's in the future → resume that schedule without re-syncing.
        # If no saved state (first run) → sync immediately.
        if saved_next is None:
            self.logger.info("First run — running initial sync")
            self.run_sync()
            self.next_sync_at = time.time() + interval
            self._save_next_sync(self.next_sync_at)
        elif saved_next <= now:
            overdue_min = int((now - saved_next) / 60)
            self.logger.info(
                f"Catch-up sync — scheduled time was {overdue_min} min ago (computer was off?)"
            )
            self.run_sync()
            self.next_sync_at = time.time() + interval
            self._save_next_sync(self.next_sync_at)
        else:
            self.next_sync_at = saved_next
            wait_min = int((saved_next - now) / 60)
            self.logger.info(f"Resuming schedule — next sync in {wait_min} min")

        while not self.stop_event.is_set():
            try:
                interval = int(self.config.get("sync_interval_minutes", 1440)) * 60
            except (TypeError, ValueError):
                interval = 1440 * 60
            if self.next_sync_at is None:
                self.next_sync_at = time.time() + interval
            wait_time = max(0.0, self.next_sync_at - time.time())
            woken = self.force_event.wait(timeout=wait_time)
            if self.stop_event.is_set():
                break

            try:
                # Reschedule signal (e.g. interval changed in GUI) — don't sync,
                # just re-evaluate the wait based on the new next_sync_at.
                if self.reschedule_event.is_set():
                    self.reschedule_event.clear()
                    self.force_event.clear()
                    remaining = int(self.next_sync_at - time.time())
                    self.logger.info(f"Schedule updated — next sync in {remaining}s")
                    continue

                if woken:
                    self.force_event.clear()
                    subset = self.force_subset
                    from_date = self.force_from_date
                    self.force_subset = None
                    self.force_from_date = None
                    self.run_sync(subset, from_date_override=from_date)
                    # Force-sync does NOT reset the scheduled time —
                    # the regular cycle stays on its rhythm.
                elif not self.paused:
                    self.run_sync()
                    self.next_sync_at = time.time() + interval
                    self._save_next_sync(self.next_sync_at)
            except Exception:
                # Never let the scheduling thread die — log and keep the cycle
                # alive so syncing resumes on the next tick.
                self.logger.exception("sync loop iteration failed (recovered)")
                self.force_event.clear()
                if self.next_sync_at is None or self.next_sync_at <= time.time():
                    self.next_sync_at = time.time() + interval

    def run_sync(self, device_names=None, from_date_override=None):
        # Hold the lock for the whole run so a force-sync from the command
        # thread can't interleave with the scheduled cycle. Per-device errors
        # are caught here so one bad device can never kill the sync thread.
        with self._sync_lock:
            devices = self.config.get("devices", [])
            if device_names is not None:
                devices = [d for d in devices if d.get("name") in device_names]
            for device in devices:
                if self.stop_event.is_set():
                    return
                try:
                    self._sync_one(device, from_date_override=from_date_override)
                except Exception as e:
                    name = device.get("name", device.get("ip", "?"))
                    self.logger.exception(f"[{name}] sync crashed (recovered)")
                    try:
                        self.status_callback(name, "error", f"internal error: {str(e)[:80]}")
                    except Exception:
                        pass

    def _sync_one(self, device, from_date_override=None):
        name = device["name"]
        self.status_callback(name, "syncing", "connecting…")
        self.logger.info(f"[{name}] sync_cycle: starting")

        client = make_device_client(
            device,
            timeout=int(self.config.get("device_timeout_seconds", 5)),
            retries=int(self.config.get("network_probe_retries", 3)),
        )

        today = date.today()

        if from_date_override is not None:
            date_from = from_date_override
            self.logger.info(
                f"[{name}] manual sync from {date_from} (overriding saved last_sync_date)"
            )
        else:
            last_sync_date = self._get_last_sync_date(name)
            if last_sync_date is None:
                self.logger.info(
                    f"[{name}] no previous sync date — pulling ALL records from device (first run / fresh install)"
                )
                date_from = None  # fetch everything on device
            else:
                date_from = last_sync_date
                self.logger.info(
                    f"[{name}] last synced {last_sync_date}; fetching from that date through today"
                )

        # No upper bound: if the device clock runs ahead, punches stamped in
        # the "future" must still be captured rather than silently dropped by a
        # date_to=today cutoff. The dedup set keeps re-fetches cheap.
        attendances, status = client.fetch_attendance(date_from=date_from, date_to=None)

        if status == "UNREACHABLE":
            if (device.get("type") or "").lower() == "htms":
                self.logger.warning(
                    f"[{name}] HTMS source unreachable: {device_address(device)} "
                    f"(folder or HAMS.mdb missing)"
                )
                self.status_callback(name, "unreachable", f"{device_address(device)} not found")
            else:
                self.logger.warning(
                    f"[{name}] device unreachable: {device_address(device)} "
                    f"(timeout after {self.config.get('device_timeout_seconds', 5)}s "
                    f"x {self.config.get('network_probe_retries', 3)} retries)"
                )
                self.status_callback(name, "unreachable", f"{device['ip']} not on network")
            return

        if status != "OK":
            self.logger.error(f"[{name}] fetch failed: {status}")
            self.status_callback(name, "error", status[:80])
            return

        self.logger.info(f"[{name}] fetched {len(attendances)} records")
        self.status_callback(
            name, "syncing", f"fetched {len(attendances)} record(s) — checking for new…"
        )

        erpnext = ErpnextClient(device)

        # Heartbeat first — server learns the bridge is alive even when the
        # device has no new punches. Failures here don't block the data sync.
        hb_ok, hb_err = erpnext.heartbeat()
        if not hb_ok:
            self.logger.warning(f"[{name}] heartbeat failed: {hb_err}")

        # Filter out records already in the local dedup set so we don't even
        # serialize them into the batch payload.
        to_send = []  # list of (key, {user_id, timestamp_str})
        skipped = 0
        serial = device.get("serial", "")
        for att in attendances:
            if self.stop_event.is_set():
                return
            ts_str = att.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            key = f"{serial}_{att.user_id}_{ts_str}"
            if self.dedup.is_synced(key):
                skipped += 1
                continue
            to_send.append((key, {"user_id": att.user_id, "timestamp_str": ts_str}))

        total_new = len(to_send)
        if total_new:
            self.status_callback(name, "syncing", f"pushing {total_new} new punch(es)…")

        synced = errors = 0
        last_err = None

        for batch_start in range(0, len(to_send), BATCH_SIZE):
            if self.stop_event.is_set():
                self.dedup.save()
                return
            batch = to_send[batch_start:batch_start + BATCH_SIZE]
            keys = [k for (k, _) in batch]
            records = [r for (_, r) in batch]

            self.status_callback(
                name, "syncing",
                f"pushing {min(batch_start + BATCH_SIZE, total_new)}/{total_new}…",
            )
            results, err = erpnext.push_batch(records)

            if results == "auth_fail":
                self.logger.error(f"[{name}] auth failed: {err}")
                self.status_callback(name, "auth_fail", err or "401/403")
                self.dedup.save()
                return

            if not results:
                # Whole batch failed (network / 5xx). Treat all as errors and
                # let the next cycle retry — dedup marks are only added below
                # for records the server confirmed.
                errors += len(records)
                last_err = err
                self.logger.error(
                    f"[{name}] batch push failed ({len(records)} records): {err}"
                )
                continue

            for k, outcome in zip(keys, results):
                if outcome == "synced":
                    synced += 1
                    self.dedup.mark(k)
                elif outcome == "skipped":
                    # Permanently unprocessable for now (e.g. employee not yet
                    # registered). NOT dedup-marked on purpose: if the employee
                    # is added while the punch is still in the fetch window, the
                    # next cycle resends it and it goes through. Not an error.
                    skipped += 1
                else:
                    errors += 1
                    last_err = err

        self.dedup.save()
        self.last_sync_per_device[name] = datetime.now().strftime("%H:%M:%S")
        # Save today's date as the last sync date so next cycle starts from here.
        # Done regardless of per-record push errors — failed records remain on the
        # device, and once the underlying issue is fixed they'll be picked up on the
        # next pass via dedup tracking.
        self._set_last_sync_date(name, today)
        self.logger.info(
            f"[{name}] sync_cycle: synced={synced} skipped={skipped} errors={errors}; "
            f"last_sync_date saved as {today}"
        )

        if errors > 0:
            self.status_callback(name, "error", f"{errors} errors ({last_err or 'see log'})")
        else:
            self.status_callback(name, "ok", f"{synced} new, {skipped} skipped")

    # ──────────────────────────────────────────────────────────────────
    # COMMAND POLLER — pulls Pending commands from the server and runs them.
    # ──────────────────────────────────────────────────────────────────
    def _command_poll_loop(self):
        """Every COMMAND_POLL_INTERVAL_SEC, ask the server for any pending
        commands for each configured device and dispatch them. Runs forever
        until stop_event is set. Failures are swallowed and logged — this
        loop must never crash the bridge."""
        # Wait a few seconds after startup so the main sync thread can settle.
        if self.stop_event.wait(timeout=5):
            return
        while not self.stop_event.is_set():
            try:
                for device in self.config.get("devices", []):
                    if self.stop_event.is_set():
                        return
                    self._poll_and_dispatch(device)
            except Exception:
                self.logger.exception("command poll loop error")
            # Sleep, but break out early if stop is signalled.
            if self.stop_event.wait(timeout=COMMAND_POLL_INTERVAL_SEC):
                return

    def _poll_and_dispatch(self, device):
        if not device.get("serial"):
            return  # device without serial can't auth against the tunnel
        erpnext = ErpnextClient(device)
        commands = erpnext.poll_commands()
        if not commands:
            return
        name = device["name"]
        self.logger.info(f"[{name}] received {len(commands)} command(s) from server")
        for cmd in commands:
            cmd_name = cmd.get("name")
            cmd_type = cmd.get("command_type")
            payload = cmd.get("payload") or {}
            self.logger.info(f"[{name}] running command {cmd_name} ({cmd_type})")
            status, result = self._run_command(device, cmd_type, payload)
            erpnext.report_command(cmd_name, status, result)
            self.logger.info(
                f"[{name}] command {cmd_name} ({cmd_type}) -> {status}: {result[:120]}"
            )

    def _run_command(self, device, cmd_type, payload):
        """Execute one command. Returns (status, result_text) where status is
        'Done' or 'Failed'. Never raises — exceptions become Failed."""
        try:
            if cmd_type == "force_sync":
                # Run a sync of just this device, optionally with a date override.
                from_date_raw = payload.get("from_date")
                from_date = None
                if from_date_raw:
                    try:
                        from_date = datetime.strptime(from_date_raw, "%Y-%m-%d").date()
                    except ValueError:
                        return "Failed", f"invalid from_date {from_date_raw!r} (need YYYY-MM-DD)"
                self.run_sync(device_names=[device["name"]], from_date_override=from_date)
                return "Done", f"force_sync executed (from_date={from_date or 'last_sync_date'})"

            if cmd_type == "test_connection":
                client = make_device_client(
                    device,
                    timeout=int(self.config.get("device_timeout_seconds", 5)),
                    retries=int(self.config.get("network_probe_retries", 3)),
                )
                ok = client.probe_network()
                if ok:
                    return "Done", f"device {device_address(device)} reachable"
                return "Failed", f"device {device_address(device)} unreachable"

            return "Failed", f"unsupported command_type {cmd_type!r}"
        except Exception as e:
            self.logger.exception(f"command {cmd_type} crashed")
            return "Failed", f"exception: {e}"


# ============================================
# SETUP WIZARD
# ============================================
class SetupWizard:
    def __init__(self, parent, config=None, on_save=None):
        self.config = (config or DEFAULT_CONFIG).copy()
        self.config.setdefault("devices", [])
        self.on_save = on_save
        self.parent = parent

        self.window = Toplevel(parent) if parent.winfo_exists() else Tk()
        self.window.title("K40 Bridge Setup")
        self.window.geometry("780x640")
        self.window.minsize(680, 540)

        # One list of row-widget dicts per section; both feed the same flat
        # config["devices"] list, discriminated by each entry's "type".
        self.device_rows = []
        self.software_rows = []
        self._build()

    def _build(self):
        # ── Step 1: ERPNext Connection ──
        f1 = ttk.LabelFrame(self.window, text="Step 1: ERPNext Connection (used by all devices below)")
        f1.pack(fill="x", padx=10, pady=6)

        ttk.Label(f1, text="ERPNext URL:").grid(row=0, column=0, sticky="e", padx=6, pady=3)
        self.url_entry = ttk.Entry(f1, width=58)
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=3)

        ttk.Label(f1, text="API Key:").grid(row=1, column=0, sticky="e", padx=6, pady=3)
        self.key_entry = ttk.Entry(f1, width=58)
        self.key_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=3)

        ttk.Label(f1, text="API Secret:").grid(row=2, column=0, sticky="e", padx=6, pady=3)
        self.secret_entry = ttk.Entry(f1, width=58, show="*")
        self.secret_entry.grid(row=2, column=1, sticky="ew", padx=6, pady=3)

        ttk.Button(f1, text="Test Connection", command=self._test).grid(row=3, column=1, sticky="w", padx=6, pady=3)
        self.test_label = ttk.Label(f1, text="")
        self.test_label.grid(row=4, column=1, sticky="w", padx=6, pady=3)

        # ── Step 2a: Direct device connections ──
        f2 = ttk.LabelFrame(self.window, text="Step 2a: Direct Device Connection (polled over the LAN)")
        f2.pack(fill="both", expand=True, padx=10, pady=(6, 3))
        ttk.Label(
            f2,
            text=(
                "Biometric units the bridge reaches over the network. Enter the "
                "DEVICE's LAN address (not this PC) — find it on the device under "
                "Menu → Comm. → Ethernet → IP."
            ),
            foreground="gray", wraplength=720, justify="left",
        ).pack(fill="x", padx=8, pady=(4, 4))

        self.devices_frame = ttk.Frame(f2)
        self.devices_frame.pack(fill="both", expand=True, padx=6)
        ttk.Button(f2, text="+ Add Device", command=lambda: self._add_row("device")).pack(pady=4)

        # ── Step 2b: Attendance software / database sources ──
        f2b = ttk.LabelFrame(self.window, text="Step 2b: Attendance Software / Database")
        f2b.pack(fill="both", expand=True, padx=10, pady=(3, 6))
        ttk.Label(
            f2b,
            text=(
                "Read punches from attendance software's own database/export "
                "(for controllers that don't speak a network protocol). Pick the "
                "software and point it at its data folder."
            ),
            foreground="gray", wraplength=720, justify="left",
        ).pack(fill="x", padx=8, pady=(4, 4))

        self.software_frame = ttk.Frame(f2b)
        self.software_frame.pack(fill="both", expand=True, padx=6)
        ttk.Button(f2b, text="+ Add Software Source",
                   command=lambda: self._add_row("software")).pack(pady=4)

        # ── Step 3: Sync Frequency ──
        f3 = ttk.LabelFrame(self.window, text="Step 3: Sync Frequency")
        f3.pack(fill="x", padx=10, pady=6)
        ttk.Label(f3, text="Sync every:").grid(row=0, column=0, sticky="e", padx=6, pady=3)
        self.interval_var = StringVar(value="1 day")
        ttk.Combobox(
            f3,
            textvariable=self.interval_var,
            values=[name for name, _ in INTERVAL_OPTIONS],
            state="readonly",
            width=16,
        ).grid(row=0, column=1, sticky="w", padx=6, pady=3)
        ttk.Label(
            f3,
            text="(Use the Force Sync Now button for ad-hoc real-time data.)",
            foreground="gray",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=2)

        # ── Buttons ──
        btns = ttk.Frame(self.window)
        btns.pack(fill="x", padx=10, pady=8)
        ttk.Button(btns, text="Save & Start", command=self._save).pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.window.destroy).pack(side="right", padx=4)

        self._populate_from_config()

    def _populate_from_config(self):
        existing = self.config.get("devices", [])
        if existing:
            first = existing[0]
            self.url_entry.insert(0, first.get("erpnext_url", ""))
            self.key_entry.insert(0, first.get("api_key", ""))
            self.secret_entry.insert(0, first.get("api_secret", ""))
            for d in existing:
                meta = integration_meta(d.get("type")) or INTEGRATIONS["zkteco"]
                self._add_row(meta["category"], d)
            mins = int(self.config.get("sync_interval_minutes", 1440))
            for name, m in INTERVAL_OPTIONS:
                if m == mins:
                    self.interval_var.set(name)
                    break
        else:
            # Fresh setup: offer one empty device row to start with.
            self._add_row("device")

    def _add_row(self, category, device=None):
        """Add one source row to the given section ("device"|"software"). Fields
        are rendered from the selected integration's schema, so the row reshapes
        itself when the Type dropdown changes."""
        choices = integrations_in(category)
        default_type = device.get("type") if device else choices[0][0]
        device = device or {"type": default_type}
        rows_list = self.device_rows if category == "device" else self.software_rows
        parent = self.devices_frame if category == "device" else self.software_frame

        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        entries = {"frame": row, "category": category, "field_entries": {}}

        # Name + Type (fixed leading widgets)
        ttk.Label(row, text="Name").grid(row=0, column=0, padx=(2, 1))
        name_e = ttk.Entry(row, width=14)
        name_e.insert(0, device.get("name", ""))
        name_e.grid(row=0, column=1, padx=(0, 6))
        entries["name"] = name_e

        type_var = StringVar(value=default_type)
        entries["type"] = type_var
        ttk.Combobox(
            row, textvariable=type_var,
            values=[f"{k}" for k, _ in choices],
            state="readonly", width=11,
        ).grid(row=0, column=2, padx=(0, 6))

        # Container the dynamic per-type fields get re-rendered into.
        fields_frame = ttk.Frame(row)
        fields_frame.grid(row=0, column=3, padx=2)
        entries["fields_frame"] = fields_frame

        # Serial + Test + remove (fixed trailing widgets)
        ttk.Label(row, text="Serial").grid(row=0, column=4, padx=(6, 1))
        serial_e = ttk.Entry(row, width=15)
        serial_e.insert(0, device.get("serial", ""))
        serial_e.grid(row=0, column=5, padx=(0, 6))
        entries["serial"] = serial_e

        test_btn = ttk.Button(row, text="Test", width=7,
                              command=lambda: self._test_device(entries))
        test_btn.grid(row=0, column=6, padx=2)
        entries["test_btn"] = test_btn

        def remove():
            row.destroy()
            rows_list[:] = [r for r in rows_list if r["frame"] is not row]

        ttk.Button(row, text="X", width=3, command=remove).grid(row=0, column=7, padx=2)

        # Initial field render + re-render on type change. _prev_device carries
        # the saved values into the first render; later renders use field
        # defaults so switching type doesn't show the previous type's data.
        self._render_fields(entries, device)
        type_var.trace_add("write", lambda *_: self._render_fields(entries, None))

        rows_list.append(entries)

    def _render_fields(self, entries, device):
        """(Re)build the dynamic field widgets for a row from its integration's
        schema. device=None means use schema defaults (after a type switch)."""
        frame = entries["fields_frame"]
        for child in frame.winfo_children():
            child.destroy()
        entries["field_entries"] = {}

        meta = integration_meta(entries["type"].get()) or INTEGRATIONS["zkteco"]
        col = 0
        for spec in meta["fields"]:
            ttk.Label(frame, text=spec["label"]).grid(row=0, column=col, padx=(2, 1))
            col += 1
            ent = ttk.Entry(frame, width=spec.get("width", 12),
                            show="*" if spec.get("secret") else "")
            value = ""
            if device is not None:
                value = device.get(spec["key"], "")
            if value in ("", None):
                value = spec.get("default", "")
            ent.insert(0, str(value))
            ent.grid(row=0, column=col, padx=(0, 6))
            col += 1
            entries["field_entries"][spec["key"]] = (ent, spec)

            if spec.get("browse") == "dir":
                def pick(e=ent):
                    d = filedialog.askdirectory(title="Select the data folder")
                    if d:
                        e.delete(0, "end")
                        e.insert(0, d)
                ttk.Button(frame, text="…", width=3, command=pick).grid(row=0, column=col, padx=(0, 4))
                col += 1

        # Hint line for this integration, under the fields.
        ttk.Label(frame, text=meta.get("help", ""), foreground="gray",
                  wraplength=520, justify="left").grid(
            row=1, column=0, columnspan=col, sticky="w", pady=(1, 0))

    def _test(self):
        url = self.url_entry.get().strip()
        key = self.key_entry.get().strip()
        secret = self.secret_entry.get().strip()
        if not (url and key and secret):
            self.test_label.config(text="● Fill all fields first", foreground="orange")
            return
        self.test_label.config(text="● Testing...", foreground="gray")
        self.window.update_idletasks()
        client = ErpnextClient(
            {"erpnext_url": url, "api_key": key, "api_secret": secret, "serial": ""}
        )
        ok, msg = client.test_connection()
        if ok:
            self.test_label.config(text=f"● Connected ({msg})", foreground="green")
        else:
            self.test_label.config(text=f"● Failed: {msg[:80]}", foreground="red")

    def _row_to_device(self, entries, url="", key="", secret=""):
        """Build a device-config dict from a row's widgets, applying each
        field's kind/default. Returns (device_dict, missing_required_labels)."""
        dtype = entries["type"].get().strip().lower()
        meta = integration_meta(dtype) or INTEGRATIONS["zkteco"]
        dev = {
            "name": entries["name"].get().strip(),
            "type": dtype,
            "serial": entries["serial"].get().strip(),
            "erpnext_url": url,
            "api_key": key,
            "api_secret": secret,
            "latitude": 27.7228,
            "longitude": 85.3211,
        }
        missing = []
        if not dev["name"]:
            missing.append("Name")
        if not dev["serial"]:
            missing.append("Serial")
        for fkey, (widget, spec) in entries["field_entries"].items():
            raw = widget.get().strip()
            if not raw and not spec.get("optional"):
                missing.append(spec["label"])
            if spec.get("kind") == "int":
                try:
                    dev[fkey] = int(raw) if raw else int(spec.get("default") or 0)
                except ValueError:
                    dev[fkey] = int(spec.get("default") or 0)
            else:
                dev[fkey] = raw
        return dev, missing

    def _test_device(self, entries):
        """Test one source row. Shows result via messagebox."""
        dev, missing = self._row_to_device(entries)
        name = dev["name"] or "(unnamed)"
        dtype = dev["type"]
        # For a test we don't require the serial (that's an ERPNext-side check),
        # only the connection inputs.
        missing = [m for m in missing if m != "Serial"]
        if missing:
            messagebox.showwarning("Test", f"Fill in: {', '.join(missing)}")
            return

        entries["test_btn"].config(text="...")
        self.window.update_idletasks()

        def worker():
            client = make_device_client(dev, timeout=5, retries=2)
            today_ = date.today()
            records, status = client.fetch_attendance(date_from=today_, date_to=today_)
            self.window.after(0, lambda: self._show_test_result(name, dtype, status, len(records), entries))

        threading.Thread(target=worker, daemon=True).start()

    def _show_test_result(self, name, dtype, status, count, entries):
        entries["test_btn"].config(text="Test")
        if status == "OK":
            messagebox.showinfo(
                "Device Test",
                f"✓ {name} ({dtype})\n\nConnected successfully.\nFound {count} record(s) for today.",
            )
        elif status == "UNREACHABLE":
            meta = integration_meta(dtype)
            is_software = bool(meta and meta["category"] == "software")
            messagebox.showerror(
                "Device Test",
                f"✗ {name}\n\nData source not found — check the folder/path."
                if is_software
                else f"✗ {name}\n\nUnreachable on the network. Check IP / port / cable.",
            )
        elif status == "AUTH_FAIL":
            messagebox.showerror(
                "Device Test",
                f"✗ {name}\n\nAuthentication failed. Check username / password / comm key.",
            )
        else:
            messagebox.showerror("Device Test", f"✗ {name}\n\n{status}")

    def _save(self):
        url = self.url_entry.get().strip().rstrip("/")
        key = self.key_entry.get().strip()
        secret = self.secret_entry.get().strip()

        if not (url and key and secret):
            messagebox.showerror("Missing fields", "Please fill ERPNext URL, API Key, and API Secret.")
            return

        # Serial is required for every source: it's the dedup key, the
        # heartbeat/command-tunnel identity, and the key the server matches
        # against a registered+enabled Biometric Device (unknown → 403).
        devices = []
        problems = []
        for r in self.device_rows + self.software_rows:
            # An untouched, entirely-blank row is skipped silently.
            blank = (not r["name"].get().strip() and not r["serial"].get().strip()
                     and all(not w.get().strip() for w, _ in r["field_entries"].values()))
            if blank:
                continue
            dev, missing = self._row_to_device(r, url, key, secret)
            if missing:
                label = dev["name"] or f"({dev['type']} row)"
                problems.append(f"• {label}: missing {', '.join(missing)}")
                continue
            devices.append(dev)

        if problems:
            messagebox.showerror("Incomplete rows", "\n".join(problems))
            return
        if not devices:
            messagebox.showerror(
                "No sources",
                "Add at least one device or software source with a Name, Serial, "
                "and its connection details.",
            )
            return

        interval_min = 1440
        for name, mins in INTERVAL_OPTIONS:
            if name == self.interval_var.get():
                interval_min = mins
                break

        self.config["devices"] = devices
        self.config["sync_interval_minutes"] = interval_min
        for k, v in DEFAULT_CONFIG.items():
            self.config.setdefault(k, v)

        save_config(self.config)
        self.window.destroy()
        if self.on_save:
            self.on_save(self.config)


# ============================================
# SINGLE INSTANCE  (one bridge per machine + "summon" channel)
# ============================================
# A loopback-only socket doubles as the single-instance lock AND the channel
# the user uses to open the app: the running (possibly invisible) instance
# binds the port; a second launch fails to bind, connects, and asks the
# running instance to show its window — then exits. Binding 127.0.0.1 does not
# trip the Windows firewall.
SINGLE_INSTANCE_PORT = 47291


def acquire_single_instance():
    """Become the one running bridge. Returns the bound listening socket if
    we're the primary, or None if another bridge already holds the port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        s.listen(5)
        return s
    except OSError:
        s.close()
        return None


def signal_existing_instance():
    """Ask the already-running bridge to show its window. Returns True only if
    a bridge actually answered, so a non-bridge app squatting on the port
    doesn't make us silently refuse to start."""
    try:
        with socket.create_connection(("127.0.0.1", SINGLE_INSTANCE_PORT), timeout=3) as c:
            c.sendall(b"SHOW\n")
            c.settimeout(3)
            return c.recv(16).strip() == b"OK"
    except OSError:
        return False


# ============================================
# CONTROL PANEL
# ============================================
class ControlPanel:
    def __init__(self, config, primary_sock=None, start_hidden=False):
        self.config = config
        # Listening socket from acquire_single_instance(): kept open for our
        # whole lifetime so no second instance can start, and used to receive
        # "show the window" requests when the user opens the app again.
        self.primary_sock = primary_sock
        self.root = Tk()
        self.root.title(f"K40 Bridge  v{VERSION}")
        self.root.geometry("960x640")
        self.root.minsize(820, 520)

        self.logger = setup_logging(config, gui_callback=self._on_log)
        self.engine = SyncEngine(config, self.logger, self._on_status)
        # Latest version learned from GitHub, or None if not checked / up to date.
        # Drives whether clicking the banner kicks off a self-update.
        self._known_latest_version = None
        self._self_update_running = False
        self.tray_icon = None
        # Whether the window is currently on screen. Drives auto-update: an
        # invisible background instance installs updates on its own (no click);
        # a visible one shows the banner so it doesn't interrupt active use.
        self._visible = False
        self._build()
        self.engine.start()
        self._tick()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # Listen for a second launch asking us to pop the window.
        self._start_summon_listener()

        if start_hidden:
            # Invisible background mode (scheduler / auto-start): no window and
            # NO tray icon — the person at the PC sees nothing at all. Posting
            # still runs. The UI appears only when someone opens the app, which
            # summons us through the single-instance listener above.
            self.root.withdraw()
            self.logger.info("Started invisibly — posting in background (no window, no tray)")
        else:
            # Launched by hand → show the window (and tray while it's open).
            self.root.after(0, self._reveal)

        # One-shot update check at startup, then a daily background re-check.
        threading.Thread(target=self._check_update_quiet, daemon=True).start()
        threading.Thread(target=self._periodic_update_check_loop, daemon=True).start()

    # ── Visibility: invisible ⇆ window+tray ────────────────────────────
    def _reveal(self):
        """Bring the app on screen: create the tray icon and show the window.
        Safe to call repeatedly (idempotent)."""
        self._ensure_tray()
        self._visible = True
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def _start_summon_listener(self):
        if self.primary_sock is None:
            return
        threading.Thread(target=self._summon_loop, daemon=True).start()

    def _summon_loop(self):
        """Accept connections from second launches and pop the window for each.
        Never crashes the app — all errors are swallowed."""
        sock = self.primary_sock
        sock.settimeout(1.0)
        while not self.engine.stop_event.is_set():
            try:
                conn, _ = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break  # socket closed on exit
            try:
                data = conn.recv(64)
                if b"SHOW" in data:
                    self.root.after(0, self._reveal)
                    try:
                        conn.sendall(b"OK\n")
                    except OSError:
                        pass
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def _build(self):
        # Per-device latest state — drives the health summary and the colored
        # status rows so the operator can tell at a glance what's happening.
        self._device_state = {}

        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=6)

        self.status_label = ttk.Label(top, text="● Running", foreground="#1a7f37",
                                      font=("TkDefaultFont", 11, "bold"))
        self.status_label.pack(side="left")
        # Live health roll-up (✓ ok · ⚠ unreachable · ✗ error). Filled by
        # _refresh_summary() whenever a device reports in.
        self.summary_label = ttk.Label(top, text="", foreground="#57606a")
        self.summary_label.pack(side="left", padx=12)
        self.countdown_label = ttk.Label(top, text="", foreground="#57606a")
        self.countdown_label.pack(side="left", padx=12)

        self.update_label = ttk.Label(top, text="", foreground="blue", cursor="hand2")
        self.update_label.pack(side="left", padx=12)
        # When a newer version is known, clicking the banner triggers the
        # in-app self-update. Falls back to opening the releases page if the
        # update server hasn't been reached yet.
        self.update_label.bind("<Button-1>", lambda e: self._handle_update_click())

        self.pause_btn = ttk.Button(top, text="Pause", command=self._toggle_pause)
        self.pause_btn.pack(side="right", padx=2)
        ttk.Button(top, text="Edit Config", command=self._edit_config).pack(side="right", padx=2)
        ttk.Button(top, text="Check Updates", command=self._check_update_manual).pack(side="right", padx=2)

        cols = ("name", "ip", "last_sync", "status")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings", height=10)
        self.tree.heading("name", text="Name")
        self.tree.heading("ip", text="Address")
        self.tree.heading("last_sync", text="Last Sync")
        self.tree.heading("status", text="Status")
        self.tree.column("name", width=180)
        self.tree.column("ip", width=170)
        self.tree.column("last_sync", width=110)
        self.tree.column("status", width=440)

        # Color each row by health so the table reads at a glance: green = ok,
        # blue = actively syncing, orange = unreachable, red = error/auth,
        # gray = idle/pending. Row tags carry both a foreground and a light tint.
        self.tree.tag_configure("ok",          foreground="#0a5d2a", background="#e6f4ea")
        self.tree.tag_configure("syncing",     foreground="#0a4fa0", background="#ddf4ff")
        self.tree.tag_configure("error",       foreground="#a40e26", background="#ffebe9")
        self.tree.tag_configure("auth_fail",   foreground="#a40e26", background="#ffebe9")
        self.tree.tag_configure("unreachable", foreground="#8a3800", background="#fff1e5")
        self.tree.tag_configure("pending",     foreground="#57606a")
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)

        # One-line legend so the glyphs/colors are self-explanatory.
        ttk.Label(
            self.root,
            text="Legend:   ● OK     ⟳ Syncing     ● Unreachable     ● Error / Auth     ○ Idle",
            foreground="#57606a", font=("TkDefaultFont", 8),
        ).pack(anchor="w", padx=12)

        self._populate_tree()

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", padx=10, pady=4)
        ttk.Button(btns, text="Force Sync All", command=self._force_all).pack(side="left", padx=2)
        ttk.Button(btns, text="Force Sync Selected", command=self._force_selected).pack(side="left", padx=2)
        ttk.Button(btns, text="Sync from Date…", command=self._sync_from_date).pack(side="left", padx=2)

        # Auto-start button (Windows only)
        if IS_WINDOWS:
            self.autostart_btn = ttk.Button(btns, text="…", command=self._toggle_autostart)
            self.autostart_btn.pack(side="left", padx=12)
            self._refresh_autostart_label()

        # Quit = full stop. The window's X only hides the app (posting keeps
        # running), so this is the explicit "actually stop" control.
        ttk.Button(btns, text="Quit Bridge", command=self._quit_app).pack(side="right", padx=2)
        ttk.Button(btns, text="Open Log Folder", command=self._open_log_folder).pack(side="right", padx=2)

        ttk.Label(self.root, text="Recent log:").pack(anchor="w", padx=10, pady=(6, 0))
        self.log_text = ScrolledText(self.root, height=10, state="disabled", font=("Courier", 9))
        # Tint log lines by severity so warnings/errors jump out of the stream.
        self.log_text.tag_configure("ERROR", foreground="#a40e26")
        self.log_text.tag_configure("WARN", foreground="#8a3800")
        self.log_text.tag_configure("OK", foreground="#0a5d2a")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=6)

    def _populate_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for d in self.config.get("devices", []):
            self._device_state[d["name"]] = "pending"
            self.tree.insert(
                "",
                "end",
                iid=d["name"],
                values=(d["name"], device_address(d), "—", "○ Idle — waiting for first sync"),
                tags=("pending",),
            )
        self._refresh_summary()

    def _on_status(self, name, state, msg):
        self.root.after(0, lambda: self._update_status(name, state, msg))

    # Glyph + human label per state. The glyph shape (not just color) carries the
    # meaning so the table still reads in greyscale / for color-blind users.
    _STATE_GLYPHS = {
        "syncing":     "⟳ Syncing…",
        "ok":          "● OK",
        "unreachable": "● Unreachable",
        "error":       "● Error",
        "auth_fail":   "● Auth failed",
        "pending":     "○ Idle",
    }

    def _update_status(self, name, state, msg):
        if not self.tree.exists(name):
            return
        last_sync = self.engine.last_sync_per_device.get(name, "—")
        device = next((d for d in self.config["devices"] if d["name"] == name), None)
        ip_port = device_address(device) if device else ""

        glyph = self._STATE_GLYPHS.get(state, state)
        label = f"{glyph} — {msg}" if msg else glyph

        self._device_state[name] = state
        tag = state if state in self._STATE_GLYPHS else "pending"
        self.tree.item(name, values=(name, ip_port, last_sync, label), tags=(tag,))
        self._refresh_summary()

    def _refresh_summary(self):
        """Roll up per-device states into the header: a one-glance health line
        plus an activity-aware main status label."""
        states = list(self._device_state.values())
        total = len(states)
        ok = states.count("ok")
        err = states.count("error") + states.count("auth_fail")
        unr = states.count("unreachable")
        syncing = states.count("syncing")
        idle = total - ok - err - unr - syncing

        parts = []
        if ok:
            parts.append(f"✓ {ok} ok")
        if syncing:
            parts.append(f"⟳ {syncing} syncing")
        if unr:
            parts.append(f"⚠ {unr} unreachable")
        if err:
            parts.append(f"✗ {err} error")
        if idle:
            parts.append(f"○ {idle} idle")
        self.summary_label.config(
            text=("   ·   ".join(parts) + f"      ({total} sources)") if total else ""
        )

        # Main label reflects live activity — unless paused, which owns the label.
        if self.engine.paused:
            return
        if syncing:
            self.status_label.config(text="⟳ Syncing…", foreground="#0a4fa0")
        elif err:
            self.status_label.config(text="● Running (with errors)", foreground="#8a3800")
        else:
            self.status_label.config(text="● Running", foreground="#1a7f37")

    def _on_log(self, line):
        self.root.after(0, lambda: self._append_log(line))

    def _append_log(self, line):
        self.log_text.config(state="normal")
        # Tag by severity token in the formatted line ("… ERROR …" / "… WARNING …")
        # or a successful sync summary, so the eye lands on what matters.
        if " ERROR " in line:
            tag = ("ERROR",)
        elif " WARNING " in line or " WARN " in line:
            tag = ("WARN",)
        elif "synced=" in line:
            tag = ("OK",)
        else:
            tag = ()
        self.log_text.insert("end", line + "\n", tag)
        # cap to last 300 lines
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 300:
            self.log_text.delete("1.0", f"{lines - 300}.0")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _force_all(self):
        self.logger.info("Force Sync All triggered from GUI")
        self.engine.force_sync()

    def _force_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a device", "Select one or more rows in the table first.")
            return
        self.logger.info(f"Force Sync Selected from GUI: {list(sel)}")
        self.engine.force_sync(list(sel))

    def _sync_from_date(self):
        """Prompt for a date, then pull all records from that date forward."""
        dlg = Toplevel(self.root)
        dlg.title("Sync from Date")
        dlg.geometry("420x230")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(
            dlg,
            text="Pull all attendance records from this date forward:",
            wraplength=380,
        ).pack(padx=12, pady=(12, 6))

        # Default to 7 days ago — common case is "I noticed records missing recently"
        from datetime import timedelta as _td
        default_date = (date.today() - _td(days=7)).strftime("%Y-%m-%d")

        date_var = StringVar(value=default_date)
        ent = ttk.Entry(dlg, textvariable=date_var, width=20)
        ent.pack(padx=12, pady=4)
        ttk.Label(dlg, text="Format: YYYY-MM-DD", foreground="gray").pack()

        sel = self.tree.selection()
        target = "selected device(s)" if sel else "all devices"
        ttk.Label(
            dlg,
            text=f"This will apply to: {target}.\n(Highlight rows before opening this dialog to limit.)",
            foreground="gray", wraplength=380, justify="center",
        ).pack(padx=12, pady=(6, 6))

        def go():
            s = date_var.get().strip()
            try:
                d = datetime.strptime(s, "%Y-%m-%d").date()
            except ValueError:
                messagebox.showerror("Invalid date", f"'{s}' is not a valid date.\nUse YYYY-MM-DD.")
                return
            if d > date.today():
                messagebox.showerror("Invalid date", "Date is in the future.")
                return
            device_names = list(sel) if sel else None
            self.logger.info(
                f"Sync from Date triggered: from={d}, devices={device_names or 'ALL'}"
            )
            self.engine.force_sync(device_names=device_names, from_date=d)
            dlg.destroy()

        btns = ttk.Frame(dlg)
        btns.pack(pady=10)
        ttk.Button(btns, text="Sync", command=go).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side="left", padx=4)

        ent.focus_set()
        ent.select_range(0, "end")

    def _toggle_pause(self):
        if self.engine.paused:
            self.engine.resume()
            self.status_label.config(text="● Running", foreground="green")
            self.pause_btn.config(text="Pause")
        else:
            self.engine.pause()
            self.status_label.config(text="● Paused", foreground="orange")
            self.pause_btn.config(text="Resume")

    def _edit_config(self):
        SetupWizard(self.root, config=self.config, on_save=self._on_config_saved)

    def _on_config_saved(self, new_config):
        self.config = new_config
        self.engine.config = new_config
        self._populate_tree()
        self.logger.info("Configuration updated from GUI")
        # Recompute next sync based on (possibly new) interval and wake the
        # sleeping thread so the change is immediate, not after old timeout.
        self.engine.reschedule()

    def _open_log_folder(self):
        if sys.platform == "win32":
            os.startfile(APP_DIR)
        elif sys.platform == "darwin":
            os.system(f'open "{APP_DIR}"')
        else:
            os.system(f'xdg-open "{APP_DIR}"')

    def _open_download_page(self):
        import webbrowser
        webbrowser.open(DOWNLOAD_PAGE_URL)

    def _check_update_quiet(self):
        """Run on startup + once a day. If a newer version exists: when the app
        is invisible (unattended background instance) install it automatically;
        when the window is open, just show the banner so we don't interrupt the
        user mid-task."""
        latest, newer = check_for_update()
        if not newer:
            return
        self._known_latest_version = latest
        self.logger.info(f"Update available: v{latest} (running v{VERSION})")
        if not self._visible:
            self.logger.info("Auto-installing update (running unattended in background)")
            self.root.after(0, lambda: self._perform_self_update(latest))
        else:
            self.root.after(0, lambda: self.update_label.config(
                text=f"⬆ v{latest} available — click to install",
                foreground="blue",
            ))

    def _check_update_manual(self):
        """Manual 'Check Updates' button — always shows result + offers self-update."""
        self.update_label.config(text="Checking…", foreground="gray")
        self.root.update_idletasks()

        def worker():
            latest, newer = check_for_update()
            def show():
                if latest is None:
                    self.update_label.config(text="", foreground="blue")
                    messagebox.showwarning("Check Updates", "Could not reach update server.")
                elif newer:
                    self._known_latest_version = latest
                    self.update_label.config(
                        text=f"⬆ v{latest} available — click to install",
                        foreground="blue",
                    )
                    if messagebox.askyesno(
                        "Update Available",
                        f"A newer version is available.\n\n"
                        f"Current: v{VERSION}\n"
                        f"Latest:  v{latest}\n\n"
                        f"Install it now? The bridge will restart automatically.",
                    ):
                        self._perform_self_update(latest)
                else:
                    self._known_latest_version = None
                    self.update_label.config(text=f"✓ Up to date (v{VERSION})", foreground="green")
                    messagebox.showinfo("Check Updates", f"You're running the latest version (v{VERSION}).")
            self.root.after(0, show)

        threading.Thread(target=worker, daemon=True).start()

    def _periodic_update_check_loop(self):
        """Re-check for updates once a day so long-running installs eventually
        notice a new release without needing a restart. Exits when the sync
        engine signals stop."""
        interval_sec = UPDATE_CHECK_INTERVAL_HOURS * 3600
        while not self.engine.stop_event.is_set():
            # Use the engine's stop_event as a sleep so we exit promptly on quit.
            if self.engine.stop_event.wait(timeout=interval_sec):
                return
            try:
                self._check_update_quiet()
            except Exception:
                self.logger.exception("periodic update check failed")

    def _handle_update_click(self):
        """User clicked the update banner. Self-update if we know there's one,
        otherwise just open the releases page so they can browse."""
        if self._self_update_running:
            return
        if self._known_latest_version:
            if messagebox.askyesno(
                "Install Update",
                f"Install K40 Bridge v{self._known_latest_version} now?\n\n"
                f"The bridge will close, the installer will run, and the\n"
                f"bridge will restart automatically. Takes about 30-60 seconds.\n\n"
                f"Make sure no sync is mid-flight you don't want interrupted.",
            ):
                self._perform_self_update(self._known_latest_version)
        else:
            # No known update yet (banner shouldn't be clickable in this state,
            # but be defensive). Open the releases page as a fallback.
            self._open_download_page()

    def _perform_self_update(self, latest):
        """Download the installer, launch it silently, then exit. The installer
        kills any remaining bridge process, overwrites the exe, and relaunches.

        Reentrancy is guarded by self._self_update_running — a second click
        while we're already downloading is a no-op."""
        if self._self_update_running:
            return
        self._self_update_running = True
        self.update_label.config(text=f"Downloading v{latest}…", foreground="gray")
        self.root.update_idletasks()

        def worker():
            try:
                installer_path = self._download_installer(latest)
                if not installer_path:
                    return  # _download_installer already surfaced the error
                self.root.after(0, lambda: self.update_label.config(
                    text=f"Installing v{latest}…", foreground="blue"
                ))
                self._launch_installer_and_exit(installer_path)
            except Exception as e:
                self.logger.exception("self-update failed")
                self._self_update_running = False
                self.root.after(0, lambda: messagebox.showerror(
                    "Update Failed",
                    f"Could not install update: {e}\n\n"
                    f"You can download the installer manually from the releases page."
                ))
                self.root.after(0, lambda: self.update_label.config(
                    text=f"⬆ v{latest} available — click to retry",
                    foreground="orange",
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _stream_download(self, url, dest_path, latest):
        """Stream `url` to `dest_path`, updating the banner with progress.
        Raises on any HTTP error so the caller can try a fallback URL."""
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(64 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded * 100 / total)
                        self.root.after(0, lambda p=pct: self.update_label.config(
                            text=f"Downloading v{latest}… {p}%",
                            foreground="gray",
                        ))

    def _download_installer(self, latest):
        """Stream-download the installer to a temp file with progress updates.
        Returns the path on success, None on failure (caller will see banner
        and dialog from the worker's except block)."""
        import tempfile

        tmp_dir = tempfile.gettempdir()
        installer_path = os.path.join(tmp_dir, f"K40BridgeSetup_{latest}.exe")
        # Version-explicit URL first (always the right version); fall back to the
        # "latest" pointer only if the pinned release/asset can't be reached.
        url = installer_download_url(latest)
        self.logger.info(f"Self-update: downloading {url} → {installer_path}")

        try:
            self._stream_download(url, installer_path, latest)
        except Exception as e:
            self.logger.warning(
                f"Self-update: version-pinned download failed ({e}); "
                f"falling back to {INSTALLER_DOWNLOAD_URL}"
            )
            self._stream_download(INSTALLER_DOWNLOAD_URL, installer_path, latest)

        # Integrity guard before we execute it: confirm we actually got a
        # Windows executable (PE files start with "MZ") of plausible size, not
        # an HTML error page or a truncated download. Full code-signing
        # verification would be the real fix; this stops the worst cases.
        size = os.path.getsize(installer_path)
        with open(installer_path, "rb") as fh:
            magic = fh.read(2)
        if magic != b"MZ" or size < 200_000:
            try:
                os.remove(installer_path)
            except OSError:
                pass
            raise ValueError(
                f"downloaded installer failed integrity check "
                f"(magic={magic!r}, size={size} bytes)"
            )
        self.logger.info(f"Self-update: downloaded {size / (1024 * 1024):.1f} MB")
        return installer_path

    def _launch_installer_and_exit(self, installer_path):
        """Spawn the installer detached, wait a beat, then kill ourselves so
        the installer can overwrite k40_bridge.exe.

        Inno Setup config (installer.iss):
          - CloseApplications=force      → kills the running bridge if needed
          - InitializeSetup → taskkill   → belt-and-suspenders against the tray icon
          - The silent-path [Run] entry  → re-launches the bridge after install

        So this code's only job is: download, spawn, exit. The installer does
        the rest."""
        # `/SILENT` shows a small progress dialog (good UX); `/VERYSILENT` hides
        # everything — pick SILENT so the user sees something is happening.
        # `/SUPPRESSMSGBOXES` skips "are you sure?" prompts.
        # `/NORESTART` ensures Windows doesn't reboot if Inno asks.
        args = [installer_path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
        self.logger.info(f"Self-update: launching installer {args}")

        if IS_WINDOWS:
            # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP so the installer
            # outlives our exit. close_fds=True severs handle inheritance.
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            subprocess.Popen(
                args,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
        else:
            # Linux/macOS — for dev builds. Inno installer is Windows-only,
            # but allow the codepath to run for smoke testing.
            subprocess.Popen(args, close_fds=True)

        # Give the installer a couple of seconds to read our exe into memory
        # before we exit (paranoia — taskkill /F handles it anyway).
        time.sleep(2)
        self.root.after(0, self._force_quit_for_update)

    def _force_quit_for_update(self):
        """Hard-exit the bridge so the installer can replace the running exe.
        Cleans up tray icon and sync engine first, then calls os._exit to
        bypass any lingering atexit handlers that might fight us."""
        self.logger.info("Self-update: exiting to allow installer to proceed")
        try:
            self.engine.stop()
        except Exception:
            pass
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        # Hard exit — the installer's CloseApplications=force will also kill
        # us if this doesn't take effect, so being aggressive is fine.
        os._exit(0)

    def _refresh_autostart_label(self):
        if not IS_WINDOWS or not hasattr(self, "autostart_btn"):
            return
        if autostart_status():
            self.autostart_btn.config(text="Auto-Start: ON")
        else:
            self.autostart_btn.config(text="Enable Auto-Start")

    def _toggle_autostart(self):
        if autostart_status():
            if not messagebox.askyesno(
                "Disable Auto-Start",
                "Disable auto-start on Windows boot?\n\n"
                "(The bridge will only run when you launch it manually.)",
            ):
                return
            ok, msg = autostart_uninstall()
        else:
            ok, msg = autostart_install()

        if ok:
            messagebox.showinfo("Auto-Start", msg)
            self.logger.info(f"Auto-start changed: {msg}")
        else:
            messagebox.showerror("Auto-Start", msg)
            self.logger.warning(f"Auto-start change failed: {msg}")
        self._refresh_autostart_label()

    def _tick(self):
        if self.engine.next_sync_at and not self.engine.paused:
            remaining = max(0, int(self.engine.next_sync_at - time.time()))
            h, rem = divmod(remaining, 3600)
            m, s = divmod(rem, 60)
            if h:
                txt = f"Next sync in: {h}h {m}m"
            elif m:
                txt = f"Next sync in: {m}m {s}s"
            else:
                txt = f"Next sync in: {s}s"
            self.countdown_label.config(text=txt)
        else:
            self.countdown_label.config(text="")
        self.root.after(1000, self._tick)

    def _ensure_tray(self):
        """Create + run the tray icon if it isn't already showing. The tray
        only exists while the app is open; closing the window removes it."""
        if not HAS_TRAY or self.tray_icon is not None:
            return
        try:
            img = Image.new("RGB", (64, 64), color=(40, 100, 200))
            d = ImageDraw.Draw(img)
            d.rectangle((10, 18, 54, 46), outline=(255, 255, 255), width=3)
            d.text((22, 22), "K40", fill=(255, 255, 255))

            menu = pystray.Menu(
                pystray.MenuItem("Show", self._show_window, default=True),
                pystray.MenuItem("Force Sync All", lambda: self.engine.force_sync()),
                pystray.MenuItem("Exit", self._real_exit),
            )
            self.tray_icon = pystray.Icon("k40_bridge", img, "K40 Bridge", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            self.logger.warning(f"Tray icon could not start: {e}")
            self.tray_icon = None

    def _remove_tray(self):
        """Stop + drop the tray icon so the app becomes fully invisible again."""
        icon, self.tray_icon = self.tray_icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    def _show_window(self, *_):
        self.root.after(0, self._reveal)

    def _on_close(self):
        """X button = go fully invisible (no window, no tray). Posting keeps
        running in the background; the app reappears only when someone opens it
        again. Use the Quit button (or tray → Exit) to actually stop."""
        self._visible = False
        self.root.withdraw()
        self._remove_tray()
        self.logger.info("Hidden — posting continues in background (no window, no tray)")

    def _quit_app(self):
        """Quit button — full stop, with a warning since X is the keep-running
        action."""
        if messagebox.askyesno(
            "Quit K40 Bridge",
            "Quitting STOPS attendance posting until the bridge is started again "
            "(e.g. at next login).\n\n"
            "To keep posting in the background, use the X button instead — it "
            "just hides the app.\n\nQuit now?",
        ):
            self._real_exit()

    def _real_exit(self, *_):
        """Fully exit the bridge: stop syncing, drop the tray, release the
        single-instance lock, and close the window."""
        self.engine.stop()
        self._remove_tray()
        try:
            if self.primary_sock:
                self.primary_sock.close()
        except Exception:
            pass
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.mainloop()


# ============================================
# MAIN
# ============================================
def main():
    # One bridge per machine. If we're not the primary, the user double-clicked
    # the exe while it's already running in the background → tell the running
    # instance to show its window, then exit. (If nobody answers, the port is
    # held by some other app; fall through and run without the lock rather than
    # refusing to start.)
    primary_sock = acquire_single_instance()
    if primary_sock is None:
        if signal_existing_instance():
            return

    config = load_config()
    start_hidden = START_HIDDEN

    if config is None or not config.get("devices"):
        # Nothing configured yet → must set up interactively, no matter how we
        # were launched. Show the wizard, then the visible control panel.
        boot = Tk()
        boot.withdraw()
        wizard_completed = {"value": False, "config": None}

        def on_save(c):
            wizard_completed["value"] = True
            wizard_completed["config"] = c
            boot.quit()

        SetupWizard(boot, on_save=on_save)
        boot.mainloop()
        boot.destroy()

        if not wizard_completed["value"]:
            if primary_sock:
                primary_sock.close()
            return  # user cancelled
        config = wizard_completed["config"]
        start_hidden = False  # just configured by hand → show the panel

    cp = ControlPanel(config, primary_sock=primary_sock, start_hidden=start_hidden)
    cp.run()


if __name__ == "__main__":
    main()
