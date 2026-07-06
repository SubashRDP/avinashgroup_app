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


def dump():
    """Print every Numbering Configuration rule with its segments."""
    frappe.set_user("Administrator")
    for name in frappe.get_all("Numbering Configuration", pluck="name"):
        doc = frappe.get_doc("Numbering Configuration", name)
        print(f"{'ON ' if doc.enabled else 'OFF'} {doc.name}")
        print(f"     doctype={doc.document_type}  company={doc.company or '(all)'}  "
              f"branch={doc.branch or '(all)'}")
        print(f"     legacy_upto={doc.legacy_upto or '-'}  "
              f"legacy_source={doc.legacy_source_field or '-'}  "
              f"target={doc.target_field}  sep='{doc.separator}'")
        for seg in doc.segments:
            extra = ""
            if seg.static_value:
                extra += f" text={seg.static_value}"
            if seg.return_value:
                extra += f" return={seg.return_value}"
            if seg.field:
                extra += f" field={seg.field}"
            print(f"       {seg.idx}. {seg.segment_type}{extra}")
        for cond in doc.conditions:
            print(f"       when {cond.field} = {cond.value}")


def run():
    frappe.set_user("Administrator")
    # invariant checks — they hold for ANY rule configuration, so this stays
    # useful while rules are edited in the form.
    normal_rule, normal_val = _resolve(
        company=GRISHMA, custom_branch="GEPL-Branch-00001",
        posting_date="2026-07-03", custom_narration="", is_return=0)
    return_rule, return_val = _resolve(
        company=GRISHMA, custom_branch="GEPL-Branch-00001",
        posting_date="2026-07-03", custom_narration="", is_return=1)

    checks = [
        (
            "OLD doc (2024-05-15) + custom_narration -> legacy number copied",
            dict(company=GRISHMA, custom_branch="GEPL-Branch-00001",
                 posting_date="2024-05-15", custom_narration="INV-OLD-2024-0001", is_return=0),
            lambda rule, val: val == "INV-OLD-2024-0001",
        ),
        (
            "OLD doc, custom_narration EMPTY -> no legacy value copied",
            dict(company=GRISHMA, custom_branch="GEPL-Branch-00001",
                 posting_date="2024-05-15", custom_narration="", is_return=0),
            lambda rule, val: val != "INV-OLD-2024-0001",
        ),
        (
            "NEW doc -> a number is generated (rule configured for this scope)",
            dict(company=GRISHMA, custom_branch="GEPL-Branch-00001",
                 posting_date="2026-07-03", custom_narration="", is_return=0),
            lambda rule, val: bool(val),
        ),
        (
            "NEW RETURN doc -> differs from the normal number (return code used)",
            dict(company=GRISHMA, custom_branch="GEPL-Branch-00001",
                 posting_date="2026-07-03", custom_narration="", is_return=1),
            lambda rule, val: val != normal_val,
        ),
        (
            "NEW doc WITH custom_narration -> narration ignored after cut-over",
            dict(company=GRISHMA, custom_branch="GEPL-Branch-00001",
                 posting_date="2026-07-03", custom_narration="some note", is_return=0),
            lambda rule, val: val and "some note" not in val,
        ),
        (
            "Nepal Gas, no branch (informational: shows which rule applies)",
            dict(company=NEPAL_GAS, custom_branch=None,
                 posting_date="2026-07-03", custom_narration="", is_return=0),
            lambda rule, val: True,
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
