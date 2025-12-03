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
    # "/assets/avinashgroup_app/js/sales_invoice.js?v=8.5",
    # "/assets/avinashgroup_app/js/purchase_invoice.js?v=1.2"
     "/assets/avinashgroup_app/js/global_filter.js?v=1.3",
    #  "/assets/avinashgroup_app/js/si.js?v=1.0" ,
    # "/assets/avinashgroup_app/js/pi.js?v=2.1",
    # "/assets/avinashgroup_app/js/journal_entry.js?v=1.2"
    #  "/assets/avinashgroup_app/js/journal_entry"
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
# }



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



#### Event Templates
 
common_fiscal_naming_events = {
    "autoname": "avinashgroup_app.custom_code.Override.naming_series.autoname"
}

company_validation_events = {
    "validate": "avinashgroup_app.custom_code.globalfilter.global.validate_company_matching"
}

purchase_invoice_specific_events = {
    "before_submit": "avinashgroup_app.custom_code.excise_ledger.modify_gl_entries"
    }


# STEP 2: Define Doctype Groups (Which doctypes need which events)
fiscal_naming_doctypes = [
    "Sales Invoice",
    "Purchase Invoice",
    "Journal Entry",
    "Payment Entry",
    "Material Request",
    "Address",
    "Contact",
    "Customer",
    "Supplier",
    "Employee",
    "Customer Group", 
    "Supplier Group", 
    "Item Group",
]

company_validation_doctypes = [
    "Sales Invoice",
    "Sales Order",
    "Delivery Note",
    "Purchase Invoice",
    "Purchase Order",
    "Purchase Receipt",
    "Payment Entry",
    "Journal Entry",
    "Quotation",
    "Supplier Quotation",
    "Material Request",
    "Stock Entry",
]

# STEP 3: Build doc_events Dictionary

# 1. Start with audit hooks
doc_events = AuditEventMapper.get_doc_events()

# 2. Merge fiscal naming events
for doctype in fiscal_naming_doctypes:
    if doctype not in doc_events:
        doc_events[doctype] = {}
    doc_events[doctype].update(common_fiscal_naming_events)

# 3. Merge company validation events
for doctype in company_validation_doctypes:
    if doctype not in doc_events:
        doc_events[doctype] = {}
    doc_events[doctype].update(company_validation_events)

# 4. Merge Purchase Invoice specific events
if "Purchase Invoice" not in doc_events:
    doc_events["Purchase Invoice"] = {}
doc_events["Purchase Invoice"].update(purchase_invoice_specific_events)




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

#ROUNDING
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

# scheduler_events = {
# 	"all": [
# 		"avinashgroup_app.tasks.all"
# 	],
# 	"daily": [
# 		"avinashgroup_app.tasks.daily"
# 	],
# 	"hourly": [
# 		"avinashgroup_app.tasks.hourly"
# 	],
# 	"weekly": [
# 		"avinashgroup_app.tasks.weekly"
# 	],
# 	"monthly": [
# 		"avinashgroup_app.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "avinashgroup_app.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "avinashgroup_app.event.get_events"
# }
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
            [
                "fieldname", "like", "custom_%"
            ]
        ]
    },
    {
        "dt": "Property Setter",
        "filters": [
            [
                "property", "=", "options"
            ],
            [
                "field_name", "=", "naming_series"
            ]
        ]
    },
    {
        "dt": "Client Script",
        "filters": [
            [
                "module", "=", "Avinash Group App"
            ]
        ]
    }
]
