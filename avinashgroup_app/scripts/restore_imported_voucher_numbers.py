"""Restore imported Sales Invoice numbers that the engine renumbered away.

Background
----------
Until the per-company uniqueness fix, `set_custom_branch_name` cleared any number
that was already held by ANOTHER document — checked group-wide, ignoring company —
and generated a fresh one in its place, silently. Legacy return numbers are bare
(`RTN/000419`, no company prefix), so NGK's import on 2026-08-03 collided with
NGI's `RTN/…` namespace (imported 2026-07-30) and 417 NGK returns were stored as
`NGK-SRTN-000417-78/79` instead of the number the sheet supplied. The sheet value
survived untouched in `custom_fact_numbering`, which is what this restores from.

Run AFTER the code fix is deployed: with the group-wide check still in place, any
later resave of one of these submitted invoices would throw "already used by
NGI-…" on the restored value.

Idempotent — rows already holding their fact number are not matched.

Run:
    bench --site <site> console
    >>> from avinashgroup_app.scripts.restore_imported_voucher_numbers import report, restore
    >>> report()      # dry run, changes nothing
    >>> restore()     # writes, then re-checks
"""

import frappe

# The damage is identifiable by shape: a generated number (ABBR-CODE-nnnnnn-FY)
# on a document that also carries a legacy number in custom_fact_numbering.
PATTERN = "%-SRTN-______-%"

WHERE = """
    custom_branch_name LIKE %(pattern)s
    AND IFNULL(custom_fact_numbering, '') != ''
    AND custom_branch_name != custom_fact_numbering
"""


def _rows():
    # custom_fact_numbering is not deployed on every site (it carries the old
    # ERP's number and only exists where legacy data was imported).
    if not frappe.db.has_column("Sales Invoice", "custom_fact_numbering"):
        return []
    return frappe.db.sql(
        """
        SELECT name, company, custom_branch_name, custom_fact_numbering
        FROM `tabSales Invoice`
        WHERE {0}
        ORDER BY company, name
        """.format(WHERE),
        {"pattern": PATTERN},
        as_dict=True,
    )


def _in_company_clashes(rows):
    """Fact numbers that another document in the SAME company already holds — the
    restore would violate per-company uniqueness, so these must be reported, not
    written."""
    clashes = []
    for r in rows:
        other = frappe.db.get_value(
            "Sales Invoice",
            {
                "company": r.company,
                "custom_branch_name": r.custom_fact_numbering,
                "name": ["!=", r.name],
                "docstatus": ["<", 2],
            },
            "name",
        )
        if other:
            clashes.append((r.name, r.custom_fact_numbering, other))
    return clashes


def report():
    """Dry run: what restore() would change, and whether it is safe."""
    rows = _rows()
    print("rows to restore: {0}".format(len(rows)))
    by_company = {}
    for r in rows:
        by_company.setdefault(r.company, 0)
        by_company[r.company] += 1
    for company, n in sorted(by_company.items()):
        print("  {0:45} {1:>6}".format(company[:45], n))
    for r in rows[:5]:
        print("  e.g. {0}: {1} -> {2}".format(
            r.name, r.custom_branch_name, r.custom_fact_numbering))

    clashes = _in_company_clashes(rows)
    if clashes:
        print("\nBLOCKED — {0} value(s) already used inside the same company:".format(len(clashes)))
        for name, value, other in clashes[:20]:
            print("  {0}: {1} is held by {2}".format(name, value, other))
    else:
        print("\nsafe: no fact number is used by another document in the same company")
    return rows, clashes


def restore():
    """Write custom_fact_numbering back into custom_branch_name.

    Raw SQL on purpose: these documents are submitted, and the value is the
    authoritative legacy number — no validation or renumbering should run.
    """
    rows, clashes = report()
    if not rows:
        print("\nnothing to do")
        return 0
    if clashes:
        print("\nrefusing to write while clashes exist — resolve them first")
        return 0

    frappe.db.sql(
        """
        UPDATE `tabSales Invoice`
        SET custom_branch_name = custom_fact_numbering
        WHERE {0}
        """.format(WHERE),
        {"pattern": PATTERN},
    )
    frappe.db.commit()
    remaining = len(_rows())
    print("\nrestored {0} row(s); remaining unrestored: {1}".format(
        len(rows) - remaining, remaining))
    return remaining
