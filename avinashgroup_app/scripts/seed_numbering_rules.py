"""Seed Numbering Configuration rules that replace the legacy BRANCH_CODE_CONFIG.

Idempotent: a rule is skipped when one already exists for the same
(document_type, company, branch). Formats and series keys are byte-identical to
the legacy code, so existing tabSeries counters continue seamlessly.

Run:
    bench --site <site> console
    >>> from avinashgroup_app.scripts.seed_numbering_rules import seed
    >>> seed()
"""

import frappe

GRISHMA = "Grishma Enterprises Pvt. Ltd."

# doctype -> branch -> (normal_code, return_code)
LEGACY_BRANCH_CODES = {
    "Sales Invoice": {
        "GEPL-Branch-00001": ("INV", "RT"),
        "GEPL-Branch-00002": ("SB", "BSR"),
        "GEPL-Branch-00003": ("GEP", "RTN"),
    },
    "Purchase Receipt": {
        "GEPL-Branch-00001": ("AN", None),
        "GEPL-Branch-00002": ("BRC", None),
        "GEPL-Branch-00003": ("RC", None),
    },
    "Purchase Invoice": {
        "GEPL-Branch-00001": ("PBA", None),
        "GEPL-Branch-00002": ("PBB", None),
        "GEPL-Branch-00003": ("PB", None),
    },
}


def seed(commit=True):
    created, skipped = [], []

    for doctype, branches in LEGACY_BRANCH_CODES.items():
        for branch, (normal_code, return_code) in branches.items():
            if not frappe.db.exists("Branch", branch):
                skipped.append(f"{doctype} / {branch}: branch missing")
                continue

            if frappe.db.exists(
                "Numbering Configuration",
                {"document_type": doctype, "company": GRISHMA, "branch": branch},
            ):
                skipped.append(f"{doctype} / {branch}: rule already exists")
                continue

            rule = frappe.new_doc("Numbering Configuration")
            rule.document_type = doctype
            rule.company = GRISHMA
            rule.branch = branch
            rule.enabled = 1
            rule.target_field = "custom_branch_name"
            rule.separator = "-"
            # legacy format: {abbr}-{code}-{seq6}-{fy}  (number in the middle)
            rule.append("segments", {"segment_type": "Company Abbr"})
            rule.append(
                "segments",
                {
                    "segment_type": "Normal / Return Code",
                    "static_value": normal_code,
                    "return_value": return_code,
                },
            )
            rule.append("segments", {"segment_type": "Number", "number_length": 6})
            rule.append("segments", {"segment_type": "Fiscal Year"})
            rule.insert(ignore_permissions=True)
            created.append(rule.name)

    if commit:
        frappe.db.commit()

    print(f"created {len(created)}:")
    for n in created:
        print("  +", n)
    print(f"skipped {len(skipped)}:")
    for s in skipped:
        print("  -", s)
    return created
