# avinashgroup_app

Custom Frappe/ERPNext v15 app for the Avinash Group (Nepal Gas Udhyog and sister companies).

## Working site

**We work on the site `avinas1`.** Assume it for every site-scoped action — bench commands, DB queries, reproducing a pasted traceback, checking doctype data — unless a different site is named explicitly.

```bash
cd /home/dell/frappe-v15
bench --site avinas1 mariadb -e "SELECT ..."
bench --site avinas1 console
```

`sites/currentsite.txt` is already `avinas1`, so a bare `bench` targets it, but pass `--site avinas1` anyway so the intent is on the page.

Other sites on this bench, and when they matter:

| Site | What it is |
| --- | --- |
| `avinas1` | The working site. Default for everything. |
| `avinas1-7yr` | Data copy for historical work. Not a target for changes. |
| `sarathilive` | Separate live site. Comes up for IRD/CBMS sync work only. |
| `sarathi`, `demo` | Not in normal use. |

## Companies on avinas1

Seven, all active. Company-scoped setup data (Fiscal Year rows, accounts, naming rules) is normally created for all seven:

| Company | Abbr |
| --- | --- |
| Nepal Gas Udhyog Pvt. Ltd. | NGI |
| Nepal Gas Udhyog (Gandaki) Pvt. Ltd. | NGG |
| Nepal Gas Udhyog (Karnali) Pvt. Ltd. | NGK |
| Nepal Gas Udhyog (Narayani) Pvt. Ltd. | NGN |
| Grihalaxmi Metal Industries Pvt. Ltd | GLMI |
| Grishma Enterprises Pvt. Ltd. | GEPL |
| Sambriddhi Gas Udhyog Pvt. Ltd. | SGU |

## Environment

- Bench root: `/home/dell/frappe-v15` — run bench commands from here.
- Two virtualenvs, and they are not interchangeable:
  - `/home/dell/frappe-env` — the **bench CLI**. Source this to run `bench`.
  - `/home/dell/frappe-v15/env` — the **frappe framework** itself. Use this interpreter for a standalone script that imports `frappe`.

Standalone script against a site — note the cwd, it matters:

```bash
cd /home/dell/frappe-v15/sites          # NOT the bench root, see below
/home/dell/frappe-v15/env/bin/python myscript.py
# inside: frappe.init(site="avinas1", sites_path="/home/dell/frappe-v15/sites"); frappe.connect()
```

Frappe's logger builds the site log path as `os.path.join(site, "logs", logfile)`, relative to **cwd**. Run from the bench root and `frappe.connect()` fails with `FileNotFoundError: .../frappe-v15/<site>/logs/database.log`, or silently creates a stray `frappe-v15/<site>/` directory. One such stray `frappe-v15/avinas1/` already exists — it is not a site.

`bench --site avinas1 execute` runs through RestrictedPython, which rejects any name starting with `_`. To exercise a private helper, use `bench console` or a standalone script.
- `avinas1` reads from a MariaDB replica on `127.0.0.1:3307` (`read_from_replica: 1`). Script Reports and list views hit the replica; all writes go to the master on `:3306`. Runbook: `docs/db-master-slave-replication.md`.
- `developer_mode` and `server_script_enabled` are on for `avinas1`.

## Fiscal years

The books run on the Nepali (Bikram Sambat) calendar — fiscal years are named `82/83`, `83/84`, and start mid-July. Document naming in `custom_code/Override/naming_series.py` looks up a Fiscal Year row spanning the posting date and throws if none exists, so a new fiscal year must be created (with all seven company rows) before the year rolls over.
