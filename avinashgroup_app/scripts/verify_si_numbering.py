"""End-to-end verification of the Sales Invoice numbering rules (one-record design).

Run:
    bench --site <site> execute avinashgroup_app.scripts.verify_si_numbering.run

Read-only: numbers are previewed with commit_series=False, nothing is saved.
"""

import frappe

from avinashgroup_app.custom_code.Override.naming_series import (
    _build_from_segments,
    _matching_numbering_rules,
)

GRISHMA = "Grishma Enterprises Pvt. Ltd."
NEPAL_GAS = "Nepal Gas Udhyog Pvt. Ltd."


def _resolve(**attrs):
    """Return (rule_name, value) the engine would produce for a doc with these attrs."""
    doc = frappe.new_doc("Sales Invoice")
    for k, v in attrs.items():
        setattr(doc, k, v)
    for rule in _matching_numbering_rules(doc):
        value = _build_from_segments(doc, rule, commit_series=False)
        if value:
            return rule["name"], value
    return None, None


def run():
    frappe.set_user("Administrator")
    checks = [
        (
            "OLD Grishma (2024-05-15) + custom_narration -> legacy copy",
            dict(company=GRISHMA, custom_branch="GEPL-Branch-00001",
                 posting_date="2024-05-15", custom_narration="INV-OLD-2024-0001", is_return=0),
            lambda rule, val: val == "INV-OLD-2024-0001",
        ),
        (
            "OLD, custom_narration EMPTY -> no legacy value (falls to doc.name)",
            dict(company=GRISHMA, custom_branch="GEPL-Branch-00001",
                 posting_date="2024-05-15", custom_narration="", is_return=0),
            lambda rule, val: val != "INV-OLD-2024-0001",
        ),
        (
            "NEW Grishma branch 1 normal -> GEPL-INV-...-82/83",
            dict(company=GRISHMA, custom_branch="GEPL-Branch-00001",
                 posting_date="2026-07-03", custom_narration="", is_return=0),
            lambda rule, val: val and "INV" in val and "82/83" in val,
        ),
        (
            "NEW Grishma branch 2 RETURN -> BSR code",
            dict(company=GRISHMA, custom_branch="GEPL-Branch-00002",
                 posting_date="2026-07-03", custom_narration="", is_return=1),
            lambda rule, val: val and "BSR" in val,
        ),
        (
            "NEW doc WITH custom_narration -> ignored after legacy date",
            dict(company=GRISHMA, custom_branch="GEPL-Branch-00001",
                 posting_date="2026-07-03", custom_narration="some note", is_return=0),
            lambda rule, val: val and "some note" not in val and "INV" in val,
        ),
        (
            "Nepal Gas, no branch, no rule -> falls back to doc.name",
            dict(company=NEPAL_GAS, custom_branch=None,
                 posting_date="2026-07-03", custom_narration="", is_return=0),
            lambda rule, val: True,  # informational: shows which rule (if any) applies
        ),
    ]

    failed = 0
    for label, attrs, expect in checks:
        rule, val = _resolve(**attrs)
        ok = expect(rule, val)
        failed += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        print(f"       rule:  {rule or '(none -> falls back to doc.name)'}")
        print(f"       value: {val}")

    print(f"\n{'ALL PASS' if not failed else str(failed) + ' FAILED'} "
          f"({len(checks) - failed}/{len(checks)})")
    return failed
