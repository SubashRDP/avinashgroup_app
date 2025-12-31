import frappe
from frappe.utils import getdate, nowdate
from erpnext.accounts.utils import get_balance_on

def validate_sales_invoice(doc, method):
    # Get customer limits
    custom_bill_count = frappe.db.get_value(
        "Customer", doc.customer, "custom_bill_count"
    ) or 0

    custom_days_limit = frappe.db.get_value(
        "Customer", doc.customer, "custom_days_limit"
    ) or 0

    custom_amount_limit = frappe.db.get_value(
        "Customer", doc.customer, "custom_amount_limit"
    ) or 0

    today = getdate(nowdate())

    # --------------------------------
    # Fetch submitted unpaid invoices
    # --------------------------------
    unpaid_invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "customer": doc.customer,
            "docstatus": 1,
            "outstanding_amount": [">", 0]
        },
        fields=["name", "posting_date"]
    )

    # -------------------------------
    # 1. Bill count check
    # -------------------------------
    unpaid_count = len(unpaid_invoices)

    if custom_bill_count and unpaid_count > custom_bill_count:
        frappe.throw(
            f"Cannot create Sales Invoice.<br>"
            f"Customer <b>{doc.customer}</b> has <b>{unpaid_count}</b> unpaid invoices, "
            f"which exceeds the allowed bill count limit of <b>{custom_bill_count}</b>."
        )

    # -------------------------------
    # 2. Days limit check
    # -------------------------------
    for inv in unpaid_invoices:
        invoice_date = getdate(inv.posting_date)
        days_passed = (today - invoice_date).days

        if custom_days_limit and days_passed > custom_days_limit:
            frappe.throw(
                f"Cannot create Sales Invoice.<br>"
                f"Invoice <b>{inv.name}</b> is unpaid for <b>{days_passed}</b> days, "
                f"which exceeds the allowed limit of <b>{custom_days_limit}</b> days."
            )

    # -------------------------------
    # 3. Amount limit check (FINAL)
    # -------------------------------
    if custom_amount_limit:
        # Customer closing balance from ledger
        closing_balance = get_balance_on(
            party_type="Customer",
            party=doc.customer,
            date=today
        ) or 0

        # New invoice amount
        new_invoice_amount = doc.grand_total or 0

        final_amount = closing_balance + new_invoice_amount

        if final_amount > custom_amount_limit:
            frappe.throw(
                f"Cannot create Sales Invoice.<br>"
                f"Customer balance after this invoice will be <b>{final_amount}</b>, "
                f"which exceeds the allowed amount limit of <b>{custom_amount_limit}</b>."
            )

