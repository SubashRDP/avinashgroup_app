import frappe


def execute():
    if not frappe.db.exists("DocType", "Fiscal Year Access Control"):
        return

    users = set()
    full_access_by_user = {}

    if frappe.db.has_column("User", "full_access"):
        for row in frappe.db.sql(
            """
            SELECT name, full_access
            FROM `tabUser`
            WHERE IFNULL(full_access, 0) = 1
            """,
            as_dict=True,
        ):
            users.add(row.name)
            full_access_by_user[row.name] = row.full_access

    legacy_rows = frappe.db.sql(
        """
        SELECT parent, doctype_name, fiscal_year, full_access
        FROM `tabUser Fiscal Year Access`
        WHERE parenttype = 'User'
            AND parentfield = 'user_fiscal_years'
        ORDER BY parent, idx
        """,
        as_dict=True,
    )

    rows_by_user = {}
    for row in legacy_rows:
        users.add(row.parent)
        rows_by_user.setdefault(row.parent, []).append(row)

    for user in users:
        access_name = frappe.db.get_value(
            "Fiscal Year Access Control",
            {"user": user},
            "name",
        )
        if access_name:
            doc = frappe.get_doc("Fiscal Year Access Control", access_name)
        else:
            doc = frappe.get_doc({
                "doctype": "Fiscal Year Access Control",
                "user": user,
            })

        if full_access_by_user.get(user):
            doc.full_access = 1

        existing = {
            (
                row.doctype_name,
                row.fiscal_year,
                int(row.full_access or 0),
            )
            for row in doc.get("access_details", [])
        }

        for row in rows_by_user.get(user, []):
            key = (
                row.doctype_name,
                row.fiscal_year,
                int(row.full_access or 0),
            )
            if key in existing:
                continue

            doc.append("access_details", {
                "doctype_name": row.doctype_name,
                "fiscal_year": row.fiscal_year,
                "full_access": row.full_access,
            })
            existing.add(key)

        if doc.is_new():
            doc.insert(ignore_permissions=True)
        else:
            doc.save(ignore_permissions=True)

        frappe.cache().delete_value(f"user_fiscal_access_{user}")

    _remove_legacy_user_custom_fields()
    frappe.clear_cache(doctype="User")
    frappe.clear_cache(doctype="Fiscal Year Access Control")


def _remove_legacy_user_custom_fields():
    for fieldname in ("user_fiscal_years", "full_access", "fiscal_year_section"):
        custom_field = f"User-{fieldname}"
        if frappe.db.exists("Custom Field", custom_field):
            frappe.delete_doc(
                "Custom Field",
                custom_field,
                ignore_permissions=True,
                force=True,
            )
