"""
Seed Numbering Configuration rules for Sales Invoice.

Implements a multi-condition, multi-source numbering system that:
  1. Preserves old invoice numbers from legacy ERP (migration mode)
  2. Generates branch-specific numbers for companies with branches
  3. Generates company-level numbers for companies without branches
  4. Automatically detects is_return and uses return codes

Idempotent: rules are skipped if they already exist.

Run:
    bench --site <site> console
    >>> from avinashgroup_app.scripts.seed_sales_invoice_numbering import seed
    >>> seed()
"""

import frappe


def seed(commit=True):
    """Seed generic and company-specific Sales Invoice numbering rules."""

    created = []
    skipped = []

    # =========================================================================
    # STEP 1: Create 3 Generic Rules (work for ALL companies)
    # =========================================================================

    # Rule 1: Migration Rule (Read from narration for old data)
    rule1_name = "Sales Invoice - Legacy Data"
    if frappe.db.exists("Numbering Configuration", rule1_name):
        skipped.append(f"{rule1_name}: already exists")
    else:
        rule1 = frappe.new_doc("Numbering Configuration")
        rule1.name = rule1_name
        rule1.document_type = "Sales Invoice"
        rule1.company = None  # Blank = all companies
        rule1.branch = None   # Blank = all branches
        rule1.enabled = 1
        rule1.target_field = "custom_branch_name"
        rule1.separator = "-"
        rule1.valid_upto = "2026-06-30"  # Users can customize cutoff date
        rule1.date_field = "posting_date"
        rule1.append("segments", {"segment_type": "Document Field", "field": "narration"})
        rule1.insert(ignore_permissions=True)
        created.append(f"{rule1.name} (migration - reads narration)")

    # Rule 2: Branch-wise Rule (Generate for companies with branches)
    rule2_name = "Sales Invoice - Branch-wise"
    if frappe.db.exists("Numbering Configuration", rule2_name):
        skipped.append(f"{rule2_name}: already exists")
    else:
        rule2 = frappe.new_doc("Numbering Configuration")
        rule2.name = rule2_name
        rule2.document_type = "Sales Invoice"
        rule2.company = None
        rule2.branch = None  # Users customize per-branch
        rule2.enabled = 1
        rule2.target_field = "custom_branch_name"
        rule2.separator = "-"
        rule2.valid_from = "2026-07-01"
        rule2.date_field = "posting_date"
        rule2.append("segments", {"segment_type": "Company Abbr"})
        rule2.append("segments", {"segment_type": "Branch Abbr"})
        rule2.append("segments", {
            "segment_type": "Normal / Return Code",
            "static_value": "SI",
            "return_value": "SR"
        })
        rule2.append("segments", {"segment_type": "Number", "number_length": 6})
        rule2.append("segments", {"segment_type": "Fiscal Year"})
        rule2.insert(ignore_permissions=True)
        created.append(f"{rule2.name} (generates with branch code)")

    # Rule 3: Company-wise Rule (Generate for companies without branches)
    rule3_name = "Sales Invoice - Company-wise"
    if frappe.db.exists("Numbering Configuration", rule3_name):
        skipped.append(f"{rule3_name}: already exists")
    else:
        rule3 = frappe.new_doc("Numbering Configuration")
        rule3.name = rule3_name
        rule3.document_type = "Sales Invoice"
        rule3.company = None
        rule3.branch = None
        rule3.enabled = 1
        rule3.target_field = "custom_branch_name"
        rule3.separator = "-"
        rule3.valid_from = "2026-07-01"
        rule3.date_field = "posting_date"
        rule3.append("segments", {"segment_type": "Company Abbr"})
        rule3.append("segments", {"segment_type": "Static Text", "static_value": "SI"})
        rule3.append("segments", {"segment_type": "Number", "number_length": 6})
        rule3.append("segments", {"segment_type": "Fiscal Year"})
        rule3.insert(ignore_permissions=True)
        created.append(f"{rule3.name} (generates company-level, fallback)")

    # =========================================================================
    # STEP 2: Create Grishma-specific Rules (override generic for branches)
    # =========================================================================

    grishma = "Grishma Enterprises Pvt. Ltd."
    branches = {
        "GEPL-Branch-00001": ("INV", "RT"),
        "GEPL-Branch-00002": ("SB", "BSR"),
        "GEPL-Branch-00003": ("GEP", "RTN"),
    }

    for branch_id, (normal_code, return_code) in branches.items():
        rule_name = f"Sales Invoice - Grishma - {branch_id.split('-')[-1]}"

        if frappe.db.exists("Numbering Configuration", {"document_type": "Sales Invoice", "company": grishma, "branch": branch_id}):
            skipped.append(f"Grishma {branch_id}: rule already exists")
            continue

        if not frappe.db.exists("Branch", branch_id):
            skipped.append(f"Grishma {branch_id}: branch master missing")
            continue

        rule = frappe.new_doc("Numbering Configuration")
        rule.document_type = "Sales Invoice"
        rule.company = grishma
        rule.branch = branch_id
        rule.enabled = 1
        rule.target_field = "custom_branch_name"
        rule.separator = "-"
        rule.valid_from = "2026-07-01"
        rule.date_field = "posting_date"
        rule.append("segments", {"segment_type": "Company Abbr"})
        rule.append("segments", {"segment_type": "Branch Abbr"})
        rule.append("segments", {
            "segment_type": "Normal / Return Code",
            "static_value": normal_code,
            "return_value": return_code
        })
        rule.append("segments", {"segment_type": "Number", "number_length": 6})
        rule.append("segments", {"segment_type": "Fiscal Year"})
        rule.insert(ignore_permissions=True)
        created.append(f"  {rule.name} ({normal_code}/{return_code})")

    if commit:
        frappe.db.commit()

    # Print summary
    print("\n" + "="*80)
    print("SEEDED SALES INVOICE NUMBERING RULES")
    print("="*80 + "\n")

    if created:
        print(f"✓ Created {len(created)} rules:")
        for c in created:
            print(f"  {c}")
        print()

    if skipped:
        print(f"⊘ Skipped {len(skipped)} rules:")
        for s in skipped:
            print(f"  {s}")
        print()

    print("="*80 + "\n")
    print("""
HOW TO USE:

1. CUSTOMIZING CUTOFF DATE (for migration):
   - Go to: Numbering Configuration
   - Edit: "Sales Invoice - Legacy Data"
   - Change: Valid Upto = your cutoff date (default: 2026-06-30)
   - Result: Invoices before this date use narration, after use generated numbers

2. FOR COMPANIES WITH BRANCHES:
   - Copy generic "Sales Invoice - Branch-wise" rule
   - Set: Company = your company
   - Set: Branch = your branch ID
   - Customize: Normal/Return codes as needed
   - Example (Grishma): GEPL-INV-000001-82/83

3. FOR COMPANIES WITHOUT BRANCHES:
   - Generic "Sales Invoice - Company-wise" rule applies automatically
   - Customize: Static code as needed
   - Example (Nepal Gas): NGI-SI-000001-82/83

4. FOR MIGRATION (OLD ERP DATA):
   - Import invoices with posting_date ≤ cutoff date
   - Put old invoice number in narration field
   - custom_branch_name will auto-populate from narration

5. FOR NEW INVOICES (AFTER MIGRATION):
   - Import invoices with posting_date ≥ cutoff date + 1
   - Leave narration empty
   - custom_branch_name will auto-generate with codes
""")

    return created


if __name__ == "__main__":
    seed()
