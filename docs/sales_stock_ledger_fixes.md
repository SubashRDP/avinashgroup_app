# Sales Stock Ledger — Fixes & Changes

## File Locations
- **Python**: `avinashgroup_app/avinash_group_app/report/sales_stock_ledger/sales_stock_ledger.py`
- **JS**: `avinashgroup_app/avinash_group_app/report/sales_stock_ledger/sales_stock_ledger.js`

---

## Bugs Fixed

### 1. Item Group filter — wrong table column
**Problem**: `sii.item_group` does not exist on `tabSales Invoice Item`.  
**Fix**: Changed to `item.item_group` (uses the existing `JOIN tabItem item` in the query).

```python
# Before
cond.append("sii.item_group = %(item_group)s")
# After
cond.append("item.item_group = %(item_group)s")
```

---

### 2. `sle.qty_after_transaction` — Unknown column error
**Problem**: Summarized + Merge mode query used `sle.qty_after_transaction` but had no `LEFT JOIN tabStock Ledger Entry`.  
**Fix**: Added the missing JOIN to the merge query branch.

```python
LEFT JOIN `tabStock Ledger Entry` sle
    ON  sle.voucher_no = si.name
    AND sle.item_code  = sii.item_code
    AND sle.voucher_detail_no = sii.name
    AND sle.docstatus = 1
```

---

### 3. Merge qty — Sales Return not subtracted
**Problem**: `ELSE + sii.qty` in merge query (returns were being added, not subtracted).  
**Fix**: Changed to `ELSE -sii.qty`.

---

### 4. Float precision not respected
**Problem**: System float precision (e.g. 5) was not applied to Float columns in the report.  
**Fix**: Added `_get_float_precision()` helper, applied `"precision": precision` to all Float columns in both detail and summarized column definitions.

```python
def _get_float_precision():
    from frappe.utils import cint
    return cint(frappe.db.get_default("float_precision")) or 2
```

---

### 5. Item filter — not scoped to company (JS)
**Problem**: Item dropdown showed items from all companies.  
**Fix**: Added `get_query` to Item filter using `tabItem Default.company`.

```js
get_query: function () {
    const company = frappe.query_report.get_filter_value("company");
    return company
        ? { filters: [["Item Default", "company", "=", company]] }
        : {};
},
```

---

### 6. Item Group filter — not scoped to company (JS)
**Problem**: Item Group dropdown showed groups from all companies.  
**Fix**: Added `get_query` using `custom_company` field on `tabItem Group`.

```js
get_query: function () {
    const company = frappe.query_report.get_filter_value("company");
    return company ? { filters: { custom_company: company } } : {};
},
```

---

### 7. Changing company did not refresh report or clear item/item_group
**Problem**: `on_change` on company filter cleared branch/warehouse/price_list/voucher_no but not item or item_group, and did not re-run the report.  
**Fix**: Added clear for item & item_group, added `frappe.query_report.refresh()`.

```js
on_change: function () {
    frappe.query_report.set_filter_value("branch", "");
    frappe.query_report.set_filter_value("warehouse", "");
    frappe.query_report.set_filter_value("price_list", "");
    frappe.query_report.set_filter_value("voucher_no", "");
    frappe.query_report.set_filter_value("item", "");
    frappe.query_report.set_filter_value("item_group", "");
    frappe.query_report.refresh();
},
```

---

## DB Field Reference
| Table | Company Field |
|---|---|
| `tabItem` | `custom_company` |
| `tabItem Default` | `company` |
| `tabItem Group` | `custom_company` |
| `tabSales Invoice` | `company` |

---

## Pending / To Investigate
- Detail mode not working as expected (under investigation)
