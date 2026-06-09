# Nepal Transaction Deletion Override

## Purpose

By default, **ERPNext blocks deleting submitted/cancelled Sales Invoices and Payment
Entries for any company whose country is Nepal**, for every user. This override lifts
that block **only for authorized roles (System Manager / Administrator)**, on the
`avinashgroup_app` site only. Everyone else keeps the original restriction.

- **Module:** `avinashgroup_app/custom_code/regional_deletion_override.py`
- **Wired in:** `avinashgroup_app/__init__.py`
- **Overrides (without editing):** `erpnext.regional.check_deletion_permission`

---

## 1. The restriction being overridden (ERPNext core)

ERPNext registers a deletion guard as an `on_trash` document event:

```python
# erpnext/erpnext/hooks.py
doc_events = {
    "Sales Invoice": { "on_trash": "erpnext.regional.check_deletion_permission" },
    "Payment Entry": { "on_trash": "erpnext.regional.check_deletion_permission" },
}
```

```python
# erpnext/erpnext/regional/__init__.py
def check_deletion_permission(doc, method):
    region = get_region(doc.company)              # = the company's Country
    if region in ["Nepal"] and doc.docstatus != 0:
        frappe.throw(_("Deletion is not permitted for country {0}").format(region))
```

- `on_trash` fires **immediately before a document is deleted**.
- `get_region(company)` returns the company's **Country** field.
- `docstatus != 0` means the guard applies to **submitted (1) and cancelled (2)**
  documents. Drafts (0) were never blocked.
- Because you must *cancel* a submitted document before deleting it, and the cancelled
  document then can't be trashed, the practical effect is: **submitted transactions for a
  Nepal company can never be removed** — the user sees the popup
  *"Deletion is not permitted for country Nepal"*.

> Why the guard exists: Nepal IRD law restricts deleting fiscal documents. We are
> deliberately narrowing it to trusted roles, not removing it.

---

## 2. How the override works — monkey-patching by name

The single most important detail: the hook value
`"erpnext.regional.check_deletion_permission"` is a **dotted string**, not a function
object. Frappe resolves it **fresh on every delete** with `frappe.get_attr()`, which is
effectively:

```python
module  = importlib.import_module("erpnext.regional")     # the module object
handler = getattr(module, "check_deletion_permission")    # looked up by NAME each time
```

Frappe never caches the original function reference — it re-reads the name on the module
every time. So if we **rebind that name** to our own function, our function runs instead.
No core file is touched.

```python
# avinashgroup_app/custom_code/regional_deletion_override.py
import frappe
import erpnext.regional

# Capture the genuine original BEFORE we replace it, so unauthorized users get
# the exact (and future-proof) ERPNext behavior.
_original_check_deletion_permission = erpnext.regional.check_deletion_permission

AUTHORIZED_ROLES = {"System Manager"}   # Administrator always carries this role

def check_deletion_permission(doc, method):
    # Scope the bypass to sites where avinashgroup_app is installed (see §4).
    if "avinashgroup_app" in frappe.get_installed_apps():
        # Authorized roles may delete; everyone else keeps the restriction.
        if frappe.session.user == "Administrator" or AUTHORIZED_ROLES & set(frappe.get_roles()):
            return                                  # allow the delete
    return _original_check_deletion_permission(doc, method)   # original guard

def apply_patch():
    erpnext.regional.check_deletion_permission = check_deletion_permission
```

Behavior:

| Caller | Result |
|--------|--------|
| Administrator / System Manager (on the avinas site) | `return` → no throw → **delete proceeds** |
| Any other user | delegates to the original ERPNext guard → **original popup** |
| Non-Nepal company (any user) | original guard returns without throwing → unchanged |

Delegating to `_original_...` (instead of re-implementing the Nepal/docstatus check) means
unauthorized users keep ERPNext's exact logic even if ERPNext changes it in a future
release.

---

## 3. When the patch is applied — at app load

The patch must run **once per Python process, before any delete**. It is hooked into the
app package init:

```python
# avinashgroup_app/__init__.py
try:
    from avinashgroup_app.custom_code.regional_deletion_override import apply_patch as apply_deletion_patch
    apply_deletion_patch()
except Exception:
    import frappe
    frappe.log_error(frappe.get_traceback(), "Regional deletion-permission patch failed to load")
```

Frappe imports every app's `__init__.py` when it boots a worker process, so
`apply_patch()` runs automatically in **every web worker and background worker**. This is
why it covers both UI deletes and programmatic deletes, and why `bench restart` is needed
after changing it. The `try/except` guarantees a bad import logs an error instead of
crashing app boot.

---

## 4. Multi-site behavior (important)

A Frappe bench is multi-tenant: **one worker process serves multiple sites**, and Python
modules live in a shared `sys.modules`. So the rebinding of
`erpnext.regional.check_deletion_permission` is **process-global, not per-site** — once a
worker has served the avinas site (importing `avinashgroup_app` and running the patch),
the rebinding is live for *every* site that worker serves afterward.

To keep other sites on the same bench (e.g. `sarathi`) on ERPNext's stock behavior, the
patched function gates the bypass on `frappe.get_installed_apps()`, which **is** evaluated
per-site at delete time:

```python
if "avinashgroup_app" in frappe.get_installed_apps():   # True only on the avinas site
    ...bypass for authorized roles...
return _original_check_deletion_permission(doc, method) # all other sites → original
```

| Site | `avinashgroup_app` installed? | Effect of the patch |
|------|------------------------------|---------------------|
| avinas1 | Yes | Authorized roles can delete Nepal transactions |
| sarathi (and any other) | No | Delegates to ERPNext original → restriction intact |

---

## 5. Configuration

To grant the bypass to additional roles, edit one line:

```python
AUTHORIZED_ROLES = {"System Manager", "Accounts Manager"}   # add roles here
```

No other change is needed; the guard logic and wiring stay the same.

---

## 6. Verification

Run on the target site (`bench --site avinas1 console`):

```python
# 1. Patch is live
import erpnext.regional
erpnext.regional.check_deletion_permission.__module__
# -> 'avinashgroup_app.custom_code.regional_deletion_override'

# 2. Real end-to-end: create -> submit -> cancel a Payment Entry for a Nepal
#    company, then frappe.delete_doc(...) as:
#      - a non-System-Manager  -> throws "Deletion is not permitted for country Nepal"
#      - Administrator/System Manager -> deletes successfully
```

Confirmed results during implementation:

```
NON-ADMIN (no System Manager): BLOCKED 'Deletion is not permitted for country Nepal'  -- PASS
SYSTEM MANAGER:                deleted, exists_after=None                              -- PASS
sarathi site:                  "avinashgroup_app" in get_installed_apps() == False     -- bypass skipped
```

---

## 7. Files

| File | Change |
|------|--------|
| `avinashgroup_app/custom_code/regional_deletion_override.py` | New — the patch |
| `avinashgroup_app/__init__.py` | Edited — calls `apply_patch()` at load |
| `erpnext/regional/__init__.py`, `erpnext/hooks.py` | **Untouched** (overridden at runtime) |
