

import json
import logging
import logging.handlers
import os
import platform
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, datetime
from tkinter import StringVar, Tk, Toplevel, messagebox, ttk
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

# ============================================
# CONSTANTS
# ============================================
VERSION = "1.0.0"

WEBHOOK_PATH = (
    "/api/method/avinashgroup_app.biometric."
    "biometric_integration.zkteco_push_attendance"
)

# URL to the version-tracker file in the repo. Bumped on each release.
UPDATE_CHECK_URL = (
    "https://raw.githubusercontent.com/SubashRDP/avinashgroup_app/"
    "develop/k40_bridge/latest_version.txt"
)
# Direct download URL — Releases on public repos work WITHOUT GitHub login.
DOWNLOAD_PAGE_URL = "https://github.com/SubashRDP/avinashgroup_app/releases/latest"
INSTALLER_DOWNLOAD_URL = (
    "https://github.com/SubashRDP/avinashgroup_app/releases/latest/download/K40BridgeSetup.exe"
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

    exe_path = os.path.abspath(sys.argv[0])
    work_dir = os.path.dirname(exe_path)

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
        '  </Settings>\n'
        '  <Actions>\n'
        f'    <Exec>\n'
        f'      <Command>{exe_path}</Command>\n'
        f'      <WorkingDirectory>{work_dir}</WorkingDirectory>\n'
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
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception:
        return None


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


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
    def __init__(self):
        self.synced = set()
        if os.path.exists(SYNCED_RECORDS_FILE):
            try:
                with open(SYNCED_RECORDS_FILE) as f:
                    self.synced = set(json.load(f))
            except Exception:
                self.synced = set()

    def is_synced(self, key):
        return key in self.synced

    def mark(self, key):
        self.synced.add(key)

    def save(self):
        try:
            with open(SYNCED_RECORDS_FILE, "w") as f:
                json.dump(list(self.synced), f)
        except Exception:
            pass


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


DEVICE_TYPES = {
    "zkteco": ZKTecoClient,
    "hikvision": HikvisionClient,
}


def make_device_client(device, timeout=5, retries=3):
    dtype = (device.get("type") or "zkteco").lower()
    cls = DEVICE_TYPES.get(dtype, ZKTecoClient)
    return cls(device, timeout=timeout, retries=retries)


# Backwards-compat alias (old code used DeviceClient directly)
DeviceClient = ZKTecoClient


# ============================================
# ERPNEXT CLIENT (with API token auth)
# ============================================
class ErpnextClient:
    def __init__(self, device):
        self.device = device
        base = device["erpnext_url"].rstrip("/")
        self.url = base + WEBHOOK_PATH
        self.auth_header = f"token {device['api_key']}:{device['api_secret']}"

    def test_connection(self):
        """Verify auth using a built-in Frappe method. Returns (ok, message)."""
        base = self.device["erpnext_url"].rstrip("/")
        try:
            r = requests.get(
                base + "/api/method/frappe.auth.get_logged_user",
                headers={"Authorization": self.auth_header},
                timeout=10,
            )
            if r.status_code == 200:
                user = r.json().get("message", "?")
                return True, f"authenticated as {user}"
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return False, str(e)

    def push_punch(self, user_id, timestamp_str):
        """Send a single punch. Returns (result, message).
        Result is one of: 'synced', 'skipped', 'auth_fail', 'error'."""
        payload = {
            "device_id": self.device.get("serial", ""),
            "employee_id": str(user_id),
            "punch_time": timestamp_str,
            "punch_type": "IN",
        }
        try:
            r = requests.post(
                self.url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": self.auth_header,
                },
                timeout=15,
            )
        except Exception as e:
            return "error", str(e)

        if r.status_code in (401, 403):
            return "auth_fail", f"HTTP {r.status_code}"
        if r.status_code != 200:
            return "error", f"HTTP {r.status_code}: {r.text[:200]}"

        try:
            msg = r.json().get("message", {})
            if isinstance(msg, dict):
                details = msg.get("error_details") or []
                for d in details:
                    if "already has a log with the same timestamp" in str(d):
                        return "skipped", "already exists"
                if msg.get("errors", 0) > 0 and msg.get("synced", 0) == 0:
                    return "error", "; ".join(str(d) for d in details[:2])
        except Exception:
            pass

        return "synced", None


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
        self.last_sync_per_device = {}
        self.next_sync_at = None
        self.reschedule_event = threading.Event()

    def start(self):
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

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
            with open(NEXT_SYNC_FILE, "w") as f:
                json.dump({"next_sync_at": ts, "saved_at": time.time()}, f)
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
            with open(LAST_SYNC_DATES_FILE, "w") as f:
                json.dump(dates, f, indent=2)
        except Exception:
            pass

    def _loop(self):
        interval = int(self.config.get("sync_interval_minutes", 1440)) * 60
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
            interval = int(self.config.get("sync_interval_minutes", 1440)) * 60
            wait_time = max(0.0, self.next_sync_at - time.time())
            woken = self.force_event.wait(timeout=wait_time)
            if self.stop_event.is_set():
                break

            # Reschedule signal (e.g. interval changed in GUI) — don't sync, just
            # re-evaluate the wait based on the new next_sync_at.
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

    def run_sync(self, device_names=None, from_date_override=None):
        devices = self.config.get("devices", [])
        if device_names is not None:
            devices = [d for d in devices if d["name"] in device_names]
        for device in devices:
            if self.stop_event.is_set():
                return
            self._sync_one(device, from_date_override=from_date_override)

    def _sync_one(self, device, from_date_override=None):
        name = device["name"]
        self.status_callback(name, "syncing", None)
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

        attendances, status = client.fetch_attendance(date_from=date_from, date_to=today)

        if status == "UNREACHABLE":
            self.logger.warning(
                f"[{name}] device unreachable: "
                f"{device['ip']}:{device.get('port', 4370)} "
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

        erpnext = ErpnextClient(device)
        synced = skipped = errors = 0
        last_err = None

        for att in attendances:
            if self.stop_event.is_set():
                return
            key = f"{device.get('serial', '')}_{att.user_id}_{att.timestamp}"
            if self.dedup.is_synced(key):
                skipped += 1
                continue

            ts_str = att.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            result, err = erpnext.push_punch(att.user_id, ts_str)

            if result == "synced":
                synced += 1
                self.dedup.mark(key)
            elif result == "skipped":
                skipped += 1
                self.dedup.mark(key)
            elif result == "auth_fail":
                self.logger.error(f"[{name}] auth failed: {err}")
                self.status_callback(name, "auth_fail", err or "401/403")
                self.dedup.save()
                return
            else:
                errors += 1
                last_err = err
                self.logger.error(f"[{name}] push error: {err}")

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

        self.device_rows = []
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

        # ── Step 2: Devices ──
        f2 = ttk.LabelFrame(self.window, text="Step 2: Devices")
        f2.pack(fill="both", expand=True, padx=10, pady=6)

        header = ttk.Frame(f2)
        header.pack(fill="x", padx=6, pady=(4, 2))
        for i, (text, width) in enumerate(
            [
                ("Name", 14),
                ("Type", 10),
                ("IP", 14),
                ("Port", 6),
                ("Serial/ID", 16),
                ("User", 10),
                ("Pass / Key", 10),
                ("Test", 7),
                ("", 3),
            ]
        ):
            ttk.Label(header, text=text, width=width, anchor="w").grid(row=0, column=i, padx=2)

        self.devices_frame = ttk.Frame(f2)
        self.devices_frame.pack(fill="both", expand=True, padx=6)

        ttk.Button(f2, text="+ Add Device", command=lambda: self._add_row()).pack(pady=4)

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
                self._add_row(d)
            mins = int(self.config.get("sync_interval_minutes", 1440))
            for name, m in INTERVAL_OPTIONS:
                if m == mins:
                    self.interval_var.set(name)
                    break
        else:
            self._add_row()

    def _add_row(self, device=None):
        device = device or {"name": "", "type": "zkteco", "ip": "", "port": 4370, "serial": ""}
        row = ttk.Frame(self.devices_frame)
        row.pack(fill="x", pady=1)

        entries = {}

        # Name
        e = ttk.Entry(row, width=14)
        e.insert(0, device.get("name", ""))
        e.grid(row=0, column=0, padx=2)
        entries["name"] = e

        # Type dropdown
        type_var = StringVar(value=device.get("type", "zkteco"))
        type_cb = ttk.Combobox(
            row, textvariable=type_var,
            values=list(DEVICE_TYPES.keys()),
            state="readonly", width=10,
        )
        type_cb.grid(row=0, column=1, padx=2)
        entries["type"] = type_var

        # IP
        e = ttk.Entry(row, width=14)
        e.insert(0, device.get("ip", ""))
        e.grid(row=0, column=2, padx=2)
        entries["ip"] = e

        # Port
        e = ttk.Entry(row, width=6)
        e.insert(0, str(device.get("port", 4370)))
        e.grid(row=0, column=3, padx=2)
        entries["port"] = e

        # Serial / Device ID
        e = ttk.Entry(row, width=16)
        e.insert(0, device.get("serial", ""))
        e.grid(row=0, column=4, padx=2)
        entries["serial"] = e

        # Username (Hikvision)
        e = ttk.Entry(row, width=10)
        e.insert(0, device.get("username", ""))
        e.grid(row=0, column=5, padx=2)
        entries["username"] = e

        # Password (Hikvision) / Comm Key (ZKTeco)
        e = ttk.Entry(row, width=10, show="*")
        e.insert(0, str(device.get("password", "") or device.get("comm_key", "")))
        e.grid(row=0, column=6, padx=2)
        entries["password"] = e

        # Test button for this device
        test_btn = ttk.Button(row, text="Test", width=7,
                              command=lambda: self._test_device(entries))
        test_btn.grid(row=0, column=7, padx=2)
        entries["test_btn"] = test_btn

        def remove():
            row.destroy()
            self.device_rows[:] = [r for r in self.device_rows if r["frame"] is not row]

        ttk.Button(row, text="X", width=3, command=remove).grid(row=0, column=8, padx=2)
        entries["frame"] = row
        self.device_rows.append(entries)

        # Auto-adjust port when type is changed
        def on_type_change(*_):
            current_port = entries["port"].get().strip()
            if type_var.get() == "hikvision" and current_port in ("4370", ""):
                entries["port"].delete(0, "end")
                entries["port"].insert(0, "80")
            elif type_var.get() == "zkteco" and current_port in ("80", "443", ""):
                entries["port"].delete(0, "end")
                entries["port"].insert(0, "4370")

        type_var.trace_add("write", on_type_change)

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

    def _test_device(self, entries):
        """Test connection to a single device row. Shows result via messagebox."""
        name = entries["name"].get().strip() or "(unnamed)"
        ip = entries["ip"].get().strip()
        dtype = entries["type"].get().strip().lower() or "zkteco"
        if not ip:
            messagebox.showwarning("Device Test", "IP address is required.")
            return

        try:
            port = int(entries["port"].get().strip() or (80 if dtype == "hikvision" else 4370))
        except ValueError:
            port = 80 if dtype == "hikvision" else 4370

        # Build a temporary device dict
        dev = {
            "name": name,
            "type": dtype,
            "ip": ip,
            "port": port,
            "serial": entries["serial"].get().strip(),
            "username": entries["username"].get().strip(),
            "password": entries["password"].get().strip(),
        }
        if dtype == "zkteco":
            try:
                dev["comm_key"] = int(dev["password"]) if dev["password"] else 0
            except ValueError:
                dev["comm_key"] = 0

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
            messagebox.showerror(
                "Device Test",
                f"✗ {name}\n\nUnreachable on the network. Check IP / port / cable.",
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

        devices = []
        for r in self.device_rows:
            name = r["name"].get().strip()
            dtype = (r["type"].get() if hasattr(r["type"], "get") else r["type"]).strip().lower() or "zkteco"
            ip = r["ip"].get().strip()
            serial = r["serial"].get().strip()
            username = r["username"].get().strip()
            password = r["password"].get().strip()
            try:
                port = int(r["port"].get().strip() or (80 if dtype == "hikvision" else 4370))
            except ValueError:
                port = 80 if dtype == "hikvision" else 4370

            if not (name and ip):
                continue
            # Hikvision needs username; ZKTeco needs serial (for device_id on checkins)
            if dtype == "zkteco" and not serial:
                continue
            if dtype == "hikvision" and not username:
                continue

            entry = {
                "name": name,
                "type": dtype,
                "ip": ip,
                "port": port,
                "serial": serial,
                "erpnext_url": url,
                "api_key": key,
                "api_secret": secret,
                "latitude": 27.7228,
                "longitude": 85.3211,
            }
            if dtype == "zkteco":
                # ZKTeco "Password" field is the numeric Comm Key (default 0)
                try:
                    entry["comm_key"] = int(password) if password else 0
                except ValueError:
                    entry["comm_key"] = 0
            else:
                entry["username"] = username
                entry["password"] = password

            devices.append(entry)

        if not devices:
            messagebox.showerror("No devices", "Add at least one device with name, IP, and serial.")
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
# CONTROL PANEL
# ============================================
class ControlPanel:
    def __init__(self, config):
        self.config = config
        self.root = Tk()
        self.root.title(f"K40 Bridge  v{VERSION}")
        self.root.geometry("960x640")
        self.root.minsize(820, 520)

        self.logger = setup_logging(config, gui_callback=self._on_log)
        self.engine = SyncEngine(config, self.logger, self._on_status)
        self._build()
        self.engine.start()
        self._tick()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.tray_icon = None
        self._setup_tray()
        # Run update check in background; popup notification if newer version exists
        threading.Thread(target=self._check_update_quiet, daemon=True).start()

    def _build(self):
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=6)

        self.status_label = ttk.Label(top, text="● Running", foreground="green", font=("TkDefaultFont", 10, "bold"))
        self.status_label.pack(side="left")
        self.countdown_label = ttk.Label(top, text="")
        self.countdown_label.pack(side="left", padx=12)

        self.update_label = ttk.Label(top, text="", foreground="blue", cursor="hand2")
        self.update_label.pack(side="left", padx=12)
        self.update_label.bind("<Button-1>", lambda e: self._open_download_page())

        self.pause_btn = ttk.Button(top, text="Pause", command=self._toggle_pause)
        self.pause_btn.pack(side="right", padx=2)
        ttk.Button(top, text="Edit Config", command=self._edit_config).pack(side="right", padx=2)
        ttk.Button(top, text="Check Updates", command=self._check_update_manual).pack(side="right", padx=2)

        cols = ("name", "ip", "last_sync", "status")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings", height=10)
        self.tree.heading("name", text="Name")
        self.tree.heading("ip", text="IP : Port")
        self.tree.heading("last_sync", text="Last Sync")
        self.tree.heading("status", text="Status")
        self.tree.column("name", width=180)
        self.tree.column("ip", width=170)
        self.tree.column("last_sync", width=110)
        self.tree.column("status", width=440)
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)

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

        ttk.Button(btns, text="Open Log Folder", command=self._open_log_folder).pack(side="right", padx=2)

        ttk.Label(self.root, text="Recent log:").pack(anchor="w", padx=10, pady=(6, 0))
        self.log_text = ScrolledText(self.root, height=10, state="disabled", font=("Courier", 9))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=6)

    def _populate_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for d in self.config.get("devices", []):
            self.tree.insert(
                "",
                "end",
                iid=d["name"],
                values=(d["name"], f"{d['ip']}:{d.get('port', 4370)}", "—", "pending"),
            )

    def _on_status(self, name, state, msg):
        self.root.after(0, lambda: self._update_status(name, state, msg))

    def _update_status(self, name, state, msg):
        if not self.tree.exists(name):
            return
        last_sync = self.engine.last_sync_per_device.get(name, "—")
        device = next((d for d in self.config["devices"] if d["name"] == name), None)
        ip_port = f"{device['ip']}:{device.get('port', 4370)}" if device else ""

        label = {
            "syncing": "⟳ syncing…",
            "ok": f"● OK — {msg or ''}",
            "unreachable": f"● UNREACHABLE — {msg or ''}",
            "error": f"● ERROR — {msg or ''}",
            "auth_fail": f"● AUTH FAIL — {msg or ''}",
            "pending": "pending",
        }.get(state, state)

        self.tree.item(name, values=(name, ip_port, last_sync, label))

    def _on_log(self, line):
        self.root.after(0, lambda: self._append_log(line))

    def _append_log(self, line):
        self.log_text.config(state="normal")
        self.log_text.insert("end", line + "\n")
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
        """Run on startup. Show banner only if newer version exists."""
        latest, newer = check_for_update()
        if newer:
            self.root.after(0, lambda: self.update_label.config(
                text=f"⬆ Update available: v{latest} (click to download)"
            ))
            self.logger.info(f"Update available: v{latest} (running v{VERSION})")

    def _check_update_manual(self):
        """Manual 'Check Updates' button — always shows result."""
        self.update_label.config(text="Checking…", foreground="gray")
        self.root.update_idletasks()

        def worker():
            latest, newer = check_for_update()
            def show():
                if latest is None:
                    self.update_label.config(text="", foreground="blue")
                    messagebox.showwarning("Check Updates", "Could not reach update server.")
                elif newer:
                    self.update_label.config(
                        text=f"⬆ Update available: v{latest} (click to download)",
                        foreground="blue",
                    )
                    if messagebox.askyesno(
                        "Update Available",
                        f"A newer version is available.\n\nCurrent: v{VERSION}\nLatest:  v{latest}\n\nOpen the download page now?",
                    ):
                        self._open_download_page()
                else:
                    self.update_label.config(text=f"✓ Up to date (v{VERSION})", foreground="green")
                    messagebox.showinfo("Check Updates", f"You're running the latest version (v{VERSION}).")
            self.root.after(0, show)

        threading.Thread(target=worker, daemon=True).start()

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

    def _setup_tray(self):
        """Create the system tray icon. Bridge keeps running when window is hidden."""
        if not HAS_TRAY:
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

    def _show_window(self, *_):
        self.root.after(0, lambda: (self.root.deiconify(), self.root.lift()))

    def _on_close(self):
        """X button = hide to tray, bridge keeps running."""
        if self.tray_icon:
            self.root.withdraw()
            self.logger.info("Window hidden to tray — bridge continues running")
        else:
            # No tray support — fall back to ask-before-exit behavior
            if messagebox.askyesno(
                "Exit K40 Bridge",
                "Closing this window will STOP the sync engine.\n\n"
                "Do you want to exit?",
            ):
                self.engine.stop()
                self.root.destroy()

    def _real_exit(self, *_):
        """Called from tray menu — fully exits the bridge."""
        self.engine.stop()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.mainloop()


# ============================================
# MAIN
# ============================================
def main():
    config = load_config()

    if config is None or not config.get("devices"):
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
            return  # user cancelled
        config = wizard_completed["config"]

    cp = ControlPanel(config)
    cp.run()


if __name__ == "__main__":
    main()
