import nepali_datetime

import frappe
from frappe import _
from frappe.utils import getdate


def execute(filters=None):
    filters = filters or {}
    _validate_permissions(filters)

    summarized = filters.get("report_type") == "Summarized"
    columns = _get_summarized_columns() if summarized else _get_detail_columns()

    # When the period is incomplete (e.g. the very first auto-load before the
    # Nepali Year/Month defaults are populated) we show an empty report rather
    # than raising an error — keeps the page clean and error-free.
    if not _resolve_period(filters):
        return columns, []

    if summarized:
        data = _get_summarized_data(filters)
    else:
        data = _add_detail_totals_row(_add_nepali_dates(_get_detail_data(filters)))

    return columns, data


# ─────────────────────────────────────────────────────────────
#  NEPALI (BIKRAM SAMBAT) CALENDAR
# ─────────────────────────────────────────────────────────────

NEPALI_MONTHS = [
    "Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
]


def _bs_month_to_gregorian_range(year, month):
    """Convert a Bikram Sambat (year, month) to a Gregorian (start, end) date pair."""
    from datetime import timedelta

    start = nepali_datetime.date(year, month, 1).to_datetime_date()
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    end = nepali_datetime.date(next_year, next_month, 1).to_datetime_date() - timedelta(days=1)
    return start, end


def _resolve_period(filters):
    """Validate the reporting period.

    Returns True when a usable from/to date range is available, False when the
    period is still incomplete (caller should render an empty report rather
    than raising). Raises only for a genuinely invalid range (From after To).

    Nepali-month filtering is handled in the browser by the shared dual-date /
    "Select Month" widget (rdp_common_app/report_nepali_date.js), which writes
    the chosen Bikram Sambat month back into from_date / to_date.
    """
    if not filters.get("from_date") or not filters.get("to_date"):
        return False

    if filters["from_date"] > filters["to_date"]:
        frappe.throw(_("From Date cannot be after To Date."))

    return True


def _to_nepali_date_str(gregorian_date):
    """Format a Gregorian date as a Bikram Sambat date string, e.g. '2082-12-05'."""
    if not gregorian_date:
        return ""
    try:
        bs = nepali_datetime.date.from_datetime_date(getdate(gregorian_date))
        return "{0:04d}-{1:02d}-{2:02d}".format(bs.year, bs.month, bs.day)
    except Exception:
        return ""


def _add_nepali_dates(rows):
    # Many detail rows share the same posting_date, so convert each distinct
    # date once and reuse the cached Bikram Sambat string.
    cache = {}
    for row in rows:
        posting_date = row.get("posting_date")
        if posting_date not in cache:
            cache[posting_date] = _to_nepali_date_str(posting_date)
        row["nepali_date"] = cache[posting_date]
    return rows


@frappe.whitelist()
def get_default_nepali_month():
    """Return the current Bikram Sambat month and its Gregorian (AD) date range.

    Used by the report's JS to default the period to the running Nepali month,
    so the report opens "in Nepali month" out of the box.
    """
    today = nepali_datetime.date.today()
    from_date, to_date = _bs_month_to_gregorian_range(today.year, today.month)
    return {
        "year": today.year,
        "month": today.month,
        "month_name": NEPALI_MONTHS[today.month - 1],
        "bs_label": "{0} {1}".format(NEPALI_MONTHS[today.month - 1], today.year),
        "from_date": str(from_date),
        "to_date": str(to_date),
    }


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


def _get_rate_precision():
    # Rates should show 5 decimals (as requested) regardless of system defaults.
    return 5


def _get_detail_columns():
    precision = _get_float_precision()
    rate_precision = _get_rate_precision()
    return [
        {
            "fieldname": "posting_date",
            "label": _("Date"),
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "fieldname": "nepali_date",
            "label": _("Nepali Date (BS)"),
            "fieldtype": "Data",
            "width": 130,
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
            "precision": rate_precision,
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
            "fieldname": "stock_rate",
            "label": _("Rate of Stock UOM (NPR)"),
            "fieldtype": "Currency",
            "precision": rate_precision,
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
            COALESCE(
                NULLIF(sii.stock_uom_rate, 0),
                (sii.rate / NULLIF(sii.conversion_factor, 0))
            )                   AS stock_rate,
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
                    THEN ABS(sii.qty) ELSE -ABS(sii.qty) END
                )                               AS total_sales_qty,
                SUM(
                    CASE WHEN si.is_return = 0
                    THEN ABS(sii.stock_qty) ELSE -ABS(sii.stock_qty) END
                )                               AS total_stock_qty,
                sii.stock_uom,
                SUM(
                    CASE WHEN si.is_return = 0
                    THEN ABS(sii.amount) ELSE -ABS(sii.amount) END
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
        "balance": total_balance,
        "bold": 1,
    }
    return list(rows) + [total_row]


def _add_detail_totals_row(rows):
    if not rows:
        return rows

    total_sales_qty = sum(r.get("sales_qty") or 0 for r in rows)
    total_stock_qty = sum(r.get("stock_qty") or 0 for r in rows)
    total_balance = sum(r.get("balance") or 0 for r in rows)

    total_row = {
        "posting_date": None,
        "nepali_date": "",
        "voucher_type": _("Total"),
        "voucher_no": "",
        "item_code": "",
        "sales_qty": total_sales_qty,
        "sales_uom": "",
        "sales_rate": None,
        "stock_qty": total_stock_qty,
        "stock_uom": "",
        "stock_rate": None,
        "balance": total_balance,
        "bold": 1,
    }

    return list(rows) + [total_row]
