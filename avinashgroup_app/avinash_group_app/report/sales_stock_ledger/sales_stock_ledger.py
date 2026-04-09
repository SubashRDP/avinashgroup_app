import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    _validate_permissions(filters)

    if filters.get("report_type") == "Summarized":
        columns = _get_summarized_columns()
        data = _get_summarized_data(filters)
    else:
        columns = _get_detail_columns()
        data = _get_detail_data(filters)

    return columns, data


# ─────────────────────────────────────────────────────────────
#  PERMISSION
# ─────────────────────────────────────────────────────────────

def _validate_permissions(filters):
    if not filters.get("company"):
        return
    allowed = {c.name for c in frappe.get_list("Company", fields=["name"])}
    if filters["company"] not in allowed:
        frappe.throw(_("Not authorized to view report for company: {0}").format(filters["company"]))


# ─────────────────────────────────────────────────────────────
#  COLUMNS
# ─────────────────────────────────────────────────────────────

def _get_float_precision():
    from frappe.utils import cint
    return cint(frappe.db.get_default("float_precision")) or 2


def _get_detail_columns():
    precision = _get_float_precision()
    return [
        {
            "fieldname": "posting_date",
            "label": _("Date"),
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "fieldname": "voucher_type",
            "label": _("Voucher Type"),
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "voucher_no",
            "label": _("Voucher No"),
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 160,
        },
        {
            "fieldname": "item_code",
            "label": _("Item"),
            "fieldtype": "Link",
            "options": "Item",
            "width": 150,
        },
        {
            "fieldname": "sales_qty",
            "label": _("Sales Qty"),
            "fieldtype": "Float",
            "precision": precision,
            "width": 100,
        },
        {
            "fieldname": "sales_uom",
            "label": _("UOM"),
            "fieldtype": "Link",
            "options": "UOM",
            "width": 80,
        },
        {
            "fieldname": "sales_rate",
            "label": _("Sales Rate"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "stock_qty",
            "label": _("Stock Qty"),
            "fieldtype": "Float",
            "precision": precision,
            "width": 100,
        },
        {
            "fieldname": "stock_uom",
            "label": _("Stock UOM"),
            "fieldtype": "Link",
            "options": "UOM",
            "width": 100,
        },
        {
            "fieldname": "valuation_rate",
            "label": _("Valuation Rate"),
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "balance",
            "label": _("Balance"),
            "fieldtype": "Currency",
            "width": 160,
        },
    ]


def _get_summarized_columns():
    precision = _get_float_precision()
    return [
        {
            "fieldname": "item_code",
            "label": _("Item"),
            "fieldtype": "Link",
            "options": "Item",
            "width": 180,
        },
        {
            "fieldname": "voucher_type",
            "label": _("Type"),
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "total_sales_qty",
            "label": _("Sales Qty"),
            "fieldtype": "Float",
            "precision": precision,
            "width": 110,
        },
        {
            "fieldname": "sales_uom",
            "label": _("UOM"),
            "fieldtype": "Link",
            "options": "UOM",
            "width": 80,
        },
        {
            "fieldname": "total_stock_qty",
            "label": _("Stock Qty"),
            "fieldtype": "Float",
            "precision": precision,
            "width": 110,
        },
        {
            "fieldname": "stock_uom",
            "label": _("Stock UOM"),
            "fieldtype": "Link",
            "options": "UOM",
            "width": 100,
        },
        {
            "fieldname": "valuation_rate",
            "label": _("Valuation Rate"),
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "balance",
            "label": _("Balance"),
            "fieldtype": "Currency",
            "width": 160,
        },
    ]


# ─────────────────────────────────────────────────────────────
#  CONDITIONS BUILDER
# ─────────────────────────────────────────────────────────────

def _build_conditions(filters):
    cond = []
    vals = {}

    if filters.get("company"):
        cond.append("si.company = %(company)s")
        vals["company"] = filters["company"]

    if filters.get("from_date"):
        cond.append("si.posting_date >= %(from_date)s")
        vals["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        cond.append("si.posting_date <= %(to_date)s")
        vals["to_date"] = filters["to_date"]

    if filters.get("warehouse"):
        cond.append("sii.warehouse = %(warehouse)s")
        vals["warehouse"] = filters["warehouse"]

    if filters.get("item"):
        cond.append("sii.item_code = %(item)s")
        vals["item"] = filters["item"]

    if filters.get("item_group"):
        cond.append("item.item_group = %(item_group)s")
        vals["item_group"] = filters["item_group"]

    if filters.get("price_list"):
        cond.append("si.selling_price_list = %(price_list)s")
        vals["price_list"] = filters["price_list"]

    if filters.get("uom"):
        cond.append("sii.uom = %(uom)s")
        vals["uom"] = filters["uom"]

    if filters.get("branch"):
        if frappe.db.has_column("Sales Invoice", "custom_branch"):
            cond.append("si.custom_branch = %(branch)s")
            vals["branch"] = filters["branch"]

    if filters.get("voucher_no"):
        cond.append("si.name = %(voucher_no)s")
        vals["voucher_no"] = filters["voucher_no"]

    if filters.get("voucher_type") == "Sales Invoice":
        cond.append("si.is_return = 0")
    elif filters.get("voucher_type") == "Sales Return":
        cond.append("si.is_return = 1")

    where = ("AND " + " AND ".join(cond)) if cond else ""
    return where, vals


# ─────────────────────────────────────────────────────────────
#  DETAIL
# ─────────────────────────────────────────────────────────────

def _get_detail_data(filters):
    where, vals = _build_conditions(filters)

    query = """
        SELECT
            si.posting_date,
            CASE WHEN si.is_return = 1 THEN 'Sales Return' ELSE 'Sales Invoice' END AS voucher_type,
            si.name             AS voucher_no,
            sii.item_code,
            sii.qty             AS sales_qty,
            sii.uom             AS sales_uom,
            sii.rate            AS sales_rate,
            sii.stock_qty,
            sii.stock_uom,
            sii.base_price_list_rate    AS valuation_rate,
            sii.amount          AS balance
        FROM
            `tabSales Invoice` si
            JOIN `tabSales Invoice Item` sii ON si.name = sii.parent
            JOIN `tabItem` item ON item.name = sii.item_code
        WHERE
            si.docstatus = 1
            AND item.is_stock_item = 1
            {where}
        ORDER BY
            si.posting_date,
            si.name,
            sii.idx
    """.format(where=where)

    return frappe.db.sql(query, vals, as_dict=True)


# ─────────────────────────────────────────────────────────────
#  SUMMARIZED
# ─────────────────────────────────────────────────────────────

def _get_summarized_data(filters):
    where, vals = _build_conditions(filters)
    merge = filters.get("sales_return_merge")

    if merge:
        query = """
            SELECT
                sii.item_code,
                sii.uom                         AS sales_uom,
                NULL                            AS voucher_type,
                SUM(
                    CASE WHEN si.is_return = 0
                    THEN sii.qty ELSE -sii.qty END
                )                               AS total_sales_qty,
                SUM(
                    CASE WHEN si.is_return = 0
                    THEN sii.stock_qty ELSE -sii.stock_qty END
                )                               AS total_stock_qty,
                sii.stock_uom,
                AVG(sii.base_price_list_rate)   AS valuation_rate,
                SUM(
                    CASE WHEN si.is_return = 0
                    THEN sii.amount ELSE -sii.amount END
                )                               AS balance
            FROM
                `tabSales Invoice` si
                JOIN `tabSales Invoice Item` sii ON si.name = sii.parent
                JOIN `tabItem` item ON item.name = sii.item_code
            WHERE
                si.docstatus = 1
                AND item.is_stock_item = 1
                {where}
            GROUP BY
                sii.item_code,
                sii.uom,
                sii.stock_uom
            ORDER BY
                sii.item_code
        """.format(where=where)
    else:
        query = """
            SELECT
                sii.item_code,
                sii.uom                                 AS sales_uom,
                CASE WHEN si.is_return = 1
                     THEN 'Sales Return'
                     ELSE 'Sales Invoice'
                END                                     AS voucher_type,
                SUM(sii.qty)                            AS total_sales_qty,
                SUM(sii.stock_qty)                      AS total_stock_qty,
                sii.stock_uom,
                AVG(sii.base_price_list_rate)           AS valuation_rate,
                SUM(sii.amount)                         AS balance
            FROM
                `tabSales Invoice` si
                JOIN `tabSales Invoice Item` sii ON si.name = sii.parent
                JOIN `tabItem` item ON item.name = sii.item_code
            WHERE
                si.docstatus = 1
                AND item.is_stock_item = 1
                {where}
            GROUP BY
                sii.item_code,
                sii.uom,
                sii.stock_uom,
                si.is_return
            ORDER BY
                sii.item_code,
                sii.uom,
                si.is_return
        """.format(where=where)

    rows = frappe.db.sql(query, vals, as_dict=True)
    return _add_totals_row(rows)


# ─────────────────────────────────────────────────────────────
#  TOTALS ROW
# ─────────────────────────────────────────────────────────────

def _add_totals_row(rows):
    if not rows:
        return rows

    total_sales_qty = sum(r.get("total_sales_qty") or 0 for r in rows)
    total_stock_qty = sum(r.get("total_stock_qty") or 0 for r in rows)
    total_balance = sum(r.get("balance") or 0 for r in rows)

    total_row = {
        "item_code": _("Total"),
        "voucher_type": "",
        "total_sales_qty": total_sales_qty,
        "sales_uom": "",
        "total_stock_qty": total_stock_qty,
        "stock_uom": "",
        "valuation_rate": None,
        "balance": total_balance,
        "bold": 1,
    }
    return list(rows) + [total_row]
