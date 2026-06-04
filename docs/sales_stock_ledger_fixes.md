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

## Nepali Month Support & UI Polish (2026-06-04)

### Nepali (Bikram Sambat) month reporting
The report now reports **in Nepali month**. This intentionally reuses the
shared dual-date system in `rdp_common_app/public/js/report_nepali_date.js`
rather than adding a parallel month selector:

- Because the report exposes `from_date` / `to_date` (`Date` fieldtype),
  rdp_common_app automatically:
  - renders a Nepali **BS date input** beside each date filter (with a Nepali
    date picker), and
  - adds the **📅 Select Month** button whose **Nepali (BS)** tab sets the
    period to a whole Bikram Sambat month.
- A new **Nepali Date (BS)** column was added to the Detail view, showing each
  voucher's posting date in BS (e.g. `2082-12-05`). Conversion uses the
  `nepali_datetime` library (`_to_nepali_date_str`).
- `get_default_nepali_month()` (whitelisted) returns the current BS month and
  its Gregorian range — a reusable helper for defaults/automation.

> A dedicated `period_type` + `nepali_year` + `nepali_month` filter set was
> prototyped first, but it duplicated and visually clashed with the global
> Select Month widget (two month pickers, hidden date fields). It was removed
> in favour of the consistent shared mechanism.

### Period validation (graceful)
`_resolve_period()` returns an **empty report** (no error popup) when the
period is incomplete, and only raises for a genuinely inverted range
(*From Date after To Date*). This keeps the first auto-load clean.

### UI polish
- Header band, zebra striping, hover highlight, and a highlighted bold **Total** row.
- Voucher Type rendered as colour-coded pill badges — green **Sales Invoice**,
  red **Sales Return** (via `formatter` + `_tagRows`).
- Nepali date emphasised (tabular figures).

### Tested (site: `avinas1`)
- Detail / Summarized / Summarized+Merge — all error-free.
- BS dates verified contained within the selected month (e.g. Chaitra 2082 →
  all rows `2082-12-01 … 2082-12-30`).
- Sales Return rows show negative qty + red badge; totals correct.
- Incomplete period → empty (no error); `from > to` → clean validation error.
