# K40 Bridge

A Windows application that syncs attendance punches to one or more ERPNext sites from:

- **ZKTeco** devices (K40, K20, F18, MB360, eSSL…) — network poll over port 4370 (`type: zkteco`)
- **Hikvision** access devices — ISAPI HTTP (`type: hikvision`)
- **HTMS-86 / HAMS** software (HUNDURE/Chiyu HTA controllers) — reads punches straight from the HAMS Access `.mdb` files, no network device to poll (`type: htms`). See **[SETUP.md → Part B-HTMS](SETUP.md)**.

> **For a full end-to-end setup walkthrough (ERPNext side + device side + bridge install),** see [SETUP.md](SETUP.md). This README is the reference for the bridge itself.

---

## Quick Start

1. Download the installer from the latest release:
   `https://github.com/SubashRDP/avinashgroup_app/releases/latest/download/K40BridgeSetup.exe`
2. Run it as administrator (it registers an auto-start task).
3. The setup wizard appears on first launch. Fill in:
   - **ERPNext URL** — e.g. `https://your-site.example.com`
   - **API Key** + **API Secret** — generated from a Frappe User (see below)
   - **Devices** — one row per K40 (Name, IP, Port, Serial)
   - **Sync Frequency** — default `1 day` (use `2 minutes` for near-real-time)
4. Click **Test Connection** to verify credentials, then **Save & Start**.
5. The control panel opens. Sync runs automatically; use **Force Sync All** for ad-hoc real-time sync.

---

## Files Created Next to the EXE

| File | Purpose |
|------|---------|
| `config.json` | Bridge configuration (devices, credentials, interval) |
| `k40_synced.json` | Tracks already-synced punches across runs (dedup) |
| `k40_bridge.log` | Rotating log file (10 MB per file, last 5 kept) |
| `k40_bridge.log.1`, `.2`, ... | Rotated logs |

To migrate to a new machine, copy the whole folder.

---

## Creating an ERPNext API Key

1. In ERPNext, create or pick a User (e.g. `bridge@yourcompany.com`).
2. Make sure that User has these permissions:
   - **Employee Checkin**: Create
   - **Biometric Device**: Read, Write
3. Open the User profile → **API Access** section → click **Generate Keys**.
4. Copy the **API Key** (always visible) and **API Secret** (shown once — save it now).
5. Paste both into the bridge's setup wizard.

The same key can be shared across all devices that push to the same ERPNext site.

---

## Control Panel

```
┌─ K40 Bridge ───────────────────────────────────────────────┐
│  ● Running   Next sync in: 23h 45m   [Pause] [Edit Config] │
│                                                            │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Name           IP : Port         Last Sync   Status │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │ Main Office    192.168.18.200    12:34:15    ● OK   │  │
│  │ Floor 2        192.168.18.202    —           ● UNR  │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                            │
│  [Force Sync All]  [Force Sync Selected]                   │
│                                                            │
│  Recent log: ...                                           │
└────────────────────────────────────────────────────────────┘
```

### Status indicators

| Indicator | Meaning |
|-----------|---------|
| `● OK — N new, M skipped` | Sync succeeded |
| `⟳ syncing…` | In progress |
| `● UNREACHABLE` | Cannot reach device on the LAN (check power/network) |
| `● ERROR` | Device responded but parsing/push failed |
| `● AUTH FAIL` | ERPNext rejected the API token |

### Buttons

| Button | Action |
|--------|--------|
| **Force Sync All** | Immediately syncs every device, ignoring the timer |
| **Force Sync Selected** | Sync only the rows highlighted in the table |
| **Pause / Resume** | Stops/starts the auto-sync loop |
| **Edit Config** | Reopens the setup wizard to add/remove devices, change interval |
| **Open Log Folder** | Opens the folder containing `k40_bridge.log` |

---

## Sync Interval

Default is **1 day** (auto-sync once every 24 hours). The Force Sync Now button is the primary way to get real-time data when needed.

You can change to a shorter interval (1 hour, 30 / 15 / 10 / 5 / 2 minutes) in the setup wizard. Faster intervals create more device load and network traffic — only use if you need near-real-time data.

---

## Network Unreachable Detection

Before each device sync, the bridge does a fast TCP probe (5-second timeout, 3 retries with exponential backoff). If the device is unreachable:

- Status turns red with `● UNREACHABLE`
- Log shows one warning line (not per retry)
- Other devices continue syncing normally
- Next cycle automatically retries — no manual intervention needed

---

## Troubleshooting

| Problem | Check |
|---------|-------|
| Status: AUTH FAIL | Verify API Key + Secret in `config.json`. Test on ERPNext: `curl -H "Authorization: token KEY:SECRET" https://your-site/api/method/frappe.auth.get_logged_user` |
| Status: UNREACHABLE | Ping the device IP from this Windows machine. Verify port 4370 is open. |
| Status: ERROR (HTTP 404) | ERPNext URL is wrong, or `avinashgroup_app` is not installed on that site. |
| No punches appearing | Verify Employee record has `attendance_device_id` matching the K40's user ID. |
| GUI doesn't open | Run the exe from a Command Prompt to see any errors. |

Logs are your friend — click **Open Log Folder** and review `k40_bridge.log`.

---

## Running on Boot (Windows Task Scheduler)

1. Open Task Scheduler → Create Basic Task
2. Name: `K40 Bridge`
3. Trigger: **When the computer starts**
4. Action: **Start a program** → `C:\K40Bridge\k40_bridge.exe`
5. Properties → check **Run whether user is logged on or not**
6. Properties → Settings → uncheck "Stop the task if it runs longer than"

The bridge runs continuously with its own internal timer — Task Scheduler only needs to launch it once at boot.

---

## Building the EXE

The exe is built automatically by GitHub Actions on every push to `k40_bridge/`. To build locally on Windows:

```cmd
pip install -r requirements.txt
pyinstaller --onefile --noconsole --name k40_bridge k40_bridge.py
```

Output is at `dist\k40_bridge.exe`.
