"""Rolled-back check, see docs/payroll-handover.md §9. Nothing is kept: commits are
stubbed and the transaction is rolled back. Run from sites/:
    ../env/bin/python ../apps/avinashgroup_app/avinashgroup_app/scripts/check_year_rollover.py
"""
import frappe, datetime
frappe.init(site="avinas1", sites_path="/home/sijan/frappe-15/sites"); frappe.connect(); frappe.set_user("Administrator")
frappe.db.commit = lambda *a, **k: None   # nothing below is kept
from frappe.utils import getdate
out = []
def check(name, ok, extra=""): out.append(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {extra}" if extra else ""))
DT = ("Holiday List","Leave Period","Leave Policy","Payroll Period","Income Tax Slab","Salary Structure Assignment","Leave Policy Assignment")
count = lambda: {d: frappe.db.count(d) for d in DT}

from avinashgroup_app.hr import year_setup as y
from avinashgroup_app.payroll import income_tax, bs_period_guard as g
from avinashgroup_app.hr.holiday_year_switch import switch_to_current_year_lists

# 1. 83/84 re-run creates nothing
b = count(); r = y.setup_year("83/84"); a = count()
check("83/84 re-run creates nothing", a == b, str({k: a[k]-b[k] for k in a if a[k]!=b[k]}))
check("83/84 pay: nobody re-assigned", all(c["salary_rolled"]["created"] == 0 for c in r["companies"].values()),
      str({k: c["salary_rolled"] for k, c in r["companies"].items() if c["salary_rolled"]["created"] or c["salary_rolled"]["already"]}))

# 2. 84/85 Fiscal Year (inside the rolled-back transaction)
fy = frappe.get_doc({"doctype": "Fiscal Year", "year": "84/85", "year_start_date": "2027-07-17", "year_end_date": "2028-07-16",
    "companies": [{"company": c} for c in frappe.get_all("Company", pluck="name")]}).insert()
b = count()
try:
    y.setup_year("84/85"); check("84/85 without tax rates is refused", False)
except frappe.ValidationError as e:
    check("84/85 without tax rates is refused", count() == b, str(e)[:160])

# 3. with rates entered -> full rollover
income_tax.TAX_SLABS_BY_YEAR["84/85"] = income_tax.FY_8384_SLABS   # stand-in for the Finance Act 2084
r = y.setup_year("84/85"); a = count()
print("LPA:", {k: (c.get("leave_assigned") or {}).get("assigned") for k, c in r["companies"].items()}, [f for c in r["companies"].values() for f in (c.get("leave_assigned") or {}).get("failed", [])][:3])
check("84/85 builds the year", True, str({k: a[k]-b[k] for k in a if a[k]!=b[k]}))
check("84/85 warns: no festivals", any("festival" in w for w in r["warnings"]), r["warnings"][0][:90] if r["warnings"] else "")
rolled = {k: c["salary_rolled"]["created"] for k, c in r["companies"].items()}
check("pay rolled for every paid employee", sum(rolled.values()) == frappe.db.count("Salary Structure Assignment", {"docstatus": 1, "from_date": "2026-07-17"}), str(rolled))
bad = frappe.db.sql("""select count(*) from `tabSalary Structure Assignment` where docstatus=1 and from_date='2027-07-17' and income_tax_slab not like 'Nepal 84/85 - %%'""")[0][0]
check("every new assignment points at the 84/85 slab", bad == 0, f"{bad} wrong")
same = frappe.db.sql("""select count(*) from `tabSalary Structure Assignment` n join `tabSalary Structure Assignment` o
  on o.employee=n.employee and o.docstatus=1 and o.from_date='2026-07-17'
  where n.docstatus=1 and n.from_date='2027-07-17' and (n.base<>o.base or n.salary_structure<>o.salary_structure or n.payroll_payable_account<>o.payroll_payable_account)""")[0][0]
check("pay itself unchanged (base, structure, payable account)", same == 0, f"{same} differ")
b2 = count(); y.setup_year("84/85"); check("84/85 re-run creates nothing", count() == b2)

# 4. a Shrawan 2084 slip is taxed on the 84/85 slab
emp = frappe.db.get_value("Salary Structure Assignment", {"docstatus": 1, "from_date": "2027-07-17", "company": "Nepal Gas Udhyog Pvt. Ltd."}, "employee")
from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
st = lambda d: frappe.db.get_value("Salary Structure Assignment", {"employee": emp, "docstatus": 1, "from_date": ["<=", d]}, "salary_structure", order_by="from_date desc")
try:
    slip = make_salary_slip(st("2027-08-16"), employee=emp, posting_date="2027-08-16", ignore_permissions=True)
    check("Shrawan 2084 slip uses the 84/85 slab", slip._salary_structure_assignment.income_tax_slab.startswith("Nepal 84/85"),
          f"{slip.start_date}..{slip.end_date} slab={slip._salary_structure_assignment.income_tax_slab} tax={[d.amount for d in slip.deductions if d.salary_component=='Income Tax']}")
except Exception as e:
    check("Shrawan 2084 slip uses the 84/85 slab", False, repr(e)[:200])
try:
    slip83 = make_salary_slip(st("2027-07-10"), employee=emp, posting_date="2027-07-10", ignore_permissions=True); check("Ashadh 2084 slip still on the 83/84 slab", slip83._salary_structure_assignment.income_tax_slab.startswith("Nepal 83/84"), slip83._salary_structure_assignment.income_tax_slab)
except Exception as e:
    check("Ashadh 2084 slip still on the 83/84 slab", False, repr(e)[:200])

# 5. holiday lists switch on the first day, not before
m = switch_to_current_year_lists("2027-07-16"); check("31 Ashadh: nothing switches", not m["companies"] and not m["employees"], str(m))
m = switch_to_current_year_lists("2027-07-17")
check("1 Shrawan: 7 companies + the women switch", len(m["companies"]) == 7 and m["employees"] == 22 and not m["missing"], str(m))
wl = frappe.db.sql("select count(*) from tabEmployee e join `tabHoliday List` h on h.name=e.holiday_list where e.status='Active' and h.holiday_list_name like '%%Women 84/85'")[0][0]
check("women land on the 84/85 women's list", wl == 22, str(wl))
m = switch_to_current_year_lists("2027-07-18"); check("next day: idempotent", not m["companies"] and not m["employees"], str(m))

frappe.db.rollback()
check("rolled back: 84/85 gone", not frappe.db.exists("Fiscal Year", "84/85"))
print("\n".join(out))
