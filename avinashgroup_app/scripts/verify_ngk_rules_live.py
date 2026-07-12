"""Live verification: with the seeded NGK rules ENABLED, insert one real
document per transaction doctype and print what the engine assigned.
Everything created is deleted and the moved series keys are restored.

Run:
    bench --site avinas1 execute \
        avinashgroup_app.scripts.verify_ngk_rules_live.run
"""

import frappe

COMPANY = "Nepal Gas Udhyog (Karnali) Pvt. Ltd."


def _series_snapshot():
    return dict(frappe.db.sql(
        "SELECT `name`, `current` FROM `tabSeries` "
        "WHERE `name` LIKE %s OR `name` LIKE %s",
        ("docno:%", "NGK-%"),
    ))


def _series_restore(snap):
    for name, cur in frappe.db.sql(
        "SELECT `name`, `current` FROM `tabSeries` "
        "WHERE `name` LIKE %s OR `name` LIKE %s",
        ("docno:%", "NGK-%"),
    ):
        old = snap.get(name)
        if old is None:
            frappe.db.sql("DELETE FROM `tabSeries` WHERE `name`=%s", name)
        elif old != cur:
            frappe.db.sql("UPDATE `tabSeries` SET `current`=%s WHERE `name`=%s",
                          (old, name))
    frappe.db.commit()


def run():
    today = frappe.utils.today()
    company = frappe.get_doc("Company", COMPANY)
    customer = frappe.db.get_value(
        "Customer", {"disabled": 0, "custom_company": COMPANY}, "name")
    supplier = frappe.db.get_value(
        "Supplier", {"disabled": 0, "custom_company": COMPANY}, "name")
    svc_item = frappe.db.get_value(
        "Item", {"disabled": 0, "is_stock_item": 0, "has_variants": 0,
                 "custom_company": COMPANY}, "name")
    stock_item = frappe.db.get_value(
        "Item", {"disabled": 0, "is_stock_item": 1, "has_variants": 0,
                 "has_batch_no": 0, "has_serial_no": 0,
                 "custom_company": COMPANY}, "name")
    warehouse = frappe.db.get_value(
        "Warehouse", {"company": COMPANY, "is_group": 0, "disabled": 0}, "name")
    accounts = frappe.get_all(
        "Account", filters={"company": COMPANY, "is_group": 0, "disabled": 0},
        pluck="name", limit=2)
    bank = frappe.db.get_value(
        "Account", {"company": COMPANY, "account_type": "Bank",
                    "is_group": 0, "disabled": 0}, "name")

    snap = _series_snapshot()
    made = []
    try:
        je = frappe.new_doc("Journal Entry")
        je.update({"company": COMPANY, "posting_date": today,
                   "voucher_type": "Journal Entry", "custom_p_type": "Bank Entry"})
        je.append("accounts", {"account": accounts[0],
                               "debit_in_account_currency": 100, "debit": 100})
        je.append("accounts", {"account": accounts[1],
                               "credit_in_account_currency": 100, "credit": 100})
        je.insert(ignore_permissions=True)
        made.append(je)

        pe = frappe.new_doc("Payment Entry")
        pe.update({"company": COMPANY, "posting_date": today,
                   "payment_type": "Receive", "custom_p_type": "NOC Payment",
                   "party_type": "Customer", "party": customer,
                   "paid_from": company.default_receivable_account,
                   "paid_to": bank, "paid_amount": 100, "received_amount": 100,
                   "source_exchange_rate": 1, "target_exchange_rate": 1,
                   "reference_no": "NGK-RULE-VERIFY", "reference_date": today})
        pe.insert(ignore_permissions=True)
        made.append(pe)

        pi = frappe.new_doc("Purchase Invoice")
        pi.update({"company": COMPANY, "posting_date": today,
                   "custom_purchase_type": "Purchase Other Service/Goods",
                   "supplier": supplier, "due_date": today,
                   "credit_to": company.default_payable_account})
        pi.append("items", {"item_code": svc_item, "qty": 1, "rate": 100,
                            "expense_account": company.default_expense_account,
                            "cost_center": company.cost_center})
        pi.custom_document_no = 424244
        pi.custom_document_no_manual = 1
        pi.insert(ignore_permissions=True)
        made.append(pi)

        pr = frappe.new_doc("Purchase Receipt")
        pr.update({"company": COMPANY, "posting_date": today,
                   "custom_receipt_type": "Other Purchase Receipt",
                   "supplier": supplier})
        pr.append("items", {"item_code": stock_item, "qty": 1, "rate": 100,
                            "warehouse": warehouse,
                            "cost_center": company.cost_center})
        pr.insert(ignore_permissions=True)
        made.append(pr)

        for d in made:
            d.reload()
            print(f"{d.doctype:18} id={d.name:28} "
                  f"docno={d.get('custom_document_no')!s:8} "
                  f"voucher={d.get('custom_name')}")
    finally:
        for d in reversed(made):
            if frappe.db.exists(d.doctype, d.name):
                frappe.delete_doc(d.doctype, d.name, force=1,
                                  ignore_permissions=True)
        frappe.db.commit()
        _series_restore(snap)
        print("cleaned up: docs deleted, series restored")
