# Fiscal Year-Wise Data Access Control

## Overview

This feature restricts user access to transactions based on assigned fiscal years. It provides a two-level access control system:

1. **Global Level**: `full_access` checkbox on User
2. **Doctype Level**: Per-doctype fiscal year assignments with individual `full_access` override

## Architecture

### Components

1. **New Child DocType**: `User Fiscal Year Access`
   - Fields:
     - `doctype_name` (Link to DocType) - e.g., "Sales Invoice"
     - `fiscal_year` (Link to Fiscal Year) - e.g., "2024-25"
     - `full_access` (Checkbox) - If checked, user sees all fiscal years for that doctype

2. **Custom Fields on User**
   - `full_access` (Checkbox) - Global override: when checked, user sees all data
   - `user_fiscal_years` (Table) - Child table with fiscal year assignments

3. **Backend Filter Hook**: `fiscal_year_filter.py`
   - Applies filters to list queries automatically
   - Validates document access on read
   - Only System Users (user_type="System User") bypass filtering

### Supported DocTypes

The following doctypes have fiscal year filtering applied:
- Sales Invoice
- Sales Order
- Quotation
- Delivery Note
- Purchase Invoice
- Purchase Order
- Request for Quotation
- Supplier Quotation
- Material Request
- Stock Entry
- Stock Reconciliation
- Journal Entry
- Payment Entry
- Attendance

## Usage

### Setting Up User Access

1. Open User form for the employee/user
2. Go to **Fiscal Year Data Access** section
3. **Option A: Global Full Access**
   - Check "Full Access (All Data)" to allow user to see everything
   - Leave table empty

4. **Option B: Restricted Access**
   - Uncheck "Full Access (All Data)"
   - Add rows to "Fiscal Year Access" table:
     - **DocType**: Select the document type (e.g., "Sales Invoice")
     - **Fiscal Year**: Select the fiscal year(s) to allow
     - **Full Access**: 
       - If checked: User sees ALL fiscal years for that doctype
       - If unchecked: User sees ONLY the selected fiscal year

### Example Configurations

**Example 1: Accounting User - Multiple Fiscal Years**
```
User: john@example.com
Full Access (All Data): ☐ unchecked

Fiscal Year Access:
├─ DocType: Sales Invoice,    Fiscal Year: 2024-25, Full Access: ☐
├─ DocType: Sales Invoice,    Fiscal Year: 2025-26, Full Access: ☐
├─ DocType: Purchase Invoice, Fiscal Year: 2024-25, Full Access: ☐
└─ DocType: Purchase Invoice, Fiscal Year: 2025-26, Full Access: ☐

Result: John can see Sales & Purchase Invoices from both FY 2024-25 and 2025-26
```

**Example 2: Sales Manager - Full Access to Sales Invoices**
```
User: sales_mgr@example.com
Full Access (All Data): ☐ unchecked

Fiscal Year Access:
└─ DocType: Sales Invoice, Fiscal Year: (any), Full Access: ☑

Result: Sales Manager can see ALL Sales Invoices from all fiscal years
```

**Example 3: System Administrator**
```
User: admin@example.com
Full Access (All Data): ☑ checked
Fiscal Year Access: (ignored)

Result: Admin can see everything
```

**Example 4: HR Payroll - Specific Fiscal Year**
```
User: payroll@example.com
Full Access (All Data): ☐ unchecked

Fiscal Year Access:
├─ DocType: Attendance, Fiscal Year: 2024-25, Full Access: ☐
├─ DocType: Payroll Entry, Fiscal Year: 2024-25, Full Access: ☐
└─ DocType: Journal Entry, Fiscal Year: 2024-25, Full Access: ☐

Result: Payroll user can only see FY 2024-25 data for these doctypes
```

## Technical Details

### Date Field Mapping

Each doctype uses a specific date field for filtering:

```python
DATE_FIELD_MAP = {
    "Attendance": "attendance_date",
    "Quotation": "transaction_date",
    "Sales Order": "transaction_date",
    "Delivery Note": "posting_date",
    "Purchase Order": "transaction_date",
    "Request for Quotation": "transaction_date",
    "Stock Entry": "posting_date",
    "Stock Reconciliation": "posting_date",
}
```

Default: `posting_date`

### Filtering Logic

**On List View:**
1. Get current user
2. Check `User.full_access` → if YES, no filter applied
3. Look up user's fiscal year assignments for the current doctype
4. If NO assignments found → deny access (empty list)
5. If `full_access=YES` for any row → no filtering (show all fiscal years)
6. If specific fiscal years assigned → filter by their date ranges (OR logic for multiple FY)

**On Document Read:**
1. Same checks as list view
2. Additionally validates that document's date is within allowed fiscal year range
3. Throws error if date is outside allowed range

### Caching

- User fiscal access is cached using `frappe.cache()` with request cache
- Cache is cleared when User document is updated
- Fiscal Year dates are also cached

## API Methods

### Get User Fiscal Access (Whitelist)

```python
# Python
access_map = frappe.call("avinashgroup_app.custom_code.fiscal_year_filter.get_user_fiscal_access", 
                          args={"user": "john@example.com"})
```

Returns:
```python
{
    "__full_access__": True  # If user has global full access, OR
    "Sales Invoice": [
        {"fiscal_year": "2024-25", "full_access": False},
        {"fiscal_year": "2025-26", "full_access": False}
    ],
    "Purchase Invoice": [
        {"full_access": True}  # This doctype has full access for this user
    ]
}
```

## Bypass / Admin Override

- **System Users** (user_type="System User") are NOT subject to fiscal year filtering
- Any user marked as "System User" in the User type field can see all documents
- Administrators should have user_type="System User" for full access

## Files Modified/Created

### New Files
- `/avinashgroup_app/avinash_group_app/doctype/user_fiscal_year_access/` - New child doctype
- `/avinashgroup_app/custom_code/fiscal_year_filter.py` - Filter logic
- `/avinashgroup_app/avinash_group_app/custom/user.json` - User custom fields

### Modified Files
- `/avinashgroup_app/hooks.py` - Added list_filters and doc_events

## Testing Checklist

- [ ] User with global full_access can see all documents
- [ ] User with no fiscal year assignments cannot see any documents
- [ ] User with specific FY assignments sees only those FY documents
- [ ] User with full_access=YES for a doctype sees all fiscal years
- [ ] System Manager/Administrator sees all documents
- [ ] Document access denied error shows when opening out-of-range document
- [ ] Cache clears when User is updated
- [ ] Date range filtering works for multiple fiscal years (OR logic)

## Future Enhancements

- [ ] UI improvements for easier user assignment
- [ ] Bulk user assignment feature
- [ ] Audit trail of data access
- [ ] Approval workflow integration
- [ ] Date range customization per user (instead of using full FY dates)
