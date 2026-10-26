# Avinash Backup Puller

A Windows app that pulls ERP database backups over the API onto an external hard disk, for an offsite copy.

**The ERP needs no changes.** It uses two standard Frappe endpoints:
- `fetch_latest_backups` tells it the name of the newest backup.
- `/backups/<file>` downloads it.

## Install

1. Download **`BackupPullerSetup.exe`** from the
   [releases page](https://github.com/SubashRDP/avinashgroup_app/releases). Look for the `backup-puller-v…` release.
2. Run it on the backup PC. No admin rights are needed.
3. Keep **"Start automatically when I sign in"** ticked. Backups are only pulled while the app is running.

## Set up each ERP site (once per site)

1. In the ERP, create a user for backups (for example `backup@yourcompany.com`) and give it the **System Manager** role.
2. Open that user, go to **Settings → API Access → Generate Keys**, and copy the API key and API secret.
3. In the app, click **Add Site** and fill in:
   - **Site name:** also the folder name.
   - **URL:** must start with `https://`.
   - **API key** and **API secret**.

   Then click **Test Connection**.

## Using it

| | |
| --- | --- |
| **Hard disk folder** | Where backups go, e.g. `E:\ERP_Backups`. |
| **Fallback folder** | A folder on this PC, used only while the hard disk is unplugged. Plug the disk back in and the backups move to it automatically. You can also click **Move to Hard Disk**. Every file is checked (SHA-256) before the fallback copy is removed. |
| **Check every** | Default 60 minutes. The servers back up every 6 hours, so hourly checks catch each one. |
| **Also pull files backup** | Per site, off by default. Also pulls the public/private file archives when the server has them. |
| **Pull Latest Now** | Pulls the selected site immediately. |
| **Open Log** | Shows that site's log. Each site has its own log. |

Backups are saved as `<disk>\<site name>\<YYYY-MM-DD_HHMMSS>\<files>`.

**Nothing is ever deleted automatically.** Delete old backups yourself in Explorer. A deleted backup is not downloaded again.

A site turns **red** in the list when no new backup has been pulled for 8 hours.

## Good to know

- **Latest backup only:** the app only sees each site's *latest* backup. While the PC is off, the backups taken in that time are missed. When it comes back on, it immediately pulls the newest one.
- **Secrets:** the API secrets are encrypted with Windows (DPAPI) for this Windows user. Settings live in `%APPDATA%\AvinashBackupPuller\`.
- **Restore:** copy the `.sql.gz` to the server and run `bench --site <site> restore <file>`.

## Release a new version

1. Bump `latest_version.txt` and `MyAppVersion` in `installer.iss`.
2. Push.

`.github/workflows/build-backup-puller.yml` then builds the exe and installer and publishes the release `backup-puller-v<version>`. The release is deliberately **not** marked "latest", because K40 Bridge's updater downloads from the repo's latest release.
