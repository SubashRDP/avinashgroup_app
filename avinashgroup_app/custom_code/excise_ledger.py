import json
from erpnext.controllers.accounts_controller import AccountsController
import frappe
from frappe import _
from frappe.utils import flt, cint
from erpnext.accounts.utils import get_account_currency
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.accounts.general_ledger import make_gl_entries



def process_taxes_and_excise(doc, method):
    """
    Calculate custom tax details, excise values, and VAT for Sales Invoice items.
    Updates taxable/non-taxable amounts and appends VAT tax rows.
    Includes excise value in custom_tax_amount and taxable_amount when excise_value > 0.
    """
    taxable_amount = 0
    non_taxable_amount = 0
    total_excise_value = 0
    vat_account = "VAT - GLMI"
    
    # Clear existing VAT rows
    doc.taxes = [t for t in doc.taxes if vat_account not in (t.account_head or "")]
    frappe.logger().info(f"Cleared existing VAT rows for account: {vat_account}")

    # Fetch tax templates and rates in bulk
    item_codes = [item.item_code for item in doc.items if item.item_code]
    item_taxes = frappe.db.get_all(
        "Item Tax",
        filters={"parent": ["in", item_codes]},
        fields=["parent", "item_tax_template"]
    )
    item_tax_map = {item["parent"]: item["item_tax_template"] for item in item_taxes}

    tax_templates = list(set(item_tax_map.values()))
    tax_details = frappe.db.get_all(
        "Item Tax Template Detail",
        filters={"parent": ["in", tax_templates]},
        fields=["parent", "tax_rate", "tax_type"]
    )
    tax_rate_map = {detail["parent"]: {"rate": detail["tax_rate"], "type": detail["tax_type"]} for detail in tax_details}

    for item in doc.items:
        # Initialize item fields
        item.custom_tax_rate = 0
        item.custom_tax_amount = 0
        item.excise_value = flt(item.stock_qty or 0) * flt(item.excise_duty or 0)
        total_excise_value += item.excise_value
        frappe.logger().info(f"Item {item.item_code}: excise_duty={item.excise_duty}, stock_qty={item.stock_qty}, excise_value={item.excise_value}")

        # Validate required fields
        if not item.amount or not item.stock_qty:
            frappe.throw(_("Amount and stock quantity are required for item {0}").format(item.item_code))

        # Fetch tax template for item
        tax_template = item_tax_map.get(item.item_code)
        if not tax_template:
            non_taxable_amount += flt(item.amount)
            continue

        # Fetch tax rate and type
        tax_info = tax_rate_map.get(tax_template, {"rate": 0, "type": ""})
        item.custom_tax_rate = flt(tax_info["rate"])
        item.item_tax_rate = json.dumps({tax_info["type"]: item.custom_tax_rate})

        # Calculate custom_tax_amount including excise_value if applicable
        taxable_base = flt(item.amount) + (item.excise_value if item.excise_value > 0 else 0)
        item.custom_tax_amount = flt(taxable_base * (item.custom_tax_rate / 100))
        
        # Update taxable/non-taxable amounts
        if item.custom_tax_rate > 0:
            taxable_amount += taxable_base
        else:
            non_taxable_amount += flt(item.amount)

        # # Append VAT tax row
        # if item.custom_tax_rate > 0:
        #     cost_center = item.cost_center or doc.get("cost_center") or frappe.get_value("Company", doc.company, "default_cost_center")
        #     if not cost_center:
        #         frappe.throw(_("Cost Center is required for item {0}").format(item.item_code))
        #     doc.append("taxes", {
        #         "charge_type": "On Net Total",
        #         "account_head": vat_account,
        #         "description": f"VAT {item.custom_tax_rate}% on {item.item_code}",
        #         "rate": item.custom_tax_rate,
        #         "tax_amount": item.custom_tax_amount,
        #         "cost_center": cost_center,
        #         "add_deduct_tax": "Add"
        #     })
        #     frappe.logger().info(
        #         f"Item {item.item_code}: Taxable amount={taxable_base}, "
        #         f"VAT amount={item.custom_tax_amount}"
        #     )

    # Update document fields
    doc.custom_taxable_amount = flt(taxable_amount)
    doc.custom_nontaxable_amount = flt(non_taxable_amount)
    doc.total_excise_value = flt(total_excise_value)
    doc.custom_vat = flt(sum(t.tax_amount for t in doc.taxes if t.account_head == vat_account))
    frappe.logger().info(f"Set total_excise_value={doc.total_excise_value} for invoice {doc.name}")

    # Recalculate totals
    doc.calculate_taxes_and_totals()
    frappe.logger().info(
        f"Document totals: Net Total={doc.net_total}, "
        f"Excise={doc.total_excise_value}, VAT={doc.custom_vat}, "
        f"Grand Total={doc.grand_total}"
    )


# def before_submit(doc, method):
#     """
#     Generate or reverse GL entries for excise value and total (excluding excise) in Sales Invoice or Sales Return.
#     For Sales Invoice:
#         - Debit: Sales Account (for excise value - reduces revenue)
#         - Credit: Excise Duty Account (for excise value - creates liability)
#         - Additional entries for total excluding excise
#     For Sales Return:
#         - Debit: Excise Duty Account (removes liability)
#         - Credit: Sales Account (restores revenue)
#         - Reverse entries for total excluding excise
#     """
#     frappe.msgprint(f"before_submit method triggered for {doc.doctype} {doc.name}", title="Debug")

#     total_excise_value = flt(doc.custom_excise)
#     total_excluding_excise = flt(doc.custom_total_excluding_excise)
#     vat = flt(doc.custom_vat)
    
#     if total_excise_value == 0 and total_excluding_excise == 0:
#         frappe.logger().info(f"Skipping GL entries for {doc.name} as both excise and total are 0")
#         frappe.msgprint(f"Skipping GL entries for {doc.name} as both excise and total are 0", title="Debug")
#         return

#     excise_account = "347714 - Excise Duty - GLMI"
#     sales_account = doc.get("items")[0].income_account   # assuming same sales account

#     for account in [excise_account, sales_account]:
#         if not frappe.db.exists("Account", account):
#             frappe.throw(_("Account {0} does not exist").format(account))
    
#     cost_center = (
#         doc.get("cost_center")
#         or doc.get("items")[0].get("cost_center")
#         or frappe.db.get_value("Company", doc.company, "cost_center")
#     )

#     if not cost_center:
#         frappe.throw("Cost Center is required but not set on the document or company.")

#     gl_entries = []
#     is_return = doc.is_return

#     if not is_return:
#         # Sales Invoice: 
#         # 1. Debit Sales (reduce revenue by excise), Credit Excise (liability)
#         if total_excise_value > 0:
#             gl_entries.append(
#                 doc.get_gl_dict({
#                     "account": sales_account,
#                     "debit": abs(total_excise_value),
#                     "credit": 0,
#                     "debit_in_account_currency": abs(total_excise_value),
#                     "credit_in_account_currency": 0,
#                     "posting_date": doc.posting_date,
#                     "company": doc.company,
#                     "voucher_type": doc.doctype,
#                     "voucher_no": doc.name,
#                     "cost_center": cost_center,
#                     "against": doc.customer,
#                     "remarks": "Excise Duty adjustment"
#                 }, get_account_currency(sales_account))
#             )

#             gl_entries.append(
#                 doc.get_gl_dict({
#                     "account": excise_account,
#                     "credit": abs(total_excise_value),
#                     "debit": 0,
#                     "credit_in_account_currency": abs(total_excise_value),
#                     "debit_in_account_currency": 0,
#                     "posting_date": doc.posting_date,
#                     "company": doc.company,
#                     "voucher_type": doc.doctype,
#                     "voucher_no": doc.name,
#                     "cost_center": cost_center,
#                     "against": doc.customer,
#                     "remarks": "Excise Duty liability"
#                 }, get_account_currency(excise_account))
#             )
        
#         # 2. Entry for total excluding excise (if needed for your accounting logic)
#         if total_excluding_excise > 0:
#             # Add your GL entries for total_excluding_excise here
#             # Example: You might want to record this separately or adjust other accounts
#             frappe.logger().info(f"Total excluding excise: {total_excluding_excise}")
#             # Uncomment and modify as per your requirement:
#             # gl_entries.append(
#             #     doc.get_gl_dict({
#             #         "account": "YOUR_ACCOUNT_HERE",
#             #         "debit": abs(total_excluding_excise),
#             #         "credit": 0,
#             #         ...
#             #     }, get_account_currency("YOUR_ACCOUNT_HERE"))
#             # )
#     else:
#         # Sales Return: 
#         # 1. Debit Excise (remove liability), Credit Sales (restore revenue)
#         if total_excise_value > 0:
#             gl_entries.append(
#                 doc.get_gl_dict({
#                     "account": excise_account,
#                     "debit": abs(total_excise_value),
#                     "credit": 0,
#                     "debit_in_account_currency": abs(total_excise_value),
#                     "credit_in_account_currency": 0,
#                     "posting_date": doc.posting_date,
#                     "company": doc.company,
#                     "voucher_type": doc.doctype,
#                     "voucher_no": doc.name,
#                     "cost_center": cost_center,
#                     "against": doc.customer,
#                     "remarks": "Excise Duty reversal"
#                 }, get_account_currency(excise_account))
#             )

#             gl_entries.append(
#                 doc.get_gl_dict({
#                     "account": sales_account,
#                     "credit": abs(total_excise_value),
#                     "debit": 0,
#                     "credit_in_account_currency": abs(total_excise_value),
#                     "debit_in_account_currency": 0,
#                     "posting_date": doc.posting_date,
#                     "company": doc.company,
#                     "voucher_type": doc.doctype,
#                     "voucher_no": doc.name,
#                     "cost_center": cost_center,
#                     "against": doc.customer,
#                     "remarks": "Excise Duty reversal adjustment"
#                 }, get_account_currency(sales_account))
#             )
        
#         # 2. Reverse entry for total excluding excise (if needed)
#         if total_excluding_excise > 0:
#             frappe.logger().info(f"Reversing total excluding excise: {total_excluding_excise}")
#             # Add reverse GL entries for total_excluding_excise here
 
#     for gle in gl_entries:
#         frappe.msgprint(f"GL Entry - Account: {gle.account}, Debit: {gle.debit}, Credit: {gle.credit}", title="Debug")

#     if gl_entries:
#         try:
#             make_gl_entries(gl_entries, cancel=False)
#             frappe.msgprint(f"Successfully created GL entries for {doc.doctype} {doc.name}", title="Debug")
#         except Exception:
#             frappe.log_error(frappe.get_traceback(), f"Error creating GL entries for {doc.doctype} {doc.name}")
#             frappe.msgprint(f"Error creating GL entries for {doc.doctype} {doc.name}. Check error log.", title="Debug")
#             raise
# # def before_submit(doc, method):
# #     """
# #     Generate or reverse GL entries for excise value in Sales Invoice or Sales Return.
# #     For Sales Invoice:
# #         - Credit: Excise Duty - EFPL
# #         - Credit: Sales - EFPL
# #     For Sales Return:
# #         - Debit: Excise Duty - EFPL
# #         - Debit: Sales - EFPL
# #     """
# #     frappe.msgprint(f"before_submit method triggered for {doc.doctype} {doc.name}", title="Debug")

# #     total_excise_value = flt(doc.custom_excise)
# #     total = flt(doc.custom_total_excluding_excise)
# #     vat= flt(doc.custom_vat)
# #     if total_excise_value == 0:
# #         frappe.logger().info(f"Skipping GL entries for {doc.name} as total_excise_value is 0")
# #         frappe.msgprint(f"Skipping GL entries for {doc.name} as total_excise_value is 0", title="Debug")
# #         return

# #     excise_account = "347714 - Excise Duty - GLMI"
# #     sales_account = doc.get("items")[0].income_account   # assuming same sales account

# #     for account in [excise_account, sales_account]:
# #         if not frappe.db.exists("Account", account):
# #             frappe.throw(_("Account {0} does not exist").format(account))
    
# #     cost_center = (
# #     doc.get("cost_center")
# #         or doc.get("items")[0].get("cost_center")
# #         or frappe.db.get_value("Company", doc.company, "cost_center")
# #     )

# #     if not cost_center:
# #         frappe.throw("Cost Center is required but not set on the document or company.")


# #     gl_entries = []
# #     is_return = doc.is_return

# #     if not is_return:
# #     # Sales Invoice: Debit Sales (reduce revenue), Credit Excise (liability)
# #         gl_entries.append(
# #             doc.get_gl_dict({
# #                 "account": sales_account,
# #                 "debit": abs(total_excise_value),
# #                 "credit": 0,
# #                 "debit_in_account_currency": abs(total_excise_value),
# #                 "credit_in_account_currency": 0,
# #                 "posting_date": doc.posting_date,
# #                 "company": doc.company,
# #                 "voucher_type": doc.doctype,
# #                 "voucher_no": doc.name,
# #                 "cost_center": cost_center,
# #                 "against": doc.customer
# #             }, get_account_currency(sales_account))
# #         )

# #         gl_entries.append(
# #             doc.get_gl_dict({
# #                 "account": excise_account,
# #                 "credit": abs(total_excise_value),
# #                 "debit": 0,
# #                 "credit_in_account_currency": abs(total_excise_value),
# #                 "debit_in_account_currency": 0,
# #                 "posting_date": doc.posting_date,
# #                 "company": doc.company,
# #                 "voucher_type": doc.doctype,
# #                 "voucher_no": doc.name,
# #                 "cost_center": cost_center,
# #                 "against": doc.customer
# #             }, get_account_currency(excise_account))
# #         )
# #     else:
# #     # Sales Return: Debit Excise (remove liability), Credit Sales (restore revenue)
# #         gl_entries.append(
# #             doc.get_gl_dict({
# #                 "account": excise_account,
# #                 "debit": abs(total_excise_value),
# #                 "credit": 0,
# #                 "debit_in_account_currency": abs(total_excise_value),
# #                 "credit_in_account_currency": 0,
# #                 "posting_date": doc.posting_date,
# #                 "company": doc.company,
# #                 "voucher_type": doc.doctype,
# #                 "voucher_no": doc.name,
# #                 "cost_center": doc.get("cost_center"),
# #                 "against": doc.customer
# #             }, get_account_currency(excise_account))
# #         )

# #         gl_entries.append(
# #             doc.get_gl_dict({
# #                 "account": sales_account,
# #                 "credit": abs(total_excise_value),
# #                 "debit": 0,
# #                 "credit_in_account_currency": abs(total_excise_value),
# #                 "debit_in_account_currency": 0,
# #                 "posting_date": doc.posting_date,
# #                 "company": doc.company,
# #                 "voucher_type": doc.doctype,
# #                 "voucher_no": doc.name,
# #                 "cost_center": doc.get("cost_center"),
# #                 "against": doc.customer
# #             }, get_account_currency(sales_account))
# #         )
 
# #     for gle in gl_entries:
# #         frappe.msgprint(f"GL Entry - Account: {gle.account}, Debit: {gle.debit}, Credit: {gle.credit}", title="Debug")

# #     if gl_entries:
# #         try:
# #             make_gl_entries(gl_entries, cancel=False)
# #             frappe.msgprint(f"Successfully created GL entries for {doc.doctype} {doc.name}", title="Debug")
# #         except Exception:
# #             frappe.log_error(frappe.get_traceback(), f"Error creating GL entries for {doc.doctype} {doc.name}")
# #             frappe.msgprint(f"Error creating GL entries for {doc.doctype} {doc.name}. Check error log.", title="Debug")
# #             raise


def before_submit(doc, method):
    """
    Generate or reverse GL entries for excise value and VAT in Sales Invoice or Sales Return.
    This function only creates adjustment entries for excise and VAT.
    The main sales GL entries (Debtors/Sales) are handled by ERPNext's standard process.
    
    For Sales Invoice:
        - Debit: Sales Account (for excise value - reduces revenue)
        - Credit: Excise Duty Account (for excise value - creates liability)
        - Debit: Sales Account (for VAT - reduces revenue)
        - Credit: VAT Account (for VAT - creates liability)
    
    For Sales Return:
        - Debit: Excise Duty Account (removes liability)
        - Credit: Sales Account (restores revenue)
        - Debit: VAT Account (removes liability)
        - Credit: Sales Account (restores revenue)
    """
    frappe.msgprint(f"before_submit method triggered for {doc.doctype} {doc.name}", title="Debug")

    total_excise_value = flt(doc.custom_excise)
    vat_value = flt(doc.custom_vat)
    total_excluding_excise = flt(doc.custom_total_excluding_excise)
    
    # Log the values for reference
    frappe.logger().info(f"Invoice {doc.name} - Total excl. excise: {total_excluding_excise}, Excise: {total_excise_value}, VAT: {vat_value}")
    
    if total_excise_value == 0 and vat_value == 0:
        frappe.logger().info(f"Skipping GL entries for {doc.name} as both excise and VAT are 0")
        frappe.msgprint(f"Skipping GL entries for {doc.name} as both excise and VAT are 0", title="Debug")
        return

    excise_account = "347714 - Excise Duty - GLMI"
    vat_account = "VAT - GLMI"
    sales_account = doc.get("items")[0].income_account   # assuming same sales account

    # Verify all accounts exist
    for account in [excise_account, sales_account, vat_account]:
        if not frappe.db.exists("Account", account):
            frappe.throw(_("Account {0} does not exist").format(account))
    
    cost_center = (
        doc.get("cost_center")
        or doc.get("items")[0].get("cost_center")
        or frappe.db.get_value("Company", doc.company, "cost_center")
    )

    if not cost_center:
        frappe.throw("Cost Center is required but not set on the document or company.")

    gl_entries = []
    is_return = doc.is_return

    if not is_return:
        # Sales Invoice: 
        # 1. Excise Duty entries
        if total_excise_value > 0:
            gl_entries.append(
                doc.get_gl_dict({
                    "account": sales_account,
                    "debit": abs(total_excise_value),
                    "credit": 0,
                    "debit_in_account_currency": abs(total_excise_value),
                    "credit_in_account_currency": 0,
                    "posting_date": doc.posting_date,
                    "company": doc.company,
                    "voucher_type": doc.doctype,
                    "voucher_no": doc.name,
                    "cost_center": cost_center,
                    "against": excise_account,
                    "remarks": "Excise Duty adjustment"
                }, get_account_currency(sales_account))
            )

            gl_entries.append(
                doc.get_gl_dict({
                    "account": excise_account,
                    "credit": abs(total_excise_value),
                    "debit": 0,
                    "credit_in_account_currency": abs(total_excise_value),
                    "debit_in_account_currency": 0,
                    "posting_date": doc.posting_date,
                    "company": doc.company,
                    "voucher_type": doc.doctype,
                    "voucher_no": doc.name,
                    "cost_center": cost_center,
                    "against": doc.customer,
                    "remarks": "Excise Duty liability"
                }, get_account_currency(excise_account))
            )
        
        # 2. VAT entries
        if vat_value > 0:
            gl_entries.append(
                doc.get_gl_dict({
                    "account": sales_account,
                    "debit": abs(vat_value),
                    "credit": 0,
                    "debit_in_account_currency": abs(vat_value),
                    "credit_in_account_currency": 0,
                    "posting_date": doc.posting_date,
                    "company": doc.company,
                    "voucher_type": doc.doctype,
                    "voucher_no": doc.name,
                    "cost_center": cost_center,
                    "against": vat_account,
                    "remarks": "VAT adjustment"
                }, get_account_currency(sales_account))
            )

            gl_entries.append(
                doc.get_gl_dict({
                    "account": vat_account,
                    "credit": abs(vat_value),
                    "debit": 0,
                    "credit_in_account_currency": abs(vat_value),
                    "debit_in_account_currency": 0,
                    "posting_date": doc.posting_date,
                    "company": doc.company,
                    "voucher_type": doc.doctype,
                    "voucher_no": doc.name,
                    "cost_center": cost_center,
                    "against": doc.customer,
                    "remarks": "VAT liability"
                }, get_account_currency(vat_account))
            )
            
    else:
        # Sales Return: 
        # 1. Reverse Excise Duty entries
        if total_excise_value > 0:
            gl_entries.append(
                doc.get_gl_dict({
                    "account": excise_account,
                    "debit": abs(total_excise_value),
                    "credit": 0,
                    "debit_in_account_currency": abs(total_excise_value),
                    "credit_in_account_currency": 0,
                    "posting_date": doc.posting_date,
                    "company": doc.company,
                    "voucher_type": doc.doctype,
                    "voucher_no": doc.name,
                    "cost_center": cost_center,
                    "against": doc.customer,
                    "remarks": "Excise Duty reversal"
                }, get_account_currency(excise_account))
            )

            gl_entries.append(
                doc.get_gl_dict({
                    "account": sales_account,
                    "credit": abs(total_excise_value),
                    "debit": 0,
                    "credit_in_account_currency": abs(total_excise_value),
                    "debit_in_account_currency": 0,
                    "posting_date": doc.posting_date,
                    "company": doc.company,
                    "voucher_type": doc.doctype,
                    "voucher_no": doc.name,
                    "cost_center": cost_center,
                    "against": excise_account,
                    "remarks": "Excise Duty reversal adjustment"
                }, get_account_currency(sales_account))
            )
        
        # 2. Reverse VAT entries
        if vat_value > 0:
            gl_entries.append(
                doc.get_gl_dict({
                    "account": vat_account,
                    "debit": abs(vat_value),
                    "credit": 0,
                    "debit_in_account_currency": abs(vat_value),
                    "debit_in_account_currency": 0,
                    "posting_date": doc.posting_date,
                    "company": doc.company,
                    "voucher_type": doc.doctype,
                    "voucher_no": doc.name,
                    "cost_center": cost_center,
                    "against": doc.customer,
                    "remarks": "VAT reversal"
                }, get_account_currency(vat_account))
            )

            gl_entries.append(
                doc.get_gl_dict({
                    "account": sales_account,
                    "credit": abs(vat_value),
                    "debit": 0,
                    "credit_in_account_currency": abs(vat_value),
                    "debit_in_account_currency": 0,
                    "posting_date": doc.posting_date,
                    "company": doc.company,
                    "voucher_type": doc.doctype,
                    "voucher_no": doc.name,
                    "cost_center": cost_center,
                    "against": vat_account,
                    "remarks": "VAT reversal adjustment"
                }, get_account_currency(sales_account))
            )
 
    # Log all GL entries for debugging
    frappe.logger().info(f"Creating {len(gl_entries)} additional GL entries for {doc.name}")
    for gle in gl_entries:
        frappe.msgprint(
            f"GL Entry - Account: {gle.account}, Debit: {gle.debit}, Credit: {gle.credit}, Remarks: {gle.get('remarks', 'N/A')}", 
            title="Debug"
        )

    if gl_entries:
        try:
            make_gl_entries(gl_entries, cancel=False)
            frappe.msgprint(
                f"Successfully created {len(gl_entries)} additional GL entries for {doc.doctype} {doc.name}<br>" +
                f"Excise: {total_excise_value}<br>" +
                f"VAT: {vat_value}", 
                title="Debug"
            )
            frappe.logger().info(f"Created {len(gl_entries)} GL entries: Excise={total_excise_value}, VAT={vat_value}")
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Error creating GL entries for {doc.doctype} {doc.name}")
            frappe.msgprint(f"Error creating GL entries for {doc.doctype} {doc.name}. Check error log.", title="Debug")
            raise



def on_submit_clear_system_vat(doc, method):
    """
    Clear VAT entries from the taxes table to prevent ERPNext from creating
    standard VAT GL entries. This should be called BEFORE before_submit.
    Hook this to 'before_submit' event with higher priority or use 'validate' event.
    """
    vat_account = "VAT - GLMI"
    
    # Remove VAT rows from taxes table to prevent system GL entries
    original_tax_count = len(doc.taxes)
    doc.taxes = [t for t in doc.taxes if vat_account not in (t.account_head or "")]
    
    if len(doc.taxes) < original_tax_count:
        frappe.logger().info(f"Removed {original_tax_count - len(doc.taxes)} VAT tax rows from {doc.name}")
        frappe.msgprint(
            f"Removed system VAT entries. Using custom_vat={doc.custom_vat} instead.", 
            title="Info"
        )


# def modify_gl_entries(doc, method):
#     """
#     Modify GL entries after they are generated but before they are saved
#     """
#     if not hasattr(doc, 'get_gl_entries'):
#         return
    
#     # Store original method
#     original_get_gl_entries = doc.get_gl_entries
    
#     def custom_get_gl_entries(*args, **kwargs):
#         # Get original GL entries
#         gl_entries = original_get_gl_entries(*args, **kwargs)
        
#         # Modify entries for payable accounts starting with 11123
#         if doc.supplier and gl_entries:
#             for entry in gl_entries:
#                 if entry.get('account') and entry['account'].startswith('34810'):
#                     account = frappe.get_cached_doc('Account', entry['account'])
                    
#                     if account.account_type == 'Payable':
#                         entry['party_type'] = 'Supplier'
#                         entry['party'] = doc.supplier
        
#         return gl_entries
    
#     # Replace method
#     doc.get_gl_entries = custom_get_gl_entries
import frappe
from frappe import _

def modify_gl_entries(doc, method):
    """
    Hook to modify GL entries before submit
    Adds party information to TDS child accounts
    """
    # Check if document has get_gl_entries method
    if not hasattr(doc, 'get_gl_entries'):
        return
    
    # Store original method
    original_get_gl_entries = doc.get_gl_entries
    
    def custom_get_gl_entries(*args, **kwargs):
        # Get original GL entries
        gl_entries = original_get_gl_entries(*args, **kwargs)
        
        # Get company suffix
        company_suffix = ""
        if doc.company:
            company_doc = frappe.get_cached_doc('Company', doc.company)
            company_suffix = company_doc.abbr if company_doc.abbr else ""
        
        # Build TDS parent account name
        tds_parent_account = f"348100 - TDS Payable - {company_suffix}" if company_suffix else "348100 - TDS Payable"
        
        # Get all TDS child accounts
        tds_child_accounts = frappe.get_all(
            'Account',
            filters={
                'parent_account': tds_parent_account,
                'company': doc.company
            },
            fields=['name', 'account_type']
        )
        
        # If no child accounts found, return original entries unchanged
        if not tds_child_accounts:
            frappe.logger().debug(f"No child accounts found under {tds_parent_account}. Returning original GL entries.")
            return gl_entries
        
        # Create set of TDS child account names for fast lookup
        tds_child_account_names = {acc.name for acc in tds_child_accounts}
        
        # Modify GL entries only if supplier exists
        if doc.supplier and gl_entries:
            for entry in gl_entries:
                if entry.get('account') and entry['account'] in tds_child_account_names:
                    account = frappe.get_cached_doc('Account', entry['account'])
                    if account.account_type == 'Payable':
                        entry['party_type'] = 'Supplier'
                        entry['party'] = doc.supplier
                        frappe.logger().debug(
                            f"Added party info to GL entry for account {entry['account']}: Supplier/{doc.supplier}"
                        )
        
        return gl_entries
    
    # Replace the method with custom version
    doc.get_gl_entries = custom_get_gl_entries

# def modify_gl_entries(doc, method):
  
#     if not hasattr(doc, 'get_gl_entries'):
#         return
    
#     original_get_gl_entries = doc.get_gl_entries

#     def custom_get_gl_entries(*args, **kwargs):
#         gl_entries = original_get_gl_entries(*args, **kwargs)
        
#         company_suffix = ""
#         if doc.company:
#             company_doc = frappe.get_cached_doc('Company', doc.company)
#             company_suffix = company_doc.abbr if company_doc.abbr else ""
        
#         tds_parent_account = f"348100 - TDS Payable - {company_suffix}" if company_suffix else "348100 - TDS Payable"
        
#         tds_child_accounts = frappe.get_all(
#             'Account',
#             filters={
#                 'parent_account': tds_parent_account,
#                 'company': doc.company
#             },
#             fields=['name', 'account_type']
#         )
#         if not tds_child_accounts:
#             return gl_entries
        
#         tds_child_account_names = {acc.name for acc in tds_child_accounts}
        
#         if doc.supplier and gl_entries:
#             for entry in gl_entries:
#                 if entry.get('account') and entry['account'] in tds_child_account_names:
#                     account = frappe.get_cached_doc('Account', entry['account'])
#                     if account.account_type == 'Payable':
#                         entry['party_type'] = 'Supplier'
#                         entry['party'] = doc.supplier
        
#         return gl_entries
    
#     # Replace method
#     doc.get_gl_entries = custom_get_gl_entries