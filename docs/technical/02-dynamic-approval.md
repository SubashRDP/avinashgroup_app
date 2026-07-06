# Dynamic Approval System — Technical Reference

> Chapter 2 of the technical documentation. Audience: developers.
> User-facing guide: [`../user_guide/02-approvals.md`](../user_guide/02-approvals.md)
>
> ⚠️ This chapter documents the **shipping code** (verified 2026-07-05). The
> older docs `dynamic_approval_guide.md`, `dynamic_approval_workflow.md` and
> `dynamic_workflow.md` in this folder have diverged from the code in places —
> see §9 for the divergence list. Where they conflict, **this chapter wins**.

## 1. Purpose

A configurable, multi-level **sequential** approval workflow attachable to
**any** doctype without editing `hooks.py` or writing per-doctype code. A
`Dynamic Approval Setting` (per doctype + company) plus its **Setup Workflow**
button injects hidden driver fields, a visible "Approval Hierarchy" child
table, an audit-log table, and a 4-state Frappe Workflow onto the target
doctype.

Approvers are a **union**: the requester's own per-document hierarchy rows
(Levels 1..N) followed by **fixed approvers** from the Setting (Levels
N+1..N+M). The document stays in `Pending Approval` through all intermediate
approvals (no ping-pong back to Draft), flipping to `Approved` / `docstatus=1`
only at the final level.

## 2. Wiring

`hooks.py:225-228` registers on `"*"` (all doctypes):

| Event | Handler |
|-------|---------|
| `validate` | `custom_code/dynamic_approval.py::validate` |
| `before_save` | `::before_save` |
| `on_update` | `::on_update` |
| `before_workflow_action` | `::before_workflow_action` |

`hooks.py:261-262` overrides `frappe.model.workflow.get_transitions` /
`apply_workflow` with `custom_code/workflow_admin_bypass.py`.

The universal hooks are cheap: `_is_managed_doctype(doc)`
(`dynamic_approval.py:25-33`) short-circuits with a DB-free
`doc.meta.has_field("custom_current_approver")` check.

## 3. Data model

### 3.1 Dynamic Approval Setting (parent, System Manager only)

Autoname `{document_type}-{company_abbr}-{hash6}`; `title_field:
document_type`; `track_changes`.

| Field | Type | Meaning |
|-------|------|---------|
| `document_type` | Link → DocType, reqd | target doctype |
| `company` | Link → Company, reqd | scope |
| `company_abbr` | Data, RO (fetch) | used in autoname |
| `is_active` | Check (1) | criteria scan filters on this |
| `approver_table_fieldname` | Data, reqd (default `custom_approval_approvers`) | fieldname of the hierarchy table on the target |
| `current_level_fieldname` | Data, reqd (default `custom_current_approval_level`) | fieldname of the level tracker |
| `approver_fieldname` | Data | **dead field** — defined but referenced by no code |
| `dept_config_html` | HTML | canvas for the section-card UI |
| `match_criteria` | Table → Dynamic Approval Match Criteria, hidden | rule rows (managed via dialog) |
| `approvers` | Table → Dynamic Approval Fixed Approver, hidden | fixed approvers (managed via dialog) |
| `setup_workflow_html` | HTML | help text for the Setup Workflow button |

Controller `validate` only checks criteria rows are complete.

### 3.2 Child tables

- **Dynamic Approval Match Criteria**: `section` (Data, reqd — groups rows into
  one rule), `field_name` (Autocomplete, reqd), `field_value` (Autocomplete,
  reqd). Equality-only, string compare, trimmed.
- **Dynamic Approval Fixed Approver**: `section`, `approver` (Link → User),
  `approver_name` (fetch). Order = row `idx`; levels are derived by appending
  after the user hierarchy.
- **Dynamic Approval Approver** (injected on targets as
  `custom_approval_approvers`): `level` (Int — rewritten to `idx` to stay
  gap-free), `approver` (Link → User), `approver_name` (fetch).
- **Dynamic Approval History** — created **at runtime** by
  `_ensure_history_doctype` (`dynamic_approval.py:541-558`), no source JSON:
  `action`, `user`, `user_name`, `timestamp`. Injected as
  `custom_approval_history`.

### 3.3 Custom fields injected on the target by Setup Workflow

`_ensure_custom_fields` (`dynamic_approval.py:561-706`), idempotent (repeat
runs reconcile drift):

1. `custom_approval_setting` (Link, hidden) — pinned Setting for fast lookup
2. `custom_approval_section` (Data, hidden) — pinned section
3. `custom_current_approval_level` (Int, hidden)
4. `custom_current_approver` (Data, hidden) — whose turn it is; drives workflow conditions
5. `custom_total_approval_levels` (Int, hidden)
6. `custom_section_approval_hierarchy` (Section Break, visible)
7. `custom_approval_approvers` (Table, visible, `allow_on_submit`)
8. `custom_section_approval_history` (Section Break, visible)
9. `custom_approval_history` (Table, visible, `allow_on_submit`)

## 4. Approver resolution

### 4.1 Config lookup — `_get_config_for_doc` (`dynamic_approval.py:54-145`)

- **Fast path** (`:61-65`): if `custom_approval_setting` +
  `custom_approval_section` are pinned on the doc →
  `_fetch_config_by_section` (2 queries, no scan).
- **Slow path**: requires `doc.company`. Loads all active Settings for
  `(document_type, company)`, bulk-loads criteria + fixed approvers in two
  queries, groups by `(setting, section)`.
- **Scoring** (`:103-143`): a section matches when **all** its criteria rows
  match (`str(doc.get(field)).strip() == str(value).strip()`). Score = criteria
  count; **highest score wins** (most specific). The winner is pinned onto the
  doc. No match anywhere → `None`.
- ⚠️ A section with **zero criteria is skipped** (`:118-119`) — an empty
  section is *not* a catch-all, despite the docstring at `:110` claiming
  otherwise. To make a catch-all rule, give it one criterion that always
  matches (e.g. `company = <the company>`).
- **No caching** — deliberate (`:49-51`). The pin is the optimization. There is
  no Redis cache and no `clear_config_cache`.

### 4.2 Level math

- `_get_total_levels` (`:178-185`) = user hierarchy rows + fixed approvers.
- `_get_effective_approver_at_level` (`:195-211`): levels ≤ user-count come
  from the document's hierarchy table (positional fallback if `level` unset);
  above that, `fixed_approvers[level - user_count - 1]`.
- There are **no amount thresholds and no reports-to/org-chart resolution** —
  matching is doctype+company scoping, equality criteria, and a fixed sequence.
- Degenerate cases: no config at submit → **auto-approve** (docstatus 1, log
  "Auto-approved (no matching approval rule)", `:343-353`); config with zero
  levels → single `Administrator` approver fallback (`:360-363`).

## 5. Runtime flow

**Draft save** — `before_save` logs "Created" on first save. `validate` returns
early (state ≠ Pending Approval).

**Submit for Approval** — single Draft→Pending transition, empty condition
(always shown). `before_workflow_action` (`:308-402`) resolves config, computes
`total`, sets level=1 / total / `custom_current_approver`, sets
`flags.approval_level_changed`, logs "Submitted for Approval". `on_update`
(`:405-459`) re-syncs level fields via direct DB writes
(`update_modified=False`) and emails the Level-1 approver.

**Intermediate Approve** — transition condition `approve_more` (current user is
`custom_current_approver` or Administrator, and `level < total`). The Approve
branch (`:372-398`) recomputes total, increments level, sets the next approver,
forces `workflow_state="Pending Approval"` + `docstatus=0`, logs "Approved
(Level N)". `on_update` emails the next approver.

**Final Approve** — condition `approve_final` (`level == total`). Sets
`Approved`, `docstatus=1`, logs "Approved (Final)".

**Reject** — condition `can_reject` (current approver or Administrator). Sets
`flags.is_rejection`, logs "Rejected"; state → `Rejected` (docstatus 0,
editable). **There is no Resubmit transition** — from Rejected the user edits
and the workflow restarts from Draft semantics.

### Generated workflow (`_create_or_update_workflow`, `:709-852`)

4 states — Draft, Pending Approval, Approved (docstatus 1), Rejected
(docstatus 0), all `allow_edit: All`. 4 transitions — Submit for Approval
(unconditional), Approve×2 (`approve_more` / `approve_final`), Reject.
Conditions are baked `doc.*` field-comparison strings (no `frappe.get_attr`
calls), each OR-ing `frappe.session.user == "Administrator"`. Transition roles
are derived from the target's DocPerm roles (excluding All/Guest; fallback
System Manager). Idempotent — reuses/rebuilds an existing active workflow, else
inserts `"{DocType} Approval Workflow"`. Missing Workflow State / Action Master
records are auto-created.

### Status bridge

If the target has a Select `status` field containing both "Approved" and
"Rejected" (e.g. HRMS Leave Application), the workflow states also set `status`
(`:758-770`). Patch `leave_application_dynamic_approval.py` hides the native
`leave_approver` fields so Dynamic Approval owns leave approval.

## 6. Guards in `validate` (`:262-299`)

- While Pending, a save by anyone who is not the current approver throws
  `Only {approver} may make changes`. The approver is read **from DB**, not
  `doc.get` — `before_workflow_action` has already overwritten the in-memory
  field to the next approver. Exemptions: the transition entering Pending
  (`has_value_changed("workflow_state")`) and intermediate approves
  (`flags.approval_level_changed`).
- Rows of levels already approved (level < current level) cannot be modified or
  deleted — DB rows are compared to in-memory rows.
- `on_update` rewrites user rows' `level = idx+1` (`row.db_update()`), recomputes
  the approver, clamps `current_level` to `total` if a deletion made it
  overshoot (`:445-447`).

## 7. Whitelisted API + client scripts

| Method | Caller | Purpose |
|--------|--------|---------|
| `dynamic_approval.has_approval_config(doctype, company)` | `approval_field_visibility.js:95-104` | toggle driver-field visibility |
| `dynamic_approval.setup_workflow(config_name)` (System Manager only) | `dynamic_approval_setting.js:21-24` | the Setup Workflow button |
| `dynamic_approval.is_current_approver(doctype, docname)` | *(exported, currently unused by JS)* | server-side check |
| `workflow.set_reject_reason(doctype, name, reason)` | `approval_workflow_auto.js:26` | store reject reason → `custom_reason` field if it exists, else a Comment |
| `workflow_admin_bypass.get_transitions` / `apply_workflow` | Frappe core (overridden) | see §8 |

Client scripts (all in `app_include_js`, order matters — common first):

- `approval_workflow_common.js` — defines
  `window.avinashgroup_app.approval_workflow`: hides Approve/Reject for
  non-current approvers (`:62-103`); the mandatory "Reason for Rejection"
  dialog (`:105-189`) which calls `set_reject_reason` and only then lets the
  Reject transition proceed.
- `approval_workflow_auto.js` — generic `form-refresh` binding for **any**
  doctype that has the approval fields: progress banner via `frm.set_intro`
  (`✔ Level 1 → ⏳ Level 2 (current) → ◯ Level 3`, plus "Your approval is
  required…" / "Waiting for <user>…"), and lazily binds the reject dialog once
  per doctype unless the doctype ships its own handler.
- `approval_field_visibility.js` — filters the Setting picker; while Pending
  and the session user is not the current approver → `frm.disable_form()`;
  visually locks already-approved hierarchy rows (opacity, no delete button);
  shows/hides the hidden driver fields per `has_approval_config`.

No per-doctype approval JS exists any more (`hooks.py:38-40`).

## 8. Administrator bypass (`workflow_admin_bypass.py`)

`_is_admin_bypass` (`:13-25`) — true only for the literal user
**Administrator** AND workflow name in `{"Material Request One-Line Approver",
"Purchase Order Workflow"}` or ending in `"Approval Workflow"`.

- `get_transitions` (`:27-64`): for admin-bypass cases, returns all
  condition-satisfied transitions, skipping the **role** check (conditions
  still evaluated).
- `apply_workflow` (`:67-152`): fires `before_workflow_action` server-side for
  **all** users (stock Frappe never does), still enforces
  `has_approval_access` (self-approval block), then applies the state change /
  save / submit / cancel.

Note: only `Administrator` is bypassed. There is **no** generic System Manager
override; Administrator still advances one level at a time.

## 9. Divergence of the older docs (do not trust these points)

- `dynamic_approval_guide.md` (2026-04-15): describes a department-based model
  with functions that no longer exist (`wf_can_approve_*`,
  `clear_config_cache`…), `frappe.get_attr` conditions, Memo roles, a Resubmit
  flow, and only 2 injected fields. **Fully superseded.**
- `dynamic_approval_workflow.md`: development log; concepts current but uses
  the old `group` (Int) naming — the code renamed it to `section` (Data).
- `dynamic_workflow.md` (2026-04-24): best narrative for data model/hooks, but
  its workflow sections are aspirational: it documents 9 transitions with
  System-Manager parallels and Resubmit, a `tf==0` auto-approve transition, and
  a Draft-time `validate` precompute — none of which the code implements (4
  transitions; auto-approve is imperative inside `before_workflow_action`).

## 10. Email notifications

`_send_approval_notification` (`:466-517`) fires only when
`flags.approval_level_changed` and state is Pending; distinct subject/body for
rejection vs approval; `frappe.sendmail(now=False)` in try/except so mail
failures never abort a save.
