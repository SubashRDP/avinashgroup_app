# Standalone Biometric Integration Setup (for a different ERPNext site)

If you have a ZKTeco K40 (or compatible) and want to push punches into **your own** ERPNext — not the Avinash Group site — use the standalone **`biometric-rpl`** repo. It's the same code, just unbundled from `avinashgroup_app`.

- **Frappe app:** https://github.com/SubashRDP/biometric-rpl
- **Bridge installer (latest):** https://github.com/SubashRDP/biometric-rpl/releases/latest/download/K40BridgeSetup.exe

---

## 0. What you'll need

- [ ] Frappe v15 bench with your ERPNext site already running
- [ ] Shell access to the bench host
- [ ] Administrator login to the site
- [ ] K40 device on the LAN — note **IP**, **port** (default `4370`), **serial** (sticker on the back)
- [ ] An always-on Windows machine on the same LAN as the device
- [ ] Admin rights on that Windows machine

---

## Part A — Install the Frappe app

On the bench host:

```bash
cd /path/to/frappe-bench
bench get-app https://github.com/SubashRDP/biometric-rpl
bench --site your-site install-app biometric_integration
bench --site your-site migrate
bench build --app biometric_integration
bench restart   # or restart `bench start` if running in dev mode
```

After this, the site has:
- A **Biometric Device** DocType (search for it in the desk)
- Six Shift Deviation custom fields on **Attendance** (`custom_late_entry`, `custom_early_entry`, `custom_early_exit`, `custom_late_exit`, plus their section + column break)
- A POST endpoint at:
  `/api/method/biometric_integration.biometric_integration.biometric_integration.zkteco_push_attendance`

---

## Part B — Set up an API user

The bridge authenticates with a Frappe API Key + Secret. Best practice: create a dedicated user instead of using `Administrator`.

1. **User → New** in the desk. E.g. `bridge@yourcompany.com`. Role: **Employee Self Service**.
2. Give that user permission on:
   - **Employee Checkin** — Create, Read
   - **Biometric Device** — Read, Write
   - **Employee** — Read
3. Open the user → scroll to **API Access** → click **Generate Keys**.
4. Copy the **API Key** (always visible) and the **API Secret** (shown once — save it now).

---

## Part C — Tag your employees

Each fingerprint enrolled on the device has a User ID number (`1`, `2`, …). That number must match the **Attendance Device ID** field on the matching Employee record.

For each employee:
1. Open the **Employee** record.
2. Find **Attendance Device ID** (in Attendance & Leave Details).
3. Enter the same number the device uses for that person.
4. Save.

> If you skip this for someone, their punches will arrive at the server but the Error Log will show `Employee not found for device ID: X` and nothing gets recorded.

---

## Part D — Install the Windows bridge

On the Windows machine that has LAN access to the device:

1. Download:
   ```
   https://github.com/SubashRDP/biometric-rpl/releases/latest/download/K40BridgeSetup.exe
   ```
2. Right-click → **Run as administrator**. Accept UAC.
3. Keep **Start K40 Bridge automatically when Windows boots** checked. Finish.
4. The first-run wizard appears. Fill in:

   | Field | Example |
   |---|---|
   | **ERPNext URL** | `https://your-site.example.com` (no trailing slash, must include `https://`) |
   | **API Key** | from Part B |
   | **API Secret** | from Part B |
   | **Sync Frequency** | `2 minutes` for near-real-time, or `1 day` for once-daily |
   | **Devices** | one row per K40: Name, IP, Port (`4370`), Serial |

5. **Test Connection** — both the device probe (LAN reachable) and the API auth (ERPNext) should turn green.
6. **Save & Start**.

---

## Part E — Verify end-to-end

1. Have an enrolled employee tap their finger on the device.
2. Wait for the sync interval, or click **Force Sync All** in the bridge for immediate.
3. In ERPNext, open the **Employee Checkin** list filtered by that employee — a new row should appear with the punch time.
4. Tap again — second row with `Log Type = OUT` (in the standalone version, the **first punch of a day = IN**, **last punch = OUT**; mid-day punches don't create extra checkins by default).

> If you want every punch as its own checkin with strict IN/OUT/IN/OUT alternation (proper mid-day break tracking) — that's the consolidated `avinashgroup_app` behaviour. The standalone `biometric-rpl` keeps the simpler "first IN, last OUT per day" model. Either works; pick what matches your shift policy.

---

## Common gotchas

| Symptom | Fix |
|---|---|
| Bridge `AUTH FAIL` | Wrong key/secret, or user disabled. `curl -H "Authorization: token KEY:SECRET" https://your-site/api/method/frappe.auth.get_logged_user` |
| Bridge `UNREACHABLE` | LAN problem. `ping <device-ip>` from the Windows host. Check firewall on port 4370. |
| Bridge says success, but no checkins in ERPNext | The employee's **Attendance Device ID** doesn't match the device User ID. Check Error Log. |
| HTTP 404 from ERPNext | App not installed on that site (`bench --site X list-apps`) — re-run Part A. |
| Punches show but in wrong day | Device timezone is off. Set it from the K40 menu, then re-sync. |

Logs: `%APPDATA%\K40Bridge\k40_bridge.log` (10 MB rotation, 5 files kept).

---

## Day-2 operations

- **Add a new device**: in the bridge → **Edit Config** → add row → Save.
- **Move bridge to a new Windows host**: install on the new host, then copy `%APPDATA%\K40Bridge\` from old → new (preserves dedup state so old punches don't re-send).
- **Upgrade**: download a newer `K40BridgeSetup.exe` and run it — Inno Setup upgrades in place. Config + dedup state preserved.

---

## If you want to push without the bridge (testing)

```http
POST /api/method/biometric_integration.biometric_integration.biometric_integration.zkteco_push_attendance
Authorization: token KEY:SECRET
Content-Type: application/json

{
  "device_id": "A6F5215360564",
  "employee_id": "42",
  "punch_time": "2026-05-19 09:00:00",
  "punch_type": "IN"
}
```

One POST per punch. `punch_type` in the payload is ignored — the server decides IN/OUT.
