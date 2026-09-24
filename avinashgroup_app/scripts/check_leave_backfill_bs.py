"""Rolled-back check, see docs/payroll-handover.md §9. Nothing is kept: commits are
stubbed and the transaction is rolled back. Run from sites/:
    ../env/bin/python ../apps/avinashgroup_app/avinashgroup_app/scripts/check_leave_backfill_bs.py
"""
import frappe
frappe.init(site="avinas1", sites_path="/home/sijan/frappe-15/sites"); frappe.connect(); frappe.set_user("Administrator")
frappe.db.commit = lambda *a, **k: None
from frappe.utils import getdate
out = []
def check(name, ok, extra=""): out.append(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {extra}" if extra else ""))
from avinashgroup_app.hr.leave_policy_assignment_bs import BSLeavePolicyAssignment, bs_months_backfill
from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import LeavePolicyAssignment
frappe.cache.delete_value("app_hooks"); frappe.local.app_hooks = None; frappe.local.doctype_class_cache = {} if hasattr(frappe.local, "doctype_class_cache") else None
check("override is the class Frappe loads", frappe.get_doc({"doctype": "Leave Policy Assignment"}).__class__.__name__ == "BSLeavePolicyAssignment",
      frappe.get_doc({"doctype": "Leave Policy Assignment"}).__class__.__name__)
lt = frappe.get_doc("Leave Type", "Casual Leave")
def both(joining, today):
    frappe.flags.current_date = getdate(today)
    d = frappe._dict(effective_from=getdate("2026-07-17"), effective_to=getdate("2027-07-16"))
    stock = LeavePolicyAssignment.get_leaves_for_passed_months(frappe._dict(d, get_current_and_from_date=lambda j: LeavePolicyAssignment.get_current_and_from_date(frappe._dict(d), j)), 21, lt, getdate(joining))
    bs = bs_months_backfill(21, lt, getdate(joining), d.effective_from, d.effective_to, getdate(today))
    return stock, bs
s, b = both("2020-01-01", "2026-10-10")   # 24 Ashwin: Shrawan + Bhadra done
check("assigned 24 Ashwin: 2 BS months (Shrawan, Bhadra)", b == 3.5, f"stock={s} BS={b}")
s, b = both("2020-01-01", "2026-10-17")   # 31 Ashwin = its last day
check("assigned on Ashwin's last day: 3 months", b == 5.25, f"stock={s} BS={b}")
s, b = both("2026-08-31", "2026-10-10")   # joined 15 Bhadra
check("joined 15 Bhadra, assigned 24 Ashwin: part of Bhadra only", 0 < b < 1.75, f"stock={s} BS={b}")
s, b = both("2020-01-01", "2026-07-20")   # early Shrawan
check("assigned in Shrawan: nothing yet (Shrawan credits on its last day)", b == 0, f"stock={s} BS={b}")
s, b = both("2020-01-01", "2027-07-16")   # last day of the year
check("assigned on 31 Ashadh: all 12 months = 21", b == 21, f"stock={s} BS={b}")
frappe.flags.current_date = None
frappe.db.rollback(); frappe.cache.delete_value("app_hooks")
print("\n".join(out))
