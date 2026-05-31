"""
Stock Ledger Health Check — avinashgroup_app

Run before and after any stock fix to measure damage and verify improvement.

Usage:
    bench --site avinas1 execute avinashgroup_app.custom_code.stock_health_check.run
"""

import frappe
from frappe.utils import flt


def run():
    print("\n" + "=" * 70)
    print("STOCK LEDGER HEALTH CHECK")
    print("=" * 70)

    _check_negative_stock_setting()
    _check_negative_stock_items()
    _check_zero_valuation_sales()
    _check_repost_jobs()
    _check_backdated_purchase_invoices()

    print("\n" + "=" * 70 + "\n")


# ── 1. Stock Settings ──────────────────────────────────────────────────────

def _check_negative_stock_setting():
    allow = frappe.db.get_single_value("Stock Settings", "allow_negative_stock")
    print(f"\n[1] Stock Settings → allow_negative_stock = {allow}")
    if not allow:
        print("    ⚠  DISABLED — repost jobs will fail whenever stock goes negative during replay")


# ── 2. Items currently in negative stock ──────────────────────────────────

def _check_negative_stock_items():
    rows = frappe.db.sql("""
        SELECT item_code, warehouse,
               SUM(actual_qty) AS balance
        FROM `tabStock Ledger Entry`
        WHERE is_cancelled = 0
        GROUP BY item_code, warehouse
        HAVING balance < 0
        ORDER BY balance ASC
        LIMIT 20
    """, as_dict=True)

    print(f"\n[2] Items with negative stock balance: {len(rows)}")
    for r in rows:
        print(f"    {r.item_code:30s}  {r.warehouse:40s}  qty={flt(r.balance, 2)}")


# ── 3. Sales SLEs with valuation_rate = 0 (incorrectly costed sales) ──────

def _check_zero_valuation_sales():
    result = frappe.db.sql("""
        SELECT
            item_code,
            warehouse,
            COUNT(*)                           AS sle_count,
            SUM(ABS(actual_qty))               AS total_qty_sold,
            MIN(posting_date)                  AS earliest,
            MAX(posting_date)                  AS latest
        FROM `tabStock Ledger Entry`
        WHERE is_cancelled = 0
          AND actual_qty < 0
          AND valuation_rate = 0
        GROUP BY item_code, warehouse
        ORDER BY sle_count DESC
        LIMIT 20
    """, as_dict=True)

    total_sles = sum(r.sle_count for r in result)
    print(f"\n[3] Sales SLEs with valuation_rate = 0 (COGS missing): {total_sles} entries across {len(result)} item/warehouse combos")
    for r in result:
        print(f"    {r.item_code:30s}  {r.warehouse:40s}  "
              f"SLEs={r.sle_count}  qty={flt(r.total_qty_sold, 0)}  "
              f"({r.earliest} → {r.latest})")


# ── 4. Repost Item Valuation job status ───────────────────────────────────

def _check_repost_jobs():
    summary = frappe.db.sql("""
        SELECT status, COUNT(*) AS cnt
        FROM `tabRepost Item Valuation`
        WHERE docstatus = 1
        GROUP BY status
    """, as_dict=True)

    print("\n[4] Repost Item Valuation jobs:")
    if not summary:
        print("    (none)")
    for row in summary:
        print(f"    {row.status:15s}  {row.cnt}")

    failed = frappe.get_all(
        "Repost Item Valuation",
        filters={"status": "Failed", "docstatus": 1},
        fields=["name", "item_code", "warehouse", "posting_date", "error_log"],
        limit=10,
        order_by="posting_date asc",
    )
    if failed:
        print(f"\n    Failed jobs (top {len(failed)}):")
        for f in failed:
            err_preview = (f.error_log or "")[:120].replace("\n", " ")
            print(f"    • {f.name}  {f.item_code}  {f.posting_date}")
            if err_preview:
                print(f"      Error: {err_preview}")


# ── 5. Backdated Purchase Invoices ────────────────────────────────────────

def _check_backdated_purchase_invoices():
    rows = frappe.db.sql("""
        SELECT name, supplier, posting_date,
               DATE(creation)                         AS created_on,
               DATEDIFF(DATE(creation), posting_date) AS days_backdated
        FROM `tabPurchase Invoice`
        WHERE docstatus = 1
          AND update_stock = 1
          AND DATEDIFF(DATE(creation), posting_date) > 3
        ORDER BY days_backdated DESC
        LIMIT 20
    """, as_dict=True)

    print(f"\n[5] Backdated Purchase Invoices (>3 days, update_stock=1): {len(rows)}")
    for r in rows:
        print(f"    {r.name:30s}  posted={r.posting_date}  created={r.created_on}  "
              f"backdated_by={r.days_backdated}d  supplier={r.supplier}")
