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
        "fields": ["customer", "selling_price_list"],
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
            "items":            ["item_code", "manufacturer", "project", "wip_composite_asset"],
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

    # Master doctypes — use custom_company
    "Customer": {
        "company_field": "custom_company",
        "fields": ["customer_group", "default_price_list", "default_bank_account", "default_company_bank_account"]
    },
    "Supplier": {
        "company_field": "custom_company",
        "fields": ["supplier_group", "default_price_list", "default_bank_account", "default_company_bank_account"]
    },
    "Item": {
        "company_field": "custom_company",
        "fields": ["item_group", "asset_category"],
        "child_tables": {
            "supplier_items": ["supplier"],
            "customer_items": ["customer_name"],
            "taxes":          ["item_tax_template"]
        }
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


@request_cache
def _get_allowed_transact_parents(linked_doctype, company):
    """
    Return parent names for doctypes that use the "Allowed To Transact With"
    child table to store company association (e.g., Customer, Supplier).
    """
    if not linked_doctype or not company:
        return []
    try:
        meta = frappe.get_meta(linked_doctype)
        df = meta.get_field("companies")
        if not df or df.options != "Allowed To Transact With":
            return []
        return frappe.get_all(
            "Allowed To Transact With",
            filters={"company": company, "parenttype": linked_doctype},
            pluck="parent",
        ) or []
    except Exception:
        return []


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
        # if config.get("custom"):
        #     if doctype == "Journal Entry":    self._collect_journal_entry()
        #     elif doctype == "Payment Entry":  self._collect_payment_entry()
        #     elif doctype == "Bank Account":   self._collect_bank_account()

        # Phase 2 — one query per distinct linked DocType
        self._batch_query()

        # Phase 3 — build errors from in-memory maps
        errors = []
        errors.extend(self._check_top_level())
        errors.extend(self._check_child_tables())
        # if config.get("custom"):
        #     if doctype == "Journal Entry":    errors.extend(self._check_journal_entry())
        #     elif doctype == "Payment Entry":  errors.extend(self._check_payment_entry())
        #     elif doctype == "Bank Account":   errors.extend(self._check_bank_account())

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
    Returns filter config for JS engine.
    Redis-cached — cleared when Company Filter Config is saved/deleted.
    Falls back to hardcoded FILTER_CONFIG before first migrate.
    """
    cache_key = "company_filter_config"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached

    try:
        if not frappe.db.table_exists("Company Filter Config"):
            raise Exception("table not ready")

        # ignore_permissions — this is system config, not user data
        configs = frappe.get_all(
            "Company Filter Config",
            fields=["name", "doctype_name", "company_field"],
            ignore_permissions=True
        )

        if not configs:
            raise Exception("no records — use fallback")

        # Fetch ALL child rows in one query (avoids N+1)
        all_rows = frappe.get_all(
            "Company Filter Field",
            filters={"parent": ["in", [c.name for c in configs]]},
            fields=["parent", "fieldname", "is_child_table", "child_fieldname",
                    "is_dynamic_link", "dynamic_link_field"],
            order_by="parent, idx asc",
            ignore_permissions=True
        )

        rows_by_parent = {}
        for r in all_rows:
            rows_by_parent.setdefault(r.parent, []).append(r)

        result = {}
        for config in configs:
            rows = rows_by_parent.get(config.name, [])
            # Return objects for dynamic-link fields so JS knows to use
            # search_link_by_company; plain strings for regular Link fields.
            top_fields = []
            for r in rows:
                if r.is_child_table:
                    continue
                if r.is_dynamic_link and r.dynamic_link_field:
                    top_fields.append({
                        "fieldname": r.fieldname,
                        "is_dynamic_link": True,
                        "dynamic_link_field": r.dynamic_link_field
                    })
                else:
                    top_fields.append(r.fieldname)
            child_tables = {}
            for r in rows:
                if r.is_child_table and r.child_fieldname:
                    if r.is_dynamic_link and r.dynamic_link_field:
                        child_tables.setdefault(r.fieldname, []).append({
                            "fieldname": r.child_fieldname,
                            "is_dynamic_link": True,
                            "dynamic_link_field": r.dynamic_link_field
                        })
                    else:
                        child_tables.setdefault(r.fieldname, []).append(r.child_fieldname)

            result[config.doctype_name] = {
                "company_field": config.company_field,
                "fields": top_fields,
                "child_tables": child_tables
            }

        # Pre-resolve company field for every linked doctype referenced in the config
        # so the JS engine doesn't need frappe.get_meta() on linked doctypes at runtime.
        filter_keys = {}
        for config in configs:
            doctype_name = config.doctype_name
            rows = rows_by_parent.get(config.name, [])
            for r in rows:
                try:
                    if not r.is_child_table:
                        df = frappe.get_meta(doctype_name).get_field(r.fieldname)
                        if df and df.fieldtype == "Link" and df.options:
                            linked_dt = df.options
                            if linked_dt not in result and linked_dt not in filter_keys:
                                filter_keys[linked_dt] = _resolve_company_field(linked_dt) or ""
                    else:
                        tdf = frappe.get_meta(doctype_name).get_field(r.fieldname)
                        if tdf and tdf.options:
                            cdf = frappe.get_meta(tdf.options).get_field(r.child_fieldname)
                            if cdf and cdf.fieldtype == "Link" and cdf.options:
                                linked_dt = cdf.options
                                if linked_dt not in result and linked_dt not in filter_keys:
                                    filter_keys[linked_dt] = _resolve_company_field(linked_dt) or ""
                except Exception:
                    pass

        result["__filter_keys__"] = filter_keys
        frappe.cache().set_value(cache_key, result)
        return result

    except Exception:
        # Fallback to hardcoded config (before first migrate)
        return {
            dt: {k: v for k, v in cfg.items() if k != "custom"}
            for dt, cfg in FILTER_CONFIG.items()
        }


def clear_filter_config_cache(doc, method=None):
    """Called by hooks when Company Filter Config is saved/deleted."""
    frappe.cache().delete_value("company_filter_config")
    '''
    frappe.msgprint(
        f"Company Filter cache cleared for <b>{doc.name}</b>. Refresh your browser to apply changes.",
        indicator="green",
        alert=True
    )
    '''


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

    title_field = meta.title_field if meta.show_title_field_in_link and meta.title_field else None

    company_field = _resolve_company_field(party_type)
    query_filters = {}
    if company and company_field:
        query_filters[company_field] = company
    elif company:
        parents = _get_allowed_transact_parents(party_type, company)
        if parents:
            query_filters["name"] = ["in", parents]
        else:
            return []
    if meta.get_field("disabled"):
        query_filters["disabled"] = 0

    or_filters = []
    if txt:
        or_filters.append(["name", "like", f"%{txt}%"])
        if searchfield and searchfield != "name":
            or_filters.append([searchfield, "like", f"%{txt}%"])
        if title_field and title_field != "name":
            or_filters.append([title_field, "like", f"%{txt}%"])
        if meta.search_fields:
            for field in meta.search_fields.split(","):
                field = field.strip()
                if field and field not in {"name", searchfield, title_field}:
                    or_filters.append([field, "like", f"%{txt}%"])

    fields = ["name"]
    if title_field:
        fields.append(title_field)

    records = frappe.get_list(
        party_type,
        filters=query_filters,
        or_filters=or_filters or None,
        fields=fields,
        start=start,
        page_length=page_len,
        order_by="name asc"
    )

    if title_field:
        return [[r.name, getattr(r, title_field, None)] for r in records]
    return [[r.name] for r in records]


# ─────────────────────────────────────────────────────────────
#  LINK QUERY — generic company-filtered search for Dynamic Link
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def search_link_by_company(doctype, txt, searchfield, start, page_len, filters):
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    linked_dt = filters.get("linked_doctype")
    company = filters.get("company")
    if not linked_dt:
        return []

    try:
        meta = frappe.get_meta(linked_dt)
    except Exception:
        return []

    title_field = meta.title_field if meta.show_title_field_in_link and meta.title_field else None

    company_field = _resolve_company_field(linked_dt)
    query_filters = {}
    if company and company_field:
        query_filters[company_field] = company
    elif company:
        parents = _get_allowed_transact_parents(linked_dt, company)
        if parents:
            query_filters["name"] = ["in", parents]
        else:
            # No company field and no "Allowed To Transact With" table.
            pass

    if meta.get_field("disabled"):
        query_filters["disabled"] = 0

    or_filters = []
    if txt:
        or_filters.append(["name", "like", f"%{txt}%"])
        if searchfield and searchfield != "name":
            or_filters.append([searchfield, "like", f"%{txt}%"])
        if title_field and title_field != "name":
            or_filters.append([title_field, "like", f"%{txt}%"])
        if meta.search_fields:
            for field in meta.search_fields.split(","):
                field = field.strip()
                if field and field not in {"name", searchfield, title_field}:
                    or_filters.append([field, "like", f"%{txt}%"])

    fields = ["name"]
    if title_field:
        fields.append(title_field)

    records = frappe.get_list(
        linked_dt,
        filters=query_filters,
        or_filters=or_filters or None,
        fields=fields,
        start=start,
        page_length=page_len,
        order_by="name asc"
    )


    if title_field:
        return [[r.name, getattr(r, title_field, None)] for r in records]
    return [[r.name] for r in records]