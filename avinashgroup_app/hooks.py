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
    "/assets/avinashgroup_app/js/sales_invoice.js?v=10.6",
    "/assets/avinashgroup_app/js/purchase_taxes_common.js?v=1.8",
    "/assets/avinashgroup_app/js/selling_taxes_common.js?v=1.0",
    "/assets/avinashgroup_app/js/sales_warehouse_common.js?v=1.1",
    "/assets/avinashgroup_app/js/global_filter.js?v=1.4",
    "/assets/avinashgroup_app/js/company_filter.js?v=2.4",
    "/assets/avinashgroup_app/js/payment_entry.js?v=1.2",
    "/assets/avinashgroup_app/js/approval_field_visibility.js?v=1.1",
    "/assets/avinashgroup_app/js/approval_workflow_auto.js?v=1.0",
    "/assets/avinashgroup_app/js/auto_update_document_no.js?v=2.2",
    "/assets/avinashgroup_app/js/numbering_preview.js?v=1.0",
    "/assets/avinashgroup_app/js/report_print_orientation.js?v=10",
    "/assets/avinashgroup_app/js/vehicle_mandatory.js?v=1.0",
]

# report_print_portrait.css is no longer loaded globally — it would change every
# doctype print format too. report_print_orientation.js injects it dynamically
# only when the user is on a query-report route.
app_include_css = [
    "/assets/avinashgroup_app/css/desk_focus.css?v=1.1",
]

doctype_js = {
    # Approval-workflow UI (banner + reject dialog) is now generic — see
    # approval_workflow_auto.js in app_include_js. No per-doctype file needed;
    # any doctype set up via setup_workflow gets it automatically.
    "Material Request": "public/js/material_request.js",
    "Purchase Invoice": "public/js/pi.js",
    "Journal Entry": "public/js/journal_entry.js",
    "Attendance": "public/js/attendance.js",
    "Payroll Entry": "public/js/payroll_entry.js",
    "Customer": ["public/js/party_duplicate_check.js", "public/js/party_default_account.js"],
    "Supplier": ["public/js/party_duplicate_check.js", "public/js/party_default_account.js"],
    "Item": "public/js/item_default_account.js",
}

purchase_invoice_specific_events = {
    "before_submit": "avinashgroup_app.custom_code.excise_ledger.modify_gl_entries",
    "on_submit": "avinashgroup_app.custom_code.stock_revaluation.on_purchase_invoice_submit",
    "before_validate": "avinashgroup_app.custom_code.common.purchase_taxes_handler.before_validate_purchase_invoice",
    "before_save": "avinashgroup_app.custom_code.common.purchase_taxes_handler.before_save_purchase_invoice",
    "validate": [
        "avinashgroup_app.custom_code.common.purchase_taxes_handler.validate_purchase_invoice",
        "avinashgroup_app.custom_code.vehicle_mandatory.validate_purchase_invoice",
    ],
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
    "validate": "avinashgroup_app.custom_code.SalesInvoice.salesinvoice_taxes.validate_salesinvoice",
    # IRD copy labeling: count real prints (Tax Invoice / Copy of Original / Copy of Original 2 ...)
    "before_print": "avinashgroup_app.custom_code.SalesInvoice.print_count.before_print",
}

cbms_sales_invoice_events = {
    "on_submit": "avinashgroup_app.custom_code.CBMS.sales_invoice_hooks.on_submit",
    "before_cancel": "avinashgroup_app.custom_code.CBMS.sales_invoice_hooks.before_cancel",
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

journal_entry_events = {
    "validate": "avinashgroup_app.custom_code.vehicle_mandatory.validate_journal_entry",
}

# All three run on `validate`, NOT `before_save`: auto attendance creates
# Attendance already submitted (insert with docstatus=1), and Frappe runs
# `before_submit` instead of `before_save` on that path — before_save hooks
# would silently never fire for device-marked attendance. `validate` runs on
# both save and submit-on-create.
attendance_events = {
    "validate": [
        "avinashgroup_app.payroll.attendance_allowance.set_holiday_flag",
        "avinashgroup_app.biometric.attendance_override.set_shift_deviation_fields",
        "avinashgroup_app.biometric.attendance_override.enforce_late_arrival_half_day",
    ],
}

# Jinja helpers for print formats (e.g. BS date on the Nepal Gas invoice)
jinja = {
    "methods": [
        "avinashgroup_app.custom_code.CBMS.utils.bs_date_str",
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

for _event, _handler in cbms_sales_invoice_events.items():
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

for _event, _handler in journal_entry_events.items():
    _add_doc_event("Journal Entry", _event, _handler)

for _event, _handler in attendance_events.items():
    _add_doc_event("Attendance", _event, _handler)

_add_doc_event(
    "Employee Checkin",
    "after_insert",
    "avinashgroup_app.biometric.attendance_override.reconcile_with_existing_attendance",
)

_add_doc_event(
    "Employee",
    "validate",
    "avinashgroup_app.biometric.employee.validate_unique_device_id",
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

# Numbering Configuration engine: rule-driven numbering for EVERY doctype.
# Wildcard handlers run after the doctype-specific ones, preserving the old
# order (voucher logic first, engine last). Doctypes without enabled rules
# exit through a redis-cached gate at ~zero cost.
_add_doc_event("*", "validate", "avinashgroup_app.custom_code.Override.naming_series.apply_engine_numbering")
_add_doc_event("*", "before_save", "avinashgroup_app.custom_code.Override.naming_series.apply_engine_numbering")
_add_doc_event("*", "after_delete", "avinashgroup_app.custom_code.Override.naming_series.revert_engine_series_on_delete")

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
    "cron": {
        "*/5 * * * *": [
            "avinashgroup_app.custom_code.CBMS.scheduler.retry_failed_cbms_syncs",
            "avinashgroup_app.custom_code.CBMS.scheduler.reconcile_missing_cbms_bills",
        ],
    },
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
    # Report "Add Column": show a Link field's name instead of its id.
    "frappe.desk.query_report.get_data_for_custom_field": "avinashgroup_app.custom_code.Override.query_report.get_data_for_custom_field",
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
# Document Generator templates (Inputs / Data Sources / Companies child rows
# travel inside the parent record). Restrict to the balance-confirmation
# templates so unrelated, site-specific templates aren't exported.
fixtures = [
    {
        "dt": "Document Template",
        "filters": {
            "name": ["in", ["Customer Balance Confirmation", "Vendor Balance Confirmation"]]
        },
    },
]
