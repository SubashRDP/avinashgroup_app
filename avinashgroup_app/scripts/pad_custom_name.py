"""
Zero-pad the number part of `custom_name` to 6 digits across the voucher doctypes.

Rule (from finance):
  - the numeric run in custom_name must be 6 digits wide
      NGI-CV-01193-82/83        -> NGI-CV-001193-82/83
  - a trailing letter suffix is kept, so the token becomes 7 chars
      NGK-RC-04228A-82/83       -> NGK-RC-004228A-82/83
  - any trailing "-N" copy-suffix and the "82/83" fiscal year are preserved
      NGI-PBO-00588-82/83-3     -> NGI-PBO-000588-82/83-3

SAFETY — this script never blindly rewrites:
  * SKIP if the padded value already exists on another record of the same
    doctype (would duplicate a voucher number -> reported as "collision").
  * SKIP if custom_name is not in the standard
    PREFIX-CODE-DIGITS[LETTERS]-FY[-N] shape (reported as "malformed").
  * SKIP if the digit run is already >= 6 (nothing to do).
custom_name is a plain custom field, so updates touch no GL / ledger.

Dry-run by default. Per-site (it's DB data, not code):

  # preview only
  bench --site <site> execute avinashgroup_app.scripts.pad_custom_name.run

  # apply
  bench --site <site> execute avinashgroup_app.scripts.pad_custom_name.run --kwargs '{"dry_run": 0}'
"""

import re

import frappe

DOCTYPES = ["Purchase Receipt", "Purchase Invoice", "Journal Entry", "Payment Entry"]
TARGET_WIDTH = 6

# PREFIX(-CODE) - DIGITS [LETTERS] - FY(82/83) [ -N copy suffix ]
PATTERN = re.compile(r"^([A-Z]+-[A-Z]+)-(\d+)([A-Za-z]*)-(\d+/\d+)(-\d+)?$")


def run(dry_run=1):
    dry_run = int(dry_run)
    for dt in DOCTYPES:
        _process(dt, dry_run)
    if dry_run:
        print("\nDRY RUN — nothing written. Re-run with --kwargs '{\"dry_run\": 0}' to apply.")
    else:
        frappe.db.commit()
        print("\nCOMMITTED.")


def _process(dt, dry_run):
    rows = frappe.db.sql(
        "select name, custom_name from `tab{0}` "
        "where custom_name is not null and custom_name != ''".format(dt),
        as_dict=True,
    )
    existing = {r.custom_name for r in rows}

    changed, collisions, malformed = [], [], []
    for r in rows:
        cn = r.custom_name
        m = PATTERN.match(cn)
        if not m:
            # only surface malformed rows that actually look short / wrong, not
            # every legitimately-non-matching name
            if re.search(r"(?<!\d)\d{1,5}(?!\d)", cn):
                malformed.append((r.name, cn))
            continue

        prefix, digits, letters, fy, tail = m.groups()
        if len(digits) >= TARGET_WIDTH:
            continue

        new_cn = "{0}-{1}{2}-{3}{4}".format(
            prefix, digits.zfill(TARGET_WIDTH), letters, fy, tail or ""
        )
        if new_cn in existing:
            collisions.append((r.name, cn, new_cn))
            continue

        changed.append((r.name, cn, new_cn))
        if not dry_run:
            frappe.db.set_value(dt, r.name, "custom_name", new_cn, update_modified=False)
            existing.discard(cn)
            existing.add(new_cn)

    print("\n=== {0} ===".format(dt))
    print("  pad:        {0}".format(len(changed)))
    for name, old, new in changed:
        print("    {0}: {1}  ->  {2}".format(name, old, new))
    print("  collision (LEFT as-is, padded value already used): {0}".format(len(collisions)))
    for name, old, new in collisions:
        print("    {0}: {1}  -x->  {2}".format(name, old, new))
    print("  malformed (LEFT as-is, not standard format): {0}".format(len(malformed)))
    for name, old in malformed:
        print("    {0}: {1}".format(name, old))
