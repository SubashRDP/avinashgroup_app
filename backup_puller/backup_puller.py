"""Avinash Backup Puller

Windows app that pulls ERP backups over the API onto an external hard disk.

For every site it calls Frappe's own fetch_latest_backups with the site's API
key/secret, and downloads any backup it has not pulled before from the site's
/backups/<file> URL. The ERP needs no extra code; the API user only needs the
System Manager role.

Runs in the background: the installer registers a Task Scheduler task that
starts `backup_puller.exe --run-once` every hour and at boot, as SYSTEM, so
backups are pulled with no one signed in and no window open. The window is
only for setup, manual pulls and reading the logs.

Two storage paths: the hard disk, and a fallback folder on this PC used while
the disk is unplugged. Fallback backups move to the disk once it is back.
Nothing is ever deleted automatically.
"""

import base64
import ctypes
import gzip
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
from contextlib import contextmanager
from datetime import datetime

import requests

APP_NAME = "Avinash Backup Puller"
VERSION = "1.1.0"
TASK_NAME = "Avinash Backup Puller"

# ProgramData, not APPDATA: the background task runs as SYSTEM and must read
# the same settings the window writes.
DATA_DIR = os.path.join(os.environ.get("PROGRAMDATA") or os.path.expanduser("~"), "AvinashBackupPuller")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
STATE_FILE = os.path.join(DATA_DIR, "pulled.json")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
LOCK_FILE = os.path.join(DATA_DIR, "pull.lock")
LOG_DIR = os.path.join(DATA_DIR, "logs")
ACTIVITY_LOG = os.path.join(LOG_DIR, "activity.log")
# Where 1.0.0 kept its data; moved to DATA_DIR on first start of the window.
OLD_DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "AvinashBackupPuller")
GUI_LOCK_PORT = 47613

CHUNK = 4 * 1024 * 1024
TIMEOUT = (30, 600)
STALE_HOURS = 8
ACTIVITY_LOG_MAX = 5 * 1024 * 1024

DEFAULT_CONFIG = {
	"disk_path": "E:\\ERP_Backups",
	"fallback_path": "C:\\ERP_Backups_Pending",
	"sites": [],
}

HARD_DISK = "Hard Disk"
FALLBACK = "Fallback"


# --------------------------------------------------------------------------
# Secret storage: Windows DPAPI, machine scope, so the API secret in
# config.json is unreadable off this PC but the SYSTEM task can decrypt it.
# --------------------------------------------------------------------------

CRYPTPROTECT_UI_FORBIDDEN = 0x1
CRYPTPROTECT_LOCAL_MACHINE = 0x4


class _Blob(ctypes.Structure):
	_fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data, protect):
	crypt32 = ctypes.windll.crypt32
	kernel32 = ctypes.windll.kernel32
	src = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
	out = _Blob()
	if protect:
		ok = crypt32.CryptProtectData(
			ctypes.byref(src), None, None, None, None,
			CRYPTPROTECT_UI_FORBIDDEN | CRYPTPROTECT_LOCAL_MACHINE, ctypes.byref(out),
		)
	else:
		ok = crypt32.CryptUnprotectData(
			ctypes.byref(src), None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)
		)
	if not ok:
		raise OSError("Windows could not decrypt the API secret")
	try:
		return ctypes.string_at(out.pbData, out.cbData)
	finally:
		kernel32.LocalFree(out.pbData)


def encrypt_secret(secret):
	if os.name != "nt":
		return "plain:" + secret
	return "dpapim:" + base64.b64encode(_dpapi(secret.encode(), True)).decode()


def decrypt_secret(stored):
	if stored.startswith("plain:"):
		return stored[6:]
	if stored.startswith(("dpapim:", "dpapi:")):
		# "dpapi:" is 1.0.0's per-user scope: only that user can decrypt it,
		# which is why the window re-encrypts those on start.
		try:
			return _dpapi(base64.b64decode(stored.split(":", 1)[1]), False).decode()
		except OSError:
			raise PullError("Cannot decrypt the API secret. Open the app and re-enter it (Edit Site).")
	return stored


# --------------------------------------------------------------------------
# Files, logs, lock
# --------------------------------------------------------------------------


def load_json(path, default):
	try:
		with open(path, encoding="utf-8") as f:
			return json.load(f)
	except (OSError, ValueError):
		return json.loads(json.dumps(default))


def save_json(path, data):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	tmp = path + ".tmp"
	with open(tmp, "w", encoding="utf-8") as f:
		json.dump(data, f, indent=2)
	os.replace(tmp, path)


def load_config():
	config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
	for key, value in DEFAULT_CONFIG.items():
		config.setdefault(key, value)
	return config


def safe_name(name):
	return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def site_log_path(site_name):
	return os.path.join(LOG_DIR, safe_name(site_name) + ".log")


def log(site_name, message):
	"""One line to the site's own log and to the shared activity log, which
	the window tails, so background runs show up there too."""
	line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  [{site_name}]  {message}\n"
	os.makedirs(LOG_DIR, exist_ok=True)
	try:
		if os.path.getsize(ACTIVITY_LOG) > ACTIVITY_LOG_MAX:
			os.replace(ACTIVITY_LOG, ACTIVITY_LOG + ".1")
	except OSError:
		pass
	for path in (site_log_path(site_name), ACTIVITY_LOG):
		with open(path, "a", encoding="utf-8") as f:
			f.write(line)


def human_size(size):
	for unit in ("B", "KB", "MB", "GB"):
		if size < 1024:
			return f"{size:.1f} {unit}"
		size /= 1024
	return f"{size:.1f} TB"


class Busy(Exception):
	pass


@contextmanager
def pull_lock():
	"""Across processes: the hourly task and a click in the window must not
	download the same backup at once. Raises Busy if a pull is running."""
	os.makedirs(DATA_DIR, exist_ok=True)
	f = open(LOCK_FILE, "a+")
	try:
		if os.name == "nt":
			import msvcrt

			f.seek(0)
			msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
		else:
			import fcntl

			fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
	except OSError:
		f.close()
		raise Busy("A pull is already running (probably the background task). Try again in a moment.")
	try:
		yield
	finally:
		try:
			if os.name == "nt":
				import msvcrt

				f.seek(0)
				msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
		finally:
			f.close()


def set_site_status(site_name, ok, message):
	status = load_json(STATUS_FILE, {})
	status.setdefault("sites", {})[site_name] = {
		"time": datetime.now().isoformat(timespec="seconds"),
		"ok": ok,
		"message": message,
	}
	save_json(STATUS_FILE, status)


def set_run_status(source, ok):
	status = load_json(STATUS_FILE, {})
	status["last_run"] = {"time": datetime.now().isoformat(timespec="seconds"), "source": source, "ok": ok}
	save_json(STATUS_FILE, status)


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------


def device_of(path):
	"""Device id of the nearest existing folder at or above path."""
	path = os.path.abspath(path)
	while not os.path.exists(path):
		parent = os.path.dirname(path)
		if parent == path:
			return None
		path = parent
	return os.stat(path).st_dev


def is_disk_connected(config):
	"""True when the hard disk is plugged in and writable.

	On Windows the drive letter (E:\\) disappears when the disk is unplugged.
	The path must also be on a different drive from the fallback; otherwise
	"connected" would mean nothing."""
	disk, fallback = config["disk_path"], config["fallback_path"]
	if not disk:
		return False
	drive = os.path.splitdrive(disk)[0]
	if drive and not os.path.exists(drive + os.sep):
		return False
	try:
		os.makedirs(disk, exist_ok=True)
		os.makedirs(fallback, exist_ok=True)
	except OSError:
		return False
	if not os.access(disk, os.W_OK):
		return False
	return device_of(disk) != device_of(fallback)


def target_root(config):
	if is_disk_connected(config):
		return config["disk_path"], HARD_DISK
	os.makedirs(config["fallback_path"], exist_ok=True)
	return config["fallback_path"], FALLBACK


def backup_folder_for(filename):
	"""Frappe names backups '<YYYYMMDD_HHMMSS>-<site>-...'; one folder per timestamp."""
	m = re.match(r"^(\d{8}_\d{6})-", filename)
	if not m:
		return "other"
	return datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").strftime("%Y-%m-%d_%H%M%S")


def sha256_of(path):
	sha = hashlib.sha256()
	with open(path, "rb") as f:
		for chunk in iter(lambda: f.read(CHUNK), b""):
			sha.update(chunk)
	return sha.hexdigest()


def pending_on_fallback():
	"""(count, bytes) of backups waiting on the fallback for the hard disk."""
	count = size = 0
	for files in load_json(STATE_FILE, {}).values():
		for rec in files.values():
			if rec.get("location") == FALLBACK:
				count += 1
				size += rec.get("size") or 0
	return count, size


# --------------------------------------------------------------------------
# Puller
# --------------------------------------------------------------------------


class PullError(Exception):
	pass


class Puller:
	"""All the work, no UI. Public methods take the cross-process lock."""

	def session(self, site):
		s = requests.Session()
		s.headers["Authorization"] = "token {}:{}".format(site["api_key"], decrypt_secret(site["api_secret"]))
		s.headers["Accept"] = "application/json"
		return s

	def call(self, site, session, method):
		url = site["url"].rstrip("/") + "/api/method/" + method
		try:
			r = session.get(url, timeout=TIMEOUT)
		except requests.RequestException as e:
			raise PullError(f"Cannot reach {site['url']}: {e}")
		if r.status_code in (401, 403):
			raise PullError(
				f"Login refused (HTTP {r.status_code}). Check the API key/secret; "
				"the API user needs the System Manager role."
			)
		if r.status_code != 200:
			raise PullError(f"HTTP {r.status_code} from {method}: {r.text[:300]}")
		try:
			return r.json().get("message")
		except ValueError:
			raise PullError(f"{site['url']} did not return JSON. Is the URL right?")

	def test_connection(self, site):
		s = self.session(site)
		user = self.call(site, s, "frappe.auth.get_logged_user")
		latest = self.call(site, s, "frappe.utils.backups.fetch_latest_backups") or {}
		db = latest.get("database")
		return user, (os.path.basename(db) if db else None)

	def run(self, config, sites, source):
		"""Pull the given sites, then move fallback backups to the disk.
		Returns True when every site succeeded."""
		with pull_lock():
			all_ok = True
			for site in sites:
				try:
					n = self._pull_site(config, site)
					set_site_status(site["name"], True, f"{n} new" if n else "Up to date")
				except Exception as e:
					all_ok = False
					log(site["name"], f"FAILED: {e}")
					set_site_status(site["name"], False, str(e))
			try:
				self._move_pending(config)
			except Exception as e:
				all_ok = False
				log("storage", f"Moving to the hard disk failed: {e}")
			set_run_status(source, all_ok)
			return all_ok

	def pull_site(self, config, site):
		with pull_lock():
			return self._pull_site(config, site)

	def move_pending(self, config):
		with pull_lock():
			return self._move_pending(config)

	def _pull_site(self, config, site):
		name = site["name"]
		state = load_json(STATE_FILE, {})
		pulled = state.setdefault(name, {})
		s = self.session(site)

		latest = self.call(site, s, "frappe.utils.backups.fetch_latest_backups") or {}
		types = ["database"] + (["public", "private"] if site.get("include_files") else [])
		new_files = []
		for file_type in types:
			remote_path = latest.get(file_type)
			if not remote_path:
				if file_type == "database":
					log(name, "The site has no backup from the last 30 days.")
				continue
			filename = os.path.basename(remote_path)
			if filename in pulled:
				continue
			new_files.append((file_type, filename))

		if not new_files:
			log(name, "Up to date.")
			return 0

		root, location = target_root(config)
		count = 0
		for file_type, filename in new_files:
			folder = os.path.join(root, safe_name(name), backup_folder_for(filename))
			os.makedirs(folder, exist_ok=True)
			dest = os.path.join(folder, filename)
			log(name, f"Downloading {filename} to {location} ...")
			size, sha = self.download(site, s, filename, dest)
			pulled[filename] = {
				"type": file_type,
				"path": dest,
				"location": location,
				"size": size,
				"sha256": sha,
				"pulled_on": datetime.now().isoformat(timespec="seconds"),
			}
			save_json(STATE_FILE, state)
			log(name, f"Saved {filename} ({human_size(size)}).")
			count += 1
		return count

	def download(self, site, session, filename, dest):
		url = site["url"].rstrip("/") + "/backups/" + filename
		part = dest + ".part"
		sha = hashlib.sha256()
		size = 0
		try:
			with session.get(url, stream=True, timeout=TIMEOUT) as r:
				if r.status_code != 200:
					raise PullError(f"Download of {filename} failed: HTTP {r.status_code}")
				expected = r.headers.get("Content-Length")
				with open(part, "wb") as f:
					for chunk in r.iter_content(chunk_size=CHUNK):
						f.write(chunk)
						sha.update(chunk)
						size += len(chunk)
		except requests.RequestException as e:
			_remove(part)
			raise PullError(f"Download of {filename} failed: {e}")
		except BaseException:
			_remove(part)
			raise

		if expected and int(expected) != size:
			_remove(part)
			raise PullError(f"Download of {filename} is incomplete ({size} of {expected} bytes).")
		if filename.endswith(".sql.gz") and "-enc" not in filename:
			try:
				with gzip.open(part, "rb") as f:
					while f.read(CHUNK):
						pass
			except (OSError, EOFError) as e:
				_remove(part)
				raise PullError(
					f"{filename} is not a complete gzip file ({e}). "
					"The server may still have been writing it; it will be retried next time."
				)
		if filename.endswith((".tar", ".tgz")) and "-enc" not in filename:
			try:
				with tarfile.open(part) as t:
					for _member in t:
						pass
			except (tarfile.TarError, OSError, EOFError) as e:
				_remove(part)
				raise PullError(f"{filename} is not a complete archive ({e}); it will be retried next time.")
		os.replace(part, dest)
		return size, sha.hexdigest()

	def _move_pending(self, config):
		"""Copy fallback backups to the hard disk, verify, then remove the fallback copy."""
		if not is_disk_connected(config):
			return 0
		state = load_json(STATE_FILE, {})
		moved = 0
		for site_name, files in state.items():
			for filename, rec in files.items():
				if rec.get("location") != FALLBACK:
					continue
				src = rec["path"]
				if not os.path.exists(src):
					rec["location"] = "Missing"
					continue
				dest_dir = os.path.join(config["disk_path"], safe_name(site_name), backup_folder_for(filename))
				os.makedirs(dest_dir, exist_ok=True)
				dest = os.path.join(dest_dir, filename)
				shutil.copyfile(src, dest + ".part")
				if sha256_of(dest + ".part") != rec["sha256"]:
					_remove(dest + ".part")
					log(site_name, f"Copy of {filename} to the hard disk did not verify; kept on fallback.")
					continue
				os.replace(dest + ".part", dest)
				rec.update({"path": dest, "location": HARD_DISK})
				save_json(STATE_FILE, state)
				_remove(src)
				_remove_empty_dirs(os.path.dirname(src), config["fallback_path"])
				log(site_name, f"Moved {filename} to the hard disk.")
				moved += 1
		save_json(STATE_FILE, state)
		return moved


def _remove(path):
	try:
		os.remove(path)
	except OSError:
		pass


def _remove_empty_dirs(path, stop_at):
	stop_at = os.path.abspath(stop_at)
	path = os.path.abspath(path)
	while path.startswith(stop_at) and path != stop_at:
		try:
			os.rmdir(path)
		except OSError:
			return
		path = os.path.dirname(path)


# --------------------------------------------------------------------------
# Background run (Task Scheduler)
# --------------------------------------------------------------------------


def run_once():
	"""What the hourly task runs: pull every enabled site, then exit."""
	config = load_config()
	sites = [s for s in config["sites"] if s.get("enabled", True)]
	if not sites:
		return 0
	try:
		return 0 if Puller().run(config, sites, "Background") else 1
	except Busy:
		return 0  # someone clicked Pull in the window; that run covers this hour


def background_task_installed():
	if os.name != "nt":
		return None
	try:
		r = subprocess.run(
			["schtasks", "/Query", "/TN", TASK_NAME],
			capture_output=True,
			creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
		)
		return r.returncode == 0
	except OSError:
		return None


def migrate_old_data():
	"""1.0.0 kept everything in the user's APPDATA, out of the SYSTEM task's reach."""
	if os.path.exists(CONFIG_FILE) or not os.path.exists(os.path.join(OLD_DATA_DIR, "config.json")):
		return
	os.makedirs(DATA_DIR, exist_ok=True)
	for name in ("config.json", "pulled.json"):
		src = os.path.join(OLD_DATA_DIR, name)
		if os.path.exists(src):
			shutil.copyfile(src, os.path.join(DATA_DIR, name))
	if os.path.isdir(os.path.join(OLD_DATA_DIR, "logs")):
		shutil.copytree(os.path.join(OLD_DATA_DIR, "logs"), LOG_DIR, dirs_exist_ok=True)


def upgrade_secrets(config):
	"""Re-encrypt 1.0.0's per-user secrets for the machine, so SYSTEM can read them.
	Only works here, in the window, running as the user who saved them."""
	changed = False
	for site in config["sites"]:
		if site.get("api_secret", "").startswith("dpapi:"):
			try:
				site["api_secret"] = encrypt_secret(decrypt_secret(site["api_secret"]))
				changed = True
			except PullError:
				pass
	if changed:
		save_json(CONFIG_FILE, config)


# --------------------------------------------------------------------------
# Window
# --------------------------------------------------------------------------

GREEN = "#0f7b0f"
RED = "#c42b1c"
ORANGE = "#9d5d00"
GRAY = "#6e6e6e"


def ago(iso):
	if not iso:
		return "never"
	seconds = (datetime.now() - datetime.fromisoformat(iso)).total_seconds()
	if seconds < 90:
		return "just now"
	if seconds < 3600:
		return f"{int(seconds // 60)} min ago"
	if seconds < 48 * 3600:
		return f"{int(seconds // 3600)} h ago"
	return f"{int(seconds // 86400)} days ago"


def run_app():
	import tkinter as tk
	from tkinter import filedialog, messagebox, ttk

	migrate_old_data()
	config = load_config()
	upgrade_secrets(config)
	puller = Puller()

	root = tk.Tk()
	root.title(APP_NAME)
	root.geometry("1040x700")
	root.minsize(880, 600)
	# Sun Valley (Windows 11 look). Its Card/Accent styles don't exist in the
	# stock themes, so fall back to plain styles if it is missing.
	try:
		import sv_ttk

		sv_ttk.set_theme("light")
		CARD, ACCENT = "Card.TFrame", "Accent.TButton"
	except Exception:
		ttk.Style().theme_use("vista" if os.name == "nt" else "clam")
		CARD, ACCENT = "TFrame", "TButton"

	style = ttk.Style()
	base_font = ("Segoe UI", 10)
	style.configure("Treeview", rowheight=30, font=base_font)
	style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))
	style.configure("Title.TLabel", font=("Segoe UI Semibold", 18))
	style.configure("Sub.TLabel", font=base_font, foreground=GRAY)
	style.configure("Caption.TLabel", font=("Segoe UI Semibold", 9), foreground=GRAY)
	style.configure("Big.TLabel", font=("Segoe UI Semibold", 15))
	style.configure("Detail.TLabel", font=("Segoe UI", 9), foreground=GRAY)

	def in_background(fn, *args):
		threading.Thread(target=fn, args=args, daemon=True).start()

	def show_error(message):
		root.after(0, lambda: messagebox.showerror(APP_NAME, message))

	# ---- Header ----
	header = ttk.Frame(root, padding=(20, 16, 20, 4))
	header.pack(fill="x")
	ttk.Label(header, text=APP_NAME, style="Title.TLabel").pack(side="left")
	ttk.Label(header, text=f"   Offsite ERP backups over the API  ·  v{VERSION}", style="Sub.TLabel").pack(
		side="left", pady=(6, 0)
	)

	notebook = ttk.Notebook(root)
	notebook.pack(fill="both", expand=True, padx=20, pady=(8, 20))
	overview = ttk.Frame(notebook, padding=16)
	activity = ttk.Frame(notebook, padding=16)
	settings = ttk.Frame(notebook, padding=24)
	notebook.add(overview, text="  Overview  ")
	notebook.add(activity, text="  Activity  ")
	notebook.add(settings, text="  Settings  ")

	# ---- Overview: status cards ----
	cards = ttk.Frame(overview)
	cards.pack(fill="x")
	for i in range(3):
		cards.columnconfigure(i, weight=1, uniform="card")

	def card(column, caption):
		frame = ttk.Frame(cards, style=CARD, padding=14)
		frame.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0 if column == 2 else 6))
		ttk.Label(frame, text=caption, style="Caption.TLabel").pack(anchor="w")
		big = ttk.Label(frame, text="", style="Big.TLabel")
		big.pack(anchor="w", pady=(4, 2))
		detail = ttk.Label(frame, text="", style="Detail.TLabel")
		detail.pack(anchor="w")
		return frame, big, detail

	disk_card, disk_big, disk_detail = card(0, "HARD DISK")
	disk_bar = ttk.Progressbar(disk_card, maximum=100)
	disk_bar.pack(fill="x", pady=(8, 0))
	_c, pending_big, pending_detail = card(1, "WAITING ON FALLBACK")
	_c, bg_big, bg_detail = card(2, "BACKGROUND PULLS")

	def refresh_cards():
		if is_disk_connected(config):
			usage = shutil.disk_usage(config["disk_path"])
			disk_big.config(text="Connected", foreground=GREEN)
			disk_detail.config(text=f"{human_size(usage.free)} free of {human_size(usage.total)}")
			disk_bar["value"] = usage.used * 100 / usage.total
		else:
			disk_big.config(text="Not connected", foreground=RED)
			disk_detail.config(text="New backups go to the fallback folder")
			disk_bar["value"] = 0

		count, size = pending_on_fallback()
		if count:
			pending_big.config(text=f"{count} backup{'s' if count != 1 else ''}", foreground=ORANGE)
			pending_detail.config(text=f"{human_size(size)} · moves when the disk is connected")
		else:
			pending_big.config(text="Nothing waiting", foreground=GREEN)
			pending_detail.config(text="Everything is on the hard disk")

		installed = background_task_installed()
		last = load_json(STATUS_FILE, {}).get("last_run")
		last_text = (
			f"Last run {ago(last['time'])} · {'OK' if last['ok'] else 'with errors'}" if last else "No run yet"
		)
		if installed is False:
			bg_big.config(text="Task missing", foreground=RED)
			bg_detail.config(text="Reinstall to restore the hourly task")
		else:
			bg_big.config(text="Every hour", foreground=GREEN if not last or last["ok"] else ORANGE)
			bg_detail.config(text=last_text)

	# ---- Overview: toolbar ----
	toolbar = ttk.Frame(overview)
	toolbar.pack(fill="x", pady=(16, 8))
	ttk.Label(toolbar, text="Sites", font=("Segoe UI Semibold", 13)).pack(side="left")

	# ---- Overview: sites table ----
	table_frame = ttk.Frame(overview)
	table_frame.pack(fill="both", expand=True)
	cols = ("name", "url", "files", "last", "status")
	tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
	for col, title, width, stretch in (
		("name", "Site", 170, False),
		("url", "URL", 250, True),
		("files", "Files", 60, False),
		("last", "Last new backup", 150, False),
		("status", "Status", 260, True),
	):
		tree.heading(col, text=title, anchor="w")
		tree.column(col, width=width, anchor="w", stretch=stretch)
	tree.tag_configure("ok", foreground=GREEN)
	tree.tag_configure("failed", foreground=RED)
	tree.tag_configure("stale", foreground=ORANGE)
	tree.tag_configure("disabled", foreground=GRAY)
	scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
	tree.configure(yscrollcommand=scroll.set)
	tree.pack(side="left", fill="both", expand=True)
	scroll.pack(side="left", fill="y")

	empty_hint = ttk.Label(
		overview, text="No sites yet. Click “Add Site” to connect your first ERP site.", style="Sub.TLabel"
	)

	def refresh_sites():
		selected = tree.selection()
		tree.delete(*tree.get_children())
		state = load_json(STATE_FILE, {})
		site_status = load_json(STATUS_FILE, {}).get("sites", {})
		for site in config["sites"]:
			times = [r["pulled_on"] for r in state.get(site["name"], {}).values() if r.get("pulled_on")]
			last = max(times) if times else None
			st = site_status.get(site["name"])
			if not site.get("enabled", True):
				tag, text = "disabled", "Disabled"
			elif st and not st["ok"]:
				tag, text = "failed", f"✖  Failed {ago(st['time'])}: {st['message'][:80]}"
			elif not last or (datetime.now() - datetime.fromisoformat(last)).total_seconds() > STALE_HOURS * 3600:
				tag, text = "stale", f"⚠  No new backup for {STALE_HOURS}+ hours" if last else "⚠  Nothing pulled yet"
			else:
				tag, text = "ok", f"✔  {st['message']} ({ago(st['time'])})" if st else "✔  OK"
			tree.insert(
				"",
				"end",
				iid=site["name"],
				values=(
					site["name"],
					site["url"],
					"Yes" if site.get("include_files") else "No",
					ago(last),
					text,
				),
				tags=(tag,),
			)
		if selected and tree.exists(selected[0]):
			tree.selection_set(selected[0])
		if config["sites"]:
			empty_hint.pack_forget()
		else:
			empty_hint.pack(pady=8)

	def selected_site():
		sel = tree.selection()
		if not sel:
			messagebox.showinfo(APP_NAME, "Select a site first.")
			return None
		return next(s for s in config["sites"] if s["name"] == sel[0])

	def edit_site(site=None):
		d = tk.Toplevel(root)
		d.title("Edit Site" if site else "Add Site")
		d.transient(root)
		d.resizable(False, False)
		body = ttk.Frame(d, padding=24)
		body.pack(fill="both", expand=True)
		ttk.Label(body, text="Edit Site" if site else "Add Site", font=("Segoe UI Semibold", 15)).grid(
			row=0, column=0, columnspan=2, sticky="w", pady=(0, 14)
		)
		v = {
			"name": tk.StringVar(value=site["name"] if site else ""),
			"url": tk.StringVar(value=site["url"] if site else "https://"),
			"api_key": tk.StringVar(value=site["api_key"] if site else ""),
			"api_secret": tk.StringVar(value=""),
		}
		files_var = tk.BooleanVar(value=site.get("include_files", False) if site else False)
		enabled_var = tk.BooleanVar(value=site.get("enabled", True) if site else True)
		rows = (
			("Site name", "name", False, "Also the backup folder name"),
			("Site URL", "url", False, "e.g. https://erp.yourcompany.com"),
			("API key", "api_key", False, "Of an ERP user with the System Manager role"),
			("API secret", "api_secret", True, "Leave blank to keep the saved one" if site else ""),
		)
		for i, (label, key, hidden, hint) in enumerate(rows):
			r = 1 + i * 2
			ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", padx=(0, 16))
			ttk.Entry(body, textvariable=v[key], width=46, show="•" if hidden else "").grid(row=r, column=1, sticky="we")
			ttk.Label(body, text=hint, style="Detail.TLabel").grid(row=r + 1, column=1, sticky="w", pady=(2, 10))
		ttk.Checkbutton(body, text="Also pull the files backup (public + private)", variable=files_var).grid(
			row=9, column=1, sticky="w", pady=(4, 2)
		)
		ttk.Checkbutton(body, text="Enabled (pulled automatically every hour)", variable=enabled_var).grid(
			row=10, column=1, sticky="w"
		)

		def ok():
			name, url = v["name"].get().strip(), v["url"].get().strip().rstrip("/")
			key, secret = v["api_key"].get().strip(), v["api_secret"].get().strip()
			if not name or not key or (not site and not secret):
				messagebox.showerror(APP_NAME, "Name, API key and API secret are required.", parent=d)
				return
			if not url.startswith("https://"):
				messagebox.showerror(APP_NAME, "The URL must start with https://", parent=d)
				return
			if any(s["name"] == name and s is not site for s in config["sites"]):
				messagebox.showerror(APP_NAME, "A site with this name already exists.", parent=d)
				return
			if site and site["name"] != name:
				# Keep the pulled-history under the new name, or everything re-downloads.
				state = load_json(STATE_FILE, {})
				if site["name"] in state:
					state[name] = state.pop(site["name"])
					save_json(STATE_FILE, state)
			target = site if site is not None else {}
			target.update(
				{
					"name": name,
					"url": url,
					"api_key": key,
					"include_files": files_var.get(),
					"enabled": enabled_var.get(),
				}
			)
			if secret:
				target["api_secret"] = encrypt_secret(secret)
			if site is None:
				config["sites"].append(target)
			save_json(CONFIG_FILE, config)
			d.destroy()
			refresh_sites()

		bar = ttk.Frame(body)
		bar.grid(row=11, column=0, columnspan=2, sticky="e", pady=(18, 0))
		ttk.Button(bar, text="Cancel", command=d.destroy).pack(side="right")
		ttk.Button(bar, text="Save", style=ACCENT, command=ok).pack(side="right", padx=(0, 8))
		d.grab_set()

	def remove_site():
		site = selected_site()
		if site and messagebox.askyesno(APP_NAME, f"Remove {site['name']}?\n\nBackups already pulled stay on the disk."):
			config["sites"].remove(site)
			save_json(CONFIG_FILE, config)
			refresh_sites()

	def test_selected():
		site = selected_site()
		if not site:
			return

		def run():
			try:
				user, db = puller.test_connection(site)
				msg = f"Connected as {user}.\n\nLatest backup on the server:\n{db or 'none in the last 30 days'}"
				root.after(0, lambda: messagebox.showinfo(APP_NAME, msg))
			except Exception as e:
				show_error(str(e))

		in_background(run)

	def pull(sites):
		try:
			puller.run(config, sites, "Manual")
		except Busy as e:
			show_error(str(e))

	def pull_selected():
		site = selected_site()
		if site:
			notebook.select(activity)
			in_background(pull, [site])

	def pull_all():
		notebook.select(activity)
		in_background(pull, [s for s in config["sites"] if s.get("enabled", True)])

	def move_now():
		if not is_disk_connected(config):
			messagebox.showwarning(APP_NAME, "The hard disk is not connected.")
			return

		def run():
			try:
				log("storage", f"Moved {puller.move_pending(config)} backups to the hard disk.")
			except Busy as e:
				show_error(str(e))

		notebook.select(activity)
		in_background(run)

	def open_path(path):
		if not os.path.exists(path):
			messagebox.showinfo(APP_NAME, f"{path} does not exist yet.")
		elif os.name == "nt":
			os.startfile(path)
		else:
			subprocess.Popen(["xdg-open", path])

	def open_folder():
		site = selected_site()
		if site:
			root_path, _loc = target_root(config)
			folder = os.path.join(root_path, safe_name(site["name"]))
			os.makedirs(folder, exist_ok=True)
			open_path(folder)

	def open_log():
		site = selected_site()
		if site:
			open_path(site_log_path(site["name"]))

	for text, cmd, accent in (
		("Pull All Now", pull_all, True),
		("Pull Selected", pull_selected, False),
		("Test Connection", test_selected, False),
		("Remove", remove_site, False),
		("Edit", lambda: (s := selected_site()) and edit_site(s), False),
		("Add Site", lambda: edit_site(), False),
	):
		ttk.Button(toolbar, text=text, command=cmd, style=ACCENT if accent else "TButton").pack(
			side="right", padx=(6, 0)
		)

	bottom = ttk.Frame(overview)
	bottom.pack(fill="x", pady=(10, 0))
	ttk.Button(bottom, text="Open Folder", command=open_folder).pack(side="left")
	ttk.Button(bottom, text="Open Site Log", command=open_log).pack(side="left", padx=6)
	ttk.Button(bottom, text="Move to Hard Disk Now", command=move_now).pack(side="left")
	ttk.Label(bottom, text="Double-click a site to edit it", style="Detail.TLabel").pack(side="right")
	tree.bind("<Double-1>", lambda _e: tree.selection() and edit_site(selected_site()))

	# ---- Activity ----
	act_bar = ttk.Frame(activity)
	act_bar.pack(fill="x", pady=(0, 8))
	ttk.Label(act_bar, text="Everything the app and the background task did, live.", style="Sub.TLabel").pack(
		side="left"
	)
	ttk.Button(act_bar, text="Open Logs Folder", command=lambda: open_path(LOG_DIR)).pack(side="right")
	log_box = tk.Text(
		activity, wrap="none", state="disabled", font=("Consolas", 9), relief="flat", padx=10, pady=8,
		background="#fafafa", foreground="#1f1f1f",
	)
	log_scroll = ttk.Scrollbar(activity, orient="vertical", command=log_box.yview)
	log_box.configure(yscrollcommand=log_scroll.set)
	log_box.tag_configure("failed", foreground=RED)
	log_box.tag_configure("ok", foreground=GREEN)
	log_box.pack(side="left", fill="both", expand=True)
	log_scroll.pack(side="left", fill="y")
	log_pos = {"offset": 0}

	def tail_activity():
		"""Show new lines of activity.log, from this window and the background task alike."""
		try:
			size = os.path.getsize(ACTIVITY_LOG)
		except OSError:
			return
		if size < log_pos["offset"]:
			log_pos["offset"] = 0  # rotated
		if size == log_pos["offset"]:
			return
		with open(ACTIVITY_LOG, encoding="utf-8", errors="replace") as f:
			if log_pos["offset"] == 0 and size > 200_000:
				f.seek(size - 200_000)
				f.readline()
			else:
				f.seek(log_pos["offset"])
			text = f.read()
			log_pos["offset"] = f.tell()
		log_box.config(state="normal")
		for line in text.splitlines(keepends=True):
			tag = "failed" if ("FAILED" in line or "did not verify" in line) else ("ok" if "Saved " in line or "Moved " in line else "")
			log_box.insert("end", line, tag)
		log_box.see("end")
		log_box.config(state="disabled")

	# ---- Settings ----
	disk_var = tk.StringVar(value=config["disk_path"])
	fallback_var = tk.StringVar(value=config["fallback_path"])

	def browse(var):
		path = filedialog.askdirectory(initialdir=var.get() or None)
		if path:
			var.set(os.path.normpath(path))

	ttk.Label(settings, text="Storage", font=("Segoe UI Semibold", 13)).grid(row=0, column=0, columnspan=3, sticky="w")
	for row, (label, var, hint) in enumerate(
		(
			("Hard disk folder", disk_var, "The external hard disk, e.g. E:\\ERP_Backups. Backups go here whenever it is plugged in."),
			("Fallback folder", fallback_var, "A folder on this PC, used only while the hard disk is unplugged."),
		)
	):
		r = 1 + row * 2
		ttk.Label(settings, text=label).grid(row=r, column=0, sticky="w", padx=(0, 16), pady=(14, 0))
		ttk.Entry(settings, textvariable=var, width=60).grid(row=r, column=1, sticky="we", pady=(14, 0))
		ttk.Button(settings, text="Browse…", command=lambda v=var: browse(v)).grid(row=r, column=2, padx=(8, 0), pady=(14, 0))
		ttk.Label(settings, text=hint, style="Detail.TLabel").grid(row=r + 1, column=1, sticky="w", pady=(2, 0))
	settings.columnconfigure(1, weight=1)

	def save_storage():
		disk, fallback = disk_var.get().strip(), fallback_var.get().strip()
		if not disk or not fallback or os.path.abspath(disk) == os.path.abspath(fallback):
			messagebox.showerror(APP_NAME, "Set two different folders: the hard disk and the fallback.")
			return
		config.update({"disk_path": disk, "fallback_path": fallback})
		save_json(CONFIG_FILE, config)
		refresh_cards()
		if is_disk_connected(config):
			messagebox.showinfo(APP_NAME, "Saved. The hard disk is connected.")
		else:
			messagebox.showwarning(
				APP_NAME,
				"Saved, but the hard disk is not connected (or is on the same drive as the fallback).\n\n"
				"Backups will go to the fallback folder until it is.",
			)

	ttk.Button(settings, text="Save", style=ACCENT, command=save_storage).grid(
		row=5, column=1, sticky="w", pady=(18, 0)
	)

	ttk.Separator(settings).grid(row=6, column=0, columnspan=3, sticky="we", pady=24)
	ttk.Label(settings, text="Background", font=("Segoe UI Semibold", 13)).grid(row=7, column=0, columnspan=3, sticky="w")
	ttk.Label(
		settings,
		text=(
			"Backups are pulled every hour, and 2 minutes after the PC starts, by a Windows scheduled task "
			f"(“{TASK_NAME}”). It runs even when this window is closed and no one is signed in. "
			"Keep the PC switched on and set it never to sleep."
		),
		style="Sub.TLabel",
		wraplength=760,
		justify="left",
	).grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 0))
	data_row = ttk.Frame(settings)
	data_row.grid(row=9, column=0, columnspan=3, sticky="w", pady=(14, 0))
	ttk.Label(data_row, text=f"Settings and logs:  {DATA_DIR}", style="Detail.TLabel").pack(side="left")
	ttk.Button(data_row, text="Open", command=lambda: open_path(DATA_DIR)).pack(side="left", padx=8)

	# ---- Refresh loop ----
	counter = {"n": 0}

	def tick():
		tail_activity()
		counter["n"] += 1
		if counter["n"] % 5 == 1:  # every ~10 s: background runs update these files
			refresh_sites()
			refresh_cards()
		root.after(2000, tick)

	tick()
	if "--smoke-test" in sys.argv:
		# CI: build the whole window, then exit cleanly.
		root.after(3000, root.destroy)
	root.mainloop()


def main():
	if "--run-once" in sys.argv:
		sys.exit(run_once())

	# One window at a time.
	lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	try:
		lock.bind(("127.0.0.1", GUI_LOCK_PORT))
	except OSError:
		try:
			import tkinter.messagebox as mb

			mb.showinfo(APP_NAME, f"{APP_NAME} is already open.")
		finally:
			sys.exit(0)
	run_app()


if __name__ == "__main__":
	main()
