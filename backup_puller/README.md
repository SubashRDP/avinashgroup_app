# Avinash Backup Puller

A Windows app that pulls ERP database backups over the API onto an external hard disk, for an offsite copy.

**It runs in the background.** Once it is set up, you never need to open it again.

**The ERP needs no changes.** It uses two standard Frappe endpoints:
- `fetch_latest_backups` tells it the name of the newest backup.
- `/backups/<file>` downloads it.

## Install

1. Download **`BackupPullerSetup.exe`** from the
   [releases page](https://github.com/SubashRDP/avinashgroup_app/releases). Look for the newest `backup-puller-v…` release.
2. Run it on the backup PC. It needs admin rights, because it registers the background task.
3. In Windows power settings, set the PC to **never sleep**. A sleeping PC pulls nothing.

## Set up each ERP site (once per site)

1. In the ERP, create a user for backups (for example `backup@yourcompany.com`) and give it the **System Manager** role.
2. Open that user, go to **Settings → API Access → Generate Keys**, and copy the API key and API secret.
3. Open the app, go to **Overview → Add Site** and fill in:
   - **Site name:** also the folder name.
   - **URL:** must start with `https://`.
   - **API key** and **API secret**.

   Then click **Test Connection**.
4. Go to **Settings**, set the hard disk folder (e.g. `E:\ERP_Backups`) and the fallback folder, and click **Save**.

That's all. You can close the window.

## How it runs

The installer creates two Windows scheduled tasks. Both run `backup_puller.exe --run-once` as SYSTEM:

| Task | When |
| --- | --- |
| `Avinash Backup Puller` | Every hour |
| `Avinash Backup Puller (Startup)` | 2 minutes after the PC starts |

They run **with the window closed and no one signed in**. Each run pulls any backup it hasn't pulled before, moves fallback backups to the hard disk if it's plugged in, and exits. The servers back up every 6 hours, so hourly runs catch every one.

## The window

| Tab | What it shows |
| --- | --- |
| **Overview** | Status cards: whether the hard disk is connected and its free space, backups waiting on the fallback, and the background task's last run. Below them, the sites, each with a colored status: ✔ OK, ⚠ no new backup for 8+ hours, ✖ failed (with the reason). Buttons: Pull All Now, Pull Selected, Test Connection, Open Folder, Open Site Log, Move to Hard Disk Now. Double-click a site to edit it. |
| **Activity** | A live log of everything, including the background runs. |
| **Settings** | The two folders. |

## Storage

- **Location:** backups are saved as `<disk>\<site name>\<YYYY-MM-DD_HHMMSS>\<files>`.
- **Fallback:** while the hard disk is unplugged, backups go to the fallback folder. Plug the disk back in, and the next run moves them over. Every file is checked (SHA-256) before the fallback copy is removed.
- **Files backup:** off by default. Tick it per site (Edit Site) to also pull the public/private file archives.
- **Deleting:** nothing is ever deleted automatically. Delete old backups yourself in Explorer. A deleted backup is never downloaded again.

## Good to know

- **Latest backup only:** the app sees only each site's *latest* backup. Backups taken while the PC is off are missed, except the newest one, which is pulled 2 minutes after start-up.
- **Where settings and logs live:** `C:\ProgramData\AvinashBackupPuller\`. Each site has its own log in `logs\`.
- **Secrets:** the API secrets are encrypted with Windows (DPAPI) for this PC. Copying `config.json` to another PC won't reveal them.
- **Upgrading from 1.0.0:** settings move over automatically the first time you open the window. 1.0.0 was a per-user install, so if it still appears in *Add/Remove Programs*, uninstall it.
- **Restore:** copy the `.sql.gz` to the server and run `bench --site <site> restore <file>`.

## Release a new version

1. Bump `latest_version.txt` and `MyAppVersion` in `installer.iss`.
2. Push.

`.github/workflows/build-backup-puller.yml` then smoke-tests the window and the background mode, both from source and as the built exe. It builds the installer and publishes the release `backup-puller-v<version>`. The release is deliberately **not** marked "latest", because K40 Bridge's updater downloads from the repo's latest release.
