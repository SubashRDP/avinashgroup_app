"""Load test: does NGK rule-driven numbering survive one crore of data?

Bulk-inserts synthetic draft Journal Entries (name LOADTEST-JE-*) directly
into the REAL numbering scope (custom_name NGK-BJV-<n>-82/83, numbers from
1,000,001 so they sit far above live data), then measures at checkpoints:

  * peek_next_document_no latency (the MAX-scan over the scope)
  * a full real .insert() through every hook
  * a 50-draw burst — numbers must be strictly sequential, no dupes
  * duplicate-number rejection at full scale

Cleanup deletes every synthetic row and test doc and restores every series
counter, and is standalone re-runnable:

    bench --site avinas1 execute avinashgroup_app.scripts.loadtest_ngk_numbering.run
    bench --site avinas1 execute avinashgroup_app.scripts.loadtest_ngk_numbering.cleanup
"""

import time

import frappe

COMPANY = "Nepal Gas Udhyog (Karnali) Pvt. Ltd."
FY = "82/83"
BASE = 1_000_000           # synthetic numbers start at BASE+1
TOTAL = 10_000_000         # one crore
BATCH = 1_000_000
CHECKPOINTS = {1_000_000, 2_000_000, 5_000_000, 10_000_000}
MARKER = "LOADTEST-JE-"


def _je(number=None):
    accounts = frappe.get_all(
        "Account", filters={"company": COMPANY, "is_group": 0, "disabled": 0},
        pluck="name", limit=2)
    d = frappe.new_doc("Journal Entry")
    d.update({"company": COMPANY, "posting_date": frappe.utils.today(),
              "voucher_type": "Journal Entry", "custom_p_type": "Bank Entry"})
    d.append("accounts", {"account": accounts[0],
                          "debit_in_account_currency": 100, "debit": 100})
    d.append("accounts", {"account": accounts[1],
                          "credit_in_account_currency": 100, "credit": 100})
    if number is not None:
        d.custom_document_no = number
        d.custom_document_no_manual = 1
    return d


def _peek_ms(n=3):
    from avinashgroup_app.custom_code.Override import naming_series as ns
    best = []
    for _ in range(n):
        d = _je()
        t = time.perf_counter()
        ns.peek_next_document_no(d)
        best.append((time.perf_counter() - t) * 1000)
    return sum(best) / len(best)


def _insert_ms():
    """Time one full real insert, then delete it immediately — its drawn
    number sits exactly where the next synthetic batch starts, so it must
    not linger (custom_name carries a unique index)."""
    d = _je()
    t = time.perf_counter()
    d.insert(ignore_permissions=True)
    ms = (time.perf_counter() - t) * 1000
    voucher = d.custom_name
    frappe.delete_doc("Journal Entry", d.name, force=1, ignore_permissions=True)
    frappe.db.commit()
    return ms, voucher


def _row_count():
    return frappe.db.sql(
        "SELECT COUNT(*) FROM `tabJournal Entry` WHERE name LIKE %s",
        (MARKER + "%",))[0][0]


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


def run():
    from avinashgroup_app.custom_code.Override import naming_series as ns

    frappe.db.sql("SET SESSION sql_big_selects = 1")
    snap = _series_snapshot()
    # persist the snapshot so a killed run can still restore counters
    frappe.db.set_global("ngk_loadtest_series_snapshot", frappe.as_json(snap))
    frappe.db.commit()

    results = []
    print(f"baseline rows in scope: "
          f"{frappe.db.sql('SELECT COUNT(*) FROM `tabJournal Entry`')[0][0]}")
    results.append(("baseline", _peek_ms(), *_insert_ms()))

    inserted = 0
    while inserted < TOTAL:
        lo, hi = BASE + inserted + 1, BASE + inserted + BATCH
        t = time.perf_counter()
        frappe.db.sql(f"""
            INSERT INTO `tabJournal Entry`
              (name, creation, modified, modified_by, owner, docstatus, idx,
               title, voucher_type, company, posting_date, is_opening,
               custom_p_type, custom_p_type_code, custom_document_no,
               custom_name, total_debit, total_credit)
            SELECT CONCAT(%s, LPAD(seq, 9, '0')), NOW(6), NOW(6),
               'Administrator', 'Administrator', 0, 0,
               'LOADTEST', 'Journal Entry', %s, %s, 'No',
               'Bank Entry', 'BJV', seq,
               CONCAT('NGK-BJV-', seq, '-', %s), 0, 0
            FROM seq_{lo}_to_{hi}
        """, (MARKER, COMPANY, frappe.utils.today(), FY))
        frappe.db.commit()
        inserted += BATCH
        print(f"loaded {inserted:>10,} rows "
              f"(batch {(time.perf_counter()-t):.1f}s)", flush=True)

        if inserted in CHECKPOINTS:
            peek = _peek_ms()
            ins, voucher = _insert_ms()
            results.append((f"{inserted:,} rows", peek, ins, voucher))
            print(f"  checkpoint: peek {peek:.0f} ms, "
                  f"full insert {ins:.0f} ms -> {voucher}", flush=True)

    # ---- burst at full scale: 50 sequential draws, no dupes, no gaps ----
    drawn = []
    t = time.perf_counter()
    for _ in range(50):
        d = _je()
        ns.apply_document_no(d)
        drawn.append(d.custom_document_no)
    burst_s = time.perf_counter() - t
    sequential = drawn == list(range(drawn[0], drawn[0] + 50))
    print(f"burst: 50 draws in {burst_s:.1f}s "
          f"({burst_s / 50 * 1000:.0f} ms/draw), start {drawn[0]:,}, "
          f"strictly sequential: {sequential}", flush=True)

    # ---- duplicate rejection at full scale ----
    dup_ok = False
    try:
        _je(number=BASE + 5).insert(ignore_permissions=True)
    except frappe.ValidationError:
        dup_ok = True
    print(f"duplicate number rejected at 1 crore: {dup_ok}", flush=True)

    print("\n=== latency summary ===")
    print(f"{'scale':>15} | {'peek ms':>8} | {'full insert ms':>14} | assigned")
    for label, peek, ins, voucher in results:
        print(f"{label:>15} | {peek:8.0f} | {ins:14.0f} | {voucher}")

    cleanup()
    return {"sequential": sequential, "duplicate_rejected": dup_ok}


def cleanup():
    """Delete synthetic rows + test docs, restore counters. Re-runnable."""
    from avinashgroup_app.custom_code.Override import naming_series as ns

    t = time.perf_counter()
    while True:
        n = frappe.db.sql(
            "DELETE FROM `tabJournal Entry` WHERE name LIKE %s LIMIT 500000",
            (MARKER + "%",))
        frappe.db.commit()
        remaining = _row_count()
        print(f"  deleting synthetic rows... {remaining:,} left", flush=True)
        if not remaining:
            break
    # any stragglers from a crashed run
    for name in frappe.get_all(
            "Journal Entry",
            filters={"title": "LOADTEST"}, pluck="name"):
        frappe.delete_doc("Journal Entry", name, force=1, ignore_permissions=True)
    frappe.db.commit()

    raw = frappe.db.get_global("ngk_loadtest_series_snapshot")
    if raw:
        _series_restore(frappe.parse_json(raw))
        frappe.db.set_global("ngk_loadtest_series_snapshot", None)
        frappe.db.commit()
    ns.clear_numbering_rules_cache()
    print(f"cleanup done in {(time.perf_counter()-t):.0f}s", flush=True)

    d = _je()
    nxt = ns.peek_next_document_no(d)
    print(f"post-cleanup next Bank Entry number: {nxt}", flush=True)
