"""Avinash Backup Puller

Windows app that pulls ERP backups over the API into an external hard disk.

For every site it calls Frappe's own fetch_latest_backups with the site's API
key/secret, and downloads any backup it has not pulled before from the site's
/backups/<file> URL. The ERP needs no extra code; the API user only needs the
System Manager role.

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
import queue
import re
import shutil
import socket
import tarfile
import subprocess
import sys
import threading
import time
from datetime import datetime

import requests

APP_NAME = "Avinash Backup Puller"
VERSION = "1.0.0"
APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "AvinashBackupPuller")
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
STATE_FILE = os.path.join(APP_DIR, "pulled.json")
LOG_DIR = os.path.join(APP_DIR, "logs")
LOCK_PORT = 47613

CHUNK = 4 * 1024 * 1024
TIMEOUT = (30, 600)
STALE_HOURS = 8

DEFAULT_CONFIG = {
	"disk_path": "E:\\ERP_Backups",
	"fallback_path": "C:\\ERP_Backups_Pending",
	"interval_minutes": 60,
	"sites": [],
}

HARD_DISK = "Hard Disk"
FALLBACK = "Fallback"


# --------------------------------------------------------------------------
# Secret storage: Windows DPAPI, so the API secret in config.json can only be
# read by this Windows user on this PC.
# --------------------------------------------------------------------------


class _Blob(ctypes.Structure):
	_fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data, protect):
	crypt32 = ctypes.windll.crypt32
	kernel32 = ctypes.windll.kernel32
	src = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
	out = _Blob()
	fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
	if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
		raise OSError("DPAPI call failed")
	try:
		return ctypes.string_at(out.pbData, out.cbData)
	finally:
		kernel32.LocalFree(out.pbData)


def encrypt_secret(secret):
	if os.name != "nt":
		return "plain:" + secret
	return "dpapi:" + base64.b64encode(_dpapi(secret.encode(), True)).decode()


def decrypt_secret(stored):
	if stored.startswith("plain:"):
		return stored[6:]
	if stored.startswith("dpapi:"):
		return _dpapi(base64.b64decode(stored[6:]), False).decode()
	return stored


# --------------------------------------------------------------------------
# Config, state and logs
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


def safe_name(name):
	return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def site_log_path(site_name):
	return os.path.join(LOG_DIR, safe_name(site_name) + ".log")


def human_size(size):
	for unit in ("B", "KB", "MB", "GB"):
		if size < 1024:
			return f"{size:.1f} {unit}"
		size /= 1024
	return f"{size:.1f} TB"


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


# --------------------------------------------------------------------------
# Puller
# --------------------------------------------------------------------------


class PullError(Exception):
	pass


class Puller:
	"""All the work, no UI. `log(site_name, message)` reports progress."""

	def __init__(self, log):
		self.log = log
		self.lock = threading.Lock()

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

	def pull_site(self, config, site):
		"""Download the site's latest backups that were not pulled before."""
		with self.lock:
			return self._pull_site(config, site)

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
					self.log(name, "The site has no backup from the last 30 days.")
				continue
			filename = os.path.basename(remote_path)
			if filename in pulled:
				continue
			new_files.append((file_type, filename))

		if not new_files:
			self.log(name, "Up to date.")
			return 0

		root, location = target_root(config)
		count = 0
		for file_type, filename in new_files:
			folder = os.path.join(root, safe_name(name), backup_folder_for(filename))
			os.makedirs(folder, exist_ok=True)
			dest = os.path.join(folder, filename)
			self.log(name, f"Downloading {filename} to {location} ...")
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
			self.log(name, f"Saved {filename} ({human_size(size)}).")
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

	def move_pending(self, config):
		"""Copy fallback backups to the hard disk, verify, then remove the fallback copy."""
		with self.lock:
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
						self.log(site_name, f"Copy of {filename} to the hard disk did not verify; kept on fallback.")
						continue
					os.replace(dest + ".part", dest)
					rec.update({"path": dest, "location": HARD_DISK})
					save_json(STATE_FILE, state)
					_remove(src)
					_remove_empty_dirs(os.path.dirname(src), config["fallback_path"])
					self.log(site_name, f"Moved {filename} to the hard disk.")
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
# Window
# --------------------------------------------------------------------------


def run_app(start_minimized=False):
	import tkinter as tk
	from tkinter import filedialog, messagebox, ttk
	from tkinter.scrolledtext import ScrolledText

	config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
	for key, value in DEFAULT_CONFIG.items():
		config.setdefault(key, value)
	status = {}  # site name -> (last pulled text, last status)
	messages = queue.Queue()

	def log(site_name, message):
		line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  [{site_name}]  {message}"
		os.makedirs(LOG_DIR, exist_ok=True)
		with open(site_log_path(site_name), "a", encoding="utf-8") as f:
			f.write(line + "\n")
		messages.put(line)

	puller = Puller(log)

	root = tk.Tk()
	root.title(f"{APP_NAME} {VERSION}")
	root.geometry("900x620")
	root.minsize(760, 520)

	# ---- Storage ----
	storage = ttk.LabelFrame(root, text="Storage", padding=8)
	storage.pack(fill="x", padx=10, pady=(10, 5))
	disk_var = tk.StringVar(value=config["disk_path"])
	fallback_var = tk.StringVar(value=config["fallback_path"])
	interval_var = tk.StringVar(value=str(config["interval_minutes"]))
	disk_status = ttk.Label(storage, text="")

	def browse(var):
		path = filedialog.askdirectory(initialdir=var.get() or None)
		if path:
			var.set(os.path.normpath(path))

	ttk.Label(storage, text="Hard disk folder:").grid(row=0, column=0, sticky="w")
	ttk.Entry(storage, textvariable=disk_var, width=60).grid(row=0, column=1, sticky="we", padx=5)
	ttk.Button(storage, text="Browse", command=lambda: browse(disk_var)).grid(row=0, column=2)
	disk_status.grid(row=0, column=3, padx=10, sticky="w")
	ttk.Label(storage, text="Fallback folder (this PC):").grid(row=1, column=0, sticky="w", pady=4)
	ttk.Entry(storage, textvariable=fallback_var, width=60).grid(row=1, column=1, sticky="we", padx=5)
	ttk.Button(storage, text="Browse", command=lambda: browse(fallback_var)).grid(row=1, column=2)
	ttk.Label(storage, text="Check every (minutes):").grid(row=2, column=0, sticky="w")
	ttk.Spinbox(storage, from_=10, to=720, increment=10, textvariable=interval_var, width=8).grid(
		row=2, column=1, sticky="w", padx=5
	)
	storage.columnconfigure(1, weight=1)

	def save_storage():
		try:
			interval = max(10, int(interval_var.get()))
		except ValueError:
			messagebox.showerror(APP_NAME, "Check interval must be a number of minutes.")
			return
		disk, fallback = disk_var.get().strip(), fallback_var.get().strip()
		if not disk or not fallback or os.path.abspath(disk) == os.path.abspath(fallback):
			messagebox.showerror(APP_NAME, "Set two different folders: the hard disk and the fallback.")
			return
		config.update({"disk_path": disk, "fallback_path": fallback, "interval_minutes": interval})
		save_json(CONFIG_FILE, config)
		refresh_disk_status()
		messagebox.showinfo(APP_NAME, "Saved.")

	ttk.Button(storage, text="Save", command=save_storage).grid(row=2, column=2)

	def refresh_disk_status():
		if is_disk_connected(config):
			free = shutil.disk_usage(config["disk_path"]).free
			disk_status.config(text=f"Connected ({human_size(free)} free)", foreground="green")
		else:
			disk_status.config(text="NOT connected: using fallback", foreground="red")

	# ---- Sites ----
	sites_frame = ttk.LabelFrame(root, text="Sites", padding=8)
	sites_frame.pack(fill="both", expand=True, padx=10, pady=5)
	cols = ("name", "url", "files", "last", "status")
	tree = ttk.Treeview(sites_frame, columns=cols, show="headings", height=7, selectmode="browse")
	for col, title, width in (
		("name", "Site", 160),
		("url", "URL", 240),
		("files", "Files too", 70),
		("last", "Last new backup", 150),
		("status", "Last status", 220),
	):
		tree.heading(col, text=title)
		tree.column(col, width=width, anchor="w")
	tree.tag_configure("stale", foreground="red")
	tree.tag_configure("disabled", foreground="gray")
	tree.pack(side="left", fill="both", expand=True)

	buttons = ttk.Frame(sites_frame)
	buttons.pack(side="left", fill="y", padx=(8, 0))

	def last_pulled(site_name):
		files = load_json(STATE_FILE, {}).get(site_name, {})
		times = [r["pulled_on"] for r in files.values() if r.get("pulled_on")]
		return max(times) if times else None

	def refresh_sites():
		selected = tree.selection()
		tree.delete(*tree.get_children())
		for site in config["sites"]:
			last = last_pulled(site["name"])
			tags = ()
			if not site.get("enabled", True):
				tags = ("disabled",)
			elif not last or (datetime.now() - datetime.fromisoformat(last)).total_seconds() > STALE_HOURS * 3600:
				tags = ("stale",)
			tree.insert(
				"",
				"end",
				iid=site["name"],
				values=(
					site["name"],
					site["url"],
					"Yes" if site.get("include_files") else "No",
					(last or "never").replace("T", " "),
					status.get(site["name"], "" if site.get("enabled", True) else "Disabled"),
				),
				tags=tags,
			)
		if selected and tree.exists(selected[0]):
			tree.selection_set(selected[0])

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
		d.grab_set()
		v = {
			"name": tk.StringVar(value=site["name"] if site else ""),
			"url": tk.StringVar(value=site["url"] if site else "https://"),
			"api_key": tk.StringVar(value=site["api_key"] if site else ""),
			"api_secret": tk.StringVar(value=""),
		}
		files_var = tk.BooleanVar(value=site.get("include_files", False) if site else False)
		enabled_var = tk.BooleanVar(value=site.get("enabled", True) if site else True)
		rows = (
			("Site name (folder name)", "name", False),
			("Site URL", "url", False),
			("API Key", "api_key", False),
			("API Secret" + (" (blank = keep)" if site else ""), "api_secret", True),
		)
		for i, (label, key, hidden) in enumerate(rows):
			ttk.Label(d, text=label).grid(row=i, column=0, sticky="w", padx=10, pady=4)
			ttk.Entry(d, textvariable=v[key], width=50, show="*" if hidden else "").grid(row=i, column=1, padx=10)
		ttk.Checkbutton(d, text="Also pull files backup (public + private)", variable=files_var).grid(
			row=4, column=1, sticky="w", padx=10
		)
		ttk.Checkbutton(d, text="Enabled (pulled automatically)", variable=enabled_var).grid(
			row=5, column=1, sticky="w", padx=10
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
			target = site if site is not None else {}
			if site and site["name"] != name:
				# Keep the pulled-history under the new name, or everything re-downloads.
				state = load_json(STATE_FILE, {})
				if site["name"] in state:
					state[name] = state.pop(site["name"])
					save_json(STATE_FILE, state)
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

		bar = ttk.Frame(d)
		bar.grid(row=6, column=0, columnspan=2, pady=10)
		ttk.Button(bar, text="Save", command=ok).pack(side="left", padx=5)
		ttk.Button(bar, text="Cancel", command=d.destroy).pack(side="left", padx=5)

	def remove_site():
		site = selected_site()
		if site and messagebox.askyesno(
			APP_NAME, f"Remove {site['name']}? Backups already pulled stay on the disk."
		):
			config["sites"].remove(site)
			save_json(CONFIG_FILE, config)
			refresh_sites()

	def in_background(fn, *args):
		threading.Thread(target=fn, args=args, daemon=True).start()

	def pull(sites):
		for site in sites:
			try:
				n = puller.pull_site(config, site)
				status[site["name"]] = f"OK ({n} new)" if n else "OK (up to date)"
			except Exception as e:
				status[site["name"]] = "FAILED"
				log(site["name"], f"FAILED: {e}")
		try:
			puller.move_pending(config)
		except Exception as e:
			log("storage", f"Moving to the hard disk failed: {e}")
		messages.put(None)  # refresh the table

	def test_selected():
		site = selected_site()
		if not site:
			return

		def run():
			try:
				user, db = puller.test_connection(site)
				msg = f"Connected as {user}.\nLatest backup: {db or 'none in the last 30 days'}"
				root.after(0, lambda: messagebox.showinfo(APP_NAME, msg))
			except Exception as e:
				err = str(e)
				root.after(0, lambda: messagebox.showerror(APP_NAME, err))

		in_background(run)

	def pull_selected():
		site = selected_site()
		if site:
			in_background(pull, [site])

	def pull_all():
		in_background(pull, [s for s in config["sites"] if s.get("enabled", True)])

	def move_now():
		if not is_disk_connected(config):
			messagebox.showwarning(APP_NAME, "The hard disk is not connected.")
			return
		in_background(lambda: (log("storage", f"Moved {puller.move_pending(config)} files."), messages.put(None)))

	def open_path(path):
		os.makedirs(path, exist_ok=True)
		if os.name == "nt":
			os.startfile(path)
		else:
			subprocess.Popen(["xdg-open", path])

	def open_folder():
		site = selected_site()
		if site:
			root_path, _loc = target_root(config)
			open_path(os.path.join(root_path, safe_name(site["name"])))

	def open_log():
		site = selected_site()
		if site:
			path = site_log_path(site["name"])
			if not os.path.exists(path):
				messagebox.showinfo(APP_NAME, "No log yet for this site.")
			elif os.name == "nt":
				os.startfile(path)
			else:
				subprocess.Popen(["xdg-open", path])

	for text, cmd in (
		("Add Site", lambda: edit_site()),
		("Edit Site", lambda: (s := selected_site()) and edit_site(s)),
		("Remove Site", remove_site),
		(None, None),
		("Test Connection", test_selected),
		("Pull Latest Now", pull_selected),
		("Pull All Now", pull_all),
		(None, None),
		("Open Folder", open_folder),
		("Open Log", open_log),
		("Move to Hard Disk", move_now),
	):
		if text is None:
			ttk.Separator(buttons).pack(fill="x", pady=6)
		else:
			ttk.Button(buttons, text=text, command=cmd, width=18).pack(pady=2)

	# ---- Log ----
	log_frame = ttk.LabelFrame(root, text="Activity", padding=8)
	log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))
	log_box = ScrolledText(log_frame, height=10, state="disabled", font=("Consolas", 9))
	log_box.pack(fill="both", expand=True)

	def drain_messages():
		while True:
			try:
				line = messages.get_nowait()
			except queue.Empty:
				break
			if line is None:
				refresh_sites()
				refresh_disk_status()
				continue
			log_box.config(state="normal")
			log_box.insert("end", line + "\n")
			log_box.see("end")
			log_box.config(state="disabled")
		root.after(500, drain_messages)

	# ---- Timer ----
	next_run = {"at": time.time() + 5}  # first check shortly after start

	def tick():
		if time.time() >= next_run["at"]:
			next_run["at"] = time.time() + config["interval_minutes"] * 60
			pull_all()
		refresh_disk_status()
		root.after(30 * 1000, tick)

	refresh_sites()
	refresh_disk_status()
	drain_messages()
	tick()
	if start_minimized:
		root.iconify()
	if "--smoke-test" in sys.argv:
		# CI: build the whole window, then exit cleanly.
		root.after(3000, root.destroy)
	root.mainloop()


def main():
	# One copy at a time, or two would download the same backups.
	lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	try:
		lock.bind(("127.0.0.1", LOCK_PORT))
	except OSError:
		try:
			import tkinter.messagebox as mb

			mb.showinfo(APP_NAME, f"{APP_NAME} is already running.")
		finally:
			sys.exit(0)
	run_app(start_minimized="--minimized" in sys.argv)


if __name__ == "__main__":
	main()
