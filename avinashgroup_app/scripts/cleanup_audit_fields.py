"""
Remove the custom_naming_series + custom_company fields (and the related property
setters) that AuditFieldsManager added to a doctype, after it's been commented out
of NAMING_CONFIG / AuditBase.doctypes / master_doctypes. Restores the original
autoname; never renames existing records. Pass remove_audit=True to also drop the
audit fields. Run per-site (it's DB state, not code):

  bench --site <site> execute avinashgroup_app.scripts.cleanup_audit_fields.run
"""

import frappe

# ─────────────────────────────────────────────────────────────────────────────
# ADD THE DOCTYPE(S) YOU WANT TO CLEAN UP HERE (one name per line, in quotes):
DOCTYPES_TO_CLEAN = [
    "Leave Type",
]
# ─────────────────────────────────────────────────────────────────────────────

NAMING_FIELDS = ("custom_naming_series", "custom_company")
AUDIT_FIELDS = ("audit_section", "custom_created_by", "custom_created_on", "custom_modified_by")


def run(doctypes=None, remove_audit=False):
    # Use the list above by default; --kwargs '{"doctypes": [...]}' overrides it.
    doctypes = _as_list(doctypes) or list(DOCTYPES_TO_CLEAN)
    if not doctypes:
        raise SystemExit("Add a doctype to DOCTYPES_TO_CLEAN at the top of this file, or pass --kwargs.")
    for dt in doctypes:
        if not frappe.db.exists("DocType", dt):
            print(f"!! skip {dt!r}: DocType does not exist")
            continue
        print(f"\n=== {dt} ===")
        _cleanup(dt, remove_audit=remove_audit)
    frappe.db.commit()
    print("\ndone — committed")


def _cleanup(dt, remove_audit=False):
    fields_to_drop = list(NAMING_FIELDS) + (list(AUDIT_FIELDS) if remove_audit else [])

    # 1) delete the custom fields
    for fieldname in fields_to_drop:
        cf = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname})
        if cf:
            frappe.delete_doc("Custom Field", cf)
            print(f"  deleted Custom Field {fieldname}")
        else:
            print(f"  Custom Field {fieldname} not found")

    # 2) delete the naming property setters
    for ps in (f"{dt}-custom_naming_series-unique", f"{dt}-main-autoname"):
        if frappe.db.exists("Property Setter", ps):
            frappe.delete_doc("Property Setter", ps)
            print(f"  deleted Property Setter {ps}")

    # 3) scrub the removed fieldnames out of list-style property setters
    _scrub_list_property(f"{dt}-main-field_order", drop=fields_to_drop)
    _scrub_list_property(f"{dt}-main-search_fields", drop=fields_to_drop)

    # 4) restore the original autoname from the app's JSON (handles any doctype).
    #    force=True bypasses the modified-timestamp check -- the DB autoname was edited
    #    directly, so the JSON file looks "unchanged" and a plain reload would skip it.
    before = frappe.db.get_value("DocType", dt, "autoname")
    frappe.reload_doctype(dt, force=True)
    after = frappe.db.get_value("DocType", dt, "autoname")
    print(f"  autoname: {before!r} -> {after!r}")

    frappe.clear_cache(doctype=dt)


def _scrub_list_property(ps_name, drop):
    """Remove `drop` fieldnames from a comma-list or JSON-list Property Setter value."""
    if not frappe.db.exists("Property Setter", ps_name):
        return
    doc = frappe.get_doc("Property Setter", ps_name)
    raw = doc.value or ""
    is_json = raw.strip().startswith("[")
    items = frappe.parse_json(raw) if is_json else [x.strip() for x in raw.split(",") if x.strip()]
    kept = [x for x in items if x not in drop]
    if kept == items:
        return
    doc.value = frappe.as_json(kept) if is_json else ",".join(kept)
    doc.save()
    print(f"  scrubbed {tuple(set(items) - set(kept))} from {ps_name}")


def _as_list(value):
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    return list(value)
