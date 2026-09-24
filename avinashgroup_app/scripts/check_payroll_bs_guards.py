"""Rolled-back check, see docs/payroll-handover.md §9. Nothing is kept: commits are
stubbed and the transaction is rolled back. Run from sites/:
    ../env/bin/python ../apps/avinashgroup_app/avinashgroup_app/scripts/check_payroll_bs_guards.py
"""
import frappe
frappe.init(site="avinas1", sites_path="/home/sijan/frappe-15/sites"); frappe.connect(); frappe.set_user("Administrator")
frappe.db.commit = lambda *a, **k: None
out = []
def check(name, ok, extra=""): out.append(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {extra}" if extra else ""))
from avinashgroup_app.payroll import bs_period_guard as g
NGI = "Nepal Gas Udhyog Pvt. Ltd."
def pe(posting, start="2026-08-17", end="2026-09-16"):
    return frappe._dict(doctype="Payroll Entry", company=NGI, posting_date=posting, start_date=start, end_date=end)
def raises(fn):
    try: fn(); return None
    except frappe.ValidationError as e: return str(e)
check("Bhadra entry posted 31 Bhadra: allowed", raises(lambda: g.validate_payroll_entry(pe("2026-09-16"))) is None)
check("Bhadra entry posted 1 Bhadra: allowed", raises(lambda: g.validate_payroll_entry(pe("2026-08-17"))) is None)
msg = raises(lambda: g.validate_payroll_entry(pe("2026-09-18")))
check("Bhadra entry posted 2 Ashwin: refused", bool(msg), (msg or "")[:230])
live = frappe.get_doc("Payroll Entry", "NGI-PAYR-83/84-00001")
check("the real NGI Bhadra run passes", raises(lambda: g.validate_payroll_entry(live)) is None, f"posted {live.posting_date}")
slip = frappe.db.get_value("Salary Slip", {"payroll_entry": live.name, "docstatus": 1}, "name")
check("its submitted slips pass", raises(lambda: g.validate_salary_slip(frappe.get_doc("Salary Slip", slip))) is None)
bad = frappe.get_doc("Salary Slip", slip); bad.start_date = "2026-09-17"
check("a slip for another month than its entry: refused", bool(raises(lambda: g.validate_salary_slip(bad))))

# Salary Revision
from avinashgroup_app.avinash_group_app.doctype.salary_revision import salary_revision as sr
rev = frappe.new_doc("Salary Revision"); rev.company = NGI
rev.effective_date = "2026-08-17"; check("revision on 1 Bhadra: allowed", raises(rev.validate_effective_date) is None)
rev.effective_date = "2026-08-31"; m = raises(rev.validate_effective_date)
check("revision on 15 Bhadra: refused", bool(m), (m or "")[:200])
emp = frappe.db.get_value("Salary Slip", {"payroll_entry": live.name, "docstatus": 1}, "employee")
full = sr.arrears_for(emp, "2026-08-17", 1000)
pd = frappe.db.get_value("Salary Slip", {"employee": emp, "docstatus": 1}, ["payment_days", "total_working_days"])
check("arrears follow the days paid", abs(full - 1000 * pd[0] / pd[1]) < 0.01, f"{emp}: {pd[0]}/{pd[1]} days → {full}")
lwp = frappe.db.sql("select employee, payment_days, total_working_days from `tabSalary Slip` where docstatus=1 and payment_days < total_working_days limit 1", as_dict=True)
if lwp:
    x = lwp[0]; a = sr.arrears_for(x.employee, "2026-08-17", 3100)
    check("a short month owes less", a < 3100, f"{x.employee}: {x.payment_days}/{x.total_working_days} → {a} of 3100")
from avinashgroup_app.payroll.year_rollover import tax_slab_for
check("revision in 83/84 takes the 83/84 slab", tax_slab_for(NGI, "2026-08-17") == "Nepal 83/84 - NGI")

# Dashain service in BS months
from avinashgroup_app.avinash_group_app.doctype.dashain_bonus.dashain_bonus import months_of_service as mos, add_bs_months
from rdp_common_app.utils.bs_boundaries import bs_to_ad
j = bs_to_ad(2083, 4, 16)   # Shrawan 16
check("Shrawan 16 → Kartik 1: 2.5 months", abs(mos(j, bs_to_ad(2083, 7, 1)) - 2.5) < 0.04, str(mos(j, bs_to_ad(2083, 7, 1))))
check("Shrawan 1 → Ashwin 1: exactly 2", mos(bs_to_ad(2083, 4, 1), bs_to_ad(2083, 6, 1)) == 2.0)
check("capped at 12", mos("2020-01-01", "2026-10-18") == 12.0)
check("Ashadh 32 + 1 month → Shrawan's last day", add_bs_months(bs_to_ad(2083, 3, 32), 1) == bs_to_ad(2083, 4, 31), str(add_bs_months(bs_to_ad(2083, 3, 32), 1)))
frappe.db.rollback()
print("\n".join(out))
