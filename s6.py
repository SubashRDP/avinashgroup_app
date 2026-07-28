import os, time, frappe
SP = os.path.join(os.path.expanduser("~/frappe-bench"), "sites")
os.chdir(SP)
frappe.init(site="ng-group.raindropinc.com", sites_path=SP); frappe.connect()
T = "tabSales Invoice"
def q(sql, vals=None):
    return frappe.db.sql(sql, vals or (), as_dict=True)

print("=== Numbering Configuration rules for Sales Invoice ===")
rules = q("""select name, enabled, company, branch, target_field, document_no_field,
                    separator, legacy_upto, legacy_source_field, date_field
             from `tabNumbering Configuration`
             where document_type='Sales Invoice' order by enabled desc, name""")
targets = set()
for r in rules:
    print("  %-38s enabled=%s target=%-24s docno_field=%-20s company=%s branch=%s legacy_upto=%s" % (
        r["name"], r["enabled"], r["target_field"], r["document_no_field"], r["company"], r["branch"], r["legacy_upto"]))
    if r["enabled"]:
        targets.add(r["target_field"] or "custom_branch_name")
        if r["document_no_field"]:
            targets.add(r["document_no_field"])
if not rules:
    print("  (none) -> engine falls back to custom_branch_name")
    targets.add("custom_branch_name")
print("")
print("  COLUMNS THE NUMBERING WRITES INTO:", sorted(targets))
print("")

cols = [c["Field"] for c in q("show columns from `%s`" % T)]
idx = {}
for r in q("show index from `%s`" % T):
    idx.setdefault(r["Column_name"], []).append(r["Key_name"])
print("=== index status of those columns ===")
for c in sorted(targets):
    print("  %-26s exists=%-5s indexes=%s" % (c, c in cols, idx.get(c) or "*** NONE ***"))
print("")
print("=== all custom_* indexes present on %s ===" % T)
for col, keys in sorted(idx.items()):
    if col.startswith("custom_"):
        print("  %-26s %s" % (col, keys))
print("")
print("rows:", q("select count(*) c from `%s`" % T)[0]["c"])
print("")
print("=== timing the real per-row uniqueness query on each target column ===")
for c in sorted(targets):
    if c not in cols:
        continue
    v = (q("select `%s` v from `%s` where `%s` is not null and `%s` != '' order by creation desc limit 1" % (c, T, c, c)) or [{"v": "XX"}])[0]["v"]
    sql = "select `name` from `%s` where `%s` = %%s and `docstatus` < 2 and `name` != %%s limit 1" % (T, c)
    t = time.time()
    for _ in range(3):
        q(sql, (v, "zzz"))
    ms = round((time.time() - t) * 1000 / 3, 1)
    print("  %-26s sample=%-26s %s ms/call  -> x4 per invoice = %s ms/row" % (c, str(v)[:26], ms, round(ms * 4, 1)))
    for r in q("explain " + sql, (v, "zzz")):
        print("       EXPLAIN type=%s key=%s rows=%s extra=%s" % (r.get("type"), r.get("key"), r.get("rows"), r.get("Extra")))
print("")
print("=== NAME series: counter vs data (duplicate-name bug) ===")
for s in q("select name, `current` from `tabSeries` where name like 'NG%%' order by name limit 40"):
    p = s["name"]
    d = q("select max(cast(substring(`name`, %s) as unsigned)) m, count(*) c from `" + T + "` where `name` like %s", (len(p) + 1, p + "%"))
    dm, cc = (d[0]["m"], d[0]["c"]) if d else (None, 0)
    f = ""
    if dm is not None and int(s["current"]) < int(dm):
        f = "   <<< COUNTER BEHIND DATA by %s" % (int(dm) - int(s["current"]))
    print("  %-30s current=%-8s data_max=%-8s rows=%-7s%s" % (p, s["current"], dm, cc, f))
frappe.destroy()
