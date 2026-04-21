# Dynamic Approval Workflow — Full Development Log

## Overview

A custom multi-level sequential approval system built on Frappe v15/ERPNext for `avinashgroup_app`. Replaces static ERPNext workflows with a configurable, company-scoped, criteria-driven approval chain.

---

## Phase 1 — Core Workflow Engine

### What was built
- **`Dynamic Approval Setting`** doctype — configures the approval chain per doctype + company
- **`Dynamic Approval Approver`** child table — user fills this on the document before submitting (their chosen approvers, in order)
- **`Dynamic Approval Fixed Approver`** child table — admin-configured approvers automatically appended at the end of every chain
- **`Dynamic Approval History`** child table — audit log written on every approval action

### Custom fields created on target doctypes (via `setup_workflow`)
| Field | Type | Purpose |
|---|---|---|
| `custom_current_approval_level` | Int (hidden) | Tracks which level is currently pending |
| `custom_current_approver` | Data (hidden) | User ID of the approver who must act now |
| `custom_total_approval_levels` | Int (hidden) | Total levels = user rows + fixed approvers |
| `custom_approval_approvers` | Table | The approval hierarchy (visible, editable before submit) |
| `custom_approval_history` | Table | Timeline of all approval actions (read-only) |

### Workflow states and transitions
- **Draft** → Submit for Approval → **Pending Approval**
- **Pending Approval** → Approve (intermediate) → **Pending Approval** (level++)
- **Pending Approval** → Approve (final) → **Approved** (docstatus=1)
- **Pending Approval** → Reject → **Rejected**
- **Rejected** → Resubmit → **Pending Approval**

### Key Python hooks (`dynamic_approval.py`)
- `before_workflow_action` — central hook; sets level fields and advances the chain on each Approve
- `on_update` — re-syncs approver + total after every save while Pending Approval
- `validate` — blocks non-current-approvers from saving; protects already-approved rows
- `before_save` — logs "Created" on new documents
- `setup_workflow()` — idempotent whitelisted function; creates custom fields + workflow on demand

### Client-side (`approval_field_visibility.js` — global)
- Hides the three hidden driver fields unless a config exists for the doctype+company
- Locks the entire form (`frm.disable_form()`) for non-current-approvers while Pending Approval
- Visually dims already-approved rows in the hierarchy table (opacity + pointer-events)

### Per-doctype JS (`purchase_order.js`)
- Approval progress banner: `✔ Level 1 → ⏳ Level 2 (current) → ◯ Level 3`
- Hides Approve/Reject buttons from non-current-approvers
- Rejection reason dialog (prompts for reason before allowing Reject action)

---

## Phase 2 — Department-Aware Fixed Approvers

### What was added
- `department` column on `Dynamic Approval Fixed Approver`
- Fixed approvers filtered by the document's department field at runtime
- `_get_department_fieldname()` helper — checks `custom_department` then `department` on the target doctype
- Blank department rows = global fallback (applies to all departments)

---

## Phase 3 — Form Locking (Non-Approver Protection)

### Problem
Anyone could edit a document in Pending Approval state. Only the current approver should be able to make changes.

### Solution
**Server-side (`validate` hook):**
- If `workflow_state == "Pending Approval"` and `frappe.session.user != current_approver` → throw
- Already-approved rows (level < current_level) cannot be changed or deleted even by the current approver

**Client-side (`approval_field_visibility.js`):**
- `frm.disable_form()` for non-current-approvers → fully read-only, no Save button
- Grid rows with level < current_level: opacity 0.55 + pointer-events none

---

## Phase 4 — Group-Based Dynamic Criteria Matching

### Problem
The old system only matched configs by `doctype + company + department` (hardcoded dimensions). Adding new matching dimensions (user, cost_center, territory, etc.) required code changes.

### Solution: Criteria Table + Group Number

**New doctype: `Dynamic Approval Match Criteria`**
| Field | Type | Purpose |
|---|---|---|
| `group` | Int | Links criteria rows to fixed approver rows of the same group |
| `field_name` | Autocomplete | Any fieldname on the target document |
| `field_value` | Autocomplete | Expected value to match |

**`Dynamic Approval Fixed Approver` — updated**
- Replaced `department` column with `group` (Int, default 0)
- Approvers with `group = N` are used when the criteria group N matches the document

**`Dynamic Approval Setting` — updated**
- Removed hardcoded `department` column
- Added `Match Criteria` child table
- `company` + `document_type` remain static required columns (fast DB-level scoping)

### How matching works
1. **Phase 1 (DB):** Filter all active settings by `document_type + company`
2. **Phase 2 (Python):** For each setting, score each group:
   - Check all criteria rows for that group: `doc.field_name.strip() == field_value.strip()`
   - All criteria must match (AND logic)
   - Score = number of matching criteria rows
3. Group with the **highest score** wins (most specific match)
4. A group with **zero criteria rows** = catch-all fallback (score 0)
5. The winning group's fixed approvers are appended to the chain

### Example
```
Setting: Purchase Order + Nepal Gas Udhyog (Karnali) Pvt. Ltd.

Match Criteria table:
  group=0, field_name=custom_department, field_value=Accounts - DC

Fixed Approvers table:
  group=0, approver=bishalp1080@gmail.com       ← Level 2
  group=0, approver=bipeen.shrestha@...          ← Level 3
```
A PO with `custom_department = Accounts - DC` matches group 0 → 2 fixed approvers appended → total 3 levels.

---

## Phase 5 — Pinned Setting (Performance Optimisation)

### Problem
Every approve/reject/resubmit action re-ran the full criteria scan (N+3 DB queries). For documents already in the approval flow, the correct setting is already known.

### Solution: Pin setting + group on first submission

**Two new hidden fields added to target doctypes:**
| Field | Purpose |
|---|---|
| `custom_approval_setting` | Link to Dynamic Approval Setting — pinned on first submit |
| `custom_approval_group` | Int — the winning group number, pinned on first submit |

**Lookup logic in `_get_config_for_doc()`:**
- **Fast path** (doc has `custom_approval_setting` set): fetch the pinned setting + approvers for the pinned group → **2 DB queries**
- **Slow path** (first submission or field not set): full criteria scan → pin both values on the doc → saved to DB

Users can also **pre-select** the approval chain by making `custom_approval_setting` visible on a form. The field's `set_query` filters by `document_type + company + is_active`.

---

## Phase 6 — Smart Field Pickers in Criteria UI

### `field_name` — Autocomplete dropdown
- Populated from the `document_type`'s actual fields via `frappe.model.with_doctype()`
- Standard fields prepended: `name`, `owner`, `company`, `department`, `modified_by`
- Refreshes when `document_type` changes

### `field_value` — Dynamic Autocomplete
- When `field_name` is a **Link field** → fetches values from the linked doctype (`frappe.client.get_list`)
- When `field_name` is a **Select field** → shows the predefined options
- When `field_name` is plain Data/Int → free text input
- Standard field map: `owner`/`modified_by` → User, `company` → Company, `department` → Department

---

## Bugs Fixed

### 1. Validate blocking the current approver during Approve
**Root cause:** `before_workflow_action` updates `custom_current_approver` to the *next* approver in memory before `validate` runs. So `doc.get(CURRENT_APPROVER_FIELD)` returns the next approver, blocking the current one.

**Fix:** Read from DB in `validate`:
```python
current_approver = frappe.db.get_value(doc.doctype, doc.name, CURRENT_APPROVER_FIELD) or doc.get(CURRENT_APPROVER_FIELD)
```

### 2. Criteria match failing due to leading/trailing whitespace
**Root cause:** `field_value` stored with a leading space (` Accounts - DC`) didn't match the document's value (`Accounts - DC`).

**Fix:** `.strip()` both sides of the comparison:
```python
str(doc.get(c.field_name) or "").strip() == str(c.field_value or "").strip()
```

### 3. `field_name = department` not matching (wrong fieldname)
**Root cause:** Purchase Order uses `custom_department` not `department`. The criteria was set up with the wrong fieldname.

**Fix:** The `field_name` Autocomplete now shows actual doctype fields, making it impossible to type the wrong name. Existing bad data was fixed in DB.

### 4. Config returning None (levels stayed at 0)
**Root cause:** Whitespace mismatch in criteria prevented any group from matching → config returned None → `before_workflow_action` returned early → `custom_current_approval_level` and `custom_total_approval_levels` stayed at 0 → workflow conditions False → no Approve/Reject buttons shown.

**Fix:** Combination of the `.strip()` fix above and correcting the `field_name` to `custom_department`.

---

## Files Changed

| File | Change |
|---|---|
| `custom_code/dynamic_approval.py` | Core logic: group-based lookup, fast-path pinning, validate DB read fix, `.strip()` comparison |
| `avinash_group_app/doctype/dynamic_approval_setting/dynamic_approval_setting.json` | Removed `department`, added `match_criteria` table |
| `avinash_group_app/doctype/dynamic_approval_setting/dynamic_approval_setting.py` | Updated `autoname`, `validate` |
| `avinash_group_app/doctype/dynamic_approval_setting/dynamic_approval_setting.js` | `field_name` + `field_value` dynamic dropdowns |
| `avinash_group_app/doctype/dynamic_approval_fixed_approver/dynamic_approval_fixed_approver.json` | Replaced `department` with `group` |
| `avinash_group_app/doctype/dynamic_approval_match_criteria/` | **New** child doctype |
| `public/js/approval_field_visibility.js` | Form locking, row dimming, `set_query` for approval setting picker |
| `hooks.py` | Wired `validate` hook + JS version bump |
