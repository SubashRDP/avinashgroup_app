# Document Audit Trail

One document, drawn in its own form layout, with the earlier values of each
field listed under the current one.

## Start here: User Daily Entry Summary (report)

`/app/query-report/User Daily Entry Summary` is the layer above the page. Pick a
user and a date range (both dates default to today) and it shows one row per
document type with a count per action — All, Created, Amended, Submitted,
Edited, Cancelled, Deleted, Still Draft. Click a type to list its documents;
hover a document to see the changes that user made to it in the range; click it
to open it in the Document Audit Trail page. A deleted document opens its
Deleted Document copy instead, since there is nothing left to draw.

Counts are documents, not saves. Only the document types listed in User Daily
Entry Summary Settings appear, and the running user's own permissions
(including company User Permissions) limit what they see of another user.

The screen is drawn by the report's own script: the stock grid is still built
(Export and Print use it) but hidden, because it made a poor tree. Code:
`avinash_group_app/report/user_daily_entry_summary/`.

Not counted: a document created and deleted inside the range shows as Deleted
only, and edits made by background jobs are not attributed to the person.

The report used to take a single `date` and count created documents by current
status; links saved with `date=` still work.

## Where

- Page: `/app/document-audit-trail/<doctype>/<name>`, or pick the document type
  and document at the top of the page.
- From any form whose doctype records changes: ⋯ menu → **Audit Trail**.
- Roles: Auditor, System Manager, Accounts Manager. The user also needs read
  access to the document, so company User Permissions apply as on the form.

## The pipeline in one picture

```
desk save ─► Frappe writes a Version row (old → new per field, rows added/removed)
                    │
get_document_history(doctype, name)        page/document_audit_trail/document_audit_trail.py
                    │   groups Version rows by field / table row, builds the timeline
                    ▼
document_audit_trail.js   builds a read-only FieldGroup from the doctype's own
                          field list, then appends the history under each field
```

## What it shows

- Header fields: an orange bar marks a field that was changed; under it,
  `old → new`, the user and the time, newest first.
- Child tables: a row with changes carries an "n change(s)" badge; click the row
  to see them. Rows added since creation are badged "added"; removed rows are
  listed struck through with who removed them.
- Bottom: the full history oldest first — Created, each edit, Submitted,
  Cancelled, and (Sales Invoice only) each print from Sales Invoice Print Log.

## What it cannot show

- Anything before `track_changes` was switched on for the doctype
  (`patches/enable_track_changes_audited_doctypes.py`).
- Changes written with `db_set` / raw SQL — Frappe records no Version for them.
- Text Editor, Code, HTML Editor and Markdown fields — Frappe does not diff them.
- The real person behind older background-job edits; those Version rows are
  owned by Administrator.

## Gotchas found the hard way

- **Tabs need a form.** Frappe's `Tab` reads `frm.doctype` and calls
  `frm.set_active_tab()`, so a tabbed doctype in a plain FieldGroup throws while
  the layout is being built. `DatLayout.make_tab` lends the layout a stub `frm`
  for the length of each Tab's construction only.
- **0.0 → null is not an edit.** Submitting writes dozens of blank-to-blank
  "changes" per document; `_same_blank` drops them.
- **Values are set directly on the controls**, not with `set_value()`, which
  would validate every Link field over the network.
- **Page script caching.** With developer mode off the desk keeps the page
  script in the browser's localStorage; after deploying a change users need a
  hard reload, and the Python side needs the web workers restarted.
