import json, frappe
frappe.init(site="nepalgas", sites_path="/home/sijan/frappe-15/sites")
frappe.connect(); frappe.set_user("Administrator")
from erpnext.accounts.report.general_ledger.general_ledger import execute as erp_gl
import avinashgroup_app.avinash_group_app.report.general_ledger_posting_detail.general_ledger_posting_detail as M

TOL = 0.05   # ERPNext carries float drift from its currency conversion

def erp(f):
    cols, data = erp_gl(frappe._dict(f))
    op = cl = None
    for r in data:
        if not isinstance(r, dict): continue
        a = str(r.get("account") or "")
        if "Opening" in a and "Closing" not in a: op = (r.get("debit") or 0) - (r.get("credit") or 0)
        elif "Closing" in a:                      cl = (r.get("debit") or 0) - (r.get("credit") or 0)
    return op, cl

def mine(f):
    cols, data = M.execute(dict(f))
    op = cl = 0.0; seen = False
    for d in data:
        if d.get("_section"): seen = True; continue
        if not seen: continue
        n = d.get("party_name")
        if n == "Opening Balance": op += d.get("balance_value") or 0
        elif n == "Closing Balance": cl += d.get("balance_value") or 0
    return op, cl

companies = frappe.get_all("Company", pluck="name")
years = [(y.name, str(y.year_start_date), str(y.year_end_date))
         for y in frappe.get_all("Fiscal Year", fields=["name","year_start_date","year_end_date"],
                                 filters={"name": ["in", ["82/83","83/84"]]})]
results = []
for co in companies:
    # balance-sheet accounts only: P&L opening is floored at the FY start here
    # by design, which ERPNext's General Ledger does not do
    accts = frappe.db.sql_list("""SELECT DISTINCT g.account FROM `tabGL Entry` g
        JOIN tabAccount a ON a.name=g.account WHERE g.company=%s AND g.is_cancelled=0
          AND a.root_type IN ('Asset','Liability','Equity') LIMIT 4""", co)
    for fy, f0, f1 in years:
        for acct in accts:
            base = {"company": co, "from_date": f0, "to_date": f1, "account": [acct]}
            e_op, e_cl = erp(dict(base, group_by="Group by Voucher (Consolidated)"))
            m_op, m_cl = mine(dict(base, categorized_by="Account", remarks=0))
            if e_op is None: continue
            results.append({
                "company": co, "fy": fy, "account": acct, "filter": "account",
                "erp_open": e_op, "mine_open": m_op, "erp_close": e_cl, "mine_close": m_cl,
                "open_ok": abs(e_op - m_op) <= TOL, "close_ok": abs((e_cl or 0) - m_cl) <= TOL,
            })

json.dump(results, open("/tmp/claude-1000/-home-sijan-frappe-15-apps-avinashgroup-app/9012019e-5a00-4dcf-914b-a700bd0156ef/scratchpad/crosscheck.json","w"), indent=1)
bad=[r for r in results if not (r["open_ok"] and r["close_ok"])]
print(f"comparisons: {len(results)}   mismatched: {len(bad)}")
for r in bad[:6]:
    print(f"  {r['company'][:22]:24} {r['fy']} {r['account'][:34]:36}")
    print(f"      open  erp={r['erp_open']:,.2f} mine={r['mine_open']:,.2f} diff={r['mine_open']-r['erp_open']:,.2f}")
    print(f"      close erp={r['erp_close']:,.2f} mine={r['mine_close']:,.2f} diff={r['mine_close']-r['erp_close']:,.2f}")
frappe.destroy()
