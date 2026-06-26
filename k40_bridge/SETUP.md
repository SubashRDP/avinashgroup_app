# Biometric Integration — Setup Guide

End-to-end setup for getting K40 (or other ZKTeco) fingerprint devices feeding attendance into ERPNext.

```
┌──────────┐    LAN    ┌────────────┐    HTTPS     ┌─────────┐
│   K40    │ ◀────────▶│  Windows   │ ───────────▶ │ ERPNext │
│  device  │  (TCP     │  host      │  POST punch  │ (site)  │
│ port 4370│   poll)   │  k40_bridge│              │         │
└──────────┘           └────────────┘              └─────────┘
```

The "Windows host" is any always-on Windows machine on the same LAN as the device(s). It polls the device every `sync_interval_minutes` and pushes new punches to ERPNext as Employee Checkins.

---

## 0. What you need before you start

- [ ] ERPNext site URL, e.g. `https://your-site.example.com`
- [ ] Administrator login to that site
- [ ] The K40 device powered on and connected to LAN — note its **IP**, **port** (default `4370`), and **serial number** (sticker on the back, e.g. `A6F5215360564`)
- [ ] A Windows 10 / 11 machine on the same LAN as the device, with internet access to reach the ERPNext site
- [ ] Admin rights on that Windows machine (the installer registers a Task Scheduler entry)

---

## Part A — ERPNext side (do this once per site)

### A.1 Confirm `avinashgroup_app` is installed

```bash
bench --site your-site list-apps | grep avinashgroup_app
```

If it's missing, `bench --site your-site install-app avinashgroup_app`.

### A.2 Generate an API Key + Secret for the bridge

1. In the desk, search for **User** and pick a user dedicated to the bridge (e.g. `bridge@yourcompany.com` — create one if needed, give it role **Employee Self Service** plus the permissions below).
2. Give that user permissions on:
   - **Employee Checkin** — Create, Read
   - **Biometric Device** — Read, Write
   - **Employee** — Read
3. Open the user → scroll to **API Access** → click **Generate Keys**.
4. Copy:
   - **API Key** (always visible)
   - **API Secret** (shown **once** — save it now in a password manager)

> The same key can be shared across multiple devices that push to the same site.

### A.3 Set each Employee's device ID

Each employee's User ID on the fingerprint device must match the **Attendance Device ID** field on their Employee record.

For each employee:
1. Open the **Employee** record in ERPNext.
2. Find the field **Attendance Device ID** (under the Attendance & Leave Details section).
3. Enter the User ID exactly as it appears on the device (typically a number like `1`, `2`, `42`).
4. Save.

> If you skip this step, the bridge will push punches and the server will log `Employee not found for device ID: X` for every punch from that user.

### A.4 (Optional) Create a Biometric Device record

This gives you a Frappe-side dashboard showing last-sync time, total punches synced, etc. — not required for sync to work.

1. Search for **Biometric Device** in the desk → **New**.
2. Fill in **Device Name** (matches what you'll set in the bridge), **Device IP**, **Device Port**, **Serial**.
3. Save.

---

## Part B — On the K40 device itself

1. In the device menu: **Menu → Comm. → Ethernet** — confirm IP / subnet / gateway. Static IP is recommended.
2. **Menu → Comm. → Cloud Server Setting** — leave **off** (we're using the bridge, not ADMS push).
3. Enrol each employee (fingerprint or card) and **note the User ID number assigned to them** — this is what goes into the Employee's `Attendance Device ID` field above.

Quick reachability test from the Windows host (a Command Prompt):
```cmd
ping 192.168.18.200
```
If ping fails, the bridge cannot reach the device — fix the LAN before continuing.

---

## Part B-HTMS — HTMS-86 / HAMS sources (HUNDURE / Chiyu controllers)

Some sites use **HTMS-86** (a.k.a. HAMS) access-control software driving HUNDURE
HTA-series controllers (`HTA-640PE`, `HTA-860PEF`, …). These controllers **do not
speak the ZK protocol**, so there's no device to poll on port 4370. Instead HTMS-86
writes every punch into Microsoft Access databases, and the bridge reads those
directly.

```
┌─────────────┐  writes  ┌──────────────┐   reads   ┌────────────┐  HTTPS  ┌─────────┐
│ HUNDURE HTA │ ───────▶ │  HTMS-86     │ ◀──────── │ k40_bridge │ ──────▶ │ ERPNext │
│ controllers │  punches │  HAMS_*.mdb  │  (ADO/Jet)│ (same host)│  punch  │ (site)  │
└─────────────┘          └──────────────┘           └────────────┘         └─────────┘
```

**Run the bridge on the same Windows machine that runs HTMS-86** (or any machine
that can see the HTMS-86 folder), so it can read the `.mdb` files locally.

### How the data maps

| HTMS-86 | → | ERPNext |
|---|---|---|
| `PubEvent.personID` (e.g. `0000000116`) | join via `Emp` table | — |
| `Emp.Emp_no` (e.g. `124`) | **sent as user_id** | `Employee.attendance_device_id` |
| `PubEvent.eventDate` + `eventTime` | combined | checkin time |

So set each Employee's **Attendance Device ID** to their HTMS **Emp_no (work
number)** — **exactly as stored, including any leading zeros** (HTMS stores
`003`, `077`, `01`, etc.). Look it up in HTMS under the employee's profile, or in
the `Emp` table.

### Setup steps

1. **ERPNext side:** do Part A as usual, but in **A.3** set `Attendance Device ID`
   to the HTMS `Emp_no` (not a ZK user id). In **A.4** create a **Biometric
   Device** record whose **Serial** is any stable identifier you choose for this
   HTMS feed (e.g. `HTMS-NGI-01`) and `enabled = 1` — the bridge must send a
   registered serial or the server rejects with 403.
2. **Bridge side:** in the wizard under **Step 2b — Attendance Software /
   Database**, click **+ Add Software Source** and fill:

   | Field | Value |
   |---|---|
   | Name | `HTMS Filling Plant` (any label) |
   | Type | **`htms`** |
   | HTMS-86 Folder | the folder containing `HAMS.mdb` and `HAMS_<year>.mdb`, e.g. `E:\HTMS-86` (use the **…** button to browse to it) |
   | Serial | the Biometric Device serial from step 1, e.g. `HTMS-NGI-01` |

3. Click **Test** on the row — it verifies the folder + `HAMS.mdb` exist and
   counts today's punches. Then **Save & Start**.

### Notes

- Punches live in per-year files `HAMS_<year>.mdb`; employee work-numbers live in
  the master `HAMS.mdb`. The bridge reads whichever yearly files cover the sync
  window (all of them on the first/full sync).
- One HTMS source collapses **all** of that install's controllers into a single
  feed — attendance only needs *who* and *when*, so the individual door/reader is
  not distinguished. Door/alarm rows (no person) are ignored automatically.
- Reading uses the **Jet OLEDB** provider that ships with Windows (the same one
  HTMS-86 uses), so no extra database driver is needed on a 32-bit build. If you
  run a 64-bit build against a machine without 64-bit Access drivers, install the
  **Microsoft Access Database Engine redistributable** matching the bridge's
  bitness.

---

## Part C — Windows host (bridge installation)

### C.1 Download the installer

Direct download (always points at the latest release):

```
https://github.com/SubashRDP/avinashgroup_app/releases/latest/download/K40BridgeSetup.exe
```

### C.2 Install

1. Right-click `K40BridgeSetup.exe` → **Run as administrator**.
2. Accept the UAC prompt.
3. On the "Auto-start" page, leave **Start K40 Bridge automatically when Windows boots** checked.
4. Finish the wizard. The bridge launches automatically.

### C.3 First-run wizard

The wizard appears on first launch. Fill in:

| Field | Example | Notes |
|---|---|---|
| **ERPNext URL** | `https://your-site.example.com` | No trailing slash. Must include `https://`. |
| **API Key** | from step A.2 | |
| **API Secret** | from step A.2 | |
| **Sync Frequency** | `2 minutes` | For near-real-time. Use `1 day` for once-daily. |
| **Devices** table | one row per K40 | |

The devices step has **two sections** — add each source under the one that fits:

**Step 2a — Direct Device Connection** (network-polled units): click **+ Add Device** and fill the fields the chosen Type asks for.

| Type | Fields shown |
|---|---|
| `zkteco` (K40/K20/F18…) | Device IP, Port (`4370`), Comm Key (`0` unless set) |
| `hikvision` | Device IP, Port (`80`), Username, Password |

**Step 2b — Attendance Software / Database** (read from software's own data store): click **+ Add Software Source**.

| Type | Fields shown |
|---|---|
| `htms` (HTMS-86 / HAMS) | HTMS-86 Folder (use the **…** button to browse) — see **Part B-HTMS** |

Every row, in either section, also needs a **Name** and a **Serial** (the registered Biometric Device the server matches against).

Click **Test** on the row (probes the device / data folder), then **Test Connection** for ERPNext auth — both the device probe (LAN) and the API auth (ERPNext) should turn green. If either is red, see Troubleshooting below.

Click **Save & Start**.

### C.4 Confirm it's running

The control panel shows each device with a green dot and a Last Sync time.

**How it runs:** the bridge works **invisibly in the background** — once installed it auto-starts at login with **no window and no tray icon**, so the person using the PC won't see anything. It keeps posting attendance on its own.

- **To open it** (to change settings or check status): launch **K40 Bridge** again (Start Menu / desktop / double-click the exe). The running background copy pops its window up — it does not start a second copy.
- **Closing the window (X)** just hides it again (window + tray icon disappear); **posting keeps running** in the background.
- **To fully stop it**, use the **Quit Bridge** button (or the tray icon's **Exit** while the window is open). It will start again at the next login.
- **Updates** install themselves automatically while it runs in the background.

---

## Part D — Verify end-to-end

1. On the device, have one enrolled employee tap their finger.
2. Wait `sync_interval_minutes` (or click **Force Sync All** in the bridge for immediate).
3. In ERPNext, open **Employee Checkin** list, filter by that employee.
4. You should see a new row with the punch time and `Log Type = IN` (first punch of the day) or `OUT` (second), alternating from there.
5. Tap again 30 seconds later — you should get a second checkin row with the opposite log type.

If the auto-attendance is configured on the Shift Type, an **Attendance** record will be created/updated for that date automatically a few minutes after the checkins land.

---

## Common issues

| Symptom | Most likely cause |
|---|---|
| `AUTH FAIL` in bridge | Wrong API Key/Secret, or the user is disabled. Test with `curl -H "Authorization: token KEY:SECRET" https://your-site/api/method/frappe.auth.get_logged_user` |
| `UNREACHABLE` | **ZK/Hikvision:** Windows host cannot reach device IP on port 4370 — check firewall / cable / device IP. **HTMS:** the configured folder or its `HAMS.mdb` doesn't exist — check the folder path. |
| HTMS syncs but no checkins appear | `Attendance Device ID` must equal the HTMS **Emp_no** *exactly*, including leading zeros (`003`, not `3`). |
| HTMS: `no usable Access OLEDB provider` | 64-bit build on a machine with no 64-bit Access driver. Use the 32-bit bridge build, or install the Microsoft Access Database Engine redistributable. |
| Bridge syncs but no checkins appear | Employee's `Attendance Device ID` doesn't match the User ID on the device. Open Error Log in ERPNext — there'll be a `Biometric Processing Error` row saying `Employee not found for device ID: X`. |
| HTTP 404 from ERPNext | `avinashgroup_app` not installed on that site (or you typed the URL wrong). Check `bench --site X list-apps`. |
| Checkins appear but `Log Type` is wrong | The bridge always sends raw timestamps; the **server** assigns IN/OUT by chronological position (1st of day → IN, 2nd → OUT, …). If you want all-IN or all-OUT instead, that's a server-side code change, not a config one. |
| Bridge GUI doesn't open after install | Run `k40_bridge.exe` from a Command Prompt (Win+R → `cmd` → navigate to `C:\Program Files\K40Bridge\` → `k40_bridge.exe`) — startup errors print to the console. |

Logs live in `%APPDATA%\K40Bridge\k40_bridge.log` (last 5 rotated files, 10 MB each).

---

## Day-2 operations

- **Add a new device** later: open the bridge → **Edit Config** → add a row → Save. No reinstall needed.
- **Change the API key**: same — Edit Config → update → Save.
- **Move to a different Windows host**: install the bridge there, then copy `%APPDATA%\K40Bridge\` from the old host to the same path on the new one (this preserves the dedup state in `k40_synced.json` so previously-synced punches aren't re-sent).
- **Upgrade the bridge**: the bridge checks `latest_version.txt` on its own and prompts you to upgrade when a new release is published. Or download the latest `K40BridgeSetup.exe` and run it — Inno Setup detects the existing install and upgrades in place. Config and dedup state are preserved.

---

## Reference: what the server endpoint expects

If you ever need to push punches without the bridge (testing, alternate scripts):

```http
POST /api/method/avinashgroup_app.biometric.api.receive_attendance
Authorization: token KEY:SECRET
Content-Type: application/json

{
  "device_identifier": "A6F5215360564",
  "attendance_data": [
    {"user_id": "42", "timestamp": "2026-05-19 09:00:00"},
    {"user_id": "42", "timestamp": "2026-05-19 13:30:00"}
  ]
}
```

`device_identifier` must match a registered `Biometric Device.device_serial` (with `enabled=1`) or the request is rejected 403. IN/OUT is computed from chronological position across all punches for that (employee, date) — you don't supply it.
