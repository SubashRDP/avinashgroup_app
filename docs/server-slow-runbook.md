# When the server is slow

Diagnose in this order. Every step below was walked on **2026-09-01** on the demo
box, where three separate faults were stacked on top of each other and only the
third was the one anybody went looking for.

Figures throughout are from `raindrop` / `demo-nggroup.raindropinc.com`
(6 cores, 7.7 GB RAM, 100 GB virtio disk, MariaDB 10.11, bench 5.25.9).

> This is **not** the dell box described in `CLAUDE.md`. Different host, different
> user (`frappe`, not `dell`), bench at `/home/frappe/frappe-bench`. Two machines
> answer to `raindrop` — check the prompt user and `free -h` total before assuming
> which one you are on. The ng-group box is 15 GB; this one is 7.7 GB.

---

## The three faults, in the order they were found

| # | Fault | Tell | Cost |
|---|---|---|---|
| 1 | gunicorn `-w 11` on 7.7 GB | swap 3.9/4.0 GB used | everything slow at once |
| 2 | `tabData Import Log` unindexed, 553,978 rows | queries time out at 90 s | import UI + progress crawl |
| 3 | `innodb_buffer_pool_size` = 128 MB, DB = 9,810 MB | 1.3% of the DB cached | every read hits disk |

Fixing 1 and 2 changed nothing about how fast rows imported. **Fault 3 was the one
that mattered**, and it was the last one looked at. Check the buffer pool early.

---

## Step 1 — always run this first

```bash
free -h
```

Read **`available`** and the **swap** line, not `used`. Free memory is not the goal;
a healthy server uses most of its RAM.

Swap near-full is the alarm. At 3.9 of 4.0 GB the machine is thrashing — hauling
pages between RAM and disk instead of working — and nothing on it can be fast.

Then find who is holding it:

```bash
ps -eo rss,comm,args --sort=-rss | head -20
```

---

## Step 2 — gunicorn worker count

The usual culprit. Workers grow from a ~90 MB baseline (shared, because of
`--preload`) to 700 MB–1 GB each. Eleven of them will not fit in 7.7 GB.

```bash
cd /home/frappe/frappe-bench
bench config set-common-config -c gunicorn_workers 4
sed -i 's/-w 11 --max-requests 5000/-w 4 --max-requests 500/' config/supervisor.conf
grep gunicorn config/supervisor.conf          # verify BEFORE reloading
sudo supervisorctl reread && sudo supervisorctl update
sudo supervisorctl restart frappe-bench-web:
```

Result on 2026-09-01: used 6.3 → 3.1 GB, available 1.4 → 4.6 GB.

**4 workers, not what the CPU count suggests.** With 6 cores the usual rule allows
13; RAM is the binding constraint here, and RAM sets the number.

Restarting `frappe-bench-web:` never touches background workers, so **this is safe
to run mid-import**. Restarting `frappe-bench-workers:` is not — it kills running
jobs.

### Two traps

- `bench config set-common-config **-g**` does not exist on bench 5.25.9. The flag
  is `-c`, taking a key and a value. The `-g` form errors while the `sed` edit still
  looks like it worked, leaving the setting unpersisted.
- `--max-requests` lives **only** in `config/supervisor.conf`, never in common
  config. Any future `bench setup supervisor` regenerates that file and silently
  restores 5000. Re-check the line after a bench update.

---

## Step 3 — the InnoDB buffer pool

**Check this early. It is the highest-value single number on the box.**

```bash
bench --site <site> mariadb
```
```sql
SELECT @@innodb_buffer_pool_size/1024/1024 AS pool_mb;
SELECT ROUND(SUM(data_length+index_length)/1024/1024) AS db_mb
FROM information_schema.tables WHERE table_schema = DATABASE();
```

On 2026-09-01 that read **128 MB pool against a 9,810 MB database** — the MariaDB
default, never touched since install, caching 1.3% of the data. Everything else
was a rounding error next to this.

The site's DB user has no `SUPER`, so `SET GLOBAL` fails from `bench mariadb`.
Use root, and persist it:

```bash
sudo tee /etc/mysql/mariadb.conf.d/60-innodb.cnf >/dev/null <<'EOF'
[mysqld]
innodb_buffer_pool_size_max = 4G
innodb_buffer_pool_size     = 2G
EOF
sudo systemctl restart mariadb
sudo mysql -e "SELECT @@innodb_buffer_pool_size/1024/1024/1024 AS pool_gb;"
```

To change it **without** a restart (MariaDB 10.11 resizes online — use this when a
job is in flight):

```bash
sudo mysql -e "SET GLOBAL innodb_buffer_pool_size = 2147483648;"
```

**Sizing.** The normal rule is ~70% of RAM. It does not apply here: the database
(9.6 GB) is larger than the machine's entire RAM (7.7 GB), so full caching is not
available at any setting. 2 GB holds the hot working set and leaves room for
gunicorn, the workers, and the VS Code session. Do not set 4 GB on this box — that
is the ng-group value, and that box has 15 GB.

A restart drops in-flight connections. Restarting MariaDB on 2026-09-01 killed a
running Data Import mid-row.

---

## Step 4 — slow imports specifically

`Data Import Log` grows without bound and Frappe ships **no index** on
`data_import` (`search_index: 0` in the doctype). At 553,978 rows every progress
poll was a full table scan.

```sql
ALTER TABLE `tabData Import Log` ADD INDEX idx_data_import (data_import);
```

5.2 seconds, online, no downtime. Do this once per site.

Measuring the actual row rate:

```sql
SELECT COUNT(*) AS done, MIN(creation), MAX(creation),
       TIMESTAMPDIFF(SECOND, MIN(creation), MAX(creation)) AS elapsed_sec
FROM `tabData Import Log` WHERE data_import = '<import name>';
```

Baseline seen with a 128 MB pool: **8.7 s/row** (390 rows in 3,410 s) for Payment
Entry with `submit_after_import`. That is pathological; under a second is normal.

**Resuming a partial import skips the failures too.** When the log has fewer rows
than `payload_count`, the importer adds *every* logged row to its skip list, not
just the successes. Failed rows must be re-imported as their own file.

---

## Never do these

- **`swapoff -a` while swap exceeds available RAM.** It forces every swapped page
  back at once and the OOM killer takes MariaDB. On 2026-09-01 morning this would
  have killed the box instantly. Guard it: only when available > 2× swap used.
- **`echo 3 > /proc/sys/vm/drop_caches`.** `buff/cache` is not wasted memory, and
  dropping it only forces re-reads. It does not touch the buffer pool anyway.
- **Kill the VS Code server to reclaim memory.** VS Code Remote is the only way
  into this box. The large node processes are the *live* session — match the server
  build hash against the `ptyHost --logsPath` timestamp to identify it. Only a
  stale second build hash is safe to `pkill`, and it is worth <100 MB.
- **Blanket `DELETE` on `tabData Import Log`.** One cost 357k rows here and needed
  a restore. Scope deletes to specific completed `data_import` names.

---

## False alarm, so nobody re-reports it

```
curl http://127.0.0.1:8000/api/method/ping   →  404
```

Not a fault. Frappe routes by hostname and the loopback request carries no matching
`Host` header, so no site resolves. Test properly:

```bash
curl -so /dev/null -w '%{http_code}\n' -H 'Host: <site>' http://127.0.0.1:8000/api/method/ping
```

---

## Keeping it fast

`vm.swappiness` defaults to 60, which is desktop tuning; on a DB server it lets the
buffer pool get paged out.

```bash
echo 'vm.swappiness = 10' | sudo tee /etc/sysctl.d/99-swappiness.conf
sudo sysctl --system
```

Nightly worker recycle — `/usr/local/bin/frappe-nightly-reclaim.sh`, run at 04:00
from `/etc/cron.d/frappe-nightly-reclaim`. It restarts `frappe-bench-web:` only
(safe mid-import) and drains swap **only** when `available > 2 × swap_used`.

---

## The limit tuning cannot fix

**A 9.6 GB database on a 7.7 GB machine.** Both incidents on 2026-09-01 — the
near-OOM and the half-day import — trace to that one ratio. Every setting above is
a compromise forced by it: 4 workers instead of 13, a 2 GB pool instead of 4 GB.

16 GB of RAM removes the constraint. Failing that, shrink the working set — half a
million import-log rows is the place to start, scoped by import name.

---

## Still open as of 2026-09-01

- **Post-fix import rate is unmeasured.** The job stopped at 440/4,347 when MariaDB
  restarted and was never resumed. Only the pre-fix 8.7 s/row is on record.
- **The gunicorn leak is contained, not diagnosed.** Workers reached 1.0 GB shortly
  after a reboot. `--max-requests 500` recycles them before they do damage, but
  something is still pulling very large result sets per request.
- **Disk latency never measured.** `lsblk` says `ROTA=1`, which proves nothing —
  virtio devices report rotational regardless of the backing store. Run
  `ioping -c 20 /home/frappe/frappe-bench`; under ~1 ms is SSD-backed.
- **3 failed rows** from the Payment Entry import need re-importing separately.
