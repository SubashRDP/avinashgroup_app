# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""One-off import of legacy print counts into Sales Invoice Print Count.

The old NGI billing software exports a "Sale Invoice Register" (.xls) listing,
per invoice, every print event with "No of Copy Printed". The migration stored
the old software's invoice number (e.g. NGI000001/82-83) in the Sales Invoice's
custom_branch_name, so each register row maps to exactly one migrated invoice.

Per invoice this sums the copies over all its print events (the old software
counted the first print as 2 — the TAX INVOICE + INVOICE pair — same sheet
semantics as print_count.py) and upserts Sales Invoice Print Count:

  - no row yet  -> insert with print_count = legacy sheet total
  - row exists  -> ADD the legacy sheets to the current count (ERPNext prints
                   happened after the legacy ones; the counter is total sheets)

DRY RUN unless commit=True — always inspect the dry-run summary first.
NOT idempotent: running commit=True twice adds the legacy sheets twice.

The register exports ship in this folder; xls_path defaults to the 82-83 file.
The 80-81 and 81-82 files are proper full-year registers. The "79.80" file is
NOT a year register — it is an invoice-number-contains-"79" search export
(footer: "1478 of 100072") mixing old-format NGI/xxxxxx invoices with 580
80-81 invoices, and every invoice in it carries a phantom "ANIL, 1 copy" event,
all 1478 sharing the identical timestamp 2024-03-03 15:19:10 (one bulk action
fanned out, not real prints).

Two defenses handle that file (and protect any future bad export):

  - phantom events are dropped automatically: any exact timestamp shared by
    more than PHANTOM_SHARE_LIMIT event rows is treated as a bulk artifact,
    and those rows are excluded from the totals (reported in the summary);
  - only_prefix limits the import to invoice numbers starting with a prefix,
    so the old-format invoices can be imported from the mixed file without
    touching the /80-81 ones already covered by the real 80-81 register.

DRY RUN unless commit=True — always inspect the dry-run summary first.
NOT idempotent: running commit=True twice adds the legacy sheets twice.

Usage (from the bench directory):

  # dry run — writes nothing, prints the summary:
  bench --site <site> execute \
    avinashgroup_app.legacy_print_import.import_legacy_print_counts.run

  # then, after checking the dry-run numbers:
  bench --site <site> execute \
    avinashgroup_app.legacy_print_import.import_legacy_print_counts.run \
    --kwargs "{'commit': True}"

  # old-format invoices from the mixed "79.80" search export:
  bench --site <site> execute \
    avinashgroup_app.legacy_print_import.import_legacy_print_counts.run \
    --kwargs "{'xls_path': '<folder>/79.80 NGI.xls', 'only_prefix': 'NGI/'}"
"""

import json
import os

import frappe
from frappe.utils import cint

DEFAULT_XLS = os.path.join(os.path.dirname(__file__), "82-83 NGI.xls")

INVOICE_HEADER = "Invoice Number"
COPIES_HEADER = "No of Copy Printed"
DATE_HEADER = "Date & Time of Print"

# An exact print timestamp legitimately repeats only within one batch of
# copies; the same instant on more rows than this across the register is a
# bulk-action artifact (the "79.80" file has one instant on 1478 invoices).
PHANTOM_SHARE_LIMIT = 3


def parse_register(xls_path, phantom_info=None):
    """Old invoice number -> total sheets printed, from a register export.

    Layout (both the 19- and 11-column exports): a header row names the
    columns; below it, an invoice row carries the invoice number in column A
    and each print event follows on its own row with the copy count in the
    "No of Copy Printed" column.

    Event rows whose exact timestamp is shared by more than
    PHANTOM_SHARE_LIMIT rows are dropped as bulk artifacts; pass a dict as
    phantom_info to receive what was dropped.
    """
    import xlrd

    sheet = xlrd.open_workbook(xls_path).sheet_by_index(0)

    copies_col = date_col = header_row = None
    for r in range(sheet.nrows):
        for c in range(sheet.ncols):
            head = str(sheet.cell_value(r, c)).strip()
            if head == COPIES_HEADER:
                copies_col, header_row = c, r
            elif head == DATE_HEADER:
                date_col = c
        if copies_col is not None:
            break
    if copies_col is None:
        frappe.throw(f"'{COPIES_HEADER}' header not found in {xls_path}")

    events = []  # (invoice_no, copies, timestamp)
    timestamp_rows = {}
    current = None
    for r in range(header_row + 1, sheet.nrows):
        invoice_no = str(sheet.cell_value(r, 0)).strip()
        if invoice_no == "Report Parameters":  # footer block ends the register
            break
        if invoice_no and invoice_no != INVOICE_HEADER:
            current = invoice_no
            events.append((current, 0, None))  # register the invoice itself
            continue
        copies = sheet.cell_value(r, copies_col)
        if current and copies:
            ts = sheet.cell_value(r, date_col) if date_col is not None else None
            events.append((current, cint(copies), ts))
            if ts:
                timestamp_rows[ts] = timestamp_rows.get(ts, 0) + 1

    phantom_ts = {ts for ts, n in timestamp_rows.items() if n > PHANTOM_SHARE_LIMIT}

    totals = {}
    dropped_events = dropped_sheets = 0
    for invoice_no, copies, ts in events:
        totals.setdefault(invoice_no, 0)
        if ts in phantom_ts:
            dropped_events += 1
            dropped_sheets += copies
            continue
        totals[invoice_no] += copies

    if phantom_info is not None:
        from datetime import datetime, timedelta

        phantom_info["phantom_timestamps"] = [
            str(datetime(1899, 12, 30) + timedelta(days=ts)) for ts in sorted(phantom_ts)
        ]
        phantom_info["phantom_events_dropped"] = dropped_events
        phantom_info["phantom_sheets_dropped"] = dropped_sheets
    return totals


def run(xls_path=None, commit=False, only_prefix=None):
    xls_path = xls_path or DEFAULT_XLS
    phantom_info = {}
    totals = parse_register(xls_path, phantom_info=phantom_info)
    skipped_by_prefix = 0
    if only_prefix:
        skipped_by_prefix = sum(1 for no in totals if not no.startswith(only_prefix))
        totals = {no: n for no, n in totals.items() if no.startswith(only_prefix)}

    # old software invoice number (stored in custom_branch_name) -> SI name
    mapping = {
        (old_no or "").strip(): name
        for old_no, name in frappe.db.sql(
            "SELECT custom_branch_name, name FROM `tabSales Invoice` "
            "WHERE IFNULL(custom_branch_name, '') != ''"
        )
    }

    existing = {
        r.name: cint(r.print_count)
        for r in frappe.get_all(
            "Sales Invoice Print Count", fields=["name", "print_count"]
        )
    }

    inserts, updates, unmatched = [], [], []
    for old_no, sheets in totals.items():
        if not sheets:
            continue
        si = mapping.get(old_no)
        if not si:
            unmatched.append(old_no)
        elif si in existing:
            updates.append(
                {
                    "invoice": si,
                    "old_no": old_no,
                    "from": existing[si],
                    "add": sheets,
                    "to": existing[si] + sheets,
                }
            )
        else:
            inserts.append({"invoice": si, "old_no": old_no, "print_count": sheets})

    if commit:
        for row in inserts:
            frappe.get_doc(
                {
                    "doctype": "Sales Invoice Print Count",
                    "sales_invoice": row["invoice"],
                    "branch_name": row["old_no"],
                    "print_count": row["print_count"],
                }
            ).insert(ignore_permissions=True)
        for row in updates:
            frappe.db.sql(
                "UPDATE `tabSales Invoice Print Count` "
                "SET print_count = print_count + %s WHERE name = %s",
                (row["add"], row["invoice"]),
            )
        frappe.db.commit()

    result = {
        "dry_run": not commit,
        "xls_path": xls_path,
        "only_prefix": only_prefix,
        "skipped_by_prefix": skipped_by_prefix,
        **phantom_info,
        "excel_invoices": len(totals),
        ("inserted" if commit else "would_insert"): len(inserts),
        ("updated" if commit else "would_update"): len(updates),
        "unmatched": len(unmatched),
        "unmatched_invoices": unmatched[:50],
        "total_sheets": sum(r["print_count"] for r in inserts)
        + sum(r["add"] for r in updates),
    }
    if updates:
        result["update_rows"] = updates[:50]
        result["warning"] = (
            "updates ADD legacy sheets to existing counters - if this import "
            "already ran once, committing again will double-count"
        )
    print(json.dumps(result, indent=1, default=str))
    return result
