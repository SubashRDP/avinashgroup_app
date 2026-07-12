"""Seed Numbering Configuration rules for NGK from the FACT format sheet.

One rule per transaction doctype for Nepal Gas Udhyog (Karnali) Pvt. Ltd.,
reproducing the sheet byte-for-byte on custom_name:

    NGK-<type code>-<6-digit document no.>-<fiscal year>

Auto vs Manual follows the sheet via Document No. conditions (In-list of the
auto types); every other type stays manual. The number slot is a Document
Field on custom_document_no, so the rule-derived series scope pattern
(NGK-<code>-%-<FY>) is identical to the legacy scan and existing counters
continue seamlessly.

Sales Invoice is intentionally NOT seeded: its ID (NGK-SB-<FY>-#####) comes
from the naming-series autoname override and it has no custom_name field.

Idempotent — an existing (document_type, company) rule is left alone.

Run:
    bench --site avinas1 execute \
        avinashgroup_app.scripts.seed_ngk_numbering_from_sheet.seed
"""

import frappe

COMPANY = "Nepal Gas Udhyog (Karnali) Pvt. Ltd."

# doctype -> (type field, csv of auto-numbered types from the sheet)
SHEET = {
    "Journal Entry": (
        "custom_p_type",
        "Bank Entry,Party Journal,Debit Note,Credit Note",
    ),
    "Payment Entry": (
        "custom_p_type",
        "Bank Customers Receipt,NOC Payment,Contra Voucher- cash to bank",
    ),
    "Purchase Invoice": (
        "custom_purchase_type",
        "Purchase Return",
    ),
    "Purchase Receipt": (
        "custom_receipt_type",
        "Other Purchase Receipt",
    ),
}


def seed(commit=True):
    from avinashgroup_app.custom_code.Override import naming_series as ns

    created, skipped = [], []
    for doctype, (type_field, auto_types) in SHEET.items():
        if frappe.db.exists(
            "Numbering Configuration",
            {"document_type": doctype, "company": COMPANY},
        ):
            skipped.append(f"{doctype}: rule already exists")
            continue

        rule = frappe.new_doc("Numbering Configuration")
        rule.document_type = doctype
        rule.company = COMPANY
        rule.enabled = 1
        rule.target_field = "custom_name"
        rule.separator = "-"
        rule.auto_document_no = 1
        rule.document_no_field = "custom_document_no"
        rule.duplicate_action = "Throw Error"
        rule.normal_docno_mode = "Auto"
        rule.return_docno_mode = "Auto"
        # the sheet's Auto column: number ONLY these types
        rule.append("document_no_conditions", {
            "field": type_field, "operator": "In", "value": auto_types,
        })
        # NGK-<code>-<000000>-<FY>
        rule.append("segments", {"segment_type": "Company Abbr"})
        rule.append("segments", {"segment_type": "Document Field",
                                 "field": "custom_p_type_code"})
        rule.append("segments", {"segment_type": "Document Field",
                                 "field": "custom_document_no",
                                 "number_length": 6})
        rule.append("segments", {"segment_type": "Fiscal Year"})
        rule.insert(ignore_permissions=True)
        created.append(f"{doctype}: {rule.name}")

    if commit:
        frappe.db.commit()
    ns.clear_numbering_rules_cache()

    print(f"created {len(created)}:")
    for n in created:
        print("  +", n)
    print(f"skipped {len(skipped)}:")
    for s in skipped:
        print("  -", s)
    return created
