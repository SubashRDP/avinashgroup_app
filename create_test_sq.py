import frappe
from frappe.utils import today

def run():
    company = "Grihalaxmi Metal Industries Pvt. Ltd"
    suppliers = [
        ("GLMI-SUP-00001", "A. M Plastic Udhyog"),
        ("GLMI-SUP-00002", "City Computer Systems"),
        ("GLMI-SUP-00003", "Furniture Land Store Pvt. Ltd."),
    ]
    items = [
        ("NGG-ITEM-00005", "Computer & Printer (Others)", 5),
        ("NGG-ITEM-00013", "Laptop", 3),
        ("NGG-ITEM-00015", "Printer", 2),
    ]
    price_matrix = {
        "GLMI-SUP-00001": [12000, 85000, 15000],
        "GLMI-SUP-00002": [11500, 90000, 13500],
        "GLMI-SUP-00003": [13000, 82000, 16000],
    }
    created = []
    for sup_id, sup_name in suppliers:
        sq = frappe.new_doc("Supplier Quotation")
        sq.supplier = sup_id
        sq.company = company
        sq.transaction_date = today()
        sq.valid_till = "2026-06-30"
        sq.currency = "NPR"
        sq.buying_price_list = "Standard Buying"
        prices = price_matrix[sup_id]
        for i, (item_code, item_name, qty) in enumerate(items):
            sq.append("items", {
                "item_code": item_code,
                "item_name": item_name,
                "qty": qty,
                "rate": prices[i],
                "uom": "Nos",
            })
        sq.insert(ignore_permissions=True)
        created.append(sq.name)
        print(f"Created: {sq.name} for {sup_name}")
    frappe.db.commit()
    print("Done:", created)
