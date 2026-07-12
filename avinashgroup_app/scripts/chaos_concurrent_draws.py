"""Concurrency hammer: parallel PROCESSES race to draw numbers in the SAME
numbering scope (NGK / Journal Entry / Bank Entry). The tabSeries row lock is
supposed to make duplicates impossible — this tries to disprove that.

Orchestration (separate shells so the races are real):

    bench --site avinas1 execute avinashgroup_app.scripts.chaos_concurrent_draws.prepare
    # launch K workers IN PARALLEL, e.g.:
    #   for i in $(seq 1 8); do
    #     bench --site avinas1 execute \
    #       avinashgroup_app.scripts.chaos_concurrent_draws.worker \
    #       --kwargs "{'tag': 'w$i', 'draws': 25}" &
    #   done; wait
    bench --site avinas1 execute \
        avinashgroup_app.scripts.chaos_concurrent_draws.verify_and_cleanup \
        --kwargs "{'expected': 200}"

`mixed` workers additionally type MANUAL numbers just above the current max —
the worst case for auto/manual collision.
"""

import json

import frappe

COMPANY = "Nepal Gas Udhyog (Karnali) Pvt. Ltd."
MARKER = "CHAOSHAMMER"
SNAPSHOT_KEY = "chaos_hammer_series_snapshot"


def _je(manual_no=None):
    accounts = frappe.get_all(
        "Account", filters={"company": COMPANY, "is_group": 0, "disabled": 0},
        pluck="name", limit=2)
    d = frappe.new_doc("Journal Entry")
    d.update({"company": COMPANY, "posting_date": frappe.utils.today(),
              "voucher_type": "Journal Entry", "custom_p_type": "Bank Entry",
              "user_remark": MARKER})
    d.append("accounts", {"account": accounts[0],
                          "debit_in_account_currency": 100, "debit": 100})
    d.append("accounts", {"account": accounts[1],
                          "credit_in_account_currency": 100, "credit": 100})
    if manual_no is not None:
        d.custom_document_no = manual_no
        d.custom_document_no_manual = 1
    return d


def prepare():
    """Snapshot series counters (persisted — survives everything)."""
    snap = dict(frappe.db.sql(
        "SELECT `name`, `current` FROM `tabSeries` "
        "WHERE `name` LIKE %s OR `name` LIKE %s", ("docno:%", "NGK-%")))
    frappe.db.set_global(SNAPSHOT_KEY, json.dumps(snap))
    frappe.db.commit()
    print(f"snapshot taken ({len(snap)} series rows)")


def worker(tag, draws=25):
    """Insert `draws` real auto-numbered JEs as fast as possible."""
    drawn = []
    for _ in range(int(draws)):
        d = _je()
        d.insert(ignore_permissions=True)
        frappe.db.commit()
        drawn.append(d.custom_document_no)
    print(f"{tag}: drew {drawn}")


def mixed(tag, draws=10):
    """Alternate auto draws with hostile manual numbers near the live max."""
    from avinashgroup_app.custom_code.Override import naming_series as ns
    outcomes = []
    for i in range(int(draws)):
        if i % 2:
            probe = _je()
            target = (ns.peek_next_document_no(probe) or 1) + 1  # near-future number
            d = _je(manual_no=target)
            try:
                d.insert(ignore_permissions=True)
                frappe.db.commit()
                outcomes.append(("manual", d.custom_document_no))
            except frappe.ValidationError:
                frappe.db.rollback()
                outcomes.append(("manual-rejected", target))
        else:
            d = _je()
            d.insert(ignore_permissions=True)
            frappe.db.commit()
            outcomes.append(("auto", d.custom_document_no))
    print(f"{tag}: {outcomes}")


def verify_and_cleanup(expected=None):
    """All hammered docs must hold DISTINCT numbers; then delete + restore."""
    rows = frappe.db.sql(
        "SELECT name, custom_document_no FROM `tabJournal Entry` "
        "WHERE user_remark = %s", (MARKER,))
    numbers = [int(r[1]) for r in rows if r[1]]
    dupes = {n for n in numbers if numbers.count(n) > 1}
    print(f"hammered docs: {len(rows)}, numbers: {len(numbers)}, "
          f"distinct: {len(set(numbers))}")
    if expected is not None:
        print(f"expected >= {expected}: {len(rows) >= int(expected)}")
    if dupes:
        offenders = [r for r in rows if int(r[1] or 0) in dupes]
        print(f"!!! DUPLICATES FOUND — engine broken: {sorted(dupes)}")
        for name, n in offenders:
            print(f"    {name} -> {n}")
    else:
        print("no duplicates — the scope lock held under process-parallel load")

    for name, _ in rows:
        frappe.delete_doc("Journal Entry", name, force=1, ignore_permissions=True)
    frappe.db.commit()
    raw = frappe.db.get_global(SNAPSHOT_KEY)
    if raw:
        snap = json.loads(raw)
        for name, cur in frappe.db.sql(
            "SELECT `name`, `current` FROM `tabSeries` "
            "WHERE `name` LIKE %s OR `name` LIKE %s", ("docno:%", "NGK-%")):
            old = snap.get(name)
            if old is None:
                frappe.db.sql("DELETE FROM `tabSeries` WHERE `name`=%s", name)
            elif old != cur:
                frappe.db.sql(
                    "UPDATE `tabSeries` SET `current`=%s WHERE `name`=%s", (old, name))
        frappe.db.set_global(SNAPSHOT_KEY, None)
        frappe.db.commit()
    print("cleaned up, series restored")
    return {"docs": len(rows), "duplicates": sorted(dupes)}
