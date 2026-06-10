
# MariaDB Master–Slave Replication for `avinas1` (reports served from the slave)

**Goal:** one MariaDB as **master** (all writes), a second MariaDB as **slave**
(auto-synced via GTID replication), and all **reports / list views / GET-style
reads** served from the slave.

Frappe v15 supports this natively — **no app code changes needed**:

- Functions decorated with `@frappe.read_only()` swap the DB connection to the
  replica when `read_from_replica` is set (`frappe/__init__.py` → `read_only()`
  / `connect_replica()`).
- Already decorated in core: **all query/script reports**
  (`frappe.desk.query_report.run`), **all list views & report views**
  (`frappe.desk.reportview.get`), desk counts, notifications. Every custom
  Script Report in `avinashgroup_app` runs through `query_report.run`, so all of
  them go to the slave automatically.
- **Writes** (saves, submits, workflows, payroll) always use the master, and a
  `write_only()` guard switches back to the master if a read-only request tries
  to write.

There are two deployment shapes. Pick one:

| | Path A — single box | Path B — two machines |
|---|---|---|
| Master + slave | same server, ports 3306 + 3307 | two servers, port 3306 each |
| Load isolation | partial (own buffer pool/connections, shared CPU/disk) | **full** |
| Use when | trial, dev, small load | production, real offload |

Shared facts for both paths:

- Site DB name: `_b6e1635e564c6793`
- Site DB password: `m6ti27Fdy7ueWA9v`  *(from `sites/avinas1/site_config.json`)*
- Master `server_id = 1`, slave `server_id = 2`
- Replication is **asynchronous** GTID (typically < 1 s lag). Use GTID so the
  slave always resumes cleanly.

> ⚠️ **Two pitfalls that apply to BOTH paths** — read [§7](#7-pitfalls-read-before-you-start) before starting.

---

# Path A — Single box (two instances on one server)

This is exactly what is deployed on this machine today. An idempotent script that
performs all of it lives at **`frappe-v15/setup_replica.sh`**; the steps below are
what it does, for reference and manual recovery.

### A1. Master: enable binlog + GTID

`/etc/mysql/mariadb.conf.d/61-replication.cnf`:

```ini
[mariadbd]
server_id        = 1
log_bin          = /var/lib/mysql/mysql-bin
binlog_format    = ROW
expire_logs_days = 7
gtid_strict_mode = ON
```

```bash
sudo systemctl restart mariadb     # brief restart of the live DB
```

Create the replication user (root connects via socket on Debian/Ubuntu, so use
`sudo mariadb`):

```sql
CREATE USER IF NOT EXISTS 'repl'@'127.0.0.1' IDENTIFIED BY 'REPL_PASSWORD';
CREATE USER IF NOT EXISTS 'repl'@'localhost' IDENTIFIED BY 'REPL_PASSWORD';
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'127.0.0.1';
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'localhost';
FLUSH PRIVILEGES;
```

### A2. Stand up the slave instance on port 3307

Initialise a separate data directory:

```bash
sudo mkdir -p /var/lib/mysql-replica
sudo chown mysql:mysql /var/lib/mysql-replica
sudo mariadb-install-db --user=mysql --datadir=/var/lib/mysql-replica \
  --auth-root-authentication-method=socket
```

If AppArmor confines `mariadbd`, allow the new paths in
`/etc/apparmor.d/local/usr.sbin.mariadbd`, then `sudo apparmor_parser -r
/etc/apparmor.d/usr.sbin.mariadbd`:

```
  /var/lib/mysql-replica/ rwk,
  /var/lib/mysql-replica/** rwk,
  /run/mysqld/mysqld-replica.sock rwk,
  /run/mysqld/mysqld-replica.pid rw,
```

Slave config `/etc/mysql/replica.cnf` — **note: no `log_bin`** (see [§7](#7-pitfalls-read-before-you-start)):

```ini
[mariadbd]
user             = mysql
datadir          = /var/lib/mysql-replica
socket           = /run/mysqld/mysqld-replica.sock
port             = 3307
pid-file         = /run/mysqld/mysqld-replica.pid
bind-address     = 127.0.0.1
server_id        = 2
read_only        = ON
relay_log        = /var/lib/mysql-replica/relay-bin
gtid_strict_mode = ON
replicate_do_db  = _b6e1635e564c6793
```

systemd unit `/etc/systemd/system/mariadb-replica.service` — **note: no
`RuntimeDirectory=`** (see [§7](#7-pitfalls-read-before-you-start)):

```ini
[Unit]
Description=MariaDB replica instance (port 3307) for _b6e1635e564c6793
After=network.target mariadb.service

[Service]
User=mysql
Group=mysql
ExecStartPre=/usr/bin/install -d -o mysql -g mysql -m 0755 /run/mysqld
ExecStart=/usr/sbin/mariadbd --defaults-file=/etc/mysql/replica.cnf
Restart=on-failure
LimitNOFILE=32768

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mariadb-replica.service
```

### A3. Seed the slave and start replication

```bash
# dump master (no downtime — InnoDB + --single-transaction)
sudo mariadb-dump --single-transaction --master-data=2 --gtid \
  --routines --triggers --events _b6e1635e564c6793 > /tmp/seed.sql

# record the GTID the dump was taken at
grep -m1 -i 'gtid_slave_pos' /tmp/seed.sql      # e.g. SET GLOBAL gtid_slave_pos='0-1-15'

# load into the slave
sudo mariadb --socket=/run/mysqld/mysqld-replica.sock \
  -e "CREATE DATABASE IF NOT EXISTS \`_b6e1635e564c6793\`"
sudo mariadb --socket=/run/mysqld/mysqld-replica.sock _b6e1635e564c6793 < /tmp/seed.sql
sudo rm -f /tmp/seed.sql                          # it's a full plaintext copy of the DB
```

Point the slave at the master (use the GTID from above):

```sql
-- on the slave (sudo mariadb --socket=/run/mysqld/mysqld-replica.sock)
SET GLOBAL gtid_slave_pos = '0-1-15';
CHANGE MASTER TO
  MASTER_HOST='127.0.0.1', MASTER_PORT=3306,
  MASTER_USER='repl', MASTER_PASSWORD='REPL_PASSWORD',
  MASTER_USE_GTID=slave_pos;
START SLAVE;
SHOW SLAVE STATUS\G    -- want: Slave_IO_Running=Yes, Slave_SQL_Running=Yes, Seconds_Behind_Master=0
```

Create the **read-only site user on the slave** so Frappe can connect (the
dump did not include `mysql.user`):

```sql
CREATE USER IF NOT EXISTS '_b6e1635e564c6793'@'localhost' IDENTIFIED BY 'm6ti27Fdy7ueWA9v';
CREATE USER IF NOT EXISTS '_b6e1635e564c6793'@'127.0.0.1' IDENTIFIED BY 'm6ti27Fdy7ueWA9v';
GRANT SELECT, SHOW VIEW ON `_b6e1635e564c6793`.* TO '_b6e1635e564c6793'@'localhost';
GRANT SELECT, SHOW VIEW ON `_b6e1635e564c6793`.* TO '_b6e1635e564c6793'@'127.0.0.1';
FLUSH PRIVILEGES;
```

Now go to [§4 Point Frappe at the slave](#4-point-frappe-at-the-slave) with
`replica_host = 127.0.0.1`, `replica_db_port = 3307`.

---

# Path B — Two machines (master server + slave server)

Real load isolation. Three logical roles (the app can live on the master, the
slave, or its own box — set the IPs accordingly):

- `MASTER_IP` – master DB server
- `SLAVE_IP`  – slave DB server
- `APP_IP`    – Frappe/bench server (where gunicorn runs)
- `REPL_PASSWORD` – replication user password

### B1. Master: enable binlog + GTID + allow remote

`/etc/mysql/mariadb.conf.d/61-replication.cnf` on **MASTER**:

```ini
[mariadbd]
server_id        = 1
log_bin          = /var/lib/mysql/mysql-bin
binlog_format    = ROW
expire_logs_days = 7
gtid_strict_mode = ON
bind-address     = 0.0.0.0      # or the master's LAN IP; must be reachable by slave + app
```

```bash
sudo systemctl restart mariadb
```

**Firewall:** open `3306/tcp` on the master **only** to `SLAVE_IP` and `APP_IP`
(e.g. `sudo ufw allow from SLAVE_IP to any port 3306 proto tcp`). Never expose
3306 to the world.

Replication user (host = the slave):

```sql
CREATE USER 'repl'@'SLAVE_IP' IDENTIFIED BY 'REPL_PASSWORD';
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'SLAVE_IP';
FLUSH PRIVILEGES;
```

If the **app server is a different box than the master**, the site user must
also be able to reach the master for **writes**:

```sql
CREATE USER IF NOT EXISTS '_b6e1635e564c6793'@'APP_IP' IDENTIFIED BY 'm6ti27Fdy7ueWA9v';
GRANT ALL PRIVILEGES ON `_b6e1635e564c6793`.* TO '_b6e1635e564c6793'@'APP_IP';
FLUSH PRIVILEGES;
```

### B2. Seed the slave

On the **master**:

```bash
sudo mariadb-dump --single-transaction --master-data=2 --gtid \
  --routines --triggers --events _b6e1635e564c6793 > avinas1_seed.sql
grep -m1 -i 'gtid_slave_pos' avinas1_seed.sql     # note the GTID, e.g. 0-1-15
scp avinas1_seed.sql user@SLAVE_IP:/tmp/
```

On the **slave**:

```bash
sudo mariadb -e "CREATE DATABASE \`_b6e1635e564c6793\`"
sudo mariadb _b6e1635e564c6793 < /tmp/avinas1_seed.sql
sudo rm -f /tmp/avinas1_seed.sql
```

### B3. Slave config (standard port 3306, dedicated box)

`/etc/mysql/mariadb.conf.d/61-replication.cnf` on **SLAVE** — **no `log_bin`**
unless you need it promotable (see [§7](#7-pitfalls-read-before-you-start)):

```ini
[mariadbd]
server_id        = 2
read_only        = ON
relay_log        = /var/lib/mysql/relay-bin
gtid_strict_mode = ON
bind-address     = 0.0.0.0      # app server must reach it
replicate_do_db  = _b6e1635e564c6793
```

```bash
sudo systemctl restart mariadb
```

**Firewall:** open `3306/tcp` on the slave **only** to `APP_IP`.

### B4. Start replication

```sql
-- on the slave
SET GLOBAL gtid_slave_pos = '0-1-15';      -- value from the dump
CHANGE MASTER TO
  MASTER_HOST='MASTER_IP', MASTER_PORT=3306,
  MASTER_USER='repl', MASTER_PASSWORD='REPL_PASSWORD',
  MASTER_USE_GTID=slave_pos;
START SLAVE;
SHOW SLAVE STATUS\G
```

> **Encrypt replication** if master↔slave traffic crosses any untrusted network.
> Add `MASTER_SSL=1, MASTER_SSL_VERIFY_SERVER_CERT=1` to `CHANGE MASTER TO` and
> configure server certs (`ssl_cert`/`ssl_key`/`ssl_ca`). On a trusted LAN/VPN
> this is optional.

### B5. Read-only site user on the slave

```sql
CREATE USER '_b6e1635e564c6793'@'APP_IP' IDENTIFIED BY 'm6ti27Fdy7ueWA9v';
GRANT SELECT, SHOW VIEW ON `_b6e1635e564c6793`.* TO '_b6e1635e564c6793'@'APP_IP';
FLUSH PRIVILEGES;
```

Then [§4 Point Frappe at the slave](#4-point-frappe-at-the-slave) with
`replica_host = SLAVE_IP`, `replica_db_port = 3306`. Also set `"db_host":
"MASTER_IP"` if the app server is separate from the master (writes go to
`db_host`).

---

# 4. Point Frappe at the slave

Edit `sites/avinas1/site_config.json` (no root needed). **Single box:**

```json
{
  "read_from_replica": 1,
  "replica_host": "127.0.0.1",
  "replica_db_port": 3307
}
```

**Two machines:**

```json
{
  "db_host": "MASTER_IP",
  "read_from_replica": 1,
  "replica_host": "SLAVE_IP",
  "replica_db_port": 3306
}
```

Frappe reuses `db_name` / `db_password` for the replica by default — that's why
the site user we created on the slave must use the **same name and password**.
To use a different replica account instead, add:

```json
{
  "different_credentials_for_replica": 1,
  "replica_db_name": "<replica user>",
  "replica_db_password": "<replica password>"
}
```

Apply:

```bash
bench --site avinas1 clear-cache
bench restart            # dev: restart your `bench start`; prod: sudo supervisorctl restart all
```

(Frappe reads `site_config.json` per request, so the change is picked up without
a restart, but a restart guarantees worker pools refresh.)

---

# 5. What goes where after this

| Operation | DB used |
|---|---|
| Saves, submits, workflows, payroll — every write | **Master** |
| Query/Script reports (`query_report.run`) — Party Ledger, Sales Register, Sales Stock Ledger, … | **Slave** |
| List & report views (`reportview.get`), sidebar counts, notifications | **Slave** |
| Plain `frappe.get_doc` / form loads / un-decorated custom APIs | Master |

Push a heavy custom read-only API onto the slave by decorating it:

```python
@frappe.whitelist()
@frappe.read_only()
def my_heavy_report_api(...):
    ...
```

---

# 6. Verify & monitor

**Prove routing works** (run in `bench --site avinas1 console`):

```python
import frappe
@frappe.read_only()
def via_replica():
    return frappe.db.sql("SELECT @@port port, @@server_id sid", as_dict=True)[0]
print("primary", frappe.db.sql("SELECT @@port port, @@server_id sid", as_dict=True)[0])
print("replica", via_replica())
# expect primary -> master port/server_id 1 ; replica -> slave port/server_id 2
```

**Replication health** (on the slave):

```bash
sudo mariadb [--socket=/run/mysqld/mysqld-replica.sock] \
  -e "SHOW SLAVE STATUS\G" | grep -E "Running|Seconds_Behind|Last_.*Error|Gtid"
# Slave_IO_Running: Yes / Slave_SQL_Running: Yes / Seconds_Behind_Master: 0
```

**GTID alignment & row parity:**

```bash
# master gtid_binlog_pos should equal slave gtid_slave_pos
# row counts of big tables (tabSales Invoice / tabGL Entry / tabStock Ledger Entry) should match
```

- Alert if `Seconds_Behind_Master` grows (a cron + email is enough).
- **Lag caveat:** a report opened in the same second as a save can be ~1 s
  stale — Frappe does not check lag before reading. For near-zero lag, enable
  semi-sync (`rpl_semi_sync_master_enabled=ON` / `rpl_semi_sync_slave_enabled=ON`).
- If replication breaks (e.g. duplicate key), understand the cause first; only
  then `STOP SLAVE; SET GLOBAL sql_slave_skip_counter=1; START SLAVE;`, or
  re-seed from a fresh dump.

---

# 7. Pitfalls (read before you start)

These bit this deployment; both apply to **single-box and two-machine** alike.

### 7.1 Do not give a leaf read-replica its own binary log under strict GTID

If the slave has `log_bin` + `log_slave_updates` **and** `gtid_strict_mode=ON`,
any **privileged local write on the slave** — e.g. the `CREATE USER`/`GRANT`
you run to add the site's read-only user — gets binlogged under the slave's
`server_id=2` in GTID domain 0. The master's incoming `0-1-N` stream then looks
*out of order* versus the slave's `0-2-M`, and the SQL thread halts with:

```
ERROR 1950 ... an attempt was made to binlog GTID 0-1-N which would create an
out-of-order sequence number with existing GTID 0-2-M, and gtid strict mode is enabled
```

**Fix (pure read replica):** omit `log_bin`/`log_slave_updates` entirely — a
leaf replica needs no binlog (relay log is separate and still required).

**If you need the slave promotable** (failover/chained replicas, which *does*
require its own binlog): keep `log_bin`, but run local admin writes with the
binlog suppressed so they never mint local GTIDs:

```sql
SET SESSION sql_log_bin = 0;
CREATE USER ... ; GRANT ... ;
SET SESSION sql_log_bin = 1;
```

### 7.2 Single box only: do not use `RuntimeDirectory=mysqld` in the replica unit

Both instances share `/run/mysqld`. With `RuntimeDirectory=mysqld`, systemd
**deletes that directory when the replica stops**, taking the master's
`mysqld.sock` with it. The master keeps serving TCP (so Frappe, which connects
over TCP, is unaffected), but local `mysql`/socket clients break until the
master restarts. Use instead:

```ini
ExecStartPre=/usr/bin/install -d -o mysql -g mysql -m 0755 /run/mysqld
```

### 7.3 Two machines only: users + firewall + encryption

- The **site user must exist on both servers**: on the **master** as
  `'…'@'APP_IP'` with write privileges (so the app can write), and on the
  **slave** as `'…'@'APP_IP'` with `SELECT` only (so the app can read).
- Open port 3306 by **source IP only** (master←slave, master←app, slave←app).
  Never expose it publicly.
- Encrypt replication (`MASTER_SSL=1`) if it crosses an untrusted network.

---

# 8. Rollback (undo everything)

**Single box:**

```bash
sudo systemctl disable --now mariadb-replica.service
sudo rm -f /etc/systemd/system/mariadb-replica.service && sudo systemctl daemon-reload
sudo rm -rf /var/lib/mysql-replica
sudo rm -f /etc/mysql/replica.cnf /etc/mysql/mariadb.conf.d/61-replication.cnf
sudo rm -f /etc/apparmor.d/local/usr.sbin.mariadbd   # or remove just the replica lines
# drop the repl user on the master:
sudo mariadb -e "DROP USER IF EXISTS 'repl'@'127.0.0.1', 'repl'@'localhost'; FLUSH PRIVILEGES;"
sudo systemctl restart mariadb
```

**Two machines:** `STOP SLAVE; RESET SLAVE ALL;` on the slave, decommission the
slave box, drop the `repl` user and remove `61-replication.cnf` on the master,
then `sudo systemctl restart mariadb`.

**Both:** remove `read_from_replica` / `replica_host` / `replica_db_port`
(and `db_host` if added) from `sites/avinas1/site_config.json`, then
`bench --site avinas1 clear-cache && bench restart`.

---

# 9. Promote the slave to master (failover, two-machine)

If the master dies and you must promote the slave:

```sql
-- on the slave
STOP SLAVE; RESET SLAVE ALL;
SET GLOBAL read_only = OFF;
```

Point the app at it: set `"db_host"` (and remove `read_from_replica` or
re-point `replica_host`) in `site_config.json`, ensure the site user has write
grants there, `bench --site avinas1 clear-cache && bench restart`. (For the
promoted node to in turn feed *its own* replicas it needs `log_bin` +
`log_slave_updates` — see [§7.1](#71-do-not-give-a-leaf-read-replica-its-own-binary-log-under-strict-gtid).)
