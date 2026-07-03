"""Seed the Sales Invoice numbering rules (migration cut-over + Grishma branches).

What this configures (all user-editable afterwards in Numbering Configuration):

1. MIGRATION RULE (all companies) — a PASS-THROUGH rule:
     Valid Upto = CUTOFF_DATE, single segment "Document Field: narration".
     Backdated documents (posting_date <= cutoff) copy the legacy ERP invoice
     number from narration into custom_branch_name. No counter is consumed.
     If narration is empty the engine falls through to the next matching rule.

2. GRISHMA BRANCH RULES — counter rules scoped company+branch with
     Valid From = CUTOFF_DATE + 1 day, so they only number documents AFTER the
     cut-over; before it, the migration rule wins.
     Segments: Company Abbr / Normal-Return Code / Number(6) / Fiscal Year.

Companies WITHOUT branches need no seeding here: create one rule in the form
(Company Abbr + Static code + Number + Fiscal Year, Valid From = cutoff + 1),
or rely on an existing all-company rule.

The cutoff below is only the seeded DEFAULT — change it any time by editing
Valid Upto / Valid From on the rules in the Numbering Configuration form.

Idempotent: rules are matched by scope (doctype + company + branch), never by
name (the doctype autonames with a hash, so name checks would always miss).

Run:
    bench --site <site> execute avinashgroup_app.scripts.seed_sales_invoice_numbering.seed
"""

import frappe

CUTOFF_DATE = "2026-06-30"          # narration applies up to and including this
NEW_FORMAT_FROM = "2026-07-01"      # generated numbers apply from this date

GRISHMA = "Grishma Enterprises Pvt. Ltd."

# branch -> (normal code, return code) — legacy Grishma codes
GRISHMA_BRANCH_CODES = {
    "GEPL-Branch-00001": ("INV", "RT"),
    "GEPL-Branch-00002": ("SB", "BSR"),
    "GEPL-Branch-00003": ("GEP", "RTN"),
}


def seed(commit=True):
    created, updated, skipped = [], [], []

    # ------------------------------------------------------------------ 1
    # Migration pass-through rule (all companies, all branches).
    existing = frappe.get_all(
        "Numbering Configuration",
        filters={
            "document_type": "Sales Invoice",
            "company": ("is", "not set"),
            "branch": ("is", "not set"),
            "valid_upto": ("is", "set"),
        },
        pluck="name",
    )
    if existing:
        skipped.append(f"migration rule already exists: {existing[0]}")
    else:
        rule = frappe.new_doc("Numbering Configuration")
        rule.document_type = "Sales Invoice"
        rule.enabled = 1
        rule.target_field = "custom_branch_name"
        rule.separator = "-"
        rule.valid_upto = CUTOFF_DATE
        rule.date_field = "posting_date"
        rule.append("segments", {"segment_type": "Document Field", "field": "narration"})
        rule.insert(ignore_permissions=True)
        created.append(f"{rule.name} (pass-through narration, upto {CUTOFF_DATE})")

    # ------------------------------------------------------------------ 2
    # Grishma branch rules, windowed to the new format period.
    for branch, (normal_code, return_code) in GRISHMA_BRANCH_CODES.items():
        if not frappe.db.exists("Branch", branch):
            skipped.append(f"{branch}: branch master missing")
            continue

        name = frappe.db.get_value(
            "Numbering Configuration",
            {"document_type": "Sales Invoice", "company": GRISHMA, "branch": branch},
        )
        if name:
            # rule exists (e.g. from the legacy migration seed) — just make
            # sure it is scoped to the new-format window.
            doc = frappe.get_doc("Numbering Configuration", name)
            if not doc.valid_from:
                doc.valid_from = NEW_FORMAT_FROM
                doc.date_field = doc.date_field or "posting_date"
                doc.save(ignore_permissions=True)
                updated.append(f"{name}: set valid_from={NEW_FORMAT_FROM}")
            else:
                skipped.append(f"{name}: already windowed (from {doc.valid_from})")
            continue

        rule = frappe.new_doc("Numbering Configuration")
        rule.document_type = "Sales Invoice"
        rule.company = GRISHMA
        rule.branch = branch
        rule.enabled = 1
        rule.target_field = "custom_branch_name"
        rule.separator = "-"
        rule.valid_from = NEW_FORMAT_FROM
        rule.date_field = "posting_date"
        rule.append("segments", {"segment_type": "Company Abbr"})
        rule.append("segments", {
            "segment_type": "Normal / Return Code",
            "static_value": normal_code,
            "return_value": return_code,
        })
        rule.append("segments", {"segment_type": "Number", "number_length": 6})
        rule.append("segments", {"segment_type": "Fiscal Year"})
        rule.insert(ignore_permissions=True)
        created.append(f"{rule.name} ({branch}: {normal_code}/{return_code})")

    if commit:
        frappe.db.commit()

    for label, items in (("created", created), ("updated", updated), ("skipped", skipped)):
        print(f"{label} {len(items)}:")
        for item in items:
            print(f"  - {item}")
    return created
