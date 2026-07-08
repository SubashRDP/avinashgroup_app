"""100-user load test against the avinas site — Desk-realistic traffic.

Each simulated user logs in with a session cookie (like the real Desk UI)
and runs a weighted mix of:

  frontend-shaped load                     backend-shaped load
  --------------------                     -------------------
  list views (reportview.get)              create+submit via seed.make_one
  form loads (form.load.getdoc)            (full hook/override/GL stack,
  counts (reportview.get_count)             under real user permissions)
  link-field searches (search_link)
  General Ledger report
  get_item_details (app override)

Prerequisites (once):
    bench --site avinas execute avinashgroup_app.loadtest.setup_users.make_users
    bash loadtest/run_seed.sh 1000 full        # or bigger; see README

Run:
    pip install locust
    locust -f loadtest/locustfile.py --host http://localhost:8000 \
           -u 100 -r 5 --run-time 15m
Headless:  add --headless; Web UI: open http://localhost:8089

Env:
    LOADTEST_USERS_CSV  credentials file (default: sites/avinas/loadtest_users.csv)
"""

import csv
import itertools
import json
import os
import random

from locust import HttpUser, between, task

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.abspath(
    os.path.join(HERE, "..", "..", "..", "sites", "avinas", "loadtest_users.csv")
)

READ_DOCTYPES = [
    "Sales Invoice",
    "Purchase Invoice",
    "Payment Entry",
    "Journal Entry",
    "Sales Order",
    "Purchase Order",
    "Delivery Note",
    "Purchase Receipt",
    "Material Request",
    "Quotation",
    "Supplier Quotation",
    "Stock Entry",
]

# Doctypes whose create+submit is cheap enough to hammer hard vs the
# stock-ledger ones which serialize on item/warehouse locks (kept in the
# mix on purpose — that contention is a finding, not a nuisance).
WRITE_DOCTYPES = READ_DOCTYPES

LIST_FIELDS = {
    "Sales Invoice": ["name", "customer", "posting_date", "grand_total", "status"],
    "Purchase Invoice": ["name", "supplier", "posting_date", "grand_total", "status"],
    "Payment Entry": ["name", "party", "posting_date", "paid_amount", "status"],
    "Journal Entry": ["name", "posting_date", "total_debit"],
}


def _load_credentials():
    path = os.environ.get("LOADTEST_USERS_CSV", DEFAULT_CSV)
    with open(path) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"no credentials in {path} — run setup_users.make_users first")
    return rows


CREDENTIALS = _load_credentials()
_credential_cycle = itertools.cycle(CREDENTIALS)


class DeskUser(HttpUser):
    wait_time = between(1, 4)

    def on_start(self):
        cred = next(_credential_cycle)
        self.email = cred["email"]
        with self.client.post(
            "/api/method/login",
            data={"usr": cred["email"], "pwd": cred["password"]},
            name="login",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"login failed for {cred['email']}: {resp.status_code}")
        self._names = {}

    # ---------------------------------------------------------- frontend

    @task(8)
    def list_view(self):
        dt = random.choice(READ_DOCTYPES)
        fields = LIST_FIELDS.get(dt, ["name", "modified"])
        self.client.post(
            "/api/method/frappe.desk.reportview.get",
            data={
                "doctype": dt,
                "fields": json.dumps([f"`tab{dt}`.`{f}`" for f in fields]),
                "filters": "[]",
                "order_by": f"`tab{dt}`.`modified` desc",
                "start": random.choice((0, 0, 20, 100, 500)),
                "page_length": 20,
                "view": "List",
                "with_comment_count": 1,
            },
            name=f"list: {dt}",
        )

    @task(3)
    def count(self):
        dt = random.choice(READ_DOCTYPES)
        self.client.post(
            "/api/method/frappe.desk.reportview.get_count",
            data={"doctype": dt, "filters": "[]", "distinct": "false", "limit": 1001},
            name=f"count: {dt}",
        )

    @task(4)
    def form_load(self):
        dt = random.choice(READ_DOCTYPES)
        name = self._pick_name(dt)
        if not name:
            return
        self.client.get(
            "/api/method/frappe.desk.form.load.getdoc",
            params={"doctype": dt, "name": name},
            name=f"form: {dt}",
        )

    @task(3)
    def link_search(self):
        doctype, txt = random.choice(
            [("Customer", ""), ("Item", ""), ("Supplier", ""), ("Customer", "a"), ("Item", "1")]
        )
        self.client.post(
            "/api/method/frappe.desk.search.search_link",
            data={"doctype": doctype, "txt": txt, "page_length": 10},
            name=f"search_link: {doctype}",
        )

    @task(1)
    def general_ledger_report(self):
        self.client.post(
            "/api/method/frappe.desk.query_report.run",
            data={
                "report_name": "General Ledger",
                "filters": json.dumps(
                    {
                        "company": "Nepal Gas Udhyog Pvt. Ltd.",
                        "from_date": "2025-07-17",
                        "to_date": "2026-07-08",
                        "group_by": "Group by Voucher (Consolidated)",
                    }
                ),
                "ignore_prepared_report": 1,
            },
            name="report: General Ledger",
            timeout=120,
        )

    @task(2)
    def item_details(self):
        dynamic = self._item_details_dynamic()
        if not dynamic:
            return
        with self.client.post(
            "/api/method/erpnext.stock.get_item_details.get_item_details",
            data={
                "args": json.dumps(
                    {
                        "doctype": "Sales Invoice",
                        "company": "Nepal Gas Udhyog Pvt. Ltd.",
                        "currency": "NPR",
                        "conversion_rate": 1,
                        "price_list_currency": "NPR",
                        "plc_conversion_rate": 1,
                        "customer": None,
                        "transaction_date": "2026-07-08",
                        "posting_date": "2026-07-08",
                        "qty": 1,
                    }
                    | dynamic
                )
            },
            name="get_item_details (override)",
            catch_response=True,
        ) as resp:
            # 417s here mean the override rejected the args — surface as failure
            if resp.status_code not in (200,):
                resp.failure(f"{resp.status_code}: {resp.text[:120]}")

    def _item_details_dynamic(self):
        item = self._pick_name("Item")
        customer = self._pick_name("Customer")
        return {"item_code": item, "customer": customer} if item and customer else {}

    # ---------------------------------------------------------- backend

    @task(5)
    def create_and_submit(self):
        dt = random.choice(WRITE_DOCTYPES)
        # args go in the query string: they survive every auth path, while
        # token-authenticated POST bodies get dropped on this dev server
        with self.client.post(
            "/api/method/avinashgroup_app.loadtest.seed.make_one",
            params={"dt": dt, "submit": 1},
            name=f"create+submit: {dt}",
            catch_response=True,
            timeout=120,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"{resp.status_code}: {resp.text[:200]}")

    # ---------------------------------------------------------- helpers

    def _pick_name(self, dt):
        cache = self._names.get(dt)
        if not cache:
            resp = self.client.get(
                "/api/method/avinashgroup_app.loadtest.seed.sample_names",
                params={"dt": dt, "limit": 30},
                name=f"sample_names: {dt}",
            )
            if resp.status_code != 200:
                return None
            cache = self._names[dt] = resp.json().get("message") or []
        return random.choice(cache) if cache else None
