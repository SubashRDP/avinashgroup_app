import frappe
from frappe.utils import today, add_days


def inspect():
    for company in frappe.db.sql("SELECT name FROM tabCompany", as_dict=True):
        items = frappe.db.sql("""
            SELECT COUNT(*) as cnt FROM `tabItem` i
            INNER JOIN `tabItem Default` id ON id.parent = i.name
            WHERE id.company = %s
        """, company.name, as_dict=True)
        print(f"{company.name}: {items[0].cnt} items")

    sups = frappe.db.sql("SELECT name, supplier_name FROM tabSupplier WHERE name LIKE 'NGI%' LIMIT 5", as_dict=True)
    print("NGI Suppliers:", [(s.name, s.supplier_name) for s in sups])

    items = frappe.db.sql("""
        SELECT DISTINCT i.name, i.item_name, i.stock_uom FROM `tabItem` i
        INNER JOIN `tabItem Default` id ON id.parent = i.name
        WHERE id.company = 'Nepal Gas Udhyog Pvt. Ltd.'
        LIMIT 10
    """, as_dict=True)
    print("NGI Items:", [(i.name, i.item_name, i.stock_uom) for i in items])


def run():
    company = "Nepal Gas Udhyog Pvt. Ltd."

    items = frappe.db.sql("""
        SELECT i.name, i.item_name, i.stock_uom FROM `tabItem` i
        WHERE EXISTS (
            SELECT 1 FROM `tabItem Default` id
            WHERE id.parent = i.name AND id.company = %s
        ) AND NOT EXISTS (
            SELECT 1 FROM `tabItem Default` id2
            WHERE id2.parent = i.name AND id2.company != %s
        )
        LIMIT 3
    """, (company, company), as_dict=True)

    if not items:
        print("No items found. Run inspect() first.")
        return

    suppliers = frappe.db.sql(
        "SELECT name FROM tabSupplier WHERE name LIKE 'NGI%' LIMIT 3", as_dict=True
    )
    if len(suppliers) < 3:
        print("Not enough NGI suppliers found.")
        return

    sup_ids = [s.name for s in suppliers]
    print("Using company:", company)
    print("Items:", [(i.name, i.item_name) for i in items])
    print("Suppliers:", sup_ids)

    price_list = "Standard Buying"
    currency = frappe.db.get_value("Company", company, "default_currency") or "NPR"
    base_prices = [75000, 145000, 28000]
    price_matrix = {
        sup_ids[0]: [round(p * 1.02) for p in base_prices],
        sup_ids[1]: [round(p * 0.97) for p in base_prices],
        sup_ids[2]: [round(p * 1.05) for p in base_prices],
    }

    # RFQ
    rfq = frappe.new_doc("Request for Quotation")
    rfq.company = company
    rfq.transaction_date = today()
    rfq.message_for_supplier = "Please provide your best quotation for the listed items."
    for item in items:
        rfq.append("items", {
            "item_code": item.name,
            "qty": 5,
            "uom": item.stock_uom,
            "stock_uom": item.stock_uom,
            "conversion_factor": 1,
            "schedule_date": add_days(today(), 30),
        })
    for sup in sup_ids:
        rfq.append("suppliers", {"supplier": sup})
    rfq.insert(ignore_permissions=True)
    rfq.submit()
    print(f"RFQ: {rfq.name}")

    # Supplier Quotations
    sq_names = []
    for sup_id in sup_ids:
        sq = frappe.new_doc("Supplier Quotation")
        sq.supplier = sup_id
        sq.company = company
        sq.transaction_date = today()
        sq.valid_till = add_days(today(), 60)
        sq.currency = currency
        sq.buying_price_list = price_list
        for i, item in enumerate(items):
            sq.append("items", {
                "item_code": item.name,
                "qty": 5,
                "rate": price_matrix[sup_id][i],
                "uom": item.stock_uom,
                "conversion_factor": 1,
                "request_for_quotation": rfq.name,
            })
        sq.insert(ignore_permissions=True)
        sq_names.append(sq.name)
        print(f"SQ: {sq.name} ({sup_id})")

    # Purchase Order from cheapest supplier (index 1)
    chosen_sup = sup_ids[1]
    chosen_sq_name = sq_names[1]
    chosen_sq = frappe.get_doc("Supplier Quotation", chosen_sq_name)

    po = frappe.new_doc("Purchase Order")
    po.supplier = chosen_sup
    po.company = company
    po.transaction_date = today()
    po.schedule_date = add_days(today(), 30)
    po.currency = currency
    po.buying_price_list = price_list
    po.custom_approver = "Administrator"
    for i, item in enumerate(items):
        po.append("items", {
            "item_code": item.name,
            "qty": 5,
            "rate": price_matrix[chosen_sup][i],
            "uom": item.stock_uom,
            "conversion_factor": 1,
            "schedule_date": add_days(today(), 30),
            "supplier_quotation": chosen_sq_name,
            "supplier_quotation_item": chosen_sq.items[i].name,
        })
    po.insert(ignore_permissions=True)
    po.submit()
    print(f"PO: {po.name}")

    frappe.db.commit()
    print(f"\nDone! Use PO '{po.name}' in the report.")
