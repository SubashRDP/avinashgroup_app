# Biometric Attendance, K40 Bridge & Attendance Payroll — Technical Reference

> Chapter 3 of the technical documentation. Audience: developers.
> User-facing guide: [`../user_guide/03-attendance-hr.md`](../user_guide/03-attendance-hr.md)
> Bridge install runbook: `k40_bridge/SETUP.md`. Legacy migration: `docs/migrate_from_biometric_and_nepal_hrms.md` (historical — its endpoints refer to the old apps).

## 1. Architecture at a glance

```
ZKTeco device (ADMS push) ──HTTP──► /iclock/*  (IclockRenderer)
                                            │
K40 Bridge (Windows app) ──POST──► biometric.api.receive_attendance
   │  ▲                                     │
   │  └─ poll_commands / report_command_result / heartbeat.ping
   ▼
process_attendance_records()  ─► Employee Checkin (IN/OUT alternation)
                                            │ HRMS auto-attendance
                                            ▼
                                      Attendance (validate hooks:
                                      shift deviation, late half-day,
                                      holiday flag)
                                            │
                          Payroll Entry ─► Additional Salary drafts
                          (attendance-driven Salary Components)
```

Two ingestion paths converge on one core pipeline; everything is
**company-scoped through the device serial**.

## 2. Ingestion

### 2.1 ADMS push — `biometric/iclock.py`

`IclockRenderer(BaseRenderer)` registered as a `page_renderer` (`hooks.py:11`);
claims any `/iclock/*` path. Implements the ZKTeco ADMS subset:
`GET /iclock/cdata?options=all` returns the config block (`ATTLOGStamp=9999`,
`Realtime=1`, …); `POST /iclock/cdata?...&table=ATTLOG` parses tab-separated
punch rows (`_process_attlog`, `iclock.py:129-169`); `getrequest`/`ping`/
`devicecmd`/`fdata` just ack `OK`. Always returns plain-text 200 even on error
(prevents device retry-storms); failures go to Error Log and `logs/iclock.log`.
`assert_known_device(sn)` gates every upload.

### 2.2 Bridge push — `biometric/api.py`

`receive_attendance(attendance_data, device_identifier)` —
`@frappe.whitelist(methods=["POST"])`. 403 for unknown/disabled serials;
validates `user_id`+`timestamp` per record; hands to the core.

### 2.3 Core pipeline — `biometric/utils.py::process_attendance_records` (`:42-195`)

- Resolves the **device's company** from `Biometric Device.company` by serial —
  the linchpin of multi-company support.
- Groups punches by `(user_id, date)`; malformed timestamps → permanent
  `skipped_punches`. Parser accepts `%Y-%m-%d %H:%M:%S`, ISO variants.
- Employee lookup is **company-scoped**: `{attendance_device_id, company}`.
  No match → group `skipped` (retryable once the employee is registered).
- Each (employee, date) group runs in a DB savepoint.
- Returns per-punch outcome lists (`synced_punches` / `failed_punches` /
  `skipped_punches`, ids `"{user_id}_{timestamp}"`) — the bridge uses these to
  decide what to dedup vs resend.
- Updates `Biometric Device.last_sync_time` / `total_synced` on success.

### 2.4 Checkin reconciliation — `_reconcile_day_checkins` (`utils.py:198-244`)

Every punch = one Employee Checkin. Merges existing + new for the day, dedups
by exact timestamp, sorts chronologically, assigns **alternating log types**
(index 0 → IN, 1 → OUT, …). Idempotent; a late-arriving earlier punch slots in
by time and downstream rows flip IN↔OUT. New checkins get
`custom_company = employee.company`, `device_id = serial`,
`skip_auto_attendance = 0`.

## 3. Attendance hooks

All Attendance hooks run on **`validate`** — auto-attendance inserts rows
already submitted, so `before_save` would never fire (`hooks.py:118-129`).

| Hook | File | Behavior |
|------|------|----------|
| `set_shift_deviation_fields` | `biometric/attendance_override.py:15-68` | computes `custom_late_entry` / `custom_early_entry` / `custom_early_exit` / `custom_late_exit` (seconds, rounded to nearest minute, ≥30 s rounds up) vs Shift Type start/end; overnight-shift aware |
| `enforce_late_arrival_half_day` | `:117-148` | if Shift Type `custom_late_arrival_cutoff_time` is set and first check-in is later → force status Half Day + `leave_type "Leave Without Pay"`. Blank cutoff disables |
| `set_holiday_flag` | `payroll/attendance_allowance.py:207-229` | sets read-only `custom_worked_on_holiday` when the date is in the employee's (or company default) Holiday List |
| `reconcile_with_existing_attendance` (Employee Checkin `after_insert`) | `attendance_override.py:71-114` | past-date orphan punches only: link checkin to an existing Present/Half Day Attendance; never creates/changes status (that's Attendance Fix's job) |
| `validate_unique_device_id` (Employee `validate`) | `biometric/employee.py` | `attendance_device_id` unique **per company** (patch `company_scoped_attendance_device_id` dropped the stock global-unique index) |

Test suite: `biometric/test_attendance_pipeline.py` — company-scoped mapping,
IN/OUT alternation + idempotency + punch reflow, duplicate device-id block,
deviation math, late-arrival rule, and end-to-end auto-attendance
(`bench --site avinas1 run-tests --app avinashgroup_app --module
avinashgroup_app.biometric.test_attendance_pipeline`).

## 4. The K40 Bridge (`k40_bridge/`, Windows desktop app)

Python/Tkinter, PyInstaller + Inno Setup → `K40BridgeSetup.exe`.
`VERSION = "1.6.6"` (`k40_bridge.py:48`, matches `latest_version.txt`).

### 4.1 Server endpoints it uses (`k40_bridge.py:50-65`)

| Purpose | Endpoint |
|---------|----------|
| push punches | `avinashgroup_app.biometric.api.receive_attendance` |
| liveness | `avinashgroup_app.biometric.heartbeat.ping` (every cycle) |
| pull admin commands | `avinashgroup_app.biometric.bridge_commands.poll_commands` |
| report command result | `avinashgroup_app.biometric.bridge_commands.report_command_result` |
| auth test | `frappe.auth.get_logged_user` |

Auth: `Authorization: token KEY:SECRET` (`ErpnextClient`,
`k40_bridge.py:1481-1655`). Credentials Fernet-encrypted at rest.

### 4.2 Device sources

- `ZKTecoClient` — ZK TCP protocol port 4370 (K40/K20/F18/MB360/eSSL) via pyzk
- `HikvisionClient` — ISAPI HTTP
- `HtmsClient` — reads HTMS-86/HAMS Microsoft Access `.mdb` directly
  (`PubEvent.personID → Emp.Emp_no` as `user_id`); one HTMS source collapses
  all controllers into one feed

Each configured device row: name, type, ip/port or db_folder, **serial**,
**company**.

### 4.3 Sync engine (`SyncEngine`, `k40_bridge.py:1656-2100`)

Two daemon threads (scheduled sync loop + 30 s command poller) serialized by a
lock. Per device: heartbeat first (so a quiet device still looks alive), pull
punches from persisted last-sync date (first run = everything, no upper bound),
filter against a local SQLite `DedupStore` keyed `{serial}_{user_id}_{ts}`,
POST in batches of 100. Only server-confirmed `synced` punches get dedup-marked
— `skipped` ones (employee not yet registered) resend next cycle. Outcomes also
logged in a local `SyncLogStore`. Default interval 1440 min (configurable down
to 2 min).

### 4.4 Command tunnel (`biometric/bridge_commands.py`)

Outbound-polled so admins can reach devices behind NAT/LAN:
1. Desk enqueues a **Biometric Device Command** (Pending).
2. Bridge `poll_commands(serial)` atomically claims Pending→Running (raw SQL +
   `ROW_COUNT()` race guard, increments `attempts`).
3. Bridge executes: `force_sync` (optional `from_date` payload) or
   `test_connection`.
4. `report_command_result` → Done/Failed (serial-ownership verified,
   idempotent).

`enqueue_command(device, command_type, payload)` is the desk helper (used by
the "Force Bridge Sync" button on Biometric Device, which then polls the
command row every 3 s for up to 90 s).

### 4.5 Heartbeat alerting (`biometric/heartbeat.py`)

`ping(serial)` updates `last_contact_time`. Hourly scheduler
`check_bridge_heartbeats` (`hooks.py:242-245`): per enabled device with alert
recipients, compares `last_contact_time` (fallback `last_sync_time`) to
`alert_threshold_minutes` (default 120). Emails **only on state transitions**
(Connected→Disconnected and back), state persisted in `connection_status` — a
permanently dead bridge emails once, not hourly. The recovery email tells HR to
run Attendance Fix for the outage range.

## 5. Doctypes

| Doctype | Purpose / key fields |
|---------|---------------------|
| **Biometric Device** (autoname `field:device_name`) | one row per device/feed: `device_serial` (unique — matched against SN), `company` (reqd), `enabled`, ip/port/model, RO sync stats (`last_contact_time`, `last_sync_time`, `total_synced`), `alert_threshold_minutes` + `alert_recipients` table, `connection_status`. JS adds Force Bridge Sync button |
| **Biometric Device Command** (`BDC-.#####`) | `device`, `command_type` (force_sync/test_connection), `status` Pending/Running/Done/Failed, `attempts` ("Bridge Poll Count"), `payload` JSON, `result` |
| **Biometric Device Alert Recipient** (child) | `email`, `recipient_name` |
| **Attendance Fix** (submittable, `AF-.YYYY.-`) | repair tool: `shift_type` (reqd), `from_date`/`to_date` (reqd), optional `employee`/`company`/`devices`; RO progress + counters + log |
| **Attendance Fix Device** (child) | `device` link |
| **Employee Attendance Allowance** (child on Employee as `custom_attendance_allowances`) | `salary_component`, `eligible` (default 1), `rate` (overrides component default), `effective_from` |

### Attendance Fix internals (`attendance_fix.py`)

`on_submit` → status Queued → background job on the `long` queue (4 h
timeout), runs as Administrator with `frappe.flags.audit_user = doc.owner`.
`_resolve_employees`: shift-assigned employees filtered by
employee/company/device-serial checkins, Active only. `_reconcile_day`
(`:190-332`) matrix:

| Checkins? | Existing Attendance | Action |
|-----------|--------------------|--------|
| yes | none | create from checkins & link |
| yes | Absent | delete stale Absent, recreate |
| yes | Present/Half Day | relink orphan checkins |
| no | none | mark Absent (skipping holidays) |
| no | any | leave alone |

Reuses stock HRMS `mark_attendance`, `mark_attendance_and_link_log`,
`update_attendance_in_checkins`; calls `fetch_shift()` for shiftless checkins.
Per-day savepoints; realtime progress via `attendance_fix_progress` (the form
shows a live progress bar and auto-reloads while Running).

## 6. Attendance allowance engine (`payroll/attendance_allowance.py`)

Turns Attendance rows + rates into **Additional Salary** drafts.

Custom fields (patch `setup_attendance_allowance`): Salary Component —
`custom_is_attendance_driven`, `custom_condition_type` (Working Hours ≥
Threshold / Status = Present / Status = Half Day / Worked on Holiday / Early
Entry Before / Late Stay After / Late Arrival After), `custom_threshold_hours`,
`custom_time_offset_hours`, `custom_unit` (Per Day / Per Hour / Flat per
Period), `custom_default_rate`, `custom_summary_group`; Employee —
`custom_ot_eligibility`, `custom_attendance_allowances`; Additional Salary —
`custom_source`.

Flow: `trigger_for_payroll_entry(pe)` (whitelisted; the **Calculate Attendance
Allowances** button in `payroll_entry.js`) → for each employee × attendance-
driven component: skip OT-only conditions for non-OT-eligible employees;
resolve rate (employee override row → component default → skip);
`qty = Σ evaluate_rule(attendance)` over submitted rows in the period ("Flat
per Period" → 1 if any match); delete prior draft tagged
`custom_source = "Nepal HRMS Attendance Allowance"` and recreate (idempotent).
`evaluate_rule` (`:150-186`) is shared with the BS attendance reports:
Present = 1.0/day (Half Day 0.5); holiday rule needs `custom_worked_on_holiday`
+ Present/Half Day; the time rules compare `custom_early_entry` /
`custom_late_exit` / `custom_late_entry` seconds to `custom_time_offset_hours`.
`recompute_holiday_flags` (whitelisted) backfills the holiday flag.

`public/js/attendance.js` renders a read-only "Checkin Log" table (IN green /
OUT orange, linked) on the Attendance form.

## 7. HR/BS reports (module reports; see also chapter 8)

| Report | One-liner |
|--------|-----------|
| Monthly Attendance BS | per-day grid for a BS month (BS+AD dates, IN/OUT, hours, late/early minutes, dynamic per-component allowance qty columns, holiday awareness) |
| Monthly Attendance Summary BS | one row/employee/BS month mirroring the Nepal Gas physical sheet; components collapsed by `custom_summary_group` (Meal, Tea & Conveyance…), OT hrs, leave current/previous/cumulative-from-Shrawan |
| Work On Holiday BS | per-employee holiday-work counts bucketed into 12 BS months (Shrawan→Ashadh), OT-eligibility column |
| Yearly Leave Details BS | per-employee/FY: 12 BS-month leave cells (approved Leave Applications split day-by-day, half-days 0.5), allocation total (excl. carry-forward), remaining |
| Avinas Salary Statement | Salary Slip pivot for a BS month: dynamic earning/deduction columns, gross/net, previous-month net, grouped by designation with sub-totals |

All storage is AD; BS is presentation-only via `rdp_common_app.utils.bs_boundaries`
/ `nepali_datetime`. Roles: HR Manager/HR User/System Manager.

## 8. Patches in this domain

`setup_attendance_allowance`, `v1_add_biometric_device_serial`,
`add_company_to_employee_checkin` (fetch_from company on Employee Checkin),
`company_scoped_attendance_device_id`, `add_company_to_shift_type` (required
company on Shift Type — Shift Types are per-company).
