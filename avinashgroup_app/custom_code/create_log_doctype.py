import frappe

def create_doctype():
    doctype_name = "Dynamic Approval History"
    
    if not frappe.db.exists("DocType", doctype_name):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": doctype_name,
            "module": "Avinash Group App",
            "custom": 0,
            "istable": 1,
            "editable_grid": 1,
            "fields": [
                {
                    "fieldname": "action",
                    "fieldtype": "Data",
                    "label": "Action",
                    "in_list_view": 1,
                    "reqd": 0
                },
                {
                    "fieldname": "user",
                    "fieldtype": "Link",
                    "options": "User",
                    "label": "User",
                    "in_list_view": 1,
                    "reqd": 0
                },
                {
                    "fieldname": "user_name",
                    "fieldtype": "Data",
                    "label": "User Name",
                    "in_list_view": 1,
                    "fetch_from": "user.full_name",
                    "read_only": 0
                },
                {
                    "fieldname": "timestamp",
                    "fieldtype": "Datetime",
                    "label": "Date and Time",
                    "in_list_view": 1,
                    "reqd": 0
                }
            ],
            "permissions": [],
        })
        doc.insert(ignore_permissions=True)
        print(f"Created Doctype {doctype_name}")
    else:
        print(f"Doctype {doctype_name} already exists")

