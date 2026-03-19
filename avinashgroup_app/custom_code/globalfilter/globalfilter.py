import frappe
from frappe import _
from frappe.utils.caching import request_cache
from collections import defaultdict

# ─────────────────────────────────────────────────────────────
#  COMPANY FILTER CONFIG
#  company_field : field on the doc that holds the company value
#  fields        : top-level Link fields to validate
#  child_tables  : { table_fieldname: [child link fieldnames] }
#  custom        : True → extra party-type-aware logic in CompanyValidator
# ─────────────────────────────────────────────────────────────
FILTER_CONFIG = {
    "Asset": {
        "company_field": "company",
        "fields": ["item_code", "custodian", "purchase_receipt", "purchase_invoice"]
    },
    "Asset Category": {
        "company_field": "custom_company",
        "child_tables": {"accounts": ["company_name"]}
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
        "fields": ["party_name", "selling_price_list", "sales_partner"],
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
            "items": ["item_code", "manufacturer", "bom_no", "project", "wip_composite_asset"]
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
        "fields": ["supplier", "buying_price_list"],
        "child_tables": {"items": ["item_code", "warehouse", "project"]}
    },
    "Purchase Order": {
        "company_field": "company",
        "fields": ["supplier", "price_list"],
        "child_tables": {"items": ["item_code", "project", "wip_composite_asset"]}
    },
    "Purchase Receipt": {
        "company_field": "company",
        "fields": ["supplier", "price_list"],
        "child_tables": {"items": ["item_code", "batch_no", "project", "provisional_expense_account", "wip_composite_asset"]}
    },
    "Purchase Invoice": {
        "company_field": "company",
        "fields": ["supplier"],
        "child_tables": {
            "items":            ["item_code", "manufacturer", "project", "wip_composite_asset", "custom_subtype"],
            "payment_schedule": ["payment_term"]
        }
    },

    # custom=True → party-type-aware handling in CompanyValidator
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
#  HELPERS  (all @request_cache — resolved once per request)
# ─────────────────────────────────────────────────────────────

@request_cache
def _get_linked_doctype(doctype, fieldname):
    """Return the linked DocType for a Link field, or None."""
    try:
        df = frappe.get_meta(doctype).get_field(fieldname)
        if df and df.fieldtype == "Link":
            return df.options
    except Exception:
        pass
    return None


def _get_linked_doctype_from_doc(doc, fieldname):
    """Return linked DocType for Link/Dynamic Link using current doc values."""
    try:
        df = frappe.get_meta(doc.doctype).get_field(fieldname)
        if not df:
            return None
        if df.fieldtype == "Link":
            return df.options
        if df.fieldtype == "Dynamic Link":
            return getattr(doc, df.options, None)
    except Exception:
        pass
    return None


@request_cache
def _get_child_doctype(parent_doctype, table_fieldname):
    """Return the child DocType for a Table field, or None."""
    try:
        df = frappe.get_meta(parent_doctype).get_field(table_fieldname)
        if df and df.fieldtype in ("Table", "Table MultiSelect"):
            return df.options
    except Exception:
        pass
    return None


@request_cache
def _resolve_company_field(linked_doctype):
    """
    Return the field that holds the company value on linked_doctype:
      'name'           → linked_doctype is Company itself
      'company'        → standard company field exists
      'custom_company' → custom company field exists
      None             → no company association (e.g. Manufacturer) — skip validation
    """
    if linked_doctype == "Company":
        return "name"
    try:
        meta = frappe.get_meta(linked_doctype)
        if meta.get_field("company"):
            return "company"
        if meta.get_field("custom_company"):
            return "custom_company"
    except Exception:
        pass
    return None


def _get_company_map(linked_dt, values):
    """
    Batch-fetch the company value for all given names in linked_dt.
    Returns {name: company_value}. Returns {} if the doctype has no
    company field (caller skips validation automatically).
    Uses frappe.db.get_values with a list filter → lean frappe.qb path,
    no permission-layer overhead, no default ORDER BY.
    """
    if not values:
        return {}
    company_field = _resolve_company_field(linked_dt)
    if not company_field:
        return {}
    rows = frappe.db.get_values(
        linked_dt,
        filters=list(values),
        fieldname=["name", company_field],
        as_dict=True,
        order_by=None,
    ) or []
    return {r["name"]: r.get(company_field) for r in rows}


# ─────────────────────────────────────────────────────────────
#  COMPANY VALIDATOR
#  Phase 1 (collect) — gather all linked values, zero DB calls
#  Phase 2 (query)   — one frappe.db.get_values() per linked DocType
#  Phase 3 (check)   — validate from in-memory maps, build errors
# ─────────────────────────────────────────────────────────────

class CompanyValidator:

    def __init__(self, doc):
        self.doc     = doc
        self.config  = None
        self.company = None
        self._pending      = defaultdict(set)  
        self._company_maps = {}                

    # ── Phase 1: collect ─────────────────────────────────────────────────────

    def _collect_top_level(self):
        for fieldname in self.config.get("fields", []):
            val = getattr(self.doc, fieldname, None)
            if not val:
                continue
            linked_dt = _get_linked_doctype_from_doc(self.doc, fieldname)
            if linked_dt:
                self._pending[linked_dt].add(val)

    def _collect_child_tables(self):
        for table_fn, child_fields in self.config.get("child_tables", {}).items():
            rows = getattr(self.doc, table_fn, []) or []
            if not rows:
                continue
            child_dt = _get_child_doctype(self.doc.doctype, table_fn)
            if not child_dt:
                continue
            for fieldname in child_fields:
                cdf = frappe.get_meta(child_dt).get_field(fieldname)
                if not cdf:
                    continue
                for row in rows:
                    val = getattr(row, fieldname, None)
                    if not val:
                        continue
                    if cdf.fieldtype == "Link":
                        linked_dt = cdf.options
                    elif cdf.fieldtype == "Dynamic Link":
                        linked_dt = getattr(row, cdf.options, None)
                    else:
                        linked_dt = None
                    if linked_dt:
                        self._pending[linked_dt].add(val)

    def _collect_journal_entry(self):
        for row in getattr(self.doc, "accounts", []) or []:
            ba    = getattr(row, "bank_account", None)
            proj  = getattr(row, "project",      None)
            pt    = getattr(row, "party_type",   None)
            party = getattr(row, "party",        None)
            if ba:           self._pending["Bank Account"].add(ba)
            if proj:         self._pending["Project"].add(proj)
            if pt and party: self._pending[pt].add(party)

    def _collect_payment_entry(self):
        ba    = getattr(self.doc, "bank_account", None)
        pt    = getattr(self.doc, "party_type",   None)
        party = getattr(self.doc, "party",        None)
        if ba:           self._pending["Bank Account"].add(ba)
        if pt and party: self._pending[pt].add(party)

    def _collect_bank_account(self):
        pt    = getattr(self.doc, "party_type", None)
        party = getattr(self.doc, "party",      None)
        if pt and party: self._pending[pt].add(party)

    # ── Phase 2: batch query ──────────────────────────────────────────────────

    def _batch_query(self):
        for linked_dt, values in self._pending.items():
            if linked_dt == "Company":
                # Company.name IS the company — resolve in-memory, no DB call
                self._company_maps["Company"] = {v: v for v in values}
            else:
                self._company_maps[linked_dt] = _get_company_map(linked_dt, list(values))

    # ── Phase 3: check ────────────────────────────────────────────────────────

    def _mismatch(self, linked_dt, value, label):
        """Return an error string if value's company != self.company, else None."""
        if not value or not linked_dt:
            return None
        rec_co = self._company_maps.get(linked_dt, {}).get(value)
        if rec_co and rec_co != self.company:
            return _("'{0}' ({1}) belongs to '{2}', not '{3}'.").format(
                value, label, rec_co, self.company
            )
        return None

    def _check_top_level(self):
        errors = []
        for fieldname in self.config.get("fields", []):
            val = getattr(self.doc, fieldname, None)
            if not val:
                continue
            linked_dt = _get_linked_doctype_from_doc(self.doc, fieldname)
            err = self._mismatch(linked_dt, val, fieldname)
            if err:
                errors.append(err)
        return errors

    def _check_child_tables(self):
        errors = []
        for table_fn, child_fields in self.config.get("child_tables", {}).items():
            rows = getattr(self.doc, table_fn, []) or []
            if not rows:
                continue
            child_dt = _get_child_doctype(self.doc.doctype, table_fn)
            if not child_dt:
                continue
            for fieldname in child_fields:
                cdf = frappe.get_meta(child_dt).get_field(fieldname)
                if not cdf:
                    continue
                for row in rows:
                    val = getattr(row, fieldname, None)
                    if not val:
                        continue
                    if cdf.fieldtype == "Link":
                        linked_dt = cdf.options
                    elif cdf.fieldtype == "Dynamic Link":
                        linked_dt = getattr(row, cdf.options, None)
                    else:
                        linked_dt = None
                    err = self._mismatch(linked_dt, val, f"Row {row.idx} — {fieldname}")
                    if err:
                        errors.append(err)
        return errors

    def _check_journal_entry(self):
        errors = []
        for row in getattr(self.doc, "accounts", []) or []:
            for linked_dt, val, label in [
                ("Bank Account", getattr(row, "bank_account", None), f"Row {row.idx} — bank_account"),
                ("Project",      getattr(row, "project",      None), f"Row {row.idx} — project"),
            ]:
                err = self._mismatch(linked_dt, val, label)
                if err:
                    errors.append(err)
            pt    = getattr(row, "party_type", None)
            party = getattr(row, "party",      None)
            if pt and party:
                err = self._mismatch(pt, party, f"Row {row.idx} — party")
                if err:
                    errors.append(err)
        return errors

    def _check_payment_entry(self):
        errors = []
        ba    = getattr(self.doc, "bank_account", None)
        pt    = getattr(self.doc, "party_type",   None)
        party = getattr(self.doc, "party",        None)
        for linked_dt, val, label in [
            ("Bank Account", ba,    "bank_account"),
            (pt,             party, "party") if pt and party else (None, None, None),
        ]:
            err = self._mismatch(linked_dt, val, label)
            if err:
                errors.append(err)
        return errors

    def _check_bank_account(self):
        errors = []
        pt    = getattr(self.doc, "party_type", None)
        party = getattr(self.doc, "party",      None)
        if pt and party:
            err = self._mismatch(pt, party, "party")
            if err:
                errors.append(err)
        return errors

    # ── Orchestrator ──────────────────────────────────────────────────────────

    def validate(self):
        config = FILTER_CONFIG.get(self.doc.doctype)
        if not config:
            return []

        self.config  = config
        self.company = getattr(self.doc, config.get("company_field", "company"), None)
        if not self.company:
            return []

        doctype = self.doc.doctype

        # Phase 1 — collect (zero DB calls)
        self._collect_top_level()
        self._collect_child_tables()
        if config.get("custom"):
            if doctype == "Journal Entry":    self._collect_journal_entry()
            elif doctype == "Payment Entry":  self._collect_payment_entry()
            elif doctype == "Bank Account":   self._collect_bank_account()

        # Phase 2 — one query per distinct linked DocType
        self._batch_query()

        # Phase 3 — build errors from in-memory maps
        errors = []
        errors.extend(self._check_top_level())
        errors.extend(self._check_child_tables())
        if config.get("custom"):
            if doctype == "Journal Entry":    errors.extend(self._check_journal_entry())
            elif doctype == "Payment Entry":  errors.extend(self._check_payment_entry())
            elif doctype == "Bank Account":   errors.extend(self._check_bank_account())

        return errors


# ─────────────────────────────────────────────────────────────
#  MAIN VALIDATOR — called from validate hook
# ─────────────────────────────────────────────────────────────

def validate_company_matching(doc, method=None):
    errors = CompanyValidator(doc).validate()
    if not errors:
        return

    if getattr(frappe.flags, "in_import", False):
        # Warn but don't block during bulk imports
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
#  FILTER CONFIG API — exposes FILTER_CONFIG to JS
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_filter_config():
    """
    Expose FILTER_CONFIG to company_filter.js so the JS doesn't need
    a mirrored static copy. The 'custom' key is backend-only and stripped.
    """
    return {
        dt: {k: v for k, v in cfg.items() if k != "custom"}
        for dt, cfg in FILTER_CONFIG.items()
    }


# ─────────────────────────────────────────────────────────────
#  LINK QUERY — party filtered by company (used by global_filter.js)
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def search_party(doctype, txt, searchfield, start, page_len, filters):
    filters    = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    party_type = filters.get("party_type")
    company    = filters.get("company")
    if not party_type:
        return []

    try:
        meta = frappe.get_meta(party_type)
    except Exception:
        return []

    company_field = _resolve_company_field(party_type)
    query_filters = {}
    if company and company_field:
        query_filters[company_field] = company
    if meta.get_field("disabled"):
        query_filters["disabled"] = 0

    or_filters = []
    if txt:
        or_filters.append(["name", "like", f"%{txt}%"])
        if searchfield and searchfield != "name":
            or_filters.append([searchfield, "like", f"%{txt}%"])

    records = frappe.get_list(
        party_type,
        filters=query_filters,
        or_filters=or_filters or None,
        fields=["name"],
        start=start,
        page_length=page_len,
        order_by="name asc"
    )

    return [[r.name] for r in records]
