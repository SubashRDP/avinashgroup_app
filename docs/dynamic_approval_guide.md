# Dynamic Approval System — Implementation Guide

**App:** `avinashgroup_app`
**Branch:** `workflow`
**Last updated:** 2026-04-15

---

## Table of Contents

1. [What It Does](#1-what-it-does)
2. [Architecture](#2-architecture)
3. [Files & Doctypes](#3-files--doctypes)
4. [How the Flow Works](#4-how-the-flow-works)
5. [One-Time Setup (per doctype)](#5-one-time-setup-per-doctype)
6. [How to Test](#6-how-to-test)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. What It Does

Provides a configurable, multi-level sequential approval workflow that can be attached to **any Frappe doctype** (currently used on Purchase Order).

**Key design decisions:**
- The user filling the document adds their own approvers in an **Approval Hierarchy** table (Level 1, Level 2 …).
- After all user-defined levels are approved, the system automatically checks **Fixed Approvers** configured in `Dynamic Approval Setting` (e.g. Finance Head always approves last).
- Fixed approvers are **never shown** on the document — they exist only in the Setting.
- **Administrator** can approve/reject at any level but still follows the sequence (can't skip levels).
- **No ping-pong states** — the document stays in `Pending Approval` throughout all intermediate approvals.

---

## 2. Architecture

### Approval Level Resolution (the Union)

```
Document's Approval Hierarchy table   →   Levels 1 to N    (user-defined, visible)
Dynamic Approval Setting fixed approvers →  Levels N+1 to N+M  (system, hidden)
─────────────────────────────────────────────────────────────
Total levels = N + M
```

The fixed approvers are **never written to the document**. Every level check queries both sources at runtime.

### Workflow States

```
Draft
  │  "Submit for Approval"
  │  [blocked if Approval Hierarchy is empty]
  ▼
Pending Approval  ──── "Approve" (more levels remain) ────► Pending Approval (self)
  │                                                              ↑ level++
  │  "Approve" (this IS the last level)
  ▼
Approved  (docstatus = 1)

Pending Approval
  │  "Reject"
  ▼
Rejected
  │  "Resubmit"
  ▼
Pending Approval  (level resets to 1)
```

### Who Can Approve / Reject

| User | Permission |
|------|-----------|
| Listed approver at `current_level` | Yes |
| Administrator | Yes — at any level, but level still increments sequentially |
| Anyone else | No — buttons hidden in UI + server-side condition blocks |

---

## 3. Files & Doctypes

### Python

| File | Purpose |
|------|---------|
| `avinashgroup_app/custom_code/dynamic_approval.py` | All logic — hooks, level resolution, workflow conditions, setup |

### Doctypes

| DocType | Type | Purpose |
|---------|------|---------|
| `Dynamic Approval Setting` | Main doctype | Config per doctype + company + department |
| `Dynamic Approval Approver` | Child table | Approval hierarchy rows on the target document (level + approver) |
| `Dynamic Approval Fixed Approver` | Child table | Fixed approvers on the Setting (hidden from document) |

### Custom Fields created on target doctype (by Setup Workflow)

| Fieldname | Type | Purpose |
|-----------|------|---------|
| `custom_current_approval_level` | Int (hidden) | Tracks which level is currently pending |
| `custom_approval_approvers` | Table → Dynamic Approval Approver | The approval hierarchy the user fills in |

### Hooks registered (in `hooks.py`)

```python
before_save            → dynamic_approval.before_save
on_update              → dynamic_approval.on_update
before_workflow_action → dynamic_approval.before_workflow_action
```
Registered for `"*"` (all doctypes) but short-circuits immediately if the doctype has no active `Dynamic Approval Setting`.

### JavaScript

| File | What it does |
|------|-------------|
| `public/js/purchase_order.js` | On `refresh`: calls `is_current_approver` API and hides Approve/Reject buttons for non-approvers |

---

## 4. How the Flow Works

### Step-by-step

**1. User creates a Purchase Order**
- Fills in the `Approval Hierarchy` table with their approvers (Level 1, Level 2 …)
- Saves the document (stays in `Draft`)

**2. User clicks "Submit for Approval"**
- `before_workflow_action` fires:
  - Checks the `Approval Hierarchy` table is not empty → throws error if empty
  - Sets `custom_current_approval_level = 1`
- Workflow condition on this transition is empty (no condition) → always fires
- State changes to `Pending Approval`
- `on_update` fires → emails Level 1 approver

**3. Level 1 approver opens the document**
- `is_current_approver` API is called from JS → returns `True` for the Level 1 approver
- Approve and Reject buttons are visible to them; hidden for everyone else

**4. Level 1 approver clicks "Approve"**
- Frappe evaluates transition conditions:
  - `wf_can_approve_more` → checks: is session.user the Level 1 approver? AND is Level 1 < total levels?
  - `wf_can_approve_final` → checks: is session.user the Level 1 approver? AND is Level 1 == total levels?
- Whichever is True fires its transition
- `before_workflow_action` fires:
  - If intermediate: sets `custom_current_approval_level = 2`
  - If final: leaves level as-is, doc transitions to `Approved`
- `on_update` fires → emails Level 2 approver (if intermediate)

**5. After all user-defined levels approved**
- System now checks Dynamic Approval Setting fixed approvers
- The `_is_approver_at_level` function: `level > user_count` → reads from `config["fixed_approvers"]`
- Notification emails the fixed approver
- Process continues the same way

**6. Rejection**
- `before_workflow_action` sets `doc.flags.is_rejection = True`
- State moves to `Rejected`
- Requester sees the document in `Rejected` state, can click `Resubmit`
- On Resubmit: level resets to 1, emails Level 1 approver again

### Key function: `_is_approver_at_level`

```
level 1 → N   : query tabDynamic Approval Approver WHERE parent=docname AND level=N
level N+1 → end: config["fixed_approvers"][level - N - 1]  (0-indexed)
Administrator  : always returns True (bypasses the lookup)
```

### Workflow condition strings (baked in at setup time)

```python
# Intermediate approval condition
frappe.get_attr("avinashgroup_app.custom_code.dynamic_approval.wf_can_approve_more")
    ("Purchase Order", doc.name, frappe.session.user)

# Final approval condition
frappe.get_attr("avinashgroup_app.custom_code.dynamic_approval.wf_can_approve_final")
    ("Purchase Order", doc.name, frappe.session.user)

# Rejection condition
frappe.get_attr("avinashgroup_app.custom_code.dynamic_approval.wf_can_reject")
    ("Purchase Order", doc.name, frappe.session.user)
```

These are stored directly in the Workflow document's transitions. `frappe.get_attr()` is available in Frappe's `safe_eval` because `frappe` (the real module) is passed in scope.

---

## 5. One-Time Setup (per doctype)

### Step 1 — Create a Dynamic Approval Setting

Go to: **Avinash Group App → Dynamic Approval Setting → New**

| Field | Value |
|-------|-------|
| Document Type | `Purchase Order` |
| Company | Your company |
| Department | Department this config applies to (or leave blank for company-wide) |
| Approver Table Fieldname | `custom_approval_approvers` (default) |
| Current Level Fieldname | `custom_current_approval_level` (default) |
| Is Active | ✓ |

In the **Fixed Approvers** section, add anyone who must always approve at the end (e.g. Finance Head). Order matters — first row = first fixed level.

### Step 2 — Click "Setup Workflow"

On the saved Dynamic Approval Setting record, click the **Setup Workflow** button (top right).

This will:
1. Create `Memo Requester` and `Memo Approver` roles if missing
2. Create Workflow State records (Draft, Pending Approval, Approved, Rejected) if missing
3. Create custom fields on the target doctype if missing:
   - `custom_current_approval_level` (hidden Int)
   - `custom_approval_approvers` (Table)
4. Create (or update) the Workflow document on the target doctype

### Step 3 — Clear cache

```bash
bench --site avinas1 clear-cache
```

Or from the browser: **Settings → Clear Cache**

---

## 6. How to Test

### Test 1: Basic 2-level approval

**Setup:**
- Dynamic Approval Setting for Purchase Order, Company = Avinash Group, no fixed approvers
- Two users: User A (approver level 1), User B (approver level 2)

**Steps:**
1. Create a PO as any user
2. In `Approval Hierarchy` table: add User A at Level 1, User B at Level 2
3. Click **Submit for Approval**
   - Expected: State = `Pending Approval`, `custom_current_approval_level = 1`
   - Expected: User A receives an email
4. Log in as User A, open the PO
   - Expected: Approve and Reject buttons visible
   - Expected: `is_current_approver` returns `True` for User A
5. Click **Approve**
   - Expected: State stays `Pending Approval`, level = 2
   - Expected: User B receives an email
6. Log in as User B, click **Approve**
   - Expected: State = `Approved`, docstatus = 1

### Test 2: Fixed approvers (Phase 2)

**Setup:**
- Dynamic Approval Setting with 1 fixed approver (User C)
- PO with Approval Hierarchy: User A at Level 1 only

**Steps:**
1. Submit PO → level = 1, User A emailed
2. User A approves → level = 2 (now in fixed approvers range)
   - Expected: User C emailed (not visible on the PO's hierarchy table)
3. User C opens PO
   - Expected: Approve/Reject buttons visible for User C
4. User C approves → State = `Approved`

### Test 3: Empty hierarchy blocked

1. Create a PO, leave Approval Hierarchy empty
2. Click **Submit for Approval**
   - Expected: Error message: "Please add at least one approver in the Approval Hierarchy before submitting."

### Test 4: Rejection and resubmit

1. Submit PO with Level 1 = User A
2. User A clicks **Reject** (enters rejection reason in dialog)
   - Expected: State = `Rejected`
3. Requester opens PO, clicks **Resubmit**
   - Expected: State = `Pending Approval`, level = 1, User A emailed again

### Test 5: Administrator bypass

1. Submit PO with Level 1 = User A
2. Log in as Administrator, open the PO
   - Expected: Approve and Reject buttons visible (Administrator always passes `_is_approver_at_level`)
3. Administrator clicks **Approve**
   - Expected: Level advances normally (Administrator follows the flow)

### Test 6: Non-approver sees no buttons

1. Submit PO with Level 1 = User A
2. Log in as User B (not in hierarchy), open the PO
   - Expected: Approve and Reject buttons are hidden

### Verify via console

```python
# Check current level on a PO
frappe.db.get_value("Purchase Order", "PO-00001", "custom_current_approval_level")

# Check who is the approver at current level
from avinashgroup_app.custom_code.dynamic_approval import _get_config_for_docname, _get_effective_approver_at_level
config = _get_config_for_docname("Purchase Order", "PO-00001")
level = frappe.db.get_value("Purchase Order", "PO-00001", "custom_current_approval_level")
approver = _get_effective_approver_at_level("Purchase Order", "PO-00001", level, config)
print(f"Current approver at level {level}: {approver}")

# Check total levels
from avinashgroup_app.custom_code.dynamic_approval import _get_total_levels
total = _get_total_levels("Purchase Order", "PO-00001", config)
print(f"Total levels: {total}")

# Manually test a workflow condition
from avinashgroup_app.custom_code.dynamic_approval import wf_can_approve_more, wf_can_approve_final
print(wf_can_approve_more("Purchase Order", "PO-00001", "user@example.com"))
print(wf_can_approve_final("Purchase Order", "PO-00001", "user@example.com"))
```

---

## 7. Troubleshooting

### Approve/Reject buttons not showing for the correct approver

1. Check `custom_current_approval_level` on the doc — verify it's set correctly
2. Check the `Approval Hierarchy` table has rows with correct `level` values (1, 2, 3 …)
3. Run `is_current_approver` from console:
   ```python
   from avinashgroup_app.custom_code.dynamic_approval import is_current_approver
   frappe.session.user = "user@example.com"
   print(is_current_approver("Purchase Order", "PO-00001"))
   ```
4. Clear Redis cache: `bench --site avinas1 clear-cache`

### Workflow condition never fires (no valid transition error)

1. Open the Workflow document for Purchase Order → check transitions are present
2. Verify the condition strings in the transitions contain `wf_can_approve_more` / `wf_can_approve_final`
3. Check `Dynamic Approval Setting` is active (`is_active = 1`)
4. Run `wf_can_approve_more` from console (see above) to debug

### Fixed approvers not being used

1. Check `Dynamic Approval Setting` has rows in the `Fixed Approvers` table
2. Clear the config cache:
   ```python
   from avinashgroup_app.custom_code.dynamic_approval import clear_config_cache
   clear_config_cache("Purchase Order", "Avinash Group", "Admin")
   ```
3. Verify `_get_config_for_docname` returns the right config with `fixed_approvers` populated

### Department not matching

The system reads department from `custom_department` field first, then `department`. If neither exists, it falls back to company-only lookup.

Check which field holds the department on your doctype:
```python
meta = frappe.get_meta("Purchase Order")
print(meta.has_field("custom_department"), meta.has_field("department"))
```

### Migration error (HRMS patch)

The error `Column 'amount' in SET is ambiguous` is a pre-existing HRMS bug unrelated to this system. Use:
```bash
bench --site avinas1 migrate --skip-failing
```
