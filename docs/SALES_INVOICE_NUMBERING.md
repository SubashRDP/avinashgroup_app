# Sales Invoice Numbering: Multi-Condition, Multi-Source System

## Overview

Sales Invoice numbering now supports a **flexible, data-driven system** that handles:

1. **Migration scenarios** - Preserve old invoice numbers from legacy ERP
2. **Branch-specific numbering** - Different codes per branch
3. **Company-level numbering** - For companies without branches
4. **Return invoice handling** - Automatic detection and alternate codes
5. **Time-based cutoffs** - Switch numbering format at a specific date

All configuration is done through the **Numbering Configuration** form with **ZERO code changes**.

---

## How It Works

### The Three-Rule Pattern

Every company uses up to **3 rules** for Sales Invoice numbering:

```
Rule 1: MIGRATION (Read from narration)
  Applies: posting_date ≤ cutoff date (e.g., 2026-06-30)
  Source: narration field (preserves old invoice number)
  Example: INV-OLD-2024-0001

Rule 2: BRANCH-SPECIFIC (Generate with branch code)
  Applies: posting_date ≥ cutoff date + 1 (e.g., 2026-07-01) AND custom_branch is set
  Source: Numbering Configuration rule
  Example: GEPL-INV-000001-82/83 (for normal), GEPL-RT-000001-82/83 (for return)

Rule 3: COMPANY-LEVEL (Generate without branch)
  Applies: posting_date ≥ cutoff date + 1 AND custom_branch is NOT set
  Source: Numbering Configuration rule (fallback)
  Example: NGI-SI-000001-82/83
```

### Priority (Most-Specific-Wins)

When an invoice is saved, rules are checked in this order:

```
1. Is posting_date before cutoff?
   YES → Use Rule 1 (migration) → Read narration
   NO  → Continue

2. Is custom_branch set?
   YES → Use Rule 2 (branch-specific) → Generate with branch code
   NO  → Use Rule 3 (company-level) → Generate company-level code
```

---

## Real Examples

### Example 1: Grishma - Backdated Invoice (Migration)

```
Company: Grishma Enterprises Pvt. Ltd.
Custom Branch: GEPL-Branch-00001
Posting Date: 2024-05-15 (old - before cutoff 2026-06-30)
Narration: INV-OLD-2024-0001 (old ERP invoice number)
Is Return: No

Rule Matching:
  ✓ Rule 1 (Migration) matches because:
    - posting_date (2024-05-15) ≤ cutoff (2026-06-30)
    - narration is not empty

Result:
  custom_branch_name = "INV-OLD-2024-0001"
  (Preserves the old invoice number - audit trail)
```

### Example 2: Grishma - New Invoice (Branch-Specific)

```
Company: Grishma Enterprises Pvt. Ltd.
Custom Branch: GEPL-Branch-00001
Posting Date: 2026-07-03 (new - after cutoff)
Narration: (empty)
Is Return: No

Rule Matching:
  ✗ Rule 1 (Migration) doesn't match because:
    - posting_date (2026-07-03) > cutoff (2026-06-30)
  
  ✓ Rule 2 (Branch-specific) matches because:
    - posting_date (2026-07-03) ≥ cutoff + 1
    - custom_branch is set (GEPL-Branch-00001)
    - This is the most specific rule (company + branch)

Segments Applied:
  1. Company Abbr → GEPL
  2. Branch Abbr → KTM (from Branch.custom_abbr)
  3. Normal Code → INV (because is_return = 0)
  4. Number → 000001 (first invoice this branch/year)
  5. Fiscal Year → 82/83 (from posting_date 2026-07-03)

Result:
  custom_branch_name = "GEPL-KTM-INV-000001-82/83"
  
  (Branch-wise numbering - different code per branch)
```

### Example 3: Grishma - Return Invoice (Branch-Specific with Return Code)

```
Company: Grishma Enterprises Pvt. Ltd.
Custom Branch: GEPL-Branch-00001
Posting Date: 2026-07-10
Narration: (empty)
Is Return: YES (checkbox is ticked)

Rule Matching:
  ✓ Rule 2 (Branch-specific) matches (same as Example 2)

Segments Applied (with return code):
  1. Company Abbr → GEPL
  2. Branch Abbr → KTM
  3. Return Code → RT (because is_return = 1)
  4. Number → 000001 (first return this branch/year)
  5. Fiscal Year → 82/83

Result:
  custom_branch_name = "GEPL-KTM-RT-000001-82/83"
  
  (Return code automatically detected and used)
```

### Example 4: Nepal Gas - New Invoice (No Branch)

```
Company: Nepal Gas Udhyog Pvt. Ltd.
Custom Branch: (empty - not set)
Posting Date: 2026-07-03
Narration: (empty)
Is Return: No

Rule Matching:
  ✗ Rule 1 (Migration) doesn't match because:
    - posting_date > cutoff
  
  ✗ Rule 2 (Branch-specific) doesn't match because:
    - custom_branch is not set
  
  ✓ Rule 3 (Company-level) matches as fallback because:
    - posting_date ≥ cutoff + 1
    - No more specific rules matched

Segments Applied:
  1. Company Abbr → NGI
  2. Static Code → SI
  3. Number → 000001
  4. Fiscal Year → 82/83

Result:
  custom_branch_name = "NGI-SI-000001-82/83"
  
  (Company-level numbering - no branch involved)
```

---

## Setup Instructions

### Step 1: Understand the Cutoff Date

The **cutoff date** divides old and new invoices:

- **Before cutoff**: Use old ERP invoice numbers (from narration)
- **After cutoff**: Generate new numbers (from Numbering Configuration rules)

**Default cutoff**: 2026-06-30 (you can change this)

### Step 2: Confirm Branch Master Setup

For branch-specific numbering, each branch needs:

1. **Branch master record** (created in Branch doctype)
2. **custom_abbr field** (abbreviation code, e.g., "KTM", "DLH")

Check: Home → Branch → Open your branch → Scroll down → Look for "Branch Abbr"

If missing, add it in the form and save.

### Step 3: Set Custom Branch on Sales Invoices

When creating/importing a Sales Invoice:

- Set the **custom_branch** field to your branch ID (e.g., "GEPL-Branch-00001")
- If custom_branch is empty → uses company-level rule
- If custom_branch is set → uses branch-specific rule

### Step 4: Customize the Cutoff Date (Optional)

If your migration cutoff is NOT 2026-06-30:

1. Go to: **Numbering Configuration**
2. Open: **Sales Invoice - Legacy Data**
3. Change: **Valid Upto** field to your cutoff date
4. Save

**Both dates must match:**
- Migration Rule: Valid Upto = your cutoff date
- Branch Rule: Valid From = your cutoff date + 1

### Step 5: For Companies with Branches

Create branch-specific rules:

1. Go to: **Numbering Configuration**
2. Click: **New**
3. Fill:
   - Document Type: Sales Invoice
   - Company: Your company
   - Branch: Your branch ID
   - Enabled: ☑
4. Scroll down to Segments:
   - Add: Company Abbr
   - Add: Branch Abbr
   - Add: Normal / Return Code
     - Normal: Your code (e.g., "INV")
     - Return: Return code (e.g., "RT")
   - Add: Number (length 6)
   - Add: Fiscal Year
5. Scroll down to Output:
   - Store Number In: custom_branch_name
   - Separator: -
6. Fill Valid From: cutoff date + 1 (e.g., 2026-07-01)
7. Click: **Save**

**Repeat for each branch.**

### Step 6: For Companies Without Branches

No setup needed! The generic company-level rule applies automatically.

To customize the code:

1. Go to: **Numbering Configuration**
2. Open: **Sales Invoice - Company-wise**
3. Edit the "Static Text" segment
4. Change from "SI" to your code (e.g., "INV")
5. Save

---

## Migration Workflow

### Phase 1: Import Old Invoices (Before Cutoff)

```
For each old invoice from legacy ERP:
  1. Set: posting_date = original date (before cutoff)
  2. Set: custom_branch = (if applicable)
  3. Set: narration = OLD_INVOICE_NUMBER (from ERP)
  4. Leave: custom_branch_name empty (will auto-populate)
  5. Save

Result:
  custom_branch_name auto-populates with narration value
  Example: "INV-OLD-2024-0001"
  (Preserves audit trail of old numbers)
```

### Phase 2: Create New Invoices (After Cutoff)

```
For each new invoice created in Frappe:
  1. Set: posting_date = current date (or date after cutoff)
  2. Set: custom_branch = your branch ID (if applicable)
  3. Leave: narration empty (or use for other purposes)
  4. Leave: custom_branch_name empty (will auto-populate)
  5. Save

Result:
  custom_branch_name auto-populates with generated number
  Example: "GEPL-INV-000001-82/83" or "NGI-SI-000001-82/83"
  (New sequential numbering starts fresh)
```

---

## Key Fields & What They Do

| Field | Purpose | Example |
|-------|---------|---------|
| `custom_branch` | Which branch created the invoice | GEPL-Branch-00001 |
| `custom_branch_name` | Generated/migrated invoice number | GEPL-INV-000001-82/83 |
| `narration` | OLD invoice number (for migration) | INV-OLD-2024-0001 |
| `posting_date` | Document date (determines which rule applies) | 2024-05-15 or 2026-07-03 |
| `is_return` | Checkbox - marks return invoices | ☑ (triggers return code) |

---

## Troubleshooting

### Problem: custom_branch_name is blank

**Check:**
1. Is posting_date valid? (should be a proper date)
2. Is the rule enabled? (check Numbering Configuration)
3. Is there a rule that matches?
   - For old: posting_date ≤ cutoff AND narration filled
   - For new: posting_date ≥ cutoff+1

### Problem: Wrong rule is being used

**Check:**
1. Which rule matched? (check rule name vs expected rule)
2. Is custom_branch set correctly?
   - For branch-specific: custom_branch = Branch ID
   - For company-level: custom_branch = (empty)
3. Check rule specificity:
   - Branch rule (has company+branch) = most specific
   - Migration rule = less specific
   - Company rule (has no branch) = least specific

### Problem: Wrong number format

**Check:**
1. Go to: Numbering Configuration
2. Find the rule that matched
3. Review Segments:
   - Are they in the right order?
   - Do they have correct codes/values?
4. Check Separator: (is it - or / or something else?)

### Problem: Old invoice numbers not preserved

**Check:**
1. Is posting_date ≤ cutoff date?
2. Is narration field filled with old invoice number?
3. Is migration rule enabled?
   - Numbering Configuration → Sales Invoice - Legacy Data → Enabled ☑

---

## For Administrators

### Creating Rules for New Companies

**Generic template (copy for each company):**

```
Rule 1: [Company] - Legacy Data
  Document Type: Sales Invoice
  Company: [Your Company]
  Branch: (empty)
  Valid Upto: [Your cutoff date]
  Segments: Document Field (narration)

Rule 2: [Company] - Branch-wise
  Document Type: Sales Invoice
  Company: [Your Company]
  Branch: (user creates per-branch)
  Valid From: [Cutoff date + 1]
  Segments: Company Abbr + Branch Abbr + Code + Number + FY

Rule 3: [Company] - Company-wise
  Document Type: Sales Invoice
  Company: [Your Company]
  Branch: (empty)
  Valid From: [Cutoff date + 1]
  Segments: Company Abbr + Code + Number + FY
```

### Seeding Rules Programmatically

```bash
bench --site <site> console
>>> from avinashgroup_app.scripts.seed_sales_invoice_numbering import seed
>>> seed()
```

This creates the 3 generic rules + Grishma examples.

---

## Technical Details

### How Rule Matching Works

1. **Scope Matching**: Company + Branch
   - Rule with both = most specific (+2 points)
   - Rule with company only = medium (+1 point)
   - Rule with neither = least specific (0 points)

2. **Date Window Matching**: Valid From / Valid Upto
   - Compares document's posting_date against valid_from and valid_upto
   - Document must be within the window to match

3. **Condition Matching**: Field = Value
   - All conditions must match (AND logic)
   - Empty conditions = always matches

4. **Winner**: Most specific rule wins (highest score)
   - If tie: Alphabetically by rule name

### Segment Types Used

| Type | What it produces | Example |
|------|------------------|---------|
| Company Abbr | Company's abbr | GEPL, NGI |
| Branch Abbr | Branch's custom_abbr | KTM, DLH |
| Normal / Return Code | Depends on is_return | INV (normal), RT (return) |
| Document Field | Any field value | narration, remarks |
| Number | Running counter | 000001, 000002 |
| Fiscal Year | From posting_date | 82/83 |
| Static Text | Fixed text | SI, INV |

### Counter Behavior

- **Separate counters per segment combination**
  - GEPL-INV-82/83: counter = 000001, 000002, ...
  - GEPL-RT-82/83: counter = 000001, 000002, ... (different!)
  - NGI-SI-82/83: counter = 000001, 000002, ... (different!)

- **Counters reset by fiscal year**
  - 2024-2025: 000001-000999
  - 2025-2026: 000001-000999 (starts fresh)

- **Deleting an invoice reverts the counter**
  - If you delete invoice #000005 and it's the highest
  - Next counter = 000004 (rolls back)

---

## FAQ

**Q: Can I change the cutoff date after migration starts?**
A: Yes, but old invoices already imported stay as-is. Only affects NEW invoices.

**Q: What if I don't fill narration for old invoices?**
A: custom_branch_name won't populate. Make sure narration is filled during import.

**Q: Can I use a different field instead of custom_branch_name?**
A: Yes. In Numbering Configuration, change "Store Number In" to any text field.

**Q: What if a company wants different format per branch?**
A: Create separate branch-specific rules with different codes for each branch.

**Q: Can I apply this to Purchase Invoice too?**
A: Yes. Use the same 3-rule pattern. Create rules for Purchase Invoice doctype.

**Q: Does this change the document ID (name)?**
A: No. Document ID stays as-is (from standard naming series). Only custom_branch_name changes.

---

## Support

For issues or customizations:

1. Check the **Troubleshooting** section above
2. Review your **Numbering Configuration** rules
3. Test with a sample invoice using "Test on a Document" button
4. Check Frappe error logs for validation messages

