"""Seed the Sales Invoice numbering rules — ONE record per scope.

Each Numbering Configuration record now carries the whole cut-over story:

  * Legacy window ("Legacy numbers (before cut-over)" section):
      documents dated up to LEGACY_UPTO copy their number from
      LEGACY_SOURCE_FIELD (the old ERP number). No counter is consumed.
      If that field is empty the engine falls through to the next rule
      (or to doc.name when none produces a value).
  * After the legacy date the SEGMENTS generate the number as usual
      (running counter per unique segment combination).

So a company/branch needs exactly ONE rule. All dates/fields below are only
seeded defaults — edit them any time in the Numbering Configuration form.

Idempotent: rules are matched by scope (doctype + company + branch), never by
name (the doctype autonames with a hash).

Run:
    bench --site <site> execute avinashgroup_app.scripts.seed_sales_invoice_numbering.seed
"""

import frappe

LEGACY_UPTO = "2026-06-30"                 # copy old numbers up to this date
LEGACY_SOURCE_FIELD = "custom_narration"   # where the old ERP number arrives

GRISHMA = "Grishma Enterprises Pvt. Ltd."

# branch -> (normal code, return code) — legacy Grishma codes
GRISHMA_BRANCH_CODES = {
    "GEPL-Branch-00001": ("INV", "RT"),
    "GEPL-Branch-00002": ("SB", "BSR"),
    "GEPL-Branch-00003": ("GEP", "RTN"),
}


def _new_rule(company=None, branch=None):
    rule = frappe.new_doc("Numbering Configuration")
    rule.document_type = "Sales Invoice"
    rule.company = company
    rule.branch = branch
    rule.enabled = 1
    rule.target_field = "custom_branch_name"
    rule.separator = "-"
    rule.date_field = "posting_date"
    rule.legacy_upto = LEGACY_UPTO
    rule.legacy_source_field = LEGACY_SOURCE_FIELD
    return rule


def seed(commit=True):
    created, skipped = [], []

    for branch, (normal_code, return_code) in GRISHMA_BRANCH_CODES.items():
        if not frappe.db.exists("Branch", branch):
            skipped.append(f"{branch}: branch master missing")
            continue

        existing = frappe.db.get_value(
            "Numbering Configuration",
            {"document_type": "Sales Invoice", "company": GRISHMA, "branch": branch},
        )
        if existing:
            skipped.append(f"{existing} ({branch}): already exists")
            continue

        rule = _new_rule(company=GRISHMA, branch=branch)
        rule.append("segments", {"segment_type": "Company Abbr"})
        rule.append("segments", {
            "segment_type": "Normal / Return Code",
            "static_value": normal_code,
            "return_value": return_code,
        })
        rule.append("segments", {"segment_type": "Number", "number_length": 6})
        rule.append("segments", {"segment_type": "Fiscal Year"})
        rule.insert(ignore_permissions=True)
        created.append(f"{rule.name} ({branch}: {normal_code}/{return_code}, legacy upto {LEGACY_UPTO})")

    if commit:
        frappe.db.commit()

    for label, items in (("created", created), ("skipped", skipped)):
        print(f"{label} {len(items)}:")
        for item in items:
            print(f"  - {item}")

    print(
        "\nCompanies WITHOUT branches: create one rule in the form — same idea,\n"
        "leave Branch blank, segments e.g. Company Abbr / Static 'SI' / Number /\n"
        "Fiscal Year, and fill the same Legacy section if they have old data."
    )
    return created
