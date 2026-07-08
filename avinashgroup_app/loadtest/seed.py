"""Transaction seeder for load testing. Transactions only — masters are
sampled from what already exists on the site (customers, suppliers, items,
warehouses, accounts). Nothing here creates or edits a master.

Two modes:

  full  — frappe.get_doc().insert() + submit(): runs every hook, override,
          tax handler, numbering rule and GL/stock ledger write. Slow
          (~5-30 docs/s/process) but this is the "crush the logic" path.
  fast  — frappe.db.bulk_insert of draft rows (parent + children) with
          precomputed amounts. Thousands of rows/s. Skips business logic;
          exists purely to pile up table volume so list views, reports,
          link searches and permission SQL get crushed by row count.

Run one doctype (one process ≈ one core):
    bench --site avinas execute avinashgroup_app.loadtest.seed.seed_one \
        --kwargs '{"doctype": "Sales Invoice", "count": 1000, "mode": "full"}'

Run everything in parallel: loadtest/run_seed.sh (repo root).

Cleanup:
    bench --site avinas execute avinashgroup_app.loadtest.seed.purge
"""

import json
import random
import time
from collections import Counter

import frappe
from frappe.utils import add_days, flt, getdate, now, nowdate

MARK = "LOADTEST"
FAST_PREFIX = "LT-"

VEHICLE_ACCOUNT_PATTERNS = ("Fuel Expenses", "R & M - Vehicles", "Other Vehicle Expenses")


# ---------------------------------------------------------------- context

def _ctx():
    """Sampled master data, cached per process."""
    if getattr(frappe.local, "_loadtest_ctx", None):
        return frappe.local._loadtest_ctx

    today = getdate(nowdate())
    fy = frappe.db.sql(
        """select name, year_start_date, year_end_date from `tabFiscal Year`
           where %s between year_start_date and year_end_date""",
        (today,),
        as_dict=1,
    )
    if not fy:
        frappe.throw("No Fiscal Year covers today — create one before seeding")
    fy = fy[0]

    ctx = frappe._dict(
        date_from=max(getdate(fy.year_start_date), add_days(today, -300)),
        date_to=today,
        # The globalfilter layer rejects masters whose company doesn't match
        # the document's, so every pool is grouped by company ("" = unscoped).
        customers=_pool_by_company("Customer", {"disabled": 0}),
        suppliers=_pool_by_company("Supplier", {"disabled": 0}),
        item_pool=_pool_by_company(
            "Item",
            {"disabled": 0, "has_variants": 0, "is_fixed_asset": 0},
            extra_fields=("is_stock_item",),
        ),
        selling_price_lists=_pool_by_company("Price List", {"enabled": 1, "selling": 1}),
        buying_price_lists=_pool_by_company("Price List", {"enabled": 1, "buying": 1}),
        jv_types=frappe.get_all("JV Type", pluck="name"),
        payment_types=frappe.get_all("Payment - Receipt Type", pluck="name"),
        receipt_types=frappe.get_all("Receipt type", pluck="name"),
        companies=[],
    )

    for c in frappe.get_all("Company", pluck="name"):
        comp = frappe.get_cached_doc("Company", c)
        warehouses = frappe.get_all(
            "Warehouse",
            filters={"company": c, "is_group": 0, "disabled": 0},
            pluck="name",
            limit=20,
        )
        if not warehouses:
            continue
        expense_accounts = [
            a
            for a in frappe.get_all(
                "Account",
                filters={
                    "company": c,
                    "is_group": 0,
                    "disabled": 0,
                    "root_type": "Expense",
                    "account_type": ("not in", ("Stock", "Stock Adjustment")),
                },
                pluck="name",
                limit=60,
            )
            if not any(p in a for p in VEHICLE_ACCOUNT_PATTERNS)
        ]
        cash_accounts = frappe.get_all(
            "Account",
            filters={"company": c, "is_group": 0, "disabled": 0, "account_type": "Cash"},
            pluck="name",
            limit=5,
        )
        ctx.companies.append(
            frappe._dict(
                name=c,
                abbr=comp.abbr,
                cost_center=comp.cost_center,
                receivable=comp.default_receivable_account,
                payable=comp.default_payable_account,
                cash=cash_accounts[0] if cash_accounts else None,
                expense_accounts=expense_accounts,
                warehouses=warehouses,
            )
        )

    # A company is only usable if it can source a customer, supplier and item.
    ctx.companies = [
        c
        for c in ctx.companies
        if _company_pool(ctx.customers, c.name)
        and _company_pool(ctx.suppliers, c.name)
        and _company_pool(ctx.item_pool, c.name)
    ]
    if not ctx.companies:
        frappe.throw("No company with active warehouses found — cannot seed")
    frappe.local._loadtest_ctx = ctx
    return ctx


def _pool_by_company(doctype, filters=None, extra_fields=()):
    """All records of a master doctype grouped by their company scope
    (same field the globalfilter validation uses); "" holds unscoped rows,
    usable with any company."""
    from avinashgroup_app.custom_code.globalfilter.globalfilter import _resolve_company_field

    company_field = _resolve_company_field(doctype)
    fields = ["name", *extra_fields] + ([company_field] if company_field else [])
    by_company = {}
    for row in frappe.get_all(doctype, filters=filters, fields=fields, limit=6000):
        key = (row.get(company_field) or "") if company_field else ""
        by_company.setdefault(key, []).append(row)
    return by_company


def _company_pool(by_company, company):
    return by_company.get(company, []) + by_company.get("", [])


def _pick(by_company, company):
    pool = _company_pool(by_company, company)
    return random.choice(pool).name if pool else None


def _doc_no():
    """Manual Document No. far above the live sequences so the numbering
    engine's collision checks never clash with real vouchers."""
    return random.randint(50_000_000, 99_999_999)


def _date(ctx):
    span = (ctx.date_to - ctx.date_from).days or 1
    return str(add_days(ctx.date_from, random.randint(0, span)))


def _items(ctx, company, rate=True, warehouse=None, stock_only=False, n=None):
    pool = _company_pool(ctx.item_pool, company)
    if stock_only:
        pool = [i for i in pool if i.is_stock_item] or pool
    rows = []
    for it in random.sample(pool, min(n or random.randint(1, 4), len(pool))):
        row = {"item_code": it.name, "qty": random.randint(1, 20)}
        if rate:
            row["rate"] = round(random.uniform(50, 5000), 2)
        if warehouse:
            row["warehouse"] = warehouse
            row["allow_zero_valuation_rate"] = 1
        rows.append(row)
    return rows


def _strip_none(d):
    """Drop keys with None values so document defaults still apply."""
    return {k: v for k, v in d.items() if v is not None}


# ---------------------------------------------------------------- builders

def _sales_invoice(ctx):
    c = random.choice(ctx.companies)
    d = _date(ctx)
    return {
        "doctype": "Sales Invoice",
        "company": c.name,
        "customer": _pick(ctx.customers, c.name),
        "selling_price_list": _pick(ctx.selling_price_lists, c.name),
        "posting_date": d,
        "set_posting_time": 1,
        "due_date": d,
        "update_stock": 0,
        "remarks": MARK,
        "custom_abbr": c.abbr,
        "items": _items(ctx, c.name),
    }


def _purchase_invoice(ctx):
    c = random.choice(ctx.companies)
    d = _date(ctx)
    return {
        "doctype": "Purchase Invoice",
        "company": c.name,
        "supplier": _pick(ctx.suppliers, c.name),
        "buying_price_list": _pick(ctx.buying_price_lists, c.name),
        "posting_date": d,
        "set_posting_time": 1,
        "due_date": d,
        "bill_no": f"LT-{random.randint(1, 10**9)}",
        "bill_date": d,
        "custom_document_no": _doc_no(),
        "update_stock": 0,
        "remarks": MARK,
        "items": _items(ctx, c.name),
    }


def _sales_order(ctx):
    c = random.choice(ctx.companies)
    d = _date(ctx)
    return {
        "doctype": "Sales Order",
        "company": c.name,
        "customer": _pick(ctx.customers, c.name),
        "selling_price_list": _pick(ctx.selling_price_lists, c.name),
        "transaction_date": d,
        "delivery_date": add_days(d, 7),
        "items": _items(ctx, c.name),
    }


def _purchase_order(ctx):
    c = random.choice(ctx.companies)
    d = _date(ctx)
    return {
        "doctype": "Purchase Order",
        "company": c.name,
        "supplier": _pick(ctx.suppliers, c.name),
        "buying_price_list": _pick(ctx.buying_price_lists, c.name),
        "transaction_date": d,
        "schedule_date": add_days(d, 7),
        "custom_approver": "Administrator",
        "items": _items(ctx, c.name, warehouse=random.choice(c.warehouses)),
    }


def _quotation(ctx):
    c = random.choice(ctx.companies)
    return {
        "doctype": "Quotation",
        "company": c.name,
        "quotation_to": "Customer",
        "party_name": _pick(ctx.customers, c.name),
        "selling_price_list": _pick(ctx.selling_price_lists, c.name),
        "transaction_date": _date(ctx),
        "items": _items(ctx, c.name),
    }


def _supplier_quotation(ctx):
    c = random.choice(ctx.companies)
    return {
        "doctype": "Supplier Quotation",
        "company": c.name,
        "supplier": _pick(ctx.suppliers, c.name),
        "buying_price_list": _pick(ctx.buying_price_lists, c.name),
        "transaction_date": _date(ctx),
        "items": _items(ctx, c.name),
    }


def _material_request(ctx):
    c = random.choice(ctx.companies)
    d = _date(ctx)
    return {
        "doctype": "Material Request",
        "company": c.name,
        "material_request_type": "Purchase",
        "transaction_date": d,
        "schedule_date": add_days(d, 7),
        "items": _items(ctx, c.name, rate=False, warehouse=random.choice(c.warehouses)),
    }


def _delivery_note(ctx):
    c = random.choice(ctx.companies)
    return {
        "doctype": "Delivery Note",
        "company": c.name,
        "customer": _pick(ctx.customers, c.name),
        "selling_price_list": _pick(ctx.selling_price_lists, c.name),
        "posting_date": _date(ctx),
        "set_posting_time": 1,
        "items": _items(ctx, c.name, warehouse=random.choice(c.warehouses), stock_only=True),
    }


def _purchase_receipt(ctx):
    c = random.choice(ctx.companies)
    return {
        "doctype": "Purchase Receipt",
        "company": c.name,
        "supplier": _pick(ctx.suppliers, c.name),
        "buying_price_list": _pick(ctx.buying_price_lists, c.name),
        "custom_receipt_type": random.choice(ctx.receipt_types) if ctx.receipt_types else None,
        "custom_document_no": _doc_no(),
        "posting_date": _date(ctx),
        "set_posting_time": 1,
        "items": _items(ctx, c.name, warehouse=random.choice(c.warehouses), stock_only=True),
    }


def _stock_entry(ctx):
    c = random.choice(ctx.companies)
    wh = random.choice(c.warehouses)
    items = []
    for row in _items(ctx, c.name, rate=False, stock_only=True):
        items.append(
            {
                "item_code": row["item_code"],
                "qty": row["qty"],
                "t_warehouse": wh,
                "basic_rate": round(random.uniform(50, 5000), 2),
                "allow_zero_valuation_rate": 1,
            }
        )
    return {
        "doctype": "Stock Entry",
        "company": c.name,
        "stock_entry_type": "Material Receipt",
        "purpose": "Material Receipt",
        "posting_date": _date(ctx),
        "set_posting_time": 1,
        "to_warehouse": wh,
        "items": items,
    }


def _journal_entry(ctx):
    c = random.choice(ctx.companies)
    if not (c.expense_accounts and c.cash):
        c = next((x for x in ctx.companies if x.expense_accounts and x.cash), None)
        if not c:
            frappe.throw("No company has both an expense account and a cash account")
    amount = round(random.uniform(100, 50000), 2)
    return {
        "doctype": "Journal Entry",
        "company": c.name,
        "voucher_type": "Journal Entry",
        "custom_p_type": random.choice(ctx.jv_types) if ctx.jv_types else None,
        "custom_document_no": _doc_no(),
        "posting_date": _date(ctx),
        "user_remark": MARK,
        "accounts": [
            {
                "account": random.choice(c.expense_accounts),
                "cost_center": c.cost_center,
                "debit_in_account_currency": amount,
            },
            {
                "account": c.cash,
                "cost_center": c.cost_center,
                "credit_in_account_currency": amount,
            },
        ],
    }


def _payment_entry(ctx):
    c = random.choice(ctx.companies)
    if not (c.receivable and c.cash):
        c = next((x for x in ctx.companies if x.receivable and x.cash), None)
        if not c:
            frappe.throw("No company has both default receivable and cash accounts")
    amount = round(random.uniform(100, 50000), 2)
    d = _date(ctx)
    return {
        "doctype": "Payment Entry",
        "company": c.name,
        "payment_type": "Receive",
        "custom_p_type": random.choice(ctx.payment_types) if ctx.payment_types else None,
        "custom_document_no": _doc_no(),
        "party_type": "Customer",
        "party": _pick(ctx.customers, c.name),
        "posting_date": d,
        "paid_from": c.receivable,
        "paid_from_account_currency": "NPR",
        "paid_to": c.cash,
        "paid_to_account_currency": "NPR",
        "paid_amount": amount,
        "received_amount": amount,
        "source_exchange_rate": 1,
        "target_exchange_rate": 1,
        "reference_no": MARK,
        "reference_date": d,
        "remarks": MARK,
    }


BUILDERS = {
    "Sales Invoice": _sales_invoice,
    "Purchase Invoice": _purchase_invoice,
    "Sales Order": _sales_order,
    "Purchase Order": _purchase_order,
    "Quotation": _quotation,
    "Supplier Quotation": _supplier_quotation,
    "Material Request": _material_request,
    "Delivery Note": _delivery_note,
    "Purchase Receipt": _purchase_receipt,
    "Stock Entry": _stock_entry,
    "Journal Entry": _journal_entry,
    "Payment Entry": _payment_entry,
}

# Doctypes whose submit touches the stock ledger: they need stock (or
# allow_negative_stock=1 during the run) and are costlier per doc.
STOCK_DOCTYPES = ("Delivery Note", "Stock Entry", "Purchase Receipt")


# ---------------------------------------------------------------- seeding

def seed_one(doctype, count=100, mode="full", submit=1, commit_every=200):
    """Seed `count` documents of one doctype. Designed to run as one process
    per doctype (≈ one CPU core each) via loadtest/run_seed.sh."""
    if not frappe.conf.allow_tests:
        frappe.throw("Refusing to seed: site_config allow_tests is not set")
    if doctype not in BUILDERS:
        frappe.throw(f"No builder for {doctype}. Available: {', '.join(BUILDERS)}")

    count, submit, commit_every = int(count), int(submit), int(commit_every)
    ctx = _ctx()
    build = BUILDERS[doctype]
    frappe.flags.in_import = False

    ok, errors = 0, Counter()
    error_samples = {}
    names_log = open(_names_log_path(doctype), "a")
    started = time.time()

    for i in range(1, count + 1):
        savepoint = "loadtest_doc"
        frappe.db.savepoint(savepoint)
        try:
            if mode == "fast":
                name = _fast_insert(doctype, _strip_none(build(ctx)), i)
            else:
                doc = frappe.get_doc(_strip_none(build(ctx)))
                doc.flags.ignore_permissions = True
                doc.insert()
                if submit:
                    doc.submit()
                name = doc.name
            names_log.write(name + "\n")
            ok += 1
        except Exception as e:
            frappe.db.rollback(save_point=savepoint)
            if isinstance(e, frappe.DuplicateEntryError):
                _heal_naming_series(doctype, e)
            key = type(e).__name__
            errors[key] += 1
            if key not in error_samples:
                error_samples[key] = str(e)[:300]

        if i % commit_every == 0:
            frappe.db.commit()
            rate = i / (time.time() - started)
            eta = (count - i) / rate if rate else 0
            print(
                f"[{doctype}] {i}/{count} ok={ok} err={sum(errors.values())} "
                f"{rate:.1f}/s eta={eta / 60:.1f}m",
                flush=True,
            )

    frappe.db.commit()
    names_log.close()
    summary = {
        "doctype": doctype,
        "mode": mode,
        "requested": count,
        "created": ok,
        "failed": sum(errors.values()),
        "errors": dict(errors),
        "error_samples": error_samples,
        "seconds": round(time.time() - started, 1),
    }
    print(json.dumps(summary, indent=2, default=str), flush=True)
    return summary


def _heal_naming_series(doctype, exc):
    """A duplicate primary key on insert means the tabSeries counter is behind
    the data (imports/renames do this). Sync it to the real max so the next
    build gets a fresh number — this exact failure would also hit real users."""
    import re

    name = exc.args[1] if len(exc.args) > 1 and isinstance(exc.args[1], str) else None
    m = re.match(r"^(.*?)(\d+)$", name or "")
    if not m:
        return
    prefix, digits = m.group(1), len(m.group(2))
    current = frappe.db.sql(
        f"""select coalesce(max(cast(substring(name, %s) as unsigned)), 0)
            from `tab{doctype}` where name like %s""",
        (len(prefix) + 1, prefix + "%"),
    )[0][0]
    frappe.db.sql(
        "update `tabSeries` set current = %s where name = %s", (current, prefix)
    )
    frappe.db.commit()
    print(f"[{doctype}] healed series '{prefix}' -> {current}", flush=True)


def _names_log_path(doctype):
    return frappe.get_site_path(f"loadtest_seeded_{frappe.scrub(doctype)}.txt")


# ---------------------------------------------------------------- fast mode

def _fast_insert(doctype, data, seq):
    """Bulk-path draft insert: parent + child rows straight into the tables
    with precomputed amounts. No hooks, no GL — volume only."""
    meta = frappe.get_meta(doctype)
    name = f"{FAST_PREFIX}{''.join(w[0] for w in doctype.split())}-{frappe.generate_hash(length=10)}"
    ts = now()
    parent = {
        k: v for k, v in data.items() if not isinstance(v, (list, dict)) and k != "doctype"
    }

    total = 0.0
    children = []
    for fieldname in ("items", "accounts"):
        for idx, row in enumerate(data.get(fieldname) or [], start=1):
            child_dt = meta.get_field(fieldname).options
            qty = flt(row.get("qty"))
            rate = flt(row.get("rate") or row.get("basic_rate"))
            amount = flt(qty * rate, 2)
            total += amount or flt(row.get("debit_in_account_currency"))
            row = dict(
                row,
                name=frappe.generate_hash(length=10),
                parent=name,
                parenttype=doctype,
                parentfield=fieldname,
                idx=idx,
                docstatus=0,
                amount=amount,
                base_amount=amount,
                base_rate=rate,
                owner="Administrator",
                modified_by="Administrator",
                creation=ts,
                modified=ts,
            )
            children.append((child_dt, row))

    total = flt(total or data.get("paid_amount"), 2)
    parent.update(
        name=name,
        docstatus=0,
        status="Draft",
        owner="Administrator",
        modified_by="Administrator",
        creation=ts,
        modified=ts,
        currency="NPR",
        conversion_rate=1,
        total=total,
        base_total=total,
        net_total=total,
        base_net_total=total,
        grand_total=total,
        base_grand_total=total,
        rounded_total=total,
        base_rounded_total=total,
        outstanding_amount=total,
        total_debit=total,
        total_credit=total,
    )

    _bulk_row(doctype, parent)
    for child_dt, row in children:
        _bulk_row(child_dt, row)
    return name


def _bulk_row(doctype, row):
    valid = set(frappe.get_meta(doctype).get_valid_columns())
    cols = [c for c in row if c in valid]
    frappe.db.bulk_insert(doctype, cols, [[row[c] for c in cols]])


# ---------------------------------------------------------------- API for locust

# NOTE: the HTTP-facing params are named `dt`, not `doctype` — frappe's
# /api/method handler pops "doctype" from RPC kwargs (frappe/api/v1.py).

@frappe.whitelist()
def make_one(dt, submit=1):
    """One create(+submit) through the full logic stack, as the calling
    load-test user with real permissions. Hit from locust to crush hooks,
    numbering, tax handlers and ledger writes under concurrency."""
    _guard()
    if dt not in BUILDERS:
        frappe.throw(f"No builder for {dt}")
    doc = frappe.get_doc(_strip_none(BUILDERS[dt](_ctx())))
    doc.insert()
    if int(submit):
        doc.submit()
    with open(_names_log_path(dt), "a") as f:
        f.write(doc.name + "\n")
    return {"name": doc.name, "doctype": dt}


@frappe.whitelist()
def sample_names(dt, limit=30):
    """Random-ish recent document names for form-load tasks."""
    _guard()

    def fetch(offset):
        return frappe.get_all(
            dt,
            pluck="name",
            limit=int(limit),
            limit_start=offset,
            order_by="creation desc",
        )

    return fetch(random.randint(0, 2000)) or fetch(0)


def _guard():
    if not frappe.conf.allow_tests:
        frappe.throw("Load-test endpoints are disabled: allow_tests not set")
    user = frappe.session.user
    if user != "Administrator" and not user.startswith("loadtest"):
        frappe.throw("Load-test endpoints are restricted to load-test users")


# ---------------------------------------------------------------- knobs & cleanup

def set_negative_stock(enabled=1):
    """Delivery Notes at random quantities need this on during seeding."""
    frappe.db.set_single_value("Stock Settings", "allow_negative_stock", int(enabled))
    frappe.db.commit()
    print(f"Stock Settings.allow_negative_stock = {int(enabled)}")


def purge(doctype=None, batch=500):
    """Remove seeded documents. Fast-mode drafts are deleted directly;
    full-mode documents (from the per-doctype name logs) get their GL /
    Stock Ledger / Payment Ledger rows deleted too."""
    import os

    doctypes = [doctype] if doctype else list(BUILDERS)
    for dt in doctypes:
        meta = frappe.get_meta(dt)
        child_tables = [f.options for f in meta.get_table_fields()]

        names = set(
            frappe.get_all(dt, filters={"name": ("like", f"{FAST_PREFIX}%")}, pluck="name")
        )
        log = _names_log_path(dt)
        if os.path.exists(log):
            with open(log) as f:
                names.update(line.strip() for line in f if line.strip())

        names = [n for n in names if n]
        deleted = 0
        for i in range(0, len(names), batch):
            chunk = names[i : i + batch]
            for ledger in ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry"):
                frappe.db.delete(ledger, {"voucher_type": dt, "voucher_no": ("in", chunk)})
            for child in child_tables:
                frappe.db.delete(child, {"parenttype": dt, "parent": ("in", chunk)})
            frappe.db.delete(dt, {"name": ("in", chunk)})
            deleted += len(chunk)
            frappe.db.commit()
        if os.path.exists(log):
            os.remove(log)
        print(f"[{dt}] purged {deleted}")


@frappe.whitelist()
def _debug_echo(**kwargs):
    req = frappe.local.request
    return {
        "form_dict": {k: v for k, v in frappe.form_dict.items() if k != "cmd"},
        "content_type": req.content_type,
        "raw_body": req.get_data(as_text=True)[:200],
        "headers": {k: (v if k.lower() != "authorization" else "<redacted>") for k, v in req.headers.items()},
        "user": frappe.session.user,
    }
