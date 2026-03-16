from avinashgroup_app.utils.audit_file_manager import AuditEventMapper

app_name = "avinashgroup_app"
app_title = "Avinash Group App"
app_publisher = "Raindrop"
app_description = "Avinash Group App"
app_email = "subash@raindropinc.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "avinashgroup_app",
# 		"logo": "/assets/avinashgroup_app/logo.png",
# 		"title": "Avinash Group App",
# 		"route": "/avinashgroup_app",
# 		"has_permission": "avinashgroup_app.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/avinashgroup_app/css/avinashgroup_app.css"
app_include_js = [
	"/assets/avinashgroup_app/js/item_company_check.js?v=1.0",
	"/assets/avinashgroup_app/js/sales_invoice.js?v=9.6",
	"/assets/avinashgroup_app/js/purchase_taxes_common.js?v=1.2",
	"/assets/avinashgroup_app/js/global_filter.js?v=1.4",
]
# my_custom_app/hooks.py

# include js, css files in header of web template
# web_include_css = "/assets/avinashgroup_app/css/avinashgroup_app.css"
# web_include_js = "/assets/avinashgroup_app/js/avinashgroup_app.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "avinashgroup_app/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	# "Sales Invoice" : "public/js/sales_invoice.js",
	# "Journal Entry" : "custom_code/JournalEntry/journal_entry.js"
	"Purchase Order": "public/js/purchase_order.js",
	"Material Request": "public/js/material_request.js",
}

# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# doc_events = {
#     "Purchase Invoice": {
#         "autoname": "avinashgroup_app.custom_code.api.autoname_purchase_invoice"
#     }
# }

# doc_events = {
#     "Payment Entry": {
#         "before_save": "avinashgroup_app.custom_code.api.set_custom_name_field",
#         # or use "validate" instead of "before_save"
#     },
#     "Journal Entry": {
#         "before_save": "avinashgroup_app.custom_code.api.set_custom_name_jv",
#     },
#     "Purchase Invoice": {
#         "before_submit": "avinashgroup_app.custom_code.excise_ledger.modify_gl_entries"
#     }
# }

# Common event handler for auto-naming
# common_naming_events = {
#     "before_save":"avinashgroup_app.custom_code.api.handle_custom_naming"
# }

# # Define your list of DocTypes that use common naming
# naming_doctypes = [
#     "Payment Entry",
#     "Journal Entry",
#     "Purchase Invoice",
#     "Sales Invoice"
# ]

# # Build doc_events dictionary with common naming events
# doc_events = {
#     doctype: common_naming_events.copy() for doctype in naming_doctypes
# }

# # (different event)
# doc_events["Purchase Invoice"] = {
#     "before_submit": "avinashgroup_app.custom_code.excise_ledger.modify_gl_entries",
#     # "before_save":"avinashgroup_app.custom_code.api.set_custom_name_field"
# }sales_invoice_specific_events


# common_fiscal_naming_events = {
#     "autoname": "avinashgroup_app.custom_code.api.handle_naming_and_fiscal_year"
# }

# fiscal_naming_doctypes = [
#     "Sales Invoice",
#     "Purchase Invoice",
#     "Journal Entry",
#     "Payment Entry",
#     "Material Request",
# ]


# doc_events = {
#     doctype: common_fiscal_naming_events.copy() for doctype in fiscal_naming_doctypes
# }

# purchase_invoice_events = {
#     "before_submit": "avinashgroup_app.custom_code.excise_ledger.modify_gl_entries"
# }

# doc_events["Purchase Invoice"].update(purchase_invoice_events)


## Event Templates

from avinashgroup_app.utils.audit_file_manager import AuditEventMapper

# Purchase Invoice specific events (using common handler)
purchase_invoice_specific_events = {
	"before_submit": "avinashgroup_app.custom_code.excise_ledger.modify_gl_entries",
	"before_save": "avinashgroup_app.custom_code.common.purchase_taxes_handler.before_save_purchase_invoice",
	"validate": "avinashgroup_app.custom_code.common.purchase_taxes_handler.validate_purchase_invoice",
}

# Purchase Order events (using common handler)
purchase_order_events = {
	"before_save": "avinashgroup_app.custom_code.common.purchase_taxes_handler.before_save_purchase_order",
	"validate": "avinashgroup_app.custom_code.common.purchase_taxes_handler.validate_purchase_order",
}

# Purchase Receipt events (using common handler)
purchase_receipt_events = {
	"before_save": "avinashgroup_app.custom_code.common.purchase_taxes_handler.before_save_purchase_receipt",
	"validate": "avinashgroup_app.custom_code.common.purchase_taxes_handler.validate_purchase_receipt",
}

# Supplier Quotation events (using common handler)
supplier_quotation_events = {
	"before_save": "avinashgroup_app.custom_code.common.purchase_taxes_handler.before_save_supplier_quotation",
	"validate": "avinashgroup_app.custom_code.common.purchase_taxes_handler.validate_supplier_quotation",
}

sales_invoice_specific_events = {
	"before_save": "avinashgroup_app.custom_code.SalesInvoice.salesinvoice_taxes.before_save_salesinvoice",
	"validate": "avinashgroup_app.custom_code.SalesInvoice.salesinvoice_taxes.validate_salesinvoice",
}

# doc_events = {
#     "Sales Invoice": {
#         "validate": "avinashgroup_app.custom_code.SalesInvoice.validate_sales_invoice"
#     }
# }


# Build doc_events Dictionary
doc_events = AuditEventMapper.get_doc_events()

# Merge Purchase Invoice specific events
if "Purchase Invoice" not in doc_events:
	doc_events["Purchase Invoice"] = {}
doc_events["Purchase Invoice"].update(purchase_invoice_specific_events)

# Merge Purchase Order events
if "Purchase Order" not in doc_events:
	doc_events["Purchase Order"] = {}
doc_events["Purchase Order"].update(purchase_order_events)

# Merge Purchase Receipt events
if "Purchase Receipt" not in doc_events:
	doc_events["Purchase Receipt"] = {}
doc_events["Purchase Receipt"].update(purchase_receipt_events)

# Merge Supplier Quotation events
if "Supplier Quotation" not in doc_events:
	doc_events["Supplier Quotation"] = {}
doc_events["Supplier Quotation"].update(supplier_quotation_events)

if "Sales Invoice" not in doc_events:
	doc_events["Sales Invoice"] = {}
doc_events["Sales Invoice"].update(sales_invoice_specific_events)


# for doctype in fiscal_naming_doctypes:
#     if doctype not in doc_events:
#         doc_events[doctype] = {}

#     # Add autoname
#     doc_events[doctype]["autoname"] = common_fiscal_naming_events["autoname"]

#     # Add validate - if doctype also needs company validation, both will run
#     if "validate" not in doc_events[doctype]:
#         doc_events[doctype]["validate"] = []
#     elif not isinstance(doc_events[doctype]["validate"], list):
#         doc_events[doctype]["validate"] = [doc_events[doctype]["validate"]]

#     doc_events[doctype]["validate"].append(common_fiscal_naming_events["validate"])

# # 3. Merge company validation events
# for doctype in company_validation_doctypes:
#     if doctype not in doc_events:
#         doc_events[doctype] = {}

#     # Add validate
#     if "validate" not in doc_events[doctype]:
#         doc_events[doctype]["validate"] = []
#     elif not isinstance(doc_events[doctype]["validate"], list):
#         doc_events[doctype]["validate"] = [doc_events[doctype]["validate"]]

#     if company_validation_events["validate"] not in doc_events[doctype]["validate"]:
#         doc_events[doctype]["validate"].append(company_validation_events["validate"])

# # 4. Merge Purchase Invoice specific events
# if "Purchase Invoice" not in doc_events:
#     doc_events["Purchase Invoice"] = {}
# doc_events["Purchase Invoice"].update(purchase_invoice_specific_events)


# doc_events.setdefault("*", {}).update({
#     "autoname": "avinashgroup_app.custom_code.Override.naming_series.autoname"
# })


# If Journal Entry needs a different API than Payment Entry, override it
# doc_events["Journal Entry"] = {
#     "before_save": "avinashgroup_app.custom_code.api.set_custom_name_jv",
# }


# override_doctype_class = {
#     "Purchase Invoice": "avinashgroup_app.custom_code.api.CustomPurchaseInvoice"
# }
###Naming Series
# override_doctype_class = {
#     "Customer": "avinashgroup_app.custom_code.custom_customer.CustomCustomer"
# }

# Override doctype class to bypass workflow validation for Administrator
override_doctype_class = {
	"Material Request": "avinashgroup_app.custom_code.Override.material_request.MaterialRequest",
	"Purchase Order": "avinashgroup_app.custom_code.Override.purchase_order.PurchaseOrder",
}

# doc_events = {
#     # "Customer": {
#     #     "override_doctype_class": "your_app_name.overrides.customer.CustomCustomer"
#     # },
#     "Item": {
#         "override_doctype_class": "avinashgroup_app.custom_code.custom_itemname.CustomItem"
#     }
# }

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "avinashgroup_app/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "avinashgroup_app.utils.jinja_methods",
# 	"filters": "avinashgroup_app.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "avinashgroup_app.install.before_install"
# after_install = "avinashgroup_app.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "avinashgroup_app.uninstall.before_uninstall"
# after_uninstall = "avinashgroup_app.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "avinashgroup_app.utils.before_app_install"
# after_app_install = "avinashgroup_app.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "avinashgroup_app.utils.before_app_uninstall"
# after_app_uninstall = "avinashgroup_app.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "avinashgroup_app.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# hooks.py

# Document Events
# ---------------
# Hook on document methods and events

# ROUNDING
# doc_events = {
#     "Sales Invoice": {
#         # Calculate excise duty and override base_total before ERPNext validation
#         #ROUNDING
#         # "before_validate": "avinashgroup_app.custom_code.override_rounding.override_totals_before_validate",

#         #  Re-override after ERPNext recalculates
#         #ROUNDING
#         # "validate": "avinashgroup_app.custom_code.override_rounding.override_totals_validate",

#         #  Final calcul  ation before saving (ensures everything persists)
#         #ROUNDING
#         # "before_save": "avinashgroup_app.custom_code.override_rounding.override_totals_before_save",

#         #  Before submitting - finalize all calculations
#         #ROUNDING
#         # "before_submit": [
#         #     "avinashgroup_app.custom_code.override_rounding.override_totals_before_submit",
#         #     # "avinashgroup_app.custom_code.excise_ledger.before_submit"

#         # ],

#         #   On submit (last change before GL entries)
#         #ROUNDING
#         # "on_submit": "avinashgroup_app.custom_code.override_rounding.override_totals_on_submit",

#         #  Handle updates after submission
#         # "on_update_after_submit": "avinashgroup_app.custom_code.override_rounding.override_totals_on_update_after_submit"


#     }
# }
# Scheduled Tasks
# ---------------

scheduler_events = {
	# "all": [
	# 	"avinashgroup_app.tasks.all"
	# ],
	# "daily": [
	# 	"avinashgroup_app.tasks.daily"
	# ],
	# "hourly": [
	# 	"avinashgroup_app.tasks.nepali_month_deferred_calculation.process_nepali_deferred_accounting"
	# ],
	# "weekly": [
	# 	"avinashgroup_app.tasks.weekly"
	# ],
	# "monthly": [
	# 	"avinashgroup_app.tasks.monthly"
	# ],whitelist
}

# Testing
# -------

# before_tests = "avinashgroup_app.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	"erpnext.buying.doctype.request_for_quotation.request_for_quotation.create_supplier_quotation": "avinashgroup_app.templates.pages.rfq.create_supplier_quotation",
	"frappe.model.workflow.get_transitions": "avinashgroup_app.custom_code.workflow_admin_bypass.get_transitions",
	"frappe.model.workflow.apply_workflow": "avinashgroup_app.custom_code.workflow_admin_bypass.apply_workflow",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "avinashgroup_app.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["avinashgroup_app.utils.before_request"]
# after_request = ["avinashgroup_app.utils.after_request"]

# Job Events
# ----------
# before_job = ["avinashgroup_app.utils.before_job"]
# after_job = ["avinashgroup_app.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{

# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"avinashgroup_app.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }


fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			["fieldname", "like", "custom_%"],
			["fieldname", "not in", ["custom_abbr", "custom_company_abbr", "custom_fiscal_year"]],
		],
	},
	{"dt": "Client Script", "filters": [["module", "=", "Avinash Group App"]]},
	{"dt": "DocType", "filters": [["custom", "=", 1], ["module", "=", "Avinash Group App"]]},
]

