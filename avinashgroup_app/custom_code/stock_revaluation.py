import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate


REPOST_QUEUE = "long"
REPOST_TIMEOUT = 7200


def on_purchase_invoice_submit(doc, method=None):
    """Warn users that backdated stock reposting runs in the night window."""
    if not cint(doc.update_stock):
        return

    if getdate(doc.posting_date) >= getdate(nowdate()):
        return

    frappe.logger("stock_revaluation").info(
        "Backdated stock Purchase Invoice %s submitted for %s. "
        "Any generated Repost Item Valuation will run in the nightly job.",
        doc.name,
        doc.posting_date,
    )

    frappe.msgprint(
        _(
            "This is a backdated Purchase Invoice with Update Stock. "
            "Stock valuation reposting will run in the nightly job after 2 AM."
        ),
        title=_("Stock Reposting Scheduled"),
        indicator="orange",
    )


def nightly_process_pending_reposts():
    """Run pending stock valuation reposts in the nightly low-traffic window.

    This intentionally avoids forcing work every few minutes. Heavy moving-average
    reposting can touch thousands of Stock Ledger and GL rows, so we only process
    it from the scheduler after 2 AM.
    """
    pending = _get_pending_reposts()
    if not pending:
        frappe.logger("stock_revaluation").info("No pending stock reposts found.")
        return {"queued": 0}

    queued = 0
    for row in pending:
        if row.status == "Failed":
            _restart_failed_repost(row.name)

        frappe.enqueue(
            "avinashgroup_app.custom_code.stock_revaluation.process_single_repost",
            repost_name=row.name,
            queue=REPOST_QUEUE,
            timeout=REPOST_TIMEOUT,
            is_async=True,
            job_name=f"nightly_stock_repost:{row.name}",
        )
        queued += 1

    frappe.logger("stock_revaluation").info(
        "Queued %s stock valuation repost(s) for nightly processing.", queued
    )
    return {"queued": queued, "entries": [row.name for row in pending]}


def process_single_repost(repost_name):
    """Process one Repost Item Valuation using ERPNext's own repost engine."""
    from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import repost

    if not frappe.db.exists("Repost Item Valuation", repost_name):
        return

    doc = frappe.get_doc("Repost Item Valuation", repost_name)
    if doc.status in ("Completed", "Skipped"):
        return

    if doc.status == "Failed":
        doc.restart_reposting()
        frappe.db.commit()
        doc.reload()

    repost(doc)


@frappe.whitelist()
def reprocess_all_pending():
    """Manually queue all pending stock reposts for the nightly processor."""
    frappe.only_for("System Manager")
    return nightly_process_pending_reposts()


@frappe.whitelist()
def get_repost_status():
    frappe.only_for(["System Manager", "Stock Manager"])

    summary = frappe.db.sql(
        """
        SELECT status, COUNT(*) AS count
        FROM `tabRepost Item Valuation`
        WHERE docstatus = 1
        GROUP BY status
        """,
        as_dict=True,
    )

    pending = frappe.get_all(
        "Repost Item Valuation",
        filters={"status": ["in", ["Queued", "In Progress", "Failed"]], "docstatus": 1},
        fields=[
            "name",
            "status",
            "based_on",
            "item_code",
            "warehouse",
            "voucher_type",
            "voucher_no",
            "posting_date",
            "creation",
            "modified",
            "error_log",
        ],
        order_by="timestamp(posting_date, posting_time) asc, creation asc",
        limit=100,
    )

    return {
        "summary": {row.status: row.count for row in summary},
        "pending": pending,
    }


def create_and_run_repost(item_code, warehouse, posting_date, posting_time="00:00:00"):
    """Diagnostic helper to create and run one item/warehouse repost."""
    before = frappe.db.get_value(
        "Bin",
        {"item_code": item_code, "warehouse": warehouse},
        ["actual_qty", "valuation_rate", "stock_value"],
        as_dict=True,
    )

    doc = frappe.get_doc({
        "doctype": "Repost Item Valuation",
        "based_on": "Item and Warehouse",
        "item_code": item_code,
        "warehouse": warehouse,
        "posting_date": posting_date,
        "posting_time": posting_time,
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    frappe.db.commit()

    process_single_repost(doc.name)
    frappe.db.commit()
    doc.reload()

    after = frappe.db.get_value(
        "Bin",
        {"item_code": item_code, "warehouse": warehouse},
        ["actual_qty", "valuation_rate", "stock_value"],
        as_dict=True,
    )

    return {
        "repost": doc.name,
        "status": doc.status,
        "total_reposting_count": doc.total_reposting_count,
        "current_index": doc.current_index,
        "gl_reposting_index": doc.gl_reposting_index,
        "before": before,
        "after": after,
    }


def _get_pending_reposts():
    return frappe.get_all(
        "Repost Item Valuation",
        filters={"status": ["in", ["Queued", "In Progress", "Failed"]], "docstatus": 1},
        fields=["name", "status", "posting_date", "posting_time", "creation"],
        order_by="timestamp(posting_date, posting_time) asc, creation asc",
        limit=50,
    )


def _restart_failed_repost(repost_name):
    try:
        doc = frappe.get_doc("Repost Item Valuation", repost_name)
        doc.restart_reposting()
        frappe.db.commit()
    except Exception:
        frappe.log_error(title=f"Failed to restart stock repost {repost_name}")
