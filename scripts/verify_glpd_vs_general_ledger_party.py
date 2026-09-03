import json, frappe
frappe.init(site="nepalgas", sites_path="/home/sijan/frappe-15/sites")
frappe.connect(); frappe.set_user("Administrator")
from erpnext.accounts.report.general_ledger.general_ledger import execute as erp_gl
import avinashgroup_app.avinash_group_app.report.general_ledger_posting_detail.general_ledger_posting_detail as M
TOL=0.05

def erp(f):
    cols,data=erp_gl(frappe._dict(f)); op=cl=None
    for r in data:
        if not isinstance(r,dict): continue
        a=str(r.get("account") or "")
        if "Opening" in a and "Closing" not in a: op=(r.get("debit") or 0)-(r.get("credit") or 0)
        elif "Closing" in a: cl=(r.get("debit") or 0)-(r.get("credit") or 0)
    return op,cl
def mine(f):
    cols,data=M.execute(dict(f)); op=cl=0.0; seen=False
    for d in data:
        if d.get("_section"): seen=True; continue
        if not seen: continue
        n=d.get("party_name")
        if n=="Opening Balance": op+=d.get("balance_value") or 0
        elif n=="Closing Balance": cl+=d.get("balance_value") or 0
    return op,cl

rows=[]
companies=frappe.get_all("Company", pluck="name")
years=[(y.name,str(y.year_start_date),str(y.year_end_date))
       for y in frappe.get_all("Fiscal Year",fields=["name","year_start_date","year_end_date"],
                               filters={"name":["in",["82/83","83/84"]]})]
for co in companies:
    for fy,f0,f1 in years:
        # --- party filter, on a receivable account ---
        pr=frappe.db.sql("""SELECT g.account, g.party, g.party_type FROM `tabGL Entry` g
            WHERE g.company=%s AND g.is_cancelled=0 AND IFNULL(g.party,'')!=''
              AND g.posting_date BETWEEN %s AND %s LIMIT 1""",(co,f0,f1),as_dict=True)
        if pr:
            p=pr[0]
            b={"company":co,"from_date":f0,"to_date":f1,"account":[p.account],
               "party_type":p.party_type,"party":[p.party]}
            e=erp(dict(b,group_by="Group by Voucher (Consolidated)"))
            m=mine({"company":co,"from_date":f0,"to_date":f1,"account":[p.account],
                    "party_type":[p.party_type],"party":[p.party],"categorized_by":"Account","remarks":0})
            if e[0] is not None:
                rows.append(dict(company=co,fy=fy,scope=f"party {p.party}",
                    erp_open=e[0],mine_open=m[0],erp_close=e[1],mine_close=m[1],
                    open_ok=abs(e[0]-m[0])<=TOL, close_ok=abs((e[1] or 0)-m[1])<=TOL))
        # --- P&L account: expected to differ, by design ---
        pl=frappe.db.sql_list("""SELECT DISTINCT g.account FROM `tabGL Entry` g
            JOIN tabAccount a ON a.name=g.account WHERE g.company=%s AND g.is_cancelled=0
              AND a.root_type IN ('Income','Expense') LIMIT 1""",co)
        if pl:
            b={"company":co,"from_date":f0,"to_date":f1,"account":[pl[0]]}
            e=erp(dict(b,group_by="Group by Voucher (Consolidated)"))
            m=mine(dict(b,categorized_by="Account",remarks=0))
            if e[0] is not None:
                rows.append(dict(company=co,fy=fy,scope=f"P&L {pl[0][:26]}",
                    erp_open=e[0],mine_open=m[0],erp_close=e[1],mine_close=m[1],
                    open_ok=abs(e[0]-m[0])<=TOL, close_ok=abs((e[1] or 0)-m[1])<=TOL, expected_diff=True))

json.dump(rows,open("/tmp/claude-1000/-home-sijan-frappe-15-apps-avinashgroup-app/9012019e-5a00-4dcf-914b-a700bd0156ef/scratchpad/crosscheck2.json","w"),indent=1)
party=[r for r in rows if r["scope"].startswith("party")]
pl=[r for r in rows if r["scope"].startswith("P&L")]
print(f"party-filtered comparisons: {len(party)}  mismatched: {len([r for r in party if not(r['open_ok'] and r['close_ok'])])}")
print(f"P&L comparisons:            {len(pl)}  differing: {len([r for r in pl if not(r['open_ok'] and r['close_ok'])])}  (differences here are by design)")
for r in [x for x in pl if not(x['open_ok'] and x['close_ok'])][:3]:
    print(f"   {r['company'][:20]:22} {r['fy']} {r['scope'][:30]:32} erp_open={r['erp_open']:,.2f} mine_open={r['mine_open']:,.2f}")
frappe.destroy()
