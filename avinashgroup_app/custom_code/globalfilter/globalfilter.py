import frappe
from frappe import _

# ─────────────────────────────────────────────────────────────
#  COMPANY FILTER CONFIG  (mirrors company_filter.js)
#  fields       : top-level fieldnames to validate
#  child_tables : { child_table_fieldname: [fieldnames] }
#  custom       : True → handled by dedicated override below
# ─────────────────────────────────────────────────────────────
FILTER_CONFIG = {
    "Asset": {
        "company_field": "company",
        "fields": ["item_code", "custodian", "purchase_receipt", "purchase_invoice"]
    },
    "Asset Category": {
        "company_field": "custom_company",
        "child_tables": {"accounts": ["company"]}
    },
    "Asset Movement": {
        "company_field": "company",
        "child_tables": {"assets": ["asset"]}
    },
    "Asset Maintenance": {
        "company_field": "company",
        "fields": ["maintenance_team"]
    },
    "Asset Maintenance Log": {
        "company_field": "company",
        "fields": ["asset_maintenance"]
    },
    "Asset Value Adjustment": {
        "company_field": "company",
        "fields": ["asset"]
    },
    "Asset Repair": {
        "company_field": "company",
        "fields": ["asset"]
    },
    "Asset Capitalization": {
        "company_field": "company",
        "fields": ["target_item_code"],
        "child_tables": {
            "stock_items":   ["item_code"],
            "asset_items":   ["asset", "item_code"],
            "service_items": ["item_code"]
        }
    },

    "Item Group": {
        "company_field": "custom_company",
        "fields": ["parent_item_group"],
        "child_tables": {
            "item_group_defaults": ["company"],
            "taxes":               ["item_tax_template"]
        }
    },
    "Supplier Group": {
        "company_field": "custom_company",
        "fields": ["parent_supplier_group"],
        "child_tables": {"accounts": ["company"]}
    },
    "Customer Group": {
        "company_field": "custom_company",
        "fields": ["parent_customer_group", "default_price_list"],
        "child_tables": {"credit_limits": ["company"]}
    },

    "Quotation": {
        "company_field": "company",
        "fields": ["party_name", "price_list", "sales_partner"],
        "child_tables": {
            "items":            ["item_code", "warehouse"],
            "payment_schedule": ["payment_term"]
        }
    },
    "Sales Order": {
        "company_field": "company",
        "fields": ["customer", "price_list"],
        "child_tables": {
            "items": ["item_code", "supplier", "material_request", "project"]
        }
    },
    "Delivery Note": {
        "company_field": "company",
        "fields": ["customer", "price_list"],
        "child_tables": {"items": ["item_code", "batch_no", "project"]}
    },
    "Sales Invoice": {
        "company_field": "company",
        "fields": ["customer", "price_list"],
        "child_tables": {
            "items":            ["item_code", "batch_no", "project"],
            "payment_schedule": ["payment_term"]
        }
    },

    "Material Request": {
        "company_field": "company",
        "fields": ["price_list"],
        "child_tables": {
            "items": ["item_code", "manufacturer", "bom_no", "project"]
        }
    },
    "Request for Quotation": {
        "company_field": "company",
        "child_tables": {
            "suppliers": ["supplier"],
            "items":     ["item_code", "project"]
        }
    },
    "Supplier Quotation": {
        "company_field": "company",
        "fields": ["supplier", "price_list"],
        "child_tables": {"items": ["item_code", "warehouse", "project"]}
    },
    "Purchase Order": {
        "company_field": "company",
        "fields": ["supplier", "price_list"],
        "child_tables": {"items": ["item_code", "project"]}
    },
    "Purchase Receipt": {
        "company_field": "company",
        "fields": ["supplier", "price_list"],
        "child_tables": {"items": ["item_code", "batch_no", "project"]}
    },
    "Purchase Invoice": {
        "company_field": "company",
        "fields": ["supplier"],
        "child_tables": {
            "items":            ["item_code", "manufacturer", "project"],
            "payment_schedule": ["payment_term"]
        }
    },

    # custom=True → handled by dedicated functions below
    "Payment Entry": {
        "company_field": "company",
        "fields": ["bank_account"],
        "custom": True
    },
    "Journal Entry": {
        "company_field": "company",
        "custom": True
    },
    "Bank Account": {
        "company_field": "company",
        "custom": True
    },
}


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def _get_linked_doctype(doctype, fieldname):
    try:
        df = frappe.get_meta(doctype).get_field(fieldname)
        if df and df.fieldtype == "Link":
            return df.options
    except Exception:
        pass
    return None


def _get_child_doctype(parent_doctype, table_fieldname):
    try:
        df = frappe.get_meta(parent_doctype).get_field(table_fieldname)
        if df and df.fieldtype in ("Table", "Table MultiSelect"):
            return df.options
    except Exception:
        pass
    return None


def _resolve_company_field(linked_doctype):
    """Return 'company' if the linked doctype has a standard company field, else 'custom_company'."""
    try:
        meta = frappe.get_meta(linked_doctype)
        if meta.get_field("company"):
            return "company"
    except Exception:
        pass
    return "custom_company"


def _check_company(linked_doctype, value, company, label, filter_by=None):
    if not value or not linked_doctype:
        return None
    if not filter_by:
        filter_by = _resolve_company_field(linked_doctype)
    rec_company = frappe.db.get_value(linked_doctype, value, filter_by)
    if rec_company and rec_company != company:
        return _("{0} '{1}' belongs to company '{2}', not '{3}'.").format(
            label, value, rec_company, company
        )
    return None


# ─────────────────────────────────────────────────────────────
#  MAIN VALIDATOR — called from validate hook
# ─────────────────────────────────────────────────────────────

def validate_company_matching(doc, method=None):
    config = FILTER_CONFIG.get(doc.doctype)
    if not config:
        return

    company_field = config.get("company_field", "company")
    company = getattr(doc, company_field, None)
    if not company:
        return

    errors = []

    # top-level fields — filter_by auto-detected from linked doctype meta
    for fieldname in config.get("fields", []):
        value = getattr(doc, fieldname, None)
        if not value:
            continue
        linked_dt = _get_linked_doctype(doc.doctype, fieldname)
        err = _check_company(linked_dt, value, company, fieldname)
        if err:
            errors.append(err)

    # child table fields
    for table_fieldname, child_fields in config.get("child_tables", {}).items():
        rows = getattr(doc, table_fieldname, []) or []
        if not rows:
            continue

        child_dt = _get_child_doctype(doc.doctype, table_fieldname)
        if not child_dt:
            continue

        for fieldname in child_fields:
            linked_dt = _get_linked_doctype(child_dt, fieldname)
            if not linked_dt:
                continue

            # batch: one DB query per field per table
            values = list({getattr(r, fieldname) for r in rows if getattr(r, fieldname, None)})
            if not values:
                continue

            records = frappe.get_all(
                linked_dt,
                filters={"name": ["in", values]},
                fields=["name", "custom_company"]
            )
            company_map = {r.name: r.custom_company for r in records}

            for row in rows:
                val = getattr(row, fieldname, None)
                if not val:
                    continue
                rec_company = company_map.get(val)
                if rec_company and rec_company != company:
                    errors.append(
                        _("Row {0} — {1} '{2}' belongs to company '{3}', not '{4}'.").format(
                            row.idx, fieldname, val, rec_company, company
                        )
                    )

    # custom doctypes (party_type-aware)
    if config.get("custom"):
        errors.extend(_validate_custom(doc, company))

    if not errors:
        return

    # import: warn but don't block; UI/API: hard throw
    if getattr(frappe.flags, "in_import", False):
        frappe.msgprint(
            "<br>".join(errors),
            title=_("Company Mismatch Warning (Import)"),
            indicator="orange"
        )
    else:
        frappe.throw(
            "<br>".join(errors),
            title=_("Company Mismatch"),
            exc=frappe.ValidationError
        )


# ─────────────────────────────────────────────────────────────
#  CUSTOM VALIDATORS  (party_type-aware)
# ─────────────────────────────────────────────────────────────

def _validate_custom(doc, company):
    if doc.doctype == "Payment Entry":
        return _validate_payment_entry(doc, company)
    if doc.doctype == "Journal Entry":
        return _validate_journal_entry(doc, company)
    if doc.doctype == "Bank Account":
        return _validate_bank_account(doc, company)
    return []


def _validate_payment_entry(doc, company):
    errors = []
    err = _check_company("Bank Account", getattr(doc, "bank_account", None), company, "Bank Account")
    if err:
        errors.append(err)

    party_type = getattr(doc, "party_type", None)
    party      = getattr(doc, "party", None)
    if party_type and party:
        err = _check_company(party_type, party, company, "Party")
        if err:
            errors.append(err)
    return errors


def _validate_journal_entry(doc, company):
    errors = []
    for row in getattr(doc, "accounts", []) or []:
        err = _check_company("Bank Account", getattr(row, "bank_account", None),
                              company, f"Row {row.idx} Bank Account")
        if err:
            errors.append(err)

        err = _check_company("Project", getattr(row, "project", None),
                              company, f"Row {row.idx} Project")
        if err:
            errors.append(err)

        party_type = getattr(row, "party_type", None)
        party      = getattr(row, "party", None)
        if party_type and party:
            err = _check_company(party_type, party, company, f"Row {row.idx} Party")
            if err:
                errors.append(err)
    return errors


def _validate_bank_account(doc, company):
    errors = []
    party_type = getattr(doc, "party_type", None)
    party      = getattr(doc, "party", None)
    if party_type and party:
        err = _check_company(party_type, party, company, "Party")
        if err:
            errors.append(err)
    return errors
