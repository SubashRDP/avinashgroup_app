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

The register exports ship in this folder; xls_path defaults to the 82-83 file
(the only year whose invoices exist in ERPNext — the 79.80/80-81/81-82 files
are kept here purely as the archive for those unmigrated years).

Usage (from the bench directory):

  # dry run — writes nothing, prints the summary:
  bench --site <site> execute \
    avinashgroup_app.legacy_print_import.import_legacy_print_counts.run

  # then, after checking the dry-run numbers:
  bench --site <site> execute \
    avinashgroup_app.legacy_print_import.import_legacy_print_counts.run \
    --kwargs "{'commit': True}"
"""

import json
import os

import frappe
from frappe.utils import cint

DEFAULT_XLS = os.path.join(os.path.dirname(__file__), "82-83 NGI.xls")

INVOICE_HEADER = "Invoice Number"
COPIES_HEADER = "No of Copy Printed"


def parse_register(xls_path):
    """Old invoice number -> total sheets printed, from a register export.

    Layout (both the 19- and 11-column exports): a header row names the
    columns; below it, an invoice row carries the invoice number in column A
    and each print event follows on its own row with the copy count in the
    "No of Copy Printed" column.
    """
    import xlrd

    sheet = xlrd.open_workbook(xls_path).sheet_by_index(0)

    copies_col = None
    for r in range(sheet.nrows):
        for c in range(sheet.ncols):
            if str(sheet.cell_value(r, c)).strip() == COPIES_HEADER:
                copies_col = c
                header_row = r
                break
        if copies_col is not None:
            break
    if copies_col is None:
        frappe.throw(f"'{COPIES_HEADER}' header not found in {xls_path}")

    totals = {}
    current = None
    for r in range(header_row + 1, sheet.nrows):
        invoice_no = str(sheet.cell_value(r, 0)).strip()
        if invoice_no == "Report Parameters":  # footer block ends the register
            break
        if invoice_no and invoice_no != INVOICE_HEADER:
            current = invoice_no
            totals.setdefault(current, 0)
            continue
        copies = sheet.cell_value(r, copies_col)
        if current and copies:
            totals[current] += cint(copies)
    return totals


def run(xls_path=None, commit=False):
    xls_path = xls_path or DEFAULT_XLS
    totals = parse_register(xls_path)

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
