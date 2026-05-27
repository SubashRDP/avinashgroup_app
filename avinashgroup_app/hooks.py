from avinashgroup_app.utils.audit_file_manager import AuditEventMapper
from avinashgroup_app.custom_code.fiscal_year_filter import FILTERED_DOCTYPES

app_name = "avinashgroup_app"
app_title = "Avinash Group App"
app_publisher = "Raindrop"
app_description = "Avinash Group App"
app_email = "subash@raindropinc.com"
app_license = "mit"

page_renderer = ["avinashgroup_app.biometric.iclock.IclockRenderer"]

app_include_js = [
    "/assets/avinashgroup_app/js/fiscal_year_cache.js?v=1.0",
    "/assets/avinashgroup_app/js/approval_workflow_common.js?v=1.0",
    "/assets/avinashgroup_app/js/sales_invoice.js?v=10.5",
    "/assets/avinashgroup_app/js/purchase_taxes_common.js?v=1.8",
    "/assets/avinashgroup_app/js/selling_taxes_common.js?v=1.0",
    "/assets/avinashgroup_app/js/sales_warehouse_common.js?v=1.1",
    "/assets/avinashgroup_app/js/global_filter.js?v=1.4",
    "/assets/avinashgroup_app/js/company_filter.js?v=2.4",
    "/assets/avinashgroup_app/js/payment_entry.js?v=1.2",
    "/assets/avinashgroup_app/js/approval_field_visibility.js?v=1.1",
    "/assets/avinashgroup_app/js/auto_update_document_no.js?v=1.2",
]

doctype_js = {
    "Purchase Order": "public/js/purchase_order.js",
    "Material Request": "public/js/material_request.js",
    "Purchase Invoice": "public/js/pi.js",
    "Journal Entry": "public/js/journal_entry.js",
    "Attendance": "public/js/attendance.js",
    "Payroll Entry": "public/js/payroll_entry.js",
}

purchase_invoice_specific_events = {
    "before_submit": "avinashgroup_app.custom_code.excise_ledger.modify_gl_entries",
    "on_submit": "avinashgroup_app.custom_code.stock_revaluation.on_purchase_invoice_submit",
    "before_validate": "avinashgroup_app.custom_code.common.purchase_taxes_handler.before_validate_purchase_invoice",
    "before_save": "avinashgroup_app.custom_code.common.purchase_taxes_handler.before_save_purchase_invoice",
    "validate": "avinashgroup_app.custom_code.common.purchase_taxes_handler.validate_purchase_invoice"
}

purchase_order_events = {
    "before_save": "avinashgroup_app.custom_code.common.purchase_taxes_handler.before_save_purchase_order",
    "validate": "avinashgroup_app.custom_code.common.purchase_taxes_handler.validate_purchase_order"
}

purchase_receipt_events = {
    "before_save": "avinashgroup_app.custom_code.common.purchase_taxes_handler.before_save_purchase_receipt",
    "validate": "avinashgroup_app.custom_code.common.purchase_taxes_handler.validate_purchase_receipt"
}

supplier_quotation_events = {
    "before_save": "avinashgroup_app.custom_code.common.purchase_taxes_handler.before_save_supplier_quotation",
    "validate": "avinashgroup_app.custom_code.common.purchase_taxes_handler.validate_supplier_quotation"
}

sales_invoice_specific_events = {
    "before_validate": "avinashgroup_app.custom_code.SalesInvoice.salesinvoice_taxes.before_validate_salesinvoice",
    "before_save": "avinashgroup_app.custom_code.SalesInvoice.salesinvoice_taxes.before_save_salesinvoice",
    "validate": "avinashgroup_app.custom_code.SalesInvoice.salesinvoice_taxes.validate_salesinvoice"
}

quotation_events = {
    "before_validate": "avinashgroup_app.custom_code.common.selling_taxes_handler.before_validate_quotation",
    "before_save": "avinashgroup_app.custom_code.common.selling_taxes_handler.before_save_quotation",
    "validate": "avinashgroup_app.custom_code.SalesInvoice.salesinvoice_taxes.validate_quotation"
}

sales_order_events = {
    "before_validate": "avinashgroup_app.custom_code.common.selling_taxes_handler.before_validate_sales_order",
    "before_save": "avinashgroup_app.custom_code.common.selling_taxes_handler.before_save_sales_order",
    "validate": "avinashgroup_app.custom_code.SalesInvoice.salesinvoice_taxes.validate_sales_order"
}

delivery_note_events = {
    "before_validate": "avinashgroup_app.custom_code.common.selling_taxes_handler.before_validate_delivery_note",
    "before_save": "avinashgroup_app.custom_code.common.selling_taxes_handler.before_save_delivery_note",
    "validate": "avinashgroup_app.custom_code.SalesInvoice.salesinvoice_taxes.validate_delivery_note"
}

material_request_events = {
    "validate": "avinashgroup_app.custom_code.common.purchase_taxes_handler.validate_material_request"
}

rfq_events = {
    "validate": "avinashgroup_app.custom_code.common.purchase_taxes_handler.validate_request_for_quotation"
}

attendance_events = {
    "validate": "avinashgroup_app.payroll.attendance_allowance.set_holiday_flag",
    "before_save": [
        "avinashgroup_app.biometric.attendance_override.set_shift_deviation_fields",
        "avinashgroup_app.biometric.attendance_override.enforce_late_arrival_half_day",
    ],
}

doc_events = AuditEventMapper.get_doc_events()

def _add_doc_event(doctype, event, handler):
    if doctype not in doc_events:
        doc_events[doctype] = {}
    existing = doc_events[doctype].get(event)

    new_handlers = handler if isinstance(handler, list) else [handler]
    existing_list = (
        list(existing) if isinstance(existing, list) else ([existing] if existing else [])
    )

    for h in new_handlers:
        if h not in existing_list:
            existing_list.append(h)

    if not existing_list:
        return
    doc_events[doctype][event] = (
        existing_list if len(existing_list) > 1 else existing_list[0]
    )

for _event, _handler in purchase_invoice_specific_events.items():
    _add_doc_event("Purchase Invoice", _event, _handler)

for _event, _handler in purchase_order_events.items():
    _add_doc_event("Purchase Order", _event, _handler)

for _event, _handler in purchase_receipt_events.items():
    _add_doc_event("Purchase Receipt", _event, _handler)

for _event, _handler in supplier_quotation_events.items():
    _add_doc_event("Supplier Quotation", _event, _handler)

for _event, _handler in sales_invoice_specific_events.items():
    _add_doc_event("Sales Invoice", _event, _handler)

for _event, _handler in quotation_events.items():
    _add_doc_event("Quotation", _event, _handler)

for _event, _handler in sales_order_events.items():
    _add_doc_event("Sales Order", _event, _handler)

for _event, _handler in delivery_note_events.items():
    _add_doc_event("Delivery Note", _event, _handler)

for _event, _handler in material_request_events.items():
    _add_doc_event("Material Request", _event, _handler)

for _event, _handler in rfq_events.items():
    _add_doc_event("Request for Quotation", _event, _handler)

for _event, _handler in attendance_events.items():
    _add_doc_event("Attendance", _event, _handler)

_add_doc_event(
    "Employee Checkin",
    "after_insert",
    "avinashgroup_app.biometric.attendance_override.reconcile_with_existing_attendance",
)

_clear_filter_cache = "avinashgroup_app.custom_code.globalfilter.globalfilter.clear_filter_config_cache"
for _dt in ("Company Filter Config", "Company Filter Field"):
    _add_doc_event(_dt, "on_update", _clear_filter_cache)
    _add_doc_event(_dt, "on_trash", _clear_filter_cache)

# Fiscal Year Filter Hooks
_clear_user_fiscal_cache = "avinashgroup_app.custom_code.fiscal_year_filter.clear_user_fiscal_cache"
_add_doc_event("User", "on_update", _clear_user_fiscal_cache)

# List view filtering via SQL WHERE conditions
permission_query_conditions = {
    _dt: f"avinashgroup_app.custom_code.fiscal_year_filter.query_conditions_{_dt.replace(' ', '_').lower()}"
    for _dt in FILTERED_DOCTYPES
}

# Per-document access control
has_permission = {
    _dt: "avinashgroup_app.custom_code.fiscal_year_filter.has_fiscal_year_permission"
    for _dt in FILTERED_DOCTYPES
}

_add_doc_event("*", "validate", "avinashgroup_app.custom_code.dynamic_approval.validate")
_add_doc_event("*", "before_save", "avinashgroup_app.custom_code.dynamic_approval.before_save")
_add_doc_event("*", "on_update", "avinashgroup_app.custom_code.dynamic_approval.on_update")
_add_doc_event("*", "before_workflow_action", "avinashgroup_app.custom_code.dynamic_approval.before_workflow_action")

override_doctype_class = {
    "Material Request": "avinashgroup_app.custom_code.Override.overrides.MaterialRequest",
    "Purchase Order": "avinashgroup_app.custom_code.Override.overrides.PurchaseOrder",
    "Sales Invoice": "avinashgroup_app.custom_code.Override.overrides.CustomSalesInvoice",
    "Sales Order": "avinashgroup_app.custom_code.Override.overrides.SalesOrder",
    "Delivery Note": "avinashgroup_app.custom_code.Override.overrides.DeliveryNote",
    "Purchase Invoice": "avinashgroup_app.custom_code.Override.overrides.PurchaseInvoice",
    "Purchase Receipt": "avinashgroup_app.custom_code.Override.overrides.PurchaseReceipt",
    "Supplier Quotation": "avinashgroup_app.custom_code.Override.overrides.SupplierQuotation",
    "Request for Quotation": "avinashgroup_app.custom_code.Override.overrides.RequestforQuotation",
}

scheduler_events = {
    "hourly": [
        "avinashgroup_app.biometric.heartbeat.check_bridge_heartbeats",
    ],
}

before_request = [
    "avinashgroup_app.custom_code.Override.auto_insert_item_price.patch_insert_item_price_set_company"
]

override_whitelisted_methods = {
    "erpnext.buying.doctype.request_for_quotation.request_for_quotation.create_supplier_quotation": "avinashgroup_app.templates.pages.rfq.create_supplier_quotation",
    "erpnext.stock.get_item_details.get_item_details": "avinashgroup_app.custom_code.Override.get_item_details.get_item_details",
    "frappe.model.workflow.get_transitions": "avinashgroup_app.custom_code.workflow_admin_bypass.get_transitions",
    "frappe.model.workflow.apply_workflow": "avinashgroup_app.custom_code.workflow_admin_bypass.apply_workflow",
    "frappe.client.get_list": "avinashgroup_app.custom_code.fiscal_year_filter.filtered_get_list",
}

fixtures = [
    {"dt": "Company Filter Config"},
    {"dt": "Company Filter Field"},
    {
        "dt": "Custom Field",
        "filters": [
            ["name", "in", [
                "Attendance-custom_shift_deviation_section",
                "Attendance-custom_late_entry",
                "Attendance-custom_early_entry",
                "Attendance-custom_col_break_deviation",
                "Attendance-custom_early_exit",
                "Attendance-custom_late_exit",
                "Shift Type-custom_late_arrival_cutoff_time",
            ]]
        ],
    },
]
