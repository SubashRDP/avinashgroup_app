"""
Patch: Seed Company Filter Config from hardcoded FILTER_CONFIG dict.
Run once after bench migrate to populate the DB-driven config DocType.
"""
import frappe
from avinashgroup_app.custom_code.globalfilter.globalfilter import FILTER_CONFIG


def execute():
    dyn_flag_field = "is_dynamic_link"

    for doctype_name, config in FILTER_CONFIG.items():
        if frappe.db.exists("Company Filter Config", doctype_name):
            continue  # already seeded — skip

        rows = []

        # top-level Link fields
        for fieldname in config.get("fields", []):
            rows.append({
                "fieldname": fieldname,
                "is_child_table": 0,
                "child_fieldname": "",
                dyn_flag_field: 0,
                "dynamic_link_field": ""
            })

        # child table fields — one row per (table, child_field) pair
        for table_fieldname, child_fields in config.get("child_tables", {}).items():
            for child_fieldname in child_fields:
                rows.append({
                    "fieldname": table_fieldname,
                    "is_child_table": 1,
                    "child_fieldname": child_fieldname,
                    dyn_flag_field: 0,
                    "dynamic_link_field": ""
                })

        doc = frappe.get_doc({
            "doctype": "Company Filter Config",
            "doctype_name": doctype_name,
            "company_field": config.get("company_field", "company"),
            "fields": rows
        })
        doc.insert(ignore_permissions=True)

    frappe.db.commit()
    print(f"[seed_company_filter_config] Seeded {len(FILTER_CONFIG)} records.")
