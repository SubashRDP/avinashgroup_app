"""Load test: one crore (10M) rows in EACH of 10 transaction doctypes.

Covers both numbering paths on avinas1 / NGK:

  engine (scan-based, O(rows-in-scope)) — synthetic rows land INSIDE the real
  numbering scope so the MAX-scan has to wade through them:
      Journal Entry (BJV), Payment Entry (NOC),
      Purchase Invoice (RTN), Purchase Receipt (PR)

  series (tabSeries counter, O(1)) — volume in the table, counter untouched:
      Sales Invoice, Sales Order, Purchase Order,
      Delivery Note, Quotation, Stock Entry

Per doctype: measure numbering latency empty vs at 1 crore. All synthetic
rows are named LOADTEST-* and deleted afterwards; every counter moved is
restored from a persisted snapshot (crash-safe).

    bench --site avinas1 execute avinashgroup_app.scripts.loadtest_ngk_ten_doctypes.run
    bench --site avinas1 execute avinashgroup_app.scripts.loadtest_ngk_ten_doctypes.cleanup
"""

import os
import time

import frappe

COMPANY = "Nepal Gas Udhyog (Karnali) Pvt. Ltd."
FY = "82/83"
BASE = 1_000_000
TOTAL = 10_000_000
BATCH = 1_000_000
MIN_FREE_GB = 60
SNAPSHOT_KEY = "ngk_loadtest10_series_snapshot"

# mode 'engine': rows fill the real scan scope (type + code + custom_name)
# mode 'series': plain volume; naming is a counter and shouldn't care
CONFIG = [
    {"doctype": "Journal Entry", "tag": "JE", "mode": "engine",
     "date_col": "posting_date", "type_field": "custom_p_type",
     "type_value": "Bank Entry", "code": "BJV"},
    {"doctype": "Payment Entry", "tag": "PE", "mode": "engine",
     "date_col": "posting_date", "type_field": "custom_p_type",
     "type_value": "NOC Payment", "code": "NOC"},
    {"doctype": "Purchase Invoice", "tag": "PI", "mode": "engine",
     "date_col": "posting_date", "type_field": "custom_purchase_type",
     "type_value": "Purchase Return", "code": "RTN"},
    {"doctype": "Purchase Receipt", "tag": "PR", "mode": "engine",
     "date_col": "posting_date", "type_field": "custom_receipt_type",
     "type_value": "Other Purchase Receipt", "code": "PR"},
    {"doctype": "Sales Invoice", "tag": "SI", "mode": "series",
     "date_col": "posting_date", "prefix": "SB", "seq_len": 5},
    {"doctype": "Sales Order", "tag": "SO", "mode": "series",
     "date_col": "transaction_date", "prefix": "SO", "seq_len": 5},
    {"doctype": "Purchase Order", "tag": "PO", "mode": "series",
     "date_col": "transaction_date", "prefix": "PO", "seq_len": 5},
    {"doctype": "Delivery Note", "tag": "DN", "mode": "series",
     "date_col": "posting_date", "prefix": "DN", "seq_len": 5},
    {"doctype": "Quotation", "tag": "QTN", "mode": "series",
     "date_col": "transaction_date", "prefix": "QTN", "seq_len": 5},
    {"doctype": "Stock Entry", "tag": "STE", "mode": "series",
     "date_col": "posting_date", "prefix": "STE", "seq_len": 3},
]


def _free_gb():
    st = os.statvfs("/")
    return st.f_bavail * st.f_frsize / 1024 ** 3


def _series_snapshot():
    return dict(frappe.db.sql(
        "SELECT `name`, `current` FROM `tabSeries` "
        "WHERE `name` LIKE %s OR `name` LIKE %s", ("docno:%", "NGK-%")))


def _series_restore(snap):
    for name, cur in frappe.db.sql(
        "SELECT `name`, `current` FROM `tabSeries` "
        "WHERE `name` LIKE %s OR `name` LIKE %s", ("docno:%", "NGK-%")):
        old = snap.get(name)
        if old is None:
            frappe.db.sql("DELETE FROM `tabSeries` WHERE `name`=%s", name)
        elif old != cur:
            frappe.db.sql("UPDATE `tabSeries` SET `current`=%s WHERE `name`=%s",
                          (old, name))
    frappe.db.commit()


def _probe_doc(cfg):
    d = frappe.new_doc(cfg["doctype"])
    d.company = COMPANY
    d.set(cfg["date_col"], frappe.utils.today())
    if cfg["mode"] == "engine":
        d.set(cfg["type_field"], cfg["type_value"])
        if cfg["doctype"] == "Journal Entry":
            d.voucher_type = "Journal Entry"
        elif cfg["doctype"] == "Payment Entry":
            d.payment_type = "Receive"
    return d


def _measure(cfg):
    """(peek_ms or autoname_ms, drawn value) for the doctype's numbering path."""
    from avinashgroup_app.custom_code.Override import naming_series as ns
    if cfg["mode"] == "engine":
        d = _probe_doc(cfg)
        t = time.perf_counter()
        ns.peek_next_document_no(d)
        peek = (time.perf_counter() - t) * 1000
        d2 = _probe_doc(cfg)
        t = time.perf_counter()
        ns.apply_document_no(d2)
        draw = (time.perf_counter() - t) * 1000
        return peek, draw, d2.get("custom_document_no")
    d = _probe_doc(cfg)
    t = time.perf_counter()
    name = ns.make_name_with_fiscal_year(
        cfg["prefix"], d, sequence_length=cfg["seq_len"])
    ms = (time.perf_counter() - t) * 1000
    return ms, ms, name


def _load(cfg):
    tag = cfg["tag"]
    table = "tab" + cfg["doctype"]
    common_cols = ("name, creation, modified, modified_by, owner, "
                   "docstatus, idx, company, `{}`".format(cfg["date_col"]))
    inserted = 0
    while inserted < TOTAL:
        if _free_gb() < MIN_FREE_GB:
            print(f"  !! aborting {tag}: only {_free_gb():.0f} GB free",
                  flush=True)
            return inserted
        lo, hi = BASE + inserted + 1, BASE + inserted + BATCH
        t = time.perf_counter()
        if cfg["mode"] == "engine":
            frappe.db.sql(f"""
                INSERT INTO `{table}`
                  ({common_cols}, `{cfg["type_field"]}`, custom_p_type_code,
                   custom_document_no, custom_name)
                SELECT CONCAT('LOADTEST-{tag}-', LPAD(seq, 9, '0')),
                   NOW(6), NOW(6), 'Administrator', 'Administrator', 0, 0,
                   %s, %s, %s, %s, seq,
                   CONCAT('NGK-', %s, '-', seq, '-', %s)
                FROM seq_{lo}_to_{hi}
            """, (COMPANY, frappe.utils.today(), cfg["type_value"],
                  cfg["code"], cfg["code"], FY))
        else:
            frappe.db.sql(f"""
                INSERT INTO `{table}` ({common_cols})
                SELECT CONCAT('LOADTEST-{tag}-', LPAD(seq, 9, '0')),
                   NOW(6), NOW(6), 'Administrator', 'Administrator', 0, 0,
                   %s, %s
                FROM seq_{lo}_to_{hi}
            """, (COMPANY, frappe.utils.today()))
        frappe.db.commit()
        inserted += BATCH
        print(f"  {tag}: {inserted:>10,} rows (batch "
              f"{(time.perf_counter()-t):.1f}s, {_free_gb():.0f} GB free)",
              flush=True)
    return inserted


def run():
    frappe.db.sql("SET SESSION sql_big_selects = 1")
    snap = _series_snapshot()
    frappe.db.set_global(SNAPSHOT_KEY, frappe.as_json(snap))
    frappe.db.commit()

    results = []
    for cfg in CONFIG:
        tag = cfg["tag"]
        before = _measure(cfg)
        print(f"{tag}: baseline {before[0]:.0f}/{before[1]:.0f} ms "
              f"-> {before[2]}", flush=True)
        loaded = _load(cfg)
        after = _measure(cfg)
        results.append((cfg, loaded, before, after))
        print(f"{tag}: AT {loaded:,} ROWS {after[0]:.0f}/{after[1]:.0f} ms "
              f"-> {after[2]}", flush=True)

    print("\n=== 1-crore-per-doctype summary "
          "(peek/draw ms for engine, autoname ms for series) ===")
    print(f"{'doctype':18} | {'mode':6} | {'rows':>11} | "
          f"{'before ms':>12} | {'after ms':>12} | assigned at 1 crore")
    for cfg, loaded, b, a in results:
        print(f"{cfg['doctype']:18} | {cfg['mode']:6} | {loaded:>11,} | "
              f"{b[0]:5.0f}/{b[1]:5.0f} | {a[0]:5.0f}/{a[1]:5.0f} | {a[2]}")

    cleanup()
    return "done"


def cleanup():
    """Delete all LOADTEST rows in every table, restore counters."""
    from avinashgroup_app.custom_code.Override import naming_series as ns
    t = time.perf_counter()
    for cfg in CONFIG:
        table = "tab" + cfg["doctype"]
        pattern = f"LOADTEST-{cfg['tag']}-%"
        while True:
            frappe.db.sql(
                f"DELETE FROM `{table}` WHERE name LIKE %s LIMIT 500000",
                (pattern,))
            frappe.db.commit()
            left = frappe.db.sql(
                f"SELECT COUNT(*) FROM `{table}` WHERE name LIKE %s",
                (pattern,))[0][0]
            if not left:
                break
        print(f"  cleaned {cfg['tag']}", flush=True)
    raw = frappe.db.get_global(SNAPSHOT_KEY)
    if raw:
        _series_restore(frappe.parse_json(raw))
        frappe.db.set_global(SNAPSHOT_KEY, None)
        frappe.db.commit()
    ns.clear_numbering_rules_cache()
    print(f"cleanup done in {(time.perf_counter()-t)/60:.1f} min", flush=True)
