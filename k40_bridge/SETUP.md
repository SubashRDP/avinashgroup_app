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

For each device row:

| Column | Example |
|---|---|
| Name | `Main Office` |
| IP | `192.168.18.200` |
| Port | `4370` |
| Serial | `A6F5215360564` |

Click **Test Connection** — both the device probe (LAN) and the API auth (ERPNext) should turn green. If either is red, see Troubleshooting below.

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
| `UNREACHABLE` | Windows host cannot reach device IP on port 4370. Check firewall / cable / device IP setting. |
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
