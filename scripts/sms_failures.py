#!/usr/bin/env python3
"""Every submitted Sales Invoice whose customer never got an SMS — and why.

The `Sales Invoice on Submit` rule tries each recipient path in order and sends
to the first that yields a number. When none do, no SMS goes out. This script
finds those invoices and, for each one, re-resolves the chain against TODAY's
data — so a row marked RESEND is one where the number has since been filled in
and the customer can still be reached.

Whether an invoice was sent is read off the SMS Log by matching the invoice's
`custom_branch_name` inside the message body, because core SMS Log holds no
reference to the document. On a site with the `Sparrow SMS Log` doctype, use
--sparrow-log for an exact join on `reference_name` instead of text matching.

Read-only: every call is a GET. Nothing is written to the site.

    export FRAPPE_API_TOKEN='key:secret'
    python3 sms_failures.py --from-date 2026-08-19 --out sms_failures.csv

Filters (all optional):
    --fiscal-year 83/84      --from-date / --to-date
    --company "Nepal Gas Udhyog Pvt. Ltd."
    --sparrow-log            join on Sparrow SMS Log instead of message text
"""

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter

PAGE = 5000
TIMEOUT = 180
# These names ride in the query string and the server rejects a URL over ~8KB.
CHUNK = 80

# The rule's recipient chain, in the order it is tried. Kept here as data so a
# change to the rule is a one-line change here — but read the live rule with
# --show-rule before trusting this to describe what the site actually does.
CHAIN = [
    ("customer_address.phone", "invoice address"),
    ("customer.custom_mobile_number", "customer mobile"),
    ("customer.mobile_no", "customer.mobile_no"),
]

INVOICE_FIELDS = [
    "name", "custom_branch_name", "posting_date", "company",
    "customer", "customer_name", "customer_address", "grand_total",
    "custom_created_by",
]

OUT_FIELDS = INVOICE_FIELDS + ["verdict", "number_now", "found_via"]


class Api:
    def __init__(self, site, token):
        self.site, self.token = site.rstrip("/"), token

    def _get(self, path, params):
        url = f"{self.site}{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Authorization": f"token {self.token}"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = json.loads(r.read().decode())
        if "exception" in body:
            raise RuntimeError(body["exception"])
        return body

    def count(self, doctype, filters):
        return self._get("/api/method/frappe.client.get_count",
                         {"doctype": doctype, "filters": json.dumps(filters)})["message"]

    def all(self, doctype, filters, fields, label=None):
        out, start = [], 0
        while True:
            batch = self._get(
                f"/api/resource/{urllib.parse.quote(doctype)}",
                {"filters": json.dumps(filters), "fields": json.dumps(fields),
                 "limit_page_length": PAGE, "limit_start": start, "order_by": "name asc"},
            )["data"]
            out += batch
            start += PAGE
            if label:
                print(f"\r  {label}: {len(out):,}", end="", file=sys.stderr, flush=True)
            if len(batch) < PAGE:
                break
        if label:
            print(file=sys.stderr)
        return out

    def by_name(self, doctype, names, fields, label=None):
        """Rows for a known set of names, chunked to stay under the URL limit."""
        out = []
        for start in range(0, len(names), CHUNK):
            out += self.all(doctype, [["name", "in", names[start : start + CHUNK]]], fields)
            if label:
                print(f"\r  {label}: {min(start + CHUNK, len(names)):,}/{len(names):,}",
                      end="", file=sys.stderr, flush=True)
        if label:
            print(file=sys.stderr)
        return out


def sent_invoice_numbers(api, since, use_sparrow):
    """Branch numbers (or invoice names) that an SMS actually went out for."""
    if use_sparrow:
        rows = api.all("Sparrow SMS Log",
                       [["creation", ">=", since], ["status", "=", "Sent"]],
                       ["reference_name"], "sms log")
        return {r["reference_name"] for r in rows if r["reference_name"]}, "name"

    rows = api.all("SMS Log", [["creation", ">=", since]], ["message"], "sms log")
    # The template reads "...your invoice <branch number> of Rs. ...", so the
    # number is recoverable from the body even though the row does not link back
    # to the document.
    numbers = set()
    for r in rows:
        for token in (r["message"] or "").replace(",", " ").split():
            if "-" in token and any(ch.isdigit() for ch in token):
                numbers.add(token.strip(".,"))
    return numbers, "custom_branch_name"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--site", default="https://ng-group.raindropinc.com")
    p.add_argument("--token", default=os.environ.get("FRAPPE_API_TOKEN"))
    p.add_argument("--fiscal-year")
    p.add_argument("--from-date")
    p.add_argument("--to-date")
    p.add_argument("--company")
    p.add_argument("--sparrow-log", action="store_true")
    p.add_argument("--show-rule", action="store_true", help="print the live rule and exit")
    p.add_argument("--out", default="sms_failures.csv")
    args = p.parse_args()

    if not args.token:
        sys.exit("No API token. Pass --token key:secret or set FRAPPE_API_TOKEN.")
    api = Api(args.site, args.token)

    if args.show_rule:
        for rule in api.all("SMS Notification Rule", [["enabled", "=", 1]], ["name"]):
            path = urllib.parse.quote(f"/api/resource/SMS Notification Rule/{rule['name']}")
            doc = api._get(path, {})["data"]
            print(f"{doc['name']}  ({doc['document_type']} / {doc['event']})  condition: {doc.get('condition')}")
            for row in doc.get("recipients", []):
                print(f"   {row['idx']}. {row['recipient_field']}")
        return

    # The rule skips returns, so counting them as failures would be wrong.
    filters = [["docstatus", "=", 1], ["is_return", "=", 0]]
    if args.company:
        filters.append(["company", "=", args.company])
    if args.fiscal_year:
        fy = api.all("Fiscal Year", [["name", "=", args.fiscal_year]],
                     ["year_start_date", "year_end_date"])
        if not fy:
            sys.exit(f"No Fiscal Year named {args.fiscal_year!r} on this site.")
        filters += [["posting_date", ">=", fy[0]["year_start_date"]],
                    ["posting_date", "<=", fy[0]["year_end_date"]]]
    if args.from_date:
        filters.append(["posting_date", ">=", args.from_date])
    if args.to_date:
        filters.append(["posting_date", "<=", args.to_date])

    total = api.count("Sales Invoice", filters)
    print(f"Submitted invoices in scope: {total:,}", file=sys.stderr)
    if not total:
        sys.exit("Nothing in scope — check the filters.")
    invoices = api.all("Sales Invoice", filters, INVOICE_FIELDS, "invoices")

    since = min(i["posting_date"] for i in invoices)
    sent, key = sent_invoice_numbers(api, since, args.sparrow_log)
    failed = [i for i in invoices if (i.get(key) or i["name"]) not in sent]
    print(f"No SMS recorded for {len(failed):,} of {len(invoices):,}", file=sys.stderr)
    if not failed:
        sys.exit(0)

    # Re-resolve the chain against today's data, so each row says whether the
    # customer is reachable NOW — that is the difference between "resend this"
    # and "go collect a phone number".
    addr_names = sorted({i["customer_address"] for i in failed if i["customer_address"]})
    addr = {a["name"]: (a["phone"] or "").strip()
            for a in api.by_name("Address", addr_names, ["name", "phone"], "addresses")}

    cust_names = sorted({i["customer"] for i in failed})
    cust = {c["name"]: c for c in api.by_name(
        "Customer", cust_names, ["name", "custom_mobile_number", "mobile_no"], "customers")}

    def resolve(inv):
        for path, label in CHAIN:
            if path == "customer_address.phone":
                value = addr.get(inv["customer_address"] or "")
            else:
                value = (cust.get(inv["customer"], {}).get(path.split(".", 1)[1]) or "").strip()
            if value:
                return value, label
        return "", ""

    # An absent SMS Log row is not proof of an absent SMS. On a site running
    # Sparrow SMS before the log rewrite, the row is written inside
    # frappe.db.after_commit — after the request COMMIT — so it lands in a
    # transaction nothing commits and is discarded at teardown. The send still
    # happened. The Error Log is the corroborating witness: an invoice named
    # there really did fail to resolve a number. Everything else is UNCONFIRMED
    # and must not be reported as a failure.
    logged_failures = {
        e["method"].split(" for ", 1)[1]
        for e in api.all("Error Log",
                         [["method", "like", "Sparrow SMS: no mobile number%"]],
                         ["method"], "error log")
        if " for " in e["method"]
    }

    rows = []
    for inv in failed:
        number, via = resolve(inv)
        confirmed = inv["name"] in logged_failures
        if not confirmed:
            verdict = "UNCONFIRMED"
        elif number:
            verdict = "RESEND"
        else:
            verdict = "NO NUMBER"
        rows.append({**inv,
                     "verdict": verdict,
                     "number_now": number,
                     "found_via": via})

    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
        w.writeheader()
        w.writerows(rows)

    resend = [r for r in rows if r["verdict"] == "RESEND"]
    nonum = [r for r in rows if r["verdict"] == "NO NUMBER"]
    unconf = [r for r in rows if r["verdict"] == "UNCONFIRMED"]
    print(f"\nNo SMS Log row for {len(rows):,} of {len(invoices):,} invoices")
    print(f"  CONFIRMED failed (in Error Log) : {len(resend) + len(nonum):,}")
    print(f"     reachable today (RESEND)     : {len(resend):,}")
    print(f"     still no number              : {len(nonum):,}")
    print(f"  UNCONFIRMED (no log either way) : {len(unconf):,}")
    if unconf:
        print("     ^ this site writes the SMS Log after commit, so a sent SMS")
        print("       can leave no row. Treat these as unknown, not failed.")
    print(f"\nWritten to {args.out}\n")

    if resend:
        print("Reachable via:")
        for via, n in Counter(r["found_via"] for r in resend).most_common():
            print(f"  {via:<22} {n:>6,}")

    print("\nStill unreachable, worst customers:")
    stuck = Counter((r["customer_name"], r["customer"]) for r in nonum)
    for (name, code), n in stuck.most_common(10):
        print(f"  {n:>5}  {name[:38]:<40} {code}")


if __name__ == "__main__":
    main()
