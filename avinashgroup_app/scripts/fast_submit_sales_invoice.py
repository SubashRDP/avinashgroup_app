# Submit draft Sales Invoices fast, then rebuild the stock ledger once.
#
#   WHY IT IS FAST
#   Normally every submit rewrites qty_after_transaction on every later row
#   of that item+warehouse ledger. Backdated into a 75k-row ledger that is
#   ~47k row updates per invoice, and it gets worse with each one inserted.
#   Here that rewrite is switched off and replaced by a watermark: the
#   earliest date touched per (item, warehouse). At the end the ledger is
#   rebuilt once from each watermark forward. Same result, done once.
#
#   WHAT IS TRUE IN BETWEEN
#   Between submit() finishing and repost() finishing, qty_after_transaction
#   and Bin are WRONG for the touched item+warehouse pairs. Stock reports
#   will lie. Negative-stock validation is also skipped for that window.
#   Do not stop after submit(). Always finish repost().
#
# HOW TO RUN
#   bench --site ng-group.raindropinc.com console
#   >>> exec(open("/home/raindrop/fast_submit.py").read(), globals())
#   >>> count()                 # read-only: how many drafts are waiting
#   >>> run(limit=50)           # trial: submit 50 + rebuild, check the numbers
#   >>> run()                   # the rest, then the rebuild
#   >>> verify()                # read-only: Bin vs ledger agreement
#
#   If submit() is interrupted, the watermarks are already on disk. Just:
#   >>> repost()
#
#   The file also lives in the app, so instead of a copy on the server:
#   >>> from avinashgroup_app.scripts import fast_submit_sales_invoice as f
#   >>> f.count(); f.run()
#
# Every import sits inside the function that uses it, and the patched
# functions are nested so they close over their state. The bench console
# keeps globals and locals in separate namespaces; this layout cannot be
# affected by that.

COMPANY = "Nepal Gas Udhyog (Narayani) Pvt. Ltd."
PREFIX = "NGN-SB-78/79-"

# Where the watermarks are parked between submit() and repost(). Left blank
# it resolves to sites/<site>/fast_submit_marks.json, so two sites can never
# read each other's. Set it to an absolute path to override.
MARKS_FILE = ""


def marks_path():
    """Absolute path of the watermark file. Printed so it is never a
    mystery where an interrupted run left its state.

    frappe.get_site_path() returns a path relative to the bench root, so
    resolving it here keeps repost() working even if the console that
    picks up an interrupted run was started from a different directory.
    """
    import os

    if MARKS_FILE:
        return os.path.abspath(MARKS_FILE)

    import frappe

    return os.path.abspath(frappe.get_site_path("fast_submit_marks.json"))


def scope():
    """The draft filter. One definition, shared by everything here."""
    f = [["company", "=", COMPANY], ["docstatus", "=", 0]]
    if PREFIX:
        f.append(["name", "like", PREFIX + "%"])
    return f


def count():
    """Read-only. How many drafts match the scope."""
    import frappe

    n = frappe.db.count("Sales Invoice", scope())
    print("company :", COMPANY)
    print("prefix  :", PREFIX or "(any)")
    print("drafts  :", n)
    return n


def _load_marks():
    import json
    import os

    path = marks_path()
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        rows = json.load(fh)
    return {(r[0], r[1]): r[2] for r in rows}


def _save_marks(marks):
    import json

    rows = [[k[0], k[1], v] for k, v in marks.items()]
    with open(marks_path(), "w") as fh:
        json.dump(rows, fh)


def submit(limit=None, report_every=100, retries=3):
    """Submit the drafts with the future-qty rewrite switched off.

    Records a watermark per (item, warehouse) instead. Watermarks are
    written to MARKS_FILE after every page, so a Ctrl-C loses nothing.
    Returns the list of (name, error) that failed.
    """
    import time
    import frappe
    import erpnext.stock.stock_ledger as sl
    from collections import Counter
    from erpnext.controllers.stock_controller import StockController
    from frappe.utils import get_datetime

    total = count()
    if total == 0:
        print("nothing to do")
        return []

    marks = _load_marks()
    if marks:
        print("carrying forward %d existing watermarks" % len(marks))

    def record_only(args, allow_negative_stock=False):
        """Stands in for update_qty_in_future_sle. Notes, does not rewrite."""
        key = (args.get("item_code"), args.get("warehouse"))
        when = get_datetime(
            str(args.get("posting_date")) + " " + str(args.get("posting_time"))
        )
        stamp = when.strftime("%Y-%m-%d %H:%M:%S")
        if key not in marks or stamp < marks[key]:
            marks[key] = stamp

    def skip_repost(self, force=False, via_landed_cost_voucher=False):
        """Stands in for repost_future_sle_and_gle. The final repost
        covers this, so do not queue Repost Item Valuation per invoice."""
        return

    real_future_sle = sl.update_qty_in_future_sle
    real_repost = StockController.repost_future_sle_and_gle

    sl.update_qty_in_future_sle = record_only
    StockController.repost_future_sle_and_gle = skip_repost

    started = time.time()
    done = 0
    failed = []
    bad = {}

    try:
        while True:
            names = frappe.get_all(
                "Sales Invoice",
                filters=scope(),
                pluck="name",
                order_by="posting_date asc, name asc",
                limit_page_length=200,
            )
            names = [n for n in names if n not in bad]
            if not names:
                break

            stop = False
            for name in names:
                if limit and done >= limit:
                    stop = True
                    break

                err = None
                for attempt in range(retries):
                    sp = "f" + str(done) + "_" + str(attempt)
                    frappe.db.savepoint(sp)
                    try:
                        doc = frappe.get_doc("Sales Invoice", name)
                        doc.flags.ignore_permissions = True
                        doc.submit()
                        frappe.db.commit()
                        done += 1
                        err = None
                        break
                    except Exception as e:
                        frappe.db.rollback(save_point=sp)
                        err = str(e)[:160]
                        low = err.lower()
                        transient = ("deadlock" in low
                                     or "lock wait timeout" in low)
                        if not transient:
                            break
                        time.sleep(0.5 * (attempt + 1))

                if err is not None:
                    bad[name] = 1
                    failed.append((name, err))

                if done and done % report_every == 0:
                    el = time.time() - started
                    left = total - done - len(failed)
                    print("%d done | %d left | %d failed | %d ms/doc"
                          " | %.1f min | %d marks"
                          % (done, left, len(failed),
                             int(el * 1000 / done), el / 60.0, len(marks)))

            _save_marks(marks)

            if stop:
                break
    finally:
        sl.update_qty_in_future_sle = real_future_sle
        StockController.repost_future_sle_and_gle = real_repost
        _save_marks(marks)

    el = time.time() - started
    print("")
    print("SUBMIT DONE: %d submitted, %d failed, %.1f min"
          % (done, len(failed), el / 60.0))
    print("watermarks : %d item+warehouse pairs -> %s"
          % (len(marks), marks_path()))

    if failed:
        print("")
        print("failure reasons:")
        for msg, n in Counter(m for _, m in failed).most_common(12):
            print("  %4d  %s" % (n, msg))

    print("")
    print("STOCK IS NOT CORRECT YET. Run repost() next.")
    return failed


def repost(allow_negative_stock=True):
    """Rebuild the ledger once, from each watermark forward.

    This is the step that makes qty_after_transaction and Bin correct
    again. It is safe to re-run; it recomputes rather than adjusts.
    """
    import time
    import frappe
    from erpnext.stock.stock_ledger import update_entries_after

    marks = _load_marks()
    if not marks:
        print("no watermarks in %s -- nothing to rebuild" % marks_path())
        return []

    print("rebuilding %d item+warehouse pairs" % len(marks))
    print("")

    started = time.time()
    ok = 0
    failed = []

    for i, (key, stamp) in enumerate(sorted(marks.items()), 1):
        item_code, warehouse = key
        date_part, time_part = stamp.split(" ")
        try:
            update_entries_after(
                {
                    "item_code": item_code,
                    "warehouse": warehouse,
                    "posting_date": date_part,
                    "posting_time": time_part,
                },
                allow_negative_stock=allow_negative_stock,
            )
            frappe.db.commit()
            ok += 1
        except Exception as e:
            frappe.db.rollback()
            failed.append((item_code, warehouse, str(e)[:160]))

        el = time.time() - started
        print("%3d/%d  %.1f min  %s @ %s  from %s"
              % (i, len(marks), el / 60.0, item_code, warehouse, stamp))

    el = time.time() - started
    print("")
    print("REPOST DONE: %d rebuilt, %d failed, %.1f min"
          % (ok, len(failed), el / 60.0))

    for item_code, warehouse, msg in failed:
        print("  FAILED %s @ %s : %s" % (item_code, warehouse, msg))

    if not failed:
        print("")
        print("Stock is correct again. Run verify() to confirm.")
    return failed


def run(limit=None):
    """Submit, then rebuild. The whole job in one call."""
    failed = submit(limit=limit)
    print("")
    print("=" * 60)
    print("")
    repost()
    return failed


def verify():
    """Read-only. For every watermarked pair, check three numbers agree.

    The important one is sum_of_moves -- SUM(actual_qty) over the ledger.
    It is derived from the movements themselves, so it is independent of
    the denormalized running balance and cannot go stale with it.

    An earlier version of this compared only Bin.actual_qty against the
    last row's qty_after_transaction. Those are not independent: during a
    deferred run update_bin_qty assigns Bin *from* that same last row via
    get_actual_qty(). Both go stale together and the check passes while
    the ledger is wrong -- observed on GEPL-ITEM-00066 reporting agreement
    at -2052813.2 when the true balance was -3186069.2. Never compare a
    value against something that was copied from it.
    """
    import frappe

    marks = _load_marks()
    if not marks:
        print("no watermarks to check")
        return []

    bad = []
    for item_code, warehouse in sorted(marks.keys()):
        row = frappe.db.sql(
            """
            SELECT
              (SELECT SUM(actual_qty) FROM `tabStock Ledger Entry`
               WHERE item_code = %(i)s AND warehouse = %(w)s
                 AND is_cancelled = 0),
              (SELECT qty_after_transaction FROM `tabStock Ledger Entry`
               WHERE item_code = %(i)s AND warehouse = %(w)s
                 AND is_cancelled = 0
               ORDER BY posting_datetime DESC, creation DESC LIMIT 1),
              (SELECT actual_qty FROM `tabBin`
               WHERE item_code = %(i)s AND warehouse = %(w)s)
            """,
            {"i": item_code, "w": warehouse},
        )
        moves, running, bin_qty = row[0] if row else (None, None, None)

        if None in (moves, running, bin_qty):
            match = "?"
        elif (abs(float(moves) - float(running)) < 0.001
              and abs(float(moves) - float(bin_qty)) < 0.001):
            match = "ok"
        else:
            match = "MISMATCH"
            bad.append((item_code, warehouse, moves, running, bin_qty))

        print("%-8s moves=%-15s running=%-15s bin=%-15s  %s @ %s"
              % (match, moves, running, bin_qty, item_code, warehouse))

    print("")
    if bad:
        print("%d MISMATCHES -- re-run repost()" % len(bad))
    else:
        print("all %d pairs agree" % len(marks))
    return bad


def clear_marks():
    """Delete the watermark file. Only after verify() is clean, or the
    ability to finish an interrupted run is lost."""
    import os

    path = marks_path()
    if os.path.exists(path):
        os.remove(path)
        print("removed", path)
    else:
        print("no such file:", path)
