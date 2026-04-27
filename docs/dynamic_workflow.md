# Dynamic Approval Workflow — End-to-End with Reasoning

**App:** `avinashgroup_app` · **Branch:** `workflow` · **Authoritative files as of 2026-04-24**

This is the deep walkthrough. Every code block below is copied from the repo and annotated with **why** it is written that way. Read it top to bottom to understand a submission's life from the moment a user clicks "Submit for Approval" to the moment `docstatus` flips to `1`.

---

## 1. What the system does — in one paragraph

A **Dynamic Approval Setting** attaches a configurable, multi-level sequential approval workflow to **any** Frappe doctype. The requester picks their own approvers in a per-document **Approval Hierarchy** table, and the Setting appends **fixed approvers** on top. Which fixed approvers get appended is decided at submission time by a **criteria scan** against the document's fields (company, department, supplier, or any other field) — so one Setting can hold many independent approval rules ("sections"). The document walks through the levels one at a time, staying in `Pending Approval` until the final approver approves, at which point it flips to `Approved` and `docstatus=1`.

---

## 2. High-level architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Dynamic Approval Setting  (one per doctype+company)            │
│  ├─ Match Criteria  (child table — field_name = field_value)   │
│  ├─ Fixed Approvers (child table — approver, order)            │
│  └─ grouped into virtual "sections" (one Setting = N rules)    │
└───────────────────────────┬─────────────────────────────────────┘
                            │ setup_workflow() — idempotent
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Target doctype (e.g. Purchase Order) gets 7 custom fields:     │
│   • custom_approval_setting      (Link, hidden)                 │
│   • custom_approval_section      (Data, hidden)                 │
│   • custom_current_approval_level (Int, hidden)                 │
│   • custom_current_approver       (Data, hidden)                │
│   • custom_total_approval_levels  (Int, hidden)                 │
│   • custom_approval_approvers     (Table — user-fills)          │
│   • custom_approval_history       (Table — audit log)           │
│  + a Frappe Workflow with 4 states × 9 transitions              │
└─────────────────────────────────────────────────────────────────┘
                            │ runtime
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Doc events (registered with `*` in hooks.py):                  │
│   • validate                — lock doc to current approver     │
│   • before_save             — log "Created"                    │
│   • before_workflow_action  — state machine (Submit/Approve/…) │
│   • on_update               — re-sync level + send email       │
│  Plus override_whitelisted_methods → workflow_admin_bypass      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. The data model (5 doctypes)

### 3.1 `Dynamic Approval Setting` — the parent config

`avinashgroup_app/avinash_group_app/doctype/dynamic_approval_setting/dynamic_approval_setting.json`

Key fields:

| field | why |
|---|---|
| `document_type` (Link→DocType) | which target this Setting applies to |
| `company` (Link→Company) | scopes Setting — one company's rules don't affect another |
| `is_active` (Check) | lets you disable without deleting (criteria scan filters on this) |
| `approver_table_fieldname` (Data, default `custom_approval_approvers`) | which Table field on the target holds the user-defined hierarchy — configurable so two doctypes with different fieldnames can share the engine |
| `current_level_fieldname` (Data, default `custom_current_approval_level`) | same idea for the level tracker |
| `approver_fieldname` (Data) | fieldname on the target where the requester picks *their* approver — used by target-side JS to auto-populate the hierarchy table |
| `match_criteria` (Table → `Dynamic Approval Match Criteria`) | the rule rows — hidden on the form, driven by the virtual-section UI |
| `approvers` (Table → `Dynamic Approval Fixed Approver`) | fixed approvers per section — also hidden, driven by the UI |
| `dept_config_html` (HTML) | where the virtual-section UI renders |

**Why virtual sections?** A single Setting needs to hold many independent rules (e.g. "for company X, HR Accounts goes to Finance; Projects goes to PM + Finance"). Instead of making the user create N Settings, we keep one Setting and a `section` column on both child tables. Rows sharing the same `section` string form one rule. The HTML field renders them as cards; the underlying tables stay flat.

The DocType is named by `autoname()`:

```python
# dynamic_approval_setting.py
def autoname(self):
    abbr = frappe.db.get_value("Company", self.company, "abbr") or self.company
    self.name = f"{self.document_type}-{abbr}-{frappe.generate_hash(length=6)}"
```

**Why a hash suffix?** The `(doctype, company)` pair is not unique by itself if you ever want multiple Settings for the same scope (e.g. "pilot" vs "legacy"). The hash avoids collisions without requiring a unique index.

### 3.2 `Dynamic Approval Match Criteria` — the rule rows

`dynamic_approval_match_criteria.json`

```
section      : Data (required)   — groups rows into a rule
field_name   : Autocomplete      — a column on the target doctype
field_value  : Autocomplete      — the value that column must equal
```

**Why `field_name` as Autocomplete, not Link?** The field list depends on `document_type`, which is on the *parent*. Child-row Link filters don't have access to the parent in Frappe's client. Instead, the Setting JS populates the Autocomplete options at render time via `update_docfield_property("field_name", "options", …)`.

**Why store just two strings instead of typed columns?** Memory `project_dynamic_approval_criteria`: hardcoded columns (`department`, `user`, etc.) force a code change every time admins want a new dimension. The string/string table lets any field on the target become a matching dimension — company, department, supplier, custom_project — without touching Python.

### 3.3 `Dynamic Approval Fixed Approver` — fixed approver rows

```
section        : Data (required)   — same grouping key as criteria
approver       : Link → User       — who approves
approver_name  : Data (fetched)    — denormalised full name for UI
```

The order within a section is `idx` (row position). No explicit `level` column — level is derived at runtime by appending these rows after the user's hierarchy.

### 3.4 `Dynamic Approval Approver` — the per-document hierarchy (user-fills)

```
level          : Int (required)    — 1, 2, 3…
approver       : Link → User
approver_name  : Data (fetched)
```

This is the child table that gets injected onto *every target doctype* as `custom_approval_approvers`. The user fills it themselves before submitting. Levels beyond the table's size are served by the Setting's fixed approvers.

### 3.5 `Dynamic Approval History` — audit log

Created on-the-fly the first time `setup_workflow` runs, via `_ensure_history_doctype()`. It's a simple child table with `action`, `user`, `user_name`, `timestamp`. Every hook that mutates state calls `_log_approval_history(doc, "…")` — this is the only thing tying the audit trail together, so it must be called on every branch.

---

## 4. Setting-side configuration UI

`avinashgroup_app/avinash_group_app/doctype/dynamic_approval_setting/dynamic_approval_setting.js`

### 4.1 Building the field-name autocomplete options

```js
function build_field_options(doctype) {
    let meta = frappe.get_meta(doctype);
    if (!meta) return [];
    let no_column_fieldtypes = new Set([
        "Section Break", "Column Break", "Tab Break", "Fold", "Heading",
        "HTML", "Button", "Image",
        "Table", "Table MultiSelect",
    ]);
    let seen = new Set();
    let options = [];
    (meta.fields || []).forEach(f => {
        if (!f.fieldname) return;
        if (no_column_fieldtypes.has(f.fieldtype)) return;
        if (f.is_virtual) return;
        if (seen.has(f.fieldname)) return;
        seen.add(f.fieldname);
        options.push({ value: f.fieldname, description: f.label || f.fieldname });
    });
    // Framework std fields — always present as columns, not in meta.fields.
    let framework_labels = { name: "ID", owner: "Created By", … };
    (frappe.model.std_fields_list || Object.keys(framework_labels)).forEach(fn => {
        if (seen.has(fn)) return;
        seen.add(fn);
        options.push({ value: fn, description: framework_labels[fn] || fn });
    });
    return options;
}
```

**Reasoning, line by line:**

- **`no_column_fieldtypes` filter** — criteria match via `doc.get(field_name)`. If the fieldname doesn't correspond to a real column on the target's table (e.g. `Section Break`, `HTML`, child `Table`), `doc.get()` returns `None` and the criterion silently fails. We filter them out at pick time so admins can't misconfigure.
- **`is_virtual` filter** — virtual fields are computed, not stored; `doc.get()` on them inside `before_workflow_action` can return stale values. Exclude them.
- **`std_fields_list` fallback** — `meta.fields` doesn't list framework columns (`name`, `owner`, `modified_by`, etc.), but they ARE real columns and often useful for criteria (e.g. "only route if `owner = foo@x.com`"). Inject them manually.
- **`seen` set** — avoids duplicates when a framework name also happens to be in `meta.fields`.
- **`value: fieldname`, not label** — labels can collide ("Name" on two different fields); fieldnames cannot.

### 4.2 Populating `field_value` dropdown reactively

When a user picks a `field_name` on a criteria row, the `field_value` picker switches behaviour:

```js
if (field_meta.fieldtype === "Link") {
    linked_doctype = field_meta.options;         // show Link options
} else if (field_meta.fieldtype === "Select") {
    select_options = (field_meta.options || "").split("\n").filter(Boolean);
}
```

Then:

```js
if (linked_doctype) {
    frappe.call({
        method: "frappe.client.get_list",
        args: { doctype: linked_doctype, fields: ["name"], limit: 200 },
        callback(r) {
            let options = r.message.map(d => d.name).join("\n");
            _set_field_value_options(frm, cdt, cdn, options);
        },
    });
}
```

**Reasoning:**
- Guessing a Link value by hand is error-prone (typos silently break rules). Turn the `field_value` cell into a dropdown whenever the picked field is a Link or Select.
- `limit: 200` — good enough for companies/departments without blowing up the payload.
- `standard_link_map = { owner: "User", modified_by: "User" }` — framework fields aren't in `meta.fields`, so we hard-code the two that are Links.

### 4.3 The virtual-section UI

`render_sections_ui(frm)` groups `match_criteria` and `approvers` rows by their shared `section` string and renders one card per section with Edit/Delete. `open_section_dialog()` opens a Frappe Dialog with two sub-tables (Criteria and Approvers) pre-filled with that section's rows. On save, **all** rows for that section are removed from the parent tables and rewritten — no diffing, just replace.

**Why no diffing?** The child-table API in Frappe doesn't surface stable row IDs reliably across edits. Rewriting is O(rows-per-section) and eliminates whole classes of bugs (edge cases around reordering, partial updates).

**Why store section as a string, not a Link?** Section names are arbitrary labels ("HR Accounts", "Finance", "Default"). Forcing them to be Links to another doctype adds a layer without value.

### 4.4 The "Setup Workflow" button

```js
frm.add_custom_button(__("Setup Workflow"), () => {
    frappe.confirm(
        __("This will create/update the workflow and custom fields on <b>{0}</b>. Continue?", [frm.doc.document_type]),
        () => {
            frappe.call({
                method: "avinashgroup_app.custom_code.dynamic_approval.setup_workflow",
                args: { config_name: frm.doc.name },
                freeze: true,
                …
```

**Why a button, not `on_update`?** Creating custom fields and a Workflow is destructive (overwrites existing transitions). Making it an explicit, confirmed action prevents accidentally nuking a live workflow just by editing a Setting. It's also idempotent — safe to click again after changes.

---

## 5. Hooks registration

`avinashgroup_app/hooks.py` (relevant lines):

```python
# Dynamic Approval — registered on '*' so every doctype can opt in
# via a Dynamic Approval Setting without touching hooks.py again.
_add_doc_event("*", "validate", "…dynamic_approval.validate")
_add_doc_event("*", "before_save", "…dynamic_approval.before_save")
_add_doc_event("*", "on_update", "…dynamic_approval.on_update")
_add_doc_event("*", "before_workflow_action", "…dynamic_approval.before_workflow_action")

override_whitelisted_methods = {
    "frappe.model.workflow.get_transitions": "…workflow_admin_bypass.get_transitions",
    "frappe.model.workflow.apply_workflow":  "…workflow_admin_bypass.apply_workflow",
}
```

Two things worth calling out:

**(1) Why `"*"` instead of per-doctype registration?** The whole point of the system is "attach approval to any doctype by creating a Setting". Hard-wiring hooks per target would require editing `hooks.py` and restarting bench every time. The `*` registration runs the function on every doctype's save, but `_get_config_for_doc` returns `None` for doctypes without a Setting, so the cost is one indexed lookup per save.

**(2) Why override `apply_workflow`?** Frappe's stock `apply_workflow` never fires `before_workflow_action` server-side — it's a client-only hook. That would mean Administrator-driven transitions (server scripts, scheduled jobs, API calls) would bypass our level-tracking entirely. The override in `workflow_admin_bypass.py` mirrors Frappe's logic but fires `before_workflow_action` for **all** users.

`_add_doc_event` itself is a safe-merge helper (lines 187–200 of hooks.py) that avoids clobbering existing handlers — it converts single handlers into lists when needed.

---

## 6. Config lookup — the two-path design

`custom_code/dynamic_approval.py::_get_config_for_doc`

### 6.1 Fast path (pinned)

```python
pinned_setting = doc.get(APPROVAL_SETTING_FIELD)   # custom_approval_setting
pinned_section = doc.get(APPROVAL_SECTION_FIELD)   # custom_approval_section

if pinned_setting and pinned_section:
    return _fetch_config_by_section(pinned_setting, pinned_section)
```

**Why pin?** Once a document has been submitted for approval, its rule is decided. Re-running the criteria scan on every `validate` / `on_update` is wasteful and — worse — **non-deterministic** if the document's criteria fields change mid-flow (e.g. someone edits `department`). Pinning on first submission freezes the rule: one setting lookup + one approvers lookup, two DB queries total.

### 6.2 Slow path (criteria scan — first submission)

```python
settings = frappe.get_all(
    "Dynamic Approval Setting",
    filters={"document_type": doc.doctype, "company": company, "is_active": 1},
    fields=["name", "approver_table_fieldname", "current_level_fieldname"],
)
if not settings:
    return None                           # no config for this doctype+company

setting_names = [s.name for s in settings]
all_criteria = frappe.get_all("Dynamic Approval Match Criteria",
    filters={"parent": ("in", setting_names), …},
    fields=["parent", "section", "field_name", "field_value"])
all_approvers = frappe.get_all("Dynamic Approval Fixed Approver",
    filters={"parent": ("in", setting_names), …},
    fields=["parent", "section", "approver", "approver_name"],
    order_by="idx")
```

**Why three bulk queries instead of N+M per-Setting queries?** We might have several active Settings for the same `(doctype, company)` (e.g. legacy + migration in progress). One query for all criteria and one for all approvers keeps this O(1) in Settings count.

The scoring loop:

```python
for setting in settings:
    criteria_by_section = criteria_map.get(sname, {})
    approvers_by_section = approver_map.get(sname, {})

    all_sections = set(criteria_by_section.keys()) | set(approvers_by_section.keys())
    if not all_sections:
        all_sections = {""}    # no rows at all = single catch-all section

    best_section = None
    best_score = -1

    for sec in all_sections:
        criteria = criteria_by_section.get(sec, [])
        if all(
            str(doc.get(c.field_name) or "").strip() == str(c.field_value or "").strip()
            for c in criteria
        ):
            score = len(criteria)
            if score > best_score:
                best_score = score
                best_section = sec
```

**Reasoning:**

- **`all(... for c in criteria)`** — AND semantics: every row in a section must match. Admins expect "match criteria" to be a conjunction, not a disjunction.
- **`doc.get(c.field_name) or ""`** — `None == "X"` would always be False, so the `or ""` normalises missing fields to empty string. Means a criterion of `field_value = ""` does match a field that isn't set, which is deliberate: sometimes you want "only apply when `custom_project` is blank".
- **`.strip()` on both sides** — guards against stray spaces in admin-entered values (a common source of "why isn't this matching?" tickets).
- **Zero-criteria section matches everything** — `all(... for c in [])` is `True` in Python, so a section with no criteria rows has `score = 0` and becomes a catch-all fallback.
- **Highest score wins** — more specific sections (more criteria) beat the catch-all. This is the key property that makes sections layerable: you can have "Default" (no criteria) and "HR Accounts" (criteria: `department = HR`) in the same Setting; an HR doc picks the specific rule, everything else lands on Default.
- **`continue` instead of `break`** after finding a match within a Setting — we iterate through sections of one Setting and pick the best, but if Settings loop continues we'd race. In practice only one Setting is active per `(doctype, company)`; scoring is within a Setting.

After a match:

```python
doc.set(APPROVAL_SETTING_FIELD, sname)
doc.set(APPROVAL_SECTION_FIELD, best_section)
```

**Why pin inside the lookup function, not in `before_workflow_action`?** The pin needs to happen the first time the lookup succeeds. If the first caller is `validate` on the Draft save before submission, we pin there. If the first caller is `before_workflow_action` on Submit, we pin there. Putting the pin in the lookup itself covers both paths without caller coordination.

### 6.3 The "no match" return value

If no Setting exists, or none of their sections match, `_get_config_for_doc` returns `None`. Every call site treats `None` as "this document has no workflow" — validation is skipped, `before_workflow_action` auto-approves. See memory `feedback_dynamic_approval_admin_fallback`: the user explicitly wants "no match = no workflow", never a stranded document.

---

## 7. Level math

```python
def _get_total_levels(doc, config):
    table_field = config["approver_table_fieldname"]
    user_count = len(doc.get(table_field) or [])
    return user_count + len(config["fixed_approvers"])
```

Total = user-filled rows + Setting's fixed approvers (for the matched section).

```python
def _get_effective_approver_at_level(doc, level, config):
    user_rows = _get_user_rows(doc, config)
    user_count = len(user_rows)

    if level <= user_count:
        for row in user_rows:
            if cint(row.level) == level:
                return row.approver
        # Safety: positional fallback if level field not set correctly
        return user_rows[level - 1].approver if 1 <= level <= user_count else None
    else:
        fixed_idx = level - user_count - 1
        fixed = config["fixed_approvers"]
        return fixed[fixed_idx].approver if 0 <= fixed_idx < len(fixed) else None
```

**Why check both `level` field and positional fallback?** Frappe's table rows have a user-editable `level` column, but `on_update` explicitly rewrites `level = idx` (see §10) to keep things linear. The positional fallback is defensive — if level column got out of sync somehow, we still serve a sensible value rather than `None`.

**Why user rows first, fixed approvers last?** Semantics. The requester's manual hierarchy is always approved *before* the corporate fixed approvers. Doing it the other way would let a Finance VP approve before the requester's direct manager, which is not what the business wants.

---

## 8. `validate` — Pending Approval lock

```python
def validate(doc, method=None):
    config = _get_config_for_doc(doc)

    # Precompute only on Draft — once the doc is in the approval flow the total
    # was set by before_workflow_action and must not be clobbered.
    if doc.get("workflow_state") in (None, "", "Draft") and doc.meta.has_field(TOTAL_LEVELS_FIELD):
        total = _get_total_levels(doc, config) if config else 0
        doc.set(TOTAL_LEVELS_FIELD, total)
```

**Why precompute `total` on Draft saves?** Frappe evaluates workflow transition conditions **before** firing `before_workflow_action`. The "Submit for Approval" transition has two branches:

```python
{"condition": f"doc.{tf} == 0",  "next_state": "Approved"}    # auto-approve
{"condition": f"doc.{tf} > 0",   "next_state": "Pending Approval"}
```

If `total` isn't written to the DB before Submit is clicked, both conditions see `0` and Frappe picks the wrong branch (or errors out). Writing it on every Draft save guarantees the DB always reflects the latest hierarchy the moment the user hits Submit.

**Why only on Draft?** Once past Draft, `total` is owned by `before_workflow_action`. Clobbering it from `validate` would fight the state machine.

```python
    if not config:
        return
    if doc.get("workflow_state") != "Pending Approval":
        return
    if doc.is_new():
        return
    if frappe.session.user == "Administrator":
        return

    # Read from DB — before_workflow_action already updated the in-memory field
    # to the NEXT approver, so doc.get() would give the wrong value here.
    current_approver = frappe.db.get_value(doc.doctype, doc.name, CURRENT_APPROVER_FIELD) \
                       or doc.get(CURRENT_APPROVER_FIELD)

    if frappe.session.user != current_approver:
        frappe.throw(_("This document is pending approval. Only {0} (the current approver) may make changes.")…)
```

**Why read from DB instead of `doc.get()`?** Execution order during an Approve action:

1. Frappe evaluates transition condition → old DB value of `custom_current_approver` = the user approving now ✓
2. Frappe fires `before_workflow_action` → we **overwrite** `custom_current_approver` in-memory with the NEXT level's approver
3. `doc.save()` → `validate()` runs
4. By this point, `doc.get(CURRENT_APPROVER_FIELD)` returns the next approver, not the one who actually clicked Approve. DB still has the old value.

So during a normal approve transition we want the DB value (the user who triggered this transition). Fallback to `doc.get()` handles edge cases where DB hasn't been written yet (pure in-memory validate on a first save).

The remaining block protects already-approved rows:

```python
    for level, approver in saved_rows.items():
        if level >= current_level:
            continue  # Not yet approved — current approver may still change these
        if level not in current_rows:
            frappe.throw(_("Cannot delete approver at Level {0} — this level has already been approved."))
        if current_rows[level] != approver:
            frappe.throw(_("Cannot change approver at Level {0} — this level has already been approved."))
```

**Why compare saved_rows to current_rows?** Someone at Level 3 who changes Level 1's approver could retroactively rewrite the audit trail — "Alice approved" becomes "Bob approved" when only Alice ever did. Compare the in-memory doc vs what's in the DB; reject any change to a level < `current_level`.

---

## 9. `before_save` — initial log

```python
def before_save(doc, method=None):
    if doc.is_new():
        _log_approval_history(doc, "Created")
```

Nothing else. The history is the single audit trail — everything else that mutates state logs its own entry.

---

## 10. `before_workflow_action` — the state machine

This is the heart of the system. A single function handles four actions by branching on `action`.

### 10.1 Auto-approve branch (no matching rule)

```python
config = _get_config_for_doc(doc)

if not config:
    if action == "Submit for Approval":
        _log_approval_history(doc, "Auto-approved (no matching approval rule)")
    return
```

**Why no `workflow_state=Approved` / `docstatus=1` assignment here?** See the `validate` explanation — `total_levels` is `0` on Draft saves when no config matches, so the workflow's **Draft → Approved** transition (`condition: doc.tf == 0`) is what Frappe will pick. Frappe then sets `workflow_state` and `docstatus` *from the transition itself*. If we also set them here, the values get overwritten — or worse, produce an "Illegal Document Status" error because the in-memory `docstatus=1` clashes with the save/submit flow that the transition triggers.

**Lesson (cost a debugging session earlier):** let transitions set state, use `before_workflow_action` only for ancillary doc-field updates.

### 10.2 Submit branch

```python
if action == "Submit for Approval":
    total = _get_total_levels(doc, config)
    if not total:
        _log_approval_history(doc, "Auto-approved (no approvers in matched rule)")
        return
    approver = _get_effective_approver_at_level(doc, 1, config)
    doc.set(level_field, 1)
    doc.set(TOTAL_LEVELS_FIELD, total)
    doc.set(CURRENT_APPROVER_FIELD, approver)
    doc.flags.approval_level_changed = True
    _log_approval_history(doc, "Submitted for Approval")
```

**Why `total == 0` also auto-approves?** Memory `feedback_dynamic_approval_admin_fallback`: a matched rule with zero approvers (admin forgot to add any) is semantically the same as "no approval needed". Do not strand the document in Pending Approval with zero levels.

**`doc.flags.approval_level_changed = True`** — consumed by `on_update` to decide whether to send the approver-notification email. Using a flag instead of comparing old/new level keeps the email logic inside `on_update` (the only hook that runs *after* state changes are persisted) and avoids duplicate emails when `on_update` fires multiple times in one request.

### 10.3 Approve branch

```python
elif action == "Approve":
    current_level = cint(doc.get(level_field) or 1)
    total = _get_total_levels(doc, config)           # always recompute

    if current_level < total:
        new_level = current_level + 1
        approver = _get_effective_approver_at_level(doc, new_level, config)
        doc.set(level_field, new_level)
        doc.set(CURRENT_APPROVER_FIELD, approver)
        doc.set(TOTAL_LEVELS_FIELD, total)
        doc.flags.approval_level_changed = True
        _log_approval_history(doc, f"Approved (Level {current_level})")

        # Force correct state in case Frappe picked the wrong transition
        doc.workflow_state = "Pending Approval"
        doc.docstatus = 0
    else:
        # Final approval
        doc.set(TOTAL_LEVELS_FIELD, total)
        doc.workflow_state = "Approved"
        doc.docstatus = 1
        _log_approval_history(doc, f"Approved (Final)")
```

**Why recompute `total` every time?** The user could edit the hierarchy table mid-flow (adding a row while Pending). The old `total` on the doc is stale; derive from the current table + fixed approvers.

**Why force `workflow_state` / `docstatus` on the intermediate branch?** The workflow has a self-transition (`Pending Approval → Pending Approval`) and a final transition (`Pending Approval → Approved`). Both have the action label `"Approve"` — Frappe picks based on condition (`doc.lf < doc.tf` vs `doc.lf == doc.tf`). But those conditions use the **DB values**, while we've just updated `lf` in memory to `new_level`. There's a brief window where the transition evaluator could have picked the wrong branch. Forcing state here guarantees the intermediate path stays intermediate even if the transition evaluation races the in-memory update.

**On the final branch** we set `workflow_state = "Approved"` and `docstatus = 1` because that IS what the final transition does — this is a belt-and-braces assignment that makes the flow work identically whether entered via the UI transition or via `apply_workflow` from scripts.

### 10.4 Reject branch

```python
elif action == "Reject":
    doc.flags.is_rejection = True
    _log_approval_history(doc, "Rejected")
```

State change itself (`Pending Approval → Rejected`) is handled by the workflow transition. The flag drives email wording ("was rejected and is back for review" vs "is awaiting your approval").

### 10.5 Resubmit branch

```python
elif action == "Resubmit":
    total = _get_total_levels(doc, config)
    approver = _get_effective_approver_at_level(doc, 1, config)
    doc.set(level_field, 1)
    doc.set(TOTAL_LEVELS_FIELD, total)
    doc.set(CURRENT_APPROVER_FIELD, approver)
    doc.flags.approval_level_changed = True
    _log_approval_history(doc, "Resubmitted for Approval")
```

**Why reset to level 1?** After a rejection, the requester fixes the issue and resubmits. They might have added/removed approvers or changed fields that shift which section matches (though the pinned section doesn't re-scan — see §6). Starting from level 1 is the conservative semantic: "this is a new approval cycle".

---

## 11. `on_update` — re-sync and notify

```python
def on_update(doc, method=None):
    config = _get_config_for_doc(doc)
    if not config:
        return

    if doc.get("workflow_state") == "Pending Approval":
        level_field = config["current_level_fieldname"]
        current_level = cint(doc.get(level_field) or 0)

        if current_level:
            total = _get_total_levels(doc, config)
            user_rows = _get_user_rows(doc, config)
            # Enforce 'level' = idx to maintain deterministic hierarchy
            for i, row in enumerate(user_rows):
                expected_level = i + 1
                if cint(row.level) != expected_level:
                    row.level = expected_level
                    row.db_update()

            approver = _get_effective_approver_at_level(doc, current_level, config)

            if total and current_level > total:
                current_level = total
                approver = _get_effective_approver_at_level(doc, current_level, config)

            updates = {TOTAL_LEVELS_FIELD: total}
            if approver:
                updates[CURRENT_APPROVER_FIELD] = approver
            updates[level_field] = current_level

            frappe.db.set_value(doc.doctype, doc.name, updates, update_modified=False)
```

**Why rewrite `row.level = i + 1`?** The hierarchy table is user-editable. If someone deletes Level 2, rows 3 and 4 keep their old `level` values (3 and 4), so the table has a gap. Then `_get_effective_approver_at_level(doc, 2, config)` would look for `level == 2` and find nothing, falling through to positional — which returns the row formerly at idx 2 (now idx 1, previously level 3). Rewriting `level = idx` eliminates the gap and guarantees serving is deterministic.

**Why `frappe.db.set_value` instead of `doc.db_set`?** `db_set` writes to the in-memory doc AND the DB, which can trigger another save cycle (and another `on_update`). Using `frappe.db.set_value` with `update_modified=False` writes directly to the DB without touching in-memory state or bumping `modified`, avoiding loops and preserving the original save's timestamp.

**Why clamp `current_level` to `total`?** If someone deletes the last two rows while the doc was at level 4 of 4, `current_level` is now beyond the table. Rather than throwing, clamp to the new total — the system treats the shortened chain as "already past that level".

### Notification section:

```python
if getattr(doc.flags, "approval_level_changed", False):
    _send_approval_notification(doc, config)
```

**Why guard on a flag?** `on_update` fires on every save, including pure metadata edits. We only want the email on actual level changes — `before_workflow_action` sets the flag when it advances the level, `on_update` consumes it. If the user manually edits the doc, no flag, no spam.

```python
def _send_approval_notification(doc, config):
    …
    try:
        frappe.sendmail(…, now=False)
    except Exception:
        frappe.log_error(title=f"Dynamic Approval: email failed for {doc.name}", …)
```

**Why `now=False`?** Queues the email — the user's click returns immediately instead of blocking on SMTP. **Why wrap in try/except?** Email failures must not break the save — worst case we lose an email notification; we never want a transient SMTP issue to abort an approval.

---

## 12. `setup_workflow` — the idempotent installer

`custom_code/dynamic_approval.py::setup_workflow`

```python
@frappe.whitelist()
def setup_workflow(config_name):
    frappe.only_for("System Manager")

    config_doc = frappe.get_doc("Dynamic Approval Setting", config_name)
    doctype = config_doc.document_type
    table_field = config_doc.approver_table_fieldname
    level_field = config_doc.current_level_fieldname

    _ensure_history_doctype()
    _ensure_custom_fields(doctype, level_field, table_field)
    _create_or_update_workflow(doctype, level_field)

    frappe.db.commit()
```

Three phases: (1) ensure the history child doctype exists, (2) create all seven custom fields on the target, (3) create or update the Workflow.

### 12.1 `_ensure_custom_fields` — the seven fields

Written in order so `insert_after` chains them correctly:

1. `custom_approval_setting` — hidden Link, stores the pinned Setting name (§6)
2. `custom_approval_section` — hidden Data, stores the pinned section name
3. `custom_current_approval_level` — hidden Int, the level counter
4. `custom_current_approver` — hidden Data, the User ID at the current level (drives workflow conditions)
5. `custom_total_approval_levels` — hidden Int, count of levels (drives workflow conditions)
6. `custom_section_approval_hierarchy` — visible Section Break
7. `custom_approval_approvers` — visible Table, the user-fills hierarchy, `allow_on_submit=1`
8. `custom_section_approval_history` — visible Section Break
9. `custom_approval_history` — visible Table, the audit log, `allow_on_submit=1`

**Why hide the first five?** They are bookkeeping, not UX. Showing `custom_current_approver: "alice@x.com"` to end users would be confusing.

**Why `allow_on_submit=1` on the two tables?** `on_update` writes into these even after `docstatus=1`. Without this flag, Frappe blocks the write.

**Why the idempotent `if not exists … else db.set_value` pattern?** Calling `setup_workflow` twice should leave the schema identical. The `else` branch reconciles any drift (e.g. a user manually changed `insert_after` on the custom field) back to the expected state.

### 12.2 `_create_or_update_workflow` — the transitions

First, the condition strings:

```python
af = CURRENT_APPROVER_FIELD
tf = TOTAL_LEVELS_FIELD
lf = level_field

approve_more = (
    f'(doc.{af} == frappe.session.user or frappe.session.user == "Administrator")'
    f' and doc.{lf} > 0 and doc.{tf} > 0 and doc.{lf} < doc.{tf}'
)
approve_final = (
    f'(doc.{af} == frappe.session.user or frappe.session.user == "Administrator")'
    f' and doc.{lf} > 0 and doc.{tf} > 0 and doc.{lf} == doc.{tf}'
)
```

**Why conditions use only `doc.*` fields?** Frappe's workflow `safe_eval` exposes `frappe.db.get_value`, `frappe.db.get_list`, `frappe.session`, `frappe.utils` — **not** `frappe.get_attr`, custom helpers, or arbitrary Python. The condition expression is evaluated in a sandbox on every page load. So every condition must be expressible as comparisons against doc fields and `frappe.session.user`. That's why we precompute `current_approver` and `total_levels` into hidden fields during `before_workflow_action` — so conditions can be trivial.

**Why the `doc.lf > 0 and doc.tf > 0` guards?** On a fresh Draft, both fields are `0`. Without the guards, `approve_final` evaluates to `0 == 0` → True — showing Approve buttons on a document that was never submitted. Guard against the zero state explicitly.

Then the System Manager parallels:

```python
sm_approve_more = f'doc.{lf} > 0 and doc.{tf} > 0 and doc.{lf} < doc.{tf}'
sm_approve_final = f'doc.{lf} > 0 and doc.{tf} > 0 and doc.{lf} == doc.{tf}'
```

**Why identical conditions minus the `custom_current_approver` check?** Memory `feedback_system_manager_silent_override`: System Managers must be able to unstick documents whose listed approver is unavailable. Same action label, same next state — makes the UI indistinguishable from a normal approval. No "(Override)" label, no special log entry.

**Why `allowed: "System Manager"` on the parallels?** Frappe filters transitions by role server-side. The non-SM parallel transitions use `allowed: "All"` so normal approvers can fire them; the SM-specific ones are role-gated. A non-SM user who happens to be the listed approver sees only the "All" transition; an SM who isn't the listed approver sees only the SM-role transition; the listed approver who *is* also an SM sees both (but they're functionally identical, so it doesn't matter which fires).

**Dynamic role-based permissions:**

```python
doc_roles = frappe.get_all("DocPerm", filters={"parent": doctype}, fields=["role"], distinct=True)
role_list = [r.role for r in doc_roles if r.role not in ("All", "Guest")]
if not role_list:
    role_list = ["System Manager"]

permissions = [{"role": role} for role in role_list]
```

**Why derive from DocPerm instead of hardcoding?** Workflow states need a `permissions` list to decide who can see/edit docs in each state. Hardcoding "Purchase User" would break the moment we apply this to Material Request. Deriving from the doctype's own role list means the workflow inherits the target's visibility automatically.

The nine transitions:

```python
transitions = [
    # Submission
    {"state": "Draft", "action": "Submit for Approval",
     "next_state": "Approved", "allowed": "All",
     "condition": f"doc.{tf} == 0"},

    {"state": "Draft", "action": "Submit for Approval",
     "next_state": "Pending Approval", "allowed": "All",
     "condition": f"doc.{tf} > 0"},

    # Normal approvals
    {"state": "Pending Approval", "action": "Approve",
     "next_state": "Pending Approval", "allowed": "All",
     "condition": approve_more},

    {"state": "Pending Approval", "action": "Approve",
     "next_state": "Approved", "allowed": "All",
     "condition": approve_final},

    {"state": "Pending Approval", "action": "Reject",
     "next_state": "Rejected", "allowed": "All",
     "condition": can_reject},

    # Role-gated parallels (silent SM override)
    {"state": "Pending Approval", "action": "Approve",
     "next_state": "Pending Approval", "allowed": "System Manager",
     "condition": sm_approve_more},

    {"state": "Pending Approval", "action": "Approve",
     "next_state": "Approved", "allowed": "System Manager",
     "condition": sm_approve_final},

    {"state": "Pending Approval", "action": "Reject",
     "next_state": "Rejected", "allowed": "System Manager",
     "condition": ""},

    # Rejection recovery
    {"state": "Rejected", "action": "Resubmit",
     "next_state": "Pending Approval", "allowed": "All", "condition": ""},
]
```

**Reasoning points:**
- **Two Submit transitions** with mutually-exclusive conditions (`tf == 0` vs `tf > 0`). Frappe picks the one whose condition evaluates True. This is how auto-approve works without any state-machine changes.
- **Condition "" on SM reject and Resubmit** — always allowed from their source state. For SM reject, we deliberately don't constrain by listed approver (the whole point of the override).
- **Auto-create states and actions:**
  ```python
  for s in states:
      if not frappe.db.exists("Workflow State", s["state"]):
          frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": s["state"]}).insert(…)
  ```
  Frappe requires Workflow State and Workflow Action Master records to exist before a Workflow can reference them. We mirror what Frappe's UI builder does: create them on the fly.

**Why the `existing` check?**

```python
existing = frappe.get_all("Workflow", filters={"document_type": doctype, "is_active": 1}, …)
if existing:
    wf = frappe.get_doc("Workflow", existing[0])
    wf.states = []
    wf.transitions = []
    for s in states: wf.append("states", s)
    for t in transitions: wf.append("transitions", t)
    wf.save(…)
else:
    wf = frappe.get_doc({"doctype": "Workflow", …}).insert(…)
```

Idempotent update: if there's already an active workflow for this doctype, blow away its states/transitions and rebuild. That's safer than creating a second parallel workflow (Frappe doesn't stop you, but the doctype ends up with two competing state fields).

---

## 13. The `apply_workflow` override

`custom_code/workflow_admin_bypass.py`

Two whitelisted methods overridden:

### 13.1 `get_transitions`

```python
def _is_admin_bypass(workflow, user):
    if user != "Administrator" or not workflow:
        return False
    if workflow.name in BYPASS_WORKFLOW_NAMES:
        return True
    if workflow.name.endswith("Approval Workflow"):   # matches any Dynamic Approval WF
        return True
    return False
```

**Why both an explicit set AND a suffix pattern?** Legacy workflows were named by hand; Dynamic Approval workflows are auto-named `{DocType} Approval Workflow`. The suffix lets new targets opt in automatically; the set is the migration path for pre-existing names.

```python
if not _is_admin_bypass(workflow, frappe.session.user):
    return workflow_module.get_transitions(doc, workflow, raise_exception)

# Admin: show all transitions for current state whose conditions pass
transitions = []
for transition in workflow.transitions:
    if transition.state == current_state:
        if workflow_module.is_transition_condition_satisfied(transition, doc):
            transitions.append(transition.as_dict())
return transitions
```

**Why skip the role check but keep the condition check?** Administrator should be able to fire any transition, but only transitions that are *structurally valid* for the current state + values. Showing the Reject button on a Draft would be confusing and would throw when clicked. Conditions keep the button set clean.

### 13.2 `apply_workflow`

The override mirrors Frappe's stock implementation but with two deliberate changes:

```python
# Fire before_workflow_action for ALL users so level-tracking hooks run.
doc.set("workflow_action", action)
doc.run_method("before_workflow_action")
```

**Why?** Frappe's stock `apply_workflow` **never** fires `before_workflow_action` — that hook is wired only for client-side workflow actions. Server-side calls (API, scripts) would skip our level tracking entirely. Firing it here makes the approval state machine identical regardless of caller.

The rest:

```python
if not is_admin and transition.allowed not in roles:
    continue
```

Admin skips the role filter; everyone else is checked exactly as Frappe would.

```python
if doc.docstatus.is_draft() and new_docstatus.is_submitted():
    from frappe.core.doctype.submission_queue.submission_queue import queue_submission
    …
    if doc.meta.queue_in_background and not is_scheduler_inactive():
        queue_submission(doc, "Submit")
        return
    doc.submit()
```

**Why branch on docstatus transitions?** Draft → Draft is `save`; Draft → Submit is `submit`; Submit → Submit is `save`; Submit → Cancel is `cancel`. Wrong branch = silent no-op or Illegal Document Status error. The explicit branching matches what Frappe itself does in `frappe/model/workflow.py::apply_workflow`.

---

## 14. Client-side field visibility and approver lock

`avinashgroup_app/public/js/approval_field_visibility.js` — included globally via `app_include_js`.

```js
$(document).on("form-refresh", function (e, frm) {
    if (!frm || !frm.doc || !frm.meta) return;

    let has_fields = APPROVAL_FIELDS.some(f => frm.fields_dict[f]);
    if (!has_fields) return;                  // no approval fields = not a target
```

**Why `form-refresh` instead of `onload`?** `onload` fires once per doc load; `form-refresh` fires after *every* rerender, so the banner/lock updates when the server pushes back a state change.

```js
    if (frm.doc.workflow_state === "Pending Approval") {
        const current_approver = frm.doc.custom_current_approver;
        const is_current_approver = (
            frappe.session.user === current_approver ||
            frappe.session.user === "Administrator"
        );
        if (!is_current_approver) {
            frm.disable_form();
        }
```

**Why `disable_form()` client-side if `validate()` server-side already throws?** Defense in depth and UX. The server is the source of truth, but disabling inputs gives immediate feedback — no chance of typing out an edit only to have it rejected on save.

```js
        const current_level = parseInt(frm.doc.custom_current_approval_level) || 0;
        if (current_level > 1) {
            setTimeout(function () {
                Object.values(frm.fields_dict).forEach(function (field) {
                    if (field.df.fieldtype !== "Table" || field.df.options !== "Dynamic Approval Approver") return;
                    const grid = field.grid;
                    if (!grid) return;
                    (grid.grid_rows || []).forEach(function (grid_row) {
                        const lvl = parseInt((grid_row.doc || {}).level) || 0;
                        if (lvl > 0 && lvl < current_level) {
                            grid_row.row.find(".grid-delete-row, .grid-duplicate-row").hide();
                            grid_row.row.css({ "opacity": "0.55", "pointer-events": "none" });
                        }
                    });
                });
            }, 300);
        }
```

**Why `setTimeout(…, 300)`?** Frappe's grid renders asynchronously; calling `grid_rows` immediately on form-refresh can return empty. 300ms is empirically enough for the grid to finish rendering without being perceptible to the user.

**Why mutate opacity + delete-button visibility?** The server-side `validate` already throws on changes to already-approved rows. The visual lock communicates this to the user before they try.

```js
    frappe.call({
        method: "avinashgroup_app.custom_code.dynamic_approval.has_approval_config",
        args: { doctype: frm.doc.doctype, company: company },
        async: true,
        callback: function (r) {
            let show = r && r.message;
            APPROVAL_FIELDS.forEach(f => {
                if (frm.fields_dict[f]) frm.toggle_display(f, show);
            });
        }
    });
```

**Why a roundtrip just to toggle visibility?** We can't know from the browser alone whether a Setting exists for this `(doctype, company)`. Hiding on company-change (or initial load with no company) is covered by the earlier branch; this call refreshes once the company is set.

---

## 15. Per-doctype client polish — Purchase Order

`avinashgroup_app/public/js/purchase_order.js` — loaded via `doctype_js`.

### 15.1 The progress banner

```js
const steps = [];
for (let i = 1; i <= total_levels; i++) {
    if (i < current_level) {
        steps.push(`<span style="color:var(--green-500)">✔ Level ${i}</span>`);
    } else if (i === current_level) {
        steps.push(`<span style="color:var(--yellow-500);font-weight:600">⏳ Level ${i} (current)</span>`);
    } else {
        steps.push(`<span style="color:var(--gray-400)">◯ Level ${i}</span>`);
    }
}
frm.set_intro(`${steps.join("  →  ")}<br><small>${who}</small>`, banner_color);
```

**Why a banner?** The hidden hierarchy table is visible, but the level tracker and current approver aren't (by design — they're noise for most users). The banner gives the at-a-glance "where are we" without exposing the bookkeeping fields.

### 15.2 Hiding Approve/Reject for non-approvers

```js
if (!is_approver) {
    frm.page.actions_btn_group.find("li a, li button").filter(function () {
        return ["Approve", "Reject"].includes($(this).text().trim());
    }).closest("li").hide();
    …
}
```

**Why hide instead of disable?** Frappe auto-surfaces workflow action buttons based on transitions. Users who don't match the transition conditions still see the buttons, but clicking them throws "Not a valid Workflow Action". Hiding keeps the UI clean.

**Note:** this is UI polish. The server-side condition (`doc.{af} == frappe.session.user`) is what actually protects the transition. Hiding the button only de-clutters.

### 15.3 Mandatory rejection reason

```js
before_workflow_action: function (frm) {
    if (frm.selected_workflow_action !== "Reject") return;

    return new Promise((resolve, reject) => {
        …
        let d = new frappe.ui.Dialog({
            title: __("Rejection Reason"),
            fields: [{ fieldtype: "Small Text", fieldname: "reject_reason", reqd: 1 }],
            primary_action() {
                let reason = d.get_value("reject_reason");
                …
                frappe.xcall("avinashgroup_app.custom_code.workflow.set_reject_reason", {
                    doctype: frm.doctype, name: frm.doc.name, reason: reason.trim(),
                }).then(() => { frappe.msgprint("Rejection recorded"); resolveOnce(); })
                  .catch(e => { frappe.msgprint("Error"); rejectOnce(e); });
            },
            …
        });
        d.onhide = () => { if (!is_submitting) rejectOnce("dialog_closed"); };
```

**Why a client-side `before_workflow_action`?** Frappe's client-side `before_workflow_action` lets us *gate* the workflow action — by returning a Promise that rejects, we cancel the transition entirely. That's the only way to force the user to provide a reason before Reject fires.

**Why `settled` / `resolveOnce` / `rejectOnce` guards?** The dialog has three exit paths: primary action (submit), secondary action (cancel), and `onhide` (X or ESC). Without the flag, closing the dialog after submitting would double-settle the promise and log a warning.

---

## 16. End-to-end flow (concrete walkthrough)

Say we have:

- **Purchase Order** with one Setting:
  - Section "Default" — no criteria, fixed approvers `[finance.head@x.com]`
- User A creates a PO and fills the Approval Hierarchy with: Level 1 = Manager, Level 2 = Director
- Company is set, `custom_approval_approvers` has 2 rows

### 16.1 Draft save (before submission)

| Step | Code path | Writes |
|---|---|---|
| User clicks Save | `validate()` | `_get_config_for_doc(doc)` → slow-path scan → pin `custom_approval_setting=<name>`, `custom_approval_section="Default"`. `_get_total_levels` returns `2 + 1 = 3`. Writes `custom_total_approval_levels = 3`. |
| `before_save()` | Logs "Created" in history (only on first save) |  |
| `on_update()` | `workflow_state = "Draft"` so the Pending-Approval branch skips |  |

Doc now has `tf=3`, `lf=0`, `af=None`. Submit button is visible.

### 16.2 Submit for Approval

1. User clicks Submit for Approval.
2. Frappe reads transitions from `Draft` state, evaluates conditions against DB:
   - `doc.tf == 0` → False
   - `doc.tf > 0` → True → picks `Draft → Pending Approval`.
3. `before_workflow_action(doc, action="Submit for Approval")` fires:
   - `total = 3`
   - `approver = Manager` (level 1, user row)
   - Writes `lf=1`, `tf=3`, `af=manager@x.com`, `flags.approval_level_changed=True`
   - Logs "Submitted for Approval"
4. Frappe applies transition, `workflow_state = "Pending Approval"`, `docstatus` stays 0.
5. `validate()` re-runs (it's in the save cycle). `workflow_state == "Pending Approval"`, session user is the creator (not the approver), BUT `doc.is_new()` guard — wait, actually it's not new. **Creator lock-out**: the creator now can't edit their own PO until rejected. (This is the deliberate Pending lock.)
6. `on_update()`: `workflow_state == "Pending Approval"`, `current_level=1`, no row-level fixups needed. `flags.approval_level_changed` is True → `_send_approval_notification` emails `manager@x.com`.

### 16.3 Manager approves

1. Manager logs in. Client-side visibility JS sees `workflow_state == "Pending Approval"`, `custom_current_approver == manager` → DOES NOT `disable_form()`. Banner shows "Level 1 current". Approve/Reject buttons visible.
2. Manager clicks Approve.
3. Frappe reads transitions from `Pending Approval`:
   - `approve_more`: `(af == session.user or session.user == Admin) and lf > 0 and tf > 0 and lf < tf` → `(manager == manager) and 1 > 0 and 3 > 0 and 1 < 3` → **True**.
   - `approve_final`: `lf == tf` → 1 == 3 → False.
   - Picks intermediate branch: `Pending Approval → Pending Approval`.
4. `before_workflow_action(action="Approve")`:
   - `current_level = 1`, `total = 3`, `1 < 3` → intermediate.
   - `new_level = 2`, `approver = Director` (level 2, user row).
   - Writes `lf=2`, `af=director@x.com`, `tf=3`. Sets `flags.approval_level_changed=True`.
   - Forces `workflow_state = "Pending Approval"`, `docstatus = 0` (belt-and-braces).
   - Logs "Approved (Level 1)".
5. `validate()` re-runs. `workflow_state == Pending`, session user == manager. DB `af` is still `manager@x.com` (not yet written), so `current_approver` read from DB == manager == session.user → OK, passes.
6. Save commits. DB now has `lf=2`, `af=director`.
7. `on_update()`: `current_level=2`. Row-level `level = idx` rewrite runs (no-op here). `_send_approval_notification` emails director.

### 16.4 Director approves

Same as 16.3 but `current_level=2 → 3`, approver becomes `finance.head@x.com` (level 3 = first fixed approver).

### 16.5 Finance Head approves (final)

1. Finance Head clicks Approve.
2. `approve_final`: `3 == 3` → **True**. Picks `Pending Approval → Approved`.
3. `before_workflow_action`: `current_level=3`, `total=3`, `3 < 3` → False → final branch. Sets `workflow_state = "Approved"`, `docstatus = 1`. Logs "Approved (Final)".
4. Frappe applies transition → same state. `docstatus` transitions from 0 to 1 via `doc.submit()`.

PO is now submitted. `validate` and `on_update` no longer take the Pending branch.

---

## 17. Edge cases — how each is handled

| Scenario | Behaviour | Code path |
|---|---|---|
| No Setting for `(doctype, company)` | `_get_config_for_doc` returns `None`. `validate` no-ops past the total=0 set on Draft. Submit picks `tf==0` branch → `Draft → Approved`. Logs "Auto-approved (no matching approval rule)". | §6 + §10.1 |
| Setting exists but no section matches criteria | Same as above — `best_section` never assigned → scan returns `None` for that Setting. Outer loop continues; if no Setting matches, same path as "no config". | §6.2 |
| Matched section has zero approvers (user table empty + zero fixed) | `_get_total_levels` returns 0. Submit branch inside `before_workflow_action` logs "Auto-approved (no approvers in matched rule)" and returns. Workflow's `tf==0` transition fires → `Draft → Approved`. | §10.2 |
| Requester tries to edit while Pending | `validate()` throws "Only X may make changes". Client `disable_form()` prevents the edit UI from responding. | §8 + §14 |
| Approver tries to change an already-approved row | `validate()` compares `saved_rows` (DB) to `current_rows` (in-memory); throws "Cannot change approver at Level N — already approved". Client UI greys out those rows. | §8 + §14 |
| Hierarchy row deleted mid-flow | `on_update` rewrites `row.level = idx`. If deletion shrinks total below current_level, `current_level` is clamped to new total. Approver is recomputed. | §11 |
| Listed approver's user is deleted | `current_approver` condition can never match (there's no `frappe.session.user` that equals a nonexistent user). System Manager sees the SM-parallel transitions (conditions check level state only) and can approve silently. Log shows `frappe.session.user` = SM who acted — audit trail is intact with no "OVERRIDE" marker. | §12.2 + memory feedback_system_manager_silent_override |
| Administrator wants to skip levels | Admin CAN approve at any level (condition `or session.user == "Administrator"` passes), but each Approve still advances by 1 level — no actual skip. The override in `workflow_admin_bypass.apply_workflow` also fires `before_workflow_action` so Admin's approves are level-tracked. | §13 |
| Rejected doc | `before_workflow_action(action="Reject")` sets `flags.is_rejection`, logs, transitions to `Rejected`. Rejection-reason dialog (PO-specific) enforces a reason at client side via `before_workflow_action` returning a Promise. | §10.4 + §15.3 |
| Resubmit after rejection | `before_workflow_action(action="Resubmit")` resets `lf=1`, recomputes `total`, picks level-1 approver, logs "Resubmitted". New approval cycle starts from the top. | §10.5 |
| Mid-flow Setting edit (admin adds criteria row) | Doesn't affect existing docs — they have `custom_approval_setting` + `custom_approval_section` pinned. Fast-path lookup skips the criteria scan entirely. New docs pick up the new rules. | §6.1 |

---

## 18. Workflow invariants — what must always hold

These are the properties the system guarantees. Breaking any of them is a bug.

1. **A document can always progress.** No document is ever stranded in `Pending Approval` because of a missing/broken config. Missing match → auto-approve on submit. Missing approvers → auto-approve on submit. Missing current approver → SM can unstick.
2. **Already-approved rows are immutable.** Once level N is past (`current_level > N`), row N's approver cannot be changed or deleted. Audit integrity.
3. **Level monotonicity.** `custom_current_approval_level` only advances (never rewinds) except on Resubmit, which resets to 1 and is logged.
4. **Pin is sticky.** Once `custom_approval_setting` is set on a doc, that Setting is used until the doc reaches a terminal state — criteria changes to the Setting don't retroactively reroute it.
5. **Audit log matches session.** `_log_approval_history` records `frappe.session.user`. SM overrides show the SM's username, not the listed approver's — so the log is always who *actually* clicked, even if the UI labels are generic.
6. **`total_levels` reflects live hierarchy.** Every `before_workflow_action` call recomputes from the current hierarchy table + fixed approvers — never trusts an in-memory stale value.
7. **Single source of truth for who can act.** `custom_current_approver` (DB) is the only field workflow conditions trust. Everything else (banner, hide/show) is UI derived from it.

---

## 19. File map — where to look

```
avinashgroup_app/
├── hooks.py                                                      § 5  register *-doc events and method overrides
├── custom_code/
│   ├── dynamic_approval.py                                       § 6–§12  the engine
│   └── workflow_admin_bypass.py                                  § 13  apply_workflow override
├── public/js/
│   ├── approval_field_visibility.js                              § 14  global hide/lock
│   └── purchase_order.js                                         § 15  PO banner + reject dialog
└── avinash_group_app/doctype/
    ├── dynamic_approval_setting/
    │   ├── dynamic_approval_setting.json                         § 3.1
    │   ├── dynamic_approval_setting.py                           § 3.1  (autoname + simple validate)
    │   └── dynamic_approval_setting.js                           § 4    virtual-section UI
    ├── dynamic_approval_match_criteria/                          § 3.2
    ├── dynamic_approval_fixed_approver/                          § 3.3
    └── dynamic_approval_approver/                                § 3.4
```

`Dynamic Approval History` (§ 3.5) is created at runtime by `_ensure_history_doctype()` on the first `setup_workflow` call — it does not have source-controlled JSON.

---

## 20. Maintenance checklist — before editing any of the above

Before changing any piece of this system, verify you are not breaking these properties:

- [ ] Can `_get_config_for_doc` still return `None`, and does every caller handle that?
- [ ] Are workflow conditions still restricted to `doc.*` + `frappe.session.user`? (No `frappe.get_attr`, no custom functions — they'll fail in `safe_eval`.)
- [ ] Does `before_workflow_action` still recompute `total` from the live hierarchy, not a cached value?
- [ ] Do all four branches (Submit/Approve/Reject/Resubmit) still call `_log_approval_history`?
- [ ] Do the SM-parallel transitions still use identical action labels and conditions that only check level state (no `current_approver` check)?
- [ ] Does `validate` still read `current_approver` from the DB, not `doc.get()` (because of the "next approver is in-memory during an Approve" gotcha)?
- [ ] Is `setup_workflow` still idempotent — can you click the button twice in a row without breaking anything?
- [ ] Did you update the auto-created custom fields if you changed the field names?

If any answer is "no", you're breaking an invariant in § 18.
