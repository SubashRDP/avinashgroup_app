# Memo Log (Internal Memo)

## What it is

- **Memo Generator page** (`/app/memo-generator`): the main way to make a memo.
  1. Pick a template, edit the memo, and watch the paper preview.
  2. **Generate Memo** saves a draft Memo Log and shows the paper with its Memo No. (The approval box appears only after the final approval.)
  3. Then use Print, Download PDF or Open Memo Log.

  Pressing Generate again updates the same draft. You reach the page from the **Memo Generator** button
  on the Memo Log list. A memo template has a **Preview** button that shows its paper in a popup, with
  unsaved edits included and nothing saved.
- **Document Template → Is Memo**: a memo template. It holds the heading, To/From/CC,
  subject, text above and below the table, and the default table size and headings.
  Memo templates are hidden from the Document Generator page.
- **Memo Log**: one memo, submittable. Its text is rich text, and the middle table is an editable
  grid (Rows x Columns, row 1 = headings).
- **Print format "Memo Log"**: `templates/print_formats/memo_log.html`. It shows the Memo No at the top
  left and the BS date at the top right. The page preview uses the same file.
- Backend for the page: `custom_code/document_generator/memo.py`.

## Memo number

The number comes from **Numbering Configuration** (Document Type = Memo Log, target
field `custom_branch_name`). With no rule, it falls back to the doc name
(`MEMO-YYYY-#####`).

## Approval

Flow: **Save** → Draft → **Actions → Submit for Approval** → Pending Approval → each approver
**Approve**s in order → **Approved** (docstatus 1, locked). Reject cancels the memo, and Amend makes a new draft.

- **Editing:** only while Draft. From Submit for Approval onward the memo is locked for everyone (the
  form goes read-only, and the server blocks changes made any other way). Approve/Reject still work. To fix
  a mistake: Reject, then Amend.
- **Its own settings, no conditions.** Create a **Dynamic Approval Setting** with Document Type =
  **Memo Log** per company. Use fieldnames `custom_approval_approvers` / `custom_current_approval_level`.
  Add a section with only **Approvers** (no match criteria), and every memo of that company goes through
  that chain. Memo Log is in `NO_CONDITION_DOCTYPES` in `custom_code/dynamic_approval.py`; for every other
  doctype a section without criteria still matches nothing. If a section WITH criteria matches (e.g.
  Department = IT), it wins over the no-condition one.
- **No Memo Log setting for the company** means Submit for Approval auto-approves (engine behaviour).
- **Workflow + approval fields** are created by `patches/setup_memo_log_approval.py`. It runs the same
  steps as the Setup Workflow button, and it also runs on live during migrate.
- **Access:** approvers usually have no Memo Log role. On Pending Approval, the memo is shared
  (read/write/submit) with everyone in its approver list, so they can open it from the email and approve.
  The memo creator still needs the Document Template User role.
- **Testing from code:** call `avinashgroup_app.custom_code.workflow_admin_bypass.apply_workflow`, which
  is the desk's override. Frappe's core `apply_workflow` never fires the engine's
  `before_workflow_action`, so the levels stay at 0.

**Approval box on the paper:** it prints ONLY after the final approval. It has no signature images; the
blank row is for hand signing. The columns are:

1. Requested By (the creator).
2. The setting section's approvers, in order. (The Approval Hierarchy table, for extra approvers, is
   hidden and kept empty on memos.)

The headings are Forwarded / Checked / Reviewed / Verified, and the last column is always Approved By.
The designation comes from the Employee linked to each user, or failing that, the Employee with the same
name in the company. While the memo is a Draft, every save re-matches the rule. From Submit for Approval
onward, the rule stays pinned.

## Gotchas

- A submitted memo keeps its printed list, even if the rules change later.
- Reject cancels the memo (engine behaviour). Amend makes a new draft.
- Table cells are plain text, with no merged cells or bold rows. They are stored as JSON in `table_data`.
- The BS date uses `bs_date_str` (nepali_datetime).
