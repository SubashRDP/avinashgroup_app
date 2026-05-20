# Migrate from `biometric_integration` + `nepal_hrms` → `avinashgroup_app`

Runbook for sites that currently have **`biometric_integration`** and/or **`nepal_hrms`** installed alongside `avinashgroup_app`. After this, both old apps are uninstalled and all their features run from `avinashgroup_app`.

**Do NOT** run this on a fresh site that never had the old apps — there's nothing to migrate.

> Already done on avinas1 (2026-05-19). Use this guide for any other site that still has the old apps.

---

## What changes

| Before | After |
|---|---|
| `Biometric Device` DocType owned by `biometric_integration` module | Owned by `Avinash Group App` module |
| `Employee Attendance Allowance` DocType owned by `Nepal HRMS` module | Owned by `Avinash Group App` module |
| `Monthly Attendance BS`, `Monthly Attendance Summary BS` reports owned by `Nepal HRMS` | Owned by `Avinash Group App` |
| `biometric_integration` and `nepal_hrms` listed in `bench --site X list-apps` | Both gone |
| K40 bridge pushes to `…biometric_integration.zkteco_push_attendance` | Pushes to `…avinashgroup_app.biometric.biometric_integration.zkteco_push_attendance` |

---

## Why "transfer-then-uninstall" instead of "uninstall-then-reinstall"

Plain `bench uninstall-app biometric_integration` drops every DocType whose `module` belongs to that app — **and all the rows in it**. On a site with 5 `Employee Attendance Allowance` rows and 10 `Attendance.custom_worked_on_holiday=1` rows, that's data loss.

Instead, we change the `module` field on those DocTypes **first** so the old app no longer "owns" them. Then uninstall walks the old app's modules, finds nothing, and deletes nothing. `bench migrate` afterwards picks up the new app's JSON files and syncs them against the existing rows — no data loss.

---

## Pre-flight

- [ ] You have shell access to the bench host
- [ ] You know the site name (e.g. `avinas1`)
- [ ] `avinashgroup_app` is on a branch that has the consolidation commits (e.g. `consolidate-biometric-hrms` or whatever it's merged into)
- [ ] The K40 bridge can be reconfigured later (or is offline during cutover)

```bash
cd /path/to/frappe-bench
SITE=your-site-name        # change me
```

Confirm the old apps are installed and check data that will be affected:

```bash
bench --site "$SITE" list-apps
bench --site "$SITE" mariadb -N -e "
SELECT 'Biometric Device', COUNT(*) FROM \`tabBiometric Device\`
UNION ALL SELECT 'Employee Attendance Allowance', COUNT(*) FROM \`tabEmployee Attendance Allowance\`
UNION ALL SELECT 'Attendance worked_on_holiday=1', COUNT(*) FROM tabAttendance WHERE custom_worked_on_holiday=1;
"
```

> If none of the old apps show up in `list-apps`, you don't need this runbook.

---

## Step 1 — Backup

```bash
bench --site "$SITE" backup
```

Note the path of the dump it prints — keep it until the cutover is verified working.

---

## Step 2 — Transfer DocType + Report ownership

This re-homes the rows so the old apps' uninstall walks find nothing in their modules.

```bash
bench --site "$SITE" mariadb -e "
UPDATE \`tabDocType\` SET module='Avinash Group App'
  WHERE name IN ('Biometric Device', 'Employee Attendance Allowance');
UPDATE \`tabReport\` SET module='Avinash Group App'
  WHERE name IN ('Monthly Attendance BS', 'Monthly Attendance Summary BS');
"
```

Verify:

```bash
bench --site "$SITE" mariadb -N -e "
SELECT name, module FROM \`tabDocType\`
  WHERE name IN ('Biometric Device', 'Employee Attendance Allowance');
SELECT name, module FROM \`tabReport\`
  WHERE name IN ('Monthly Attendance BS', 'Monthly Attendance Summary BS');
"
```

All four rows should show `module = Avinash Group App`.

---

## Step 3 — Uninstall the old apps

If `biometric_integration` is installed:

```bash
bench --site "$SITE" uninstall-app biometric_integration --yes --force
```

If `nepal_hrms` is installed:

```bash
bench --site "$SITE" uninstall-app nepal_hrms --yes --force
```

After each, re-run the verification from Step 2 — the transferred DocTypes should still show `module = Avinash Group App`. If anything's missing, **stop and restore from backup** — Step 2 didn't take.

---

## Step 4 — Migrate

```bash
bench --site "$SITE" migrate
```

This runs the new app's `setup_attendance_allowance` patch (creates Salary Component / Attendance / Employee / Additional Salary custom fields, backfills `custom_worked_on_holiday`) and syncs the transferred DocTypes against `avinashgroup_app`'s JSON definitions.

### Known HRMS develop bug you may hit

```
pymysql.err.OperationalError: (1052, "Column 'amount' in SET is ambiguous")
```

In `hrms.patches.v15_0.update_advance_payment_ledger_amount #2025-09-23`. This is an upstream HRMS develop bug, unrelated to this migration. Workaround:

```bash
bench --site "$SITE" mariadb -e "
INSERT INTO \`tabPatch Log\` (name, creation, modified, modified_by, owner, patch, skipped)
VALUES (
  UUID(), NOW(), NOW(), 'Administrator', 'Administrator',
  'hrms.patches.v15_0.update_advance_payment_ledger_amount #2025-09-23',
  0
);
"
bench --site "$SITE" migrate
```

This inserts a `skipped=0` row for the patch so Frappe's `executed()` check returns truthy and stops re-running it.

---

## Step 5 — Build assets and clear caches

```bash
bench build --app avinashgroup_app
bench --site "$SITE" clear-cache
bench --site "$SITE" clear-website-cache
```

If the site runs under supervisor/production: `bench restart`.
If it runs under `bench start` (dev): Ctrl-C the bench start terminal and re-run `bench start`.

---

## Step 6 — Reconfigure the K40 bridge

The Frappe endpoint changed. The bridge needs the new URL.

**If using the bundled K40 bridge** (apps/avinashgroup_app/k40_bridge/): the new `WEBHOOK_PATH` is already baked in. Just install the new `K40BridgeSetup.exe` over the old one (Inno Setup detects the previous install and upgrades in place).

Direct download:
```
https://github.com/SubashRDP/avinashgroup_app/releases/latest/download/K40BridgeSetup.exe
```

**If you're using a custom bridge or curl/script**: change the URL from

```
/api/method/biometric_integration.biometric_integration.biometric_integration.zkteco_push_attendance
```

to

```
/api/method/avinashgroup_app.biometric.biometric_integration.zkteco_push_attendance
```

---

## Step 7 — Verify

```bash
bench --site "$SITE" list-apps
# biometric_integration and nepal_hrms should be GONE

bench --site "$SITE" mariadb -N -e "
SELECT name, module FROM \`tabDocType\` WHERE name IN ('Biometric Device', 'Employee Attendance Allowance');
SELECT COUNT(*) AS rate_overrides FROM \`tabEmployee Attendance Allowance\`;
SELECT COUNT(*) AS holiday_flags FROM tabAttendance WHERE custom_worked_on_holiday=1;
"
```

Counts should match what you saw in pre-flight.

Smoke test in the desk:
- Open **Biometric Device** list — loads, the form's buttons (Test Connection, Sync Attendance) work
- Open a recent **Attendance** — `custom_late_entry` / `custom_early_entry` etc. fields are present
- Open a **Payroll Entry** — the **Calculate Attendance Allowances** button appears under the "Nepal HRMS" group
- Open **Monthly Attendance BS** report — runs without import errors

---

## Rollback (if something goes badly wrong)

The backup from Step 1 contains the pre-cutover state:

```bash
bench --site "$SITE" restore /path/to/backup/yyyymmdd_hhmmss-SITE-database.sql.gz
bench --site "$SITE" install-app biometric_integration   # if those apps' code is still on disk
bench --site "$SITE" install-app nepal_hrms
bench --site "$SITE" migrate
```

Then revert `avinashgroup_app` to the commit before the consolidation merged in.

---

## Cleanup (after a week of stable operation)

Once you've confirmed everything works for a few days of normal traffic:

```bash
# Remove old app directories from disk
rm -rf /path/to/frappe-bench/apps/biometric_integration
rm -rf /path/to/frappe-bench/apps/nepal_hrms

# Remove them from bench's app list
# Edit /path/to/frappe-bench/sites/apps.txt — delete the two lines
nano /path/to/frappe-bench/sites/apps.txt

bench setup requirements
```

> Until you do this cleanup, the old code stays on disk as a safety net. `bench build` will still link their assets (harmless, just wastes a few seconds).
