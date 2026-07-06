# Document Generator — Technical Reference

> Chapter 7 of the technical documentation. Audience: developers & template authors.
> User-facing guide: [`../user_guide/06-document-generator.md`](../user_guide/06-document-generator.md)

Generates formal letters (e.g. balance-confirmation letters) from admin-authored
HTML+Jinja templates with SQL/Python data sources, editable in a WYSIWYG page,
output as PDF (letterhead-aware) or email. Every printed/emailed copy is
persisted as a **Generated Document**.

## 1. File inventory

| Path | Role |
|------|------|
| `custom_code/document_generator/api.py` | all whitelisted endpoints |
| `custom_code/document_generator/providers.py` | context builders, SQL/Python source runners |
| `custom_code/document_generator/pdf.py` | pdfkit/wkhtmltopdf wrapper |
| `custom_code/document_generator/styles.py` | HTML page wrapper + print-safe CSS |
| `avinash_group_app/page/document_generator/` | the desk page (JS 527 lines + CSS) |
| doctypes | `document_template`, `document_template_input`, `document_template_data_source`, `document_template_company`, `generated_document` |
| `fixtures/document_template.json` | the two bundled balance-confirmation templates |
| patches | `create_document_generator_roles`, `cleanup_document_generator_sections`, `create_document_generator_image_fields`, `create_document_generator_signatory_field` |

End-to-end call chain (`api.py:6-8`): `get_matching_templates` →
`get_template_meta` → `instantiate_document` → user edits →
`save_generated_document` → `download_document_pdf` / `send_document_email`.

## 2. Data model

### Document Template (autoname `field:template_name`, track_changes)

| Field | Meaning |
|-------|---------|
| `template_name` | unique id |
| `target_doctype` | optional — only for default email-recipient resolution |
| `companies` (Table MultiSelect → Document Template Company) | scoping; empty = all companies |
| `letter_head` | fallback header/footer when `header_html`/`footer_html` blank (`api.py:108-112`) |
| `print_orientation` | Portrait/Landscape |
| `default_recipient_field` | default `email_id` |
| `is_active` | only active templates appear in the picker |
| `email_subject` | Jinja-enabled |
| `inputs` / `data_sources` | child tables (below) |
| `header_html` + `header_height` (default 25 mm) / `footer_html` + `footer_height` (default 15 mm) | letterhead bands |
| `body_html` | the HTML+Jinja body |

Controller: `validate_companies` de-dupes; `validate_jinja`
(`document_template.py:24-42`) dry-renders body/header/footer against a stub
context at save so Jinja syntax errors are caught early.

Permissions: **System Manager** and **Document Template Manager** full;
**Document Template User** read/print/report only.

### Document Template Input (child)

`fieldname` (becomes the `%(fieldname)s` SQL param and `inputs.fieldname` Jinja
var), `label`, `input_type` (Data/Link/Date/Select/Int/Float/Check), `options`
(Link target or Select options), `reqd` (⚠️ client-side cue only — nothing
server-side enforces it), `exclusive_group` (inputs filled together as a
bundle), `exclusive_set` (bundles in the same set are mutually exclusive).

### Document Template Data Source (child)

`source_name` (exposed as `data.<name>`), `source_type` (SQL | Python),
`description`, `query`.

### Generated Document (autoname `DOC-GEN-.YYYY.-.#####`)

`title`, `template`, `company`, `target_doctype`/`reference_name`/`party` (RO),
`status` (Draft/Finalized/Sent), `print_orientation` (snapshotted so the PDF
reproduces even if the template changes), `payload` (exact inputs JSON),
`rendered_document` (preview), `body_html` (final rendered/edited HTML — the
PDF/email source), header/footer snapshot fields, `output_action`,
`recipients`, `email_status` (Not Sent/Queued/Sent/Failed), `error`.
Controller: title defaults to template name; `Sent` without recipients throws.
Document Template User has full CRUD but `if_owner` only.

## 3. Rendering pipeline

- **Jinja** via `frappe.render_template` for body (`api.py:132`), header/footer
  (`_render_hf`, `api.py:104-115`), preview (`api.py:167-168`).
- **Context** (`providers.py:182-198`, `:278-286`): `data.<source>.rows` /
  `.row` (first row), `inputs.<field>`, `company`, `org` (`company_name`,
  `vat`=Company.tax_id, `logo`, `stamp` — images as base64 data URIs so
  wkhtmltopdf renders them reliably), `user` (`full_name`, `designation`,
  `signature` — Employee resolved via the **custom `Employee.custom_document_user`
  → User link**, not `user_id`), `today`, `today_bs`, `bs()` (AD→BS via
  `nepali_datetime`), `fmt` (Indian grouping, blanks zeros), `money`
  (2 dp, shows 0.00).
- **Inputs → params** (`providers.py:256-286`): every declared input is bound
  as a named SQL param; missing inputs normalized to `None` (no KeyError). A
  `fiscal_year` input auto-fills `from_date`/`to_date` from the Fiscal Year
  (`_resolve_fiscal_year`, `providers.py:242-253`) unless explicit dates given.
- **SQL sources** → `frappe.db.sql(query, params, as_dict=True)` guarded by
  `_assert_safe_select` (§5). **Python sources** → Frappe `safe_exec` sandbox;
  script reads `params`, assigns `result` (dict = one row, list = rows).
- **PDF** (`pdf.py:24-50`): pdfkit directly (not `frappe.utils.pdf.get_pdf`)
  for exact margin control. Two modes (`api._doc_pdf`, `api.py:196-219`):
  `include_hf=True` draws header/footer (digital/email);
  `include_hf=False` reserves `header_height`/`footer_height` mm as blank
  margins for pre-printed letterhead paper.
- **CSS** (`styles.py`): print-safe, no flexbox — inline-block `.row`/`.col-*`
  grid + `.bordered` tables that wkhtmltopdf renders correctly.

## 4. The desk page (`page/document_generator/document_generator.js`)

Restricted to roles System Manager / Document Template Manager / Document
Template User. Flow:

1. Pick Template (Link filtered `is_active:1`).
2. Company control appears — Select from the template's companies list, else a
   free Company Link. Changing company clears company-scoped Link inputs.
3. Inputs render as native controls. Link inputs whose target has a
   `company`/`custom_company` field are auto-filtered to the chosen company
   (server detection `_company_filter_field`, `api.py:86-99`).
4. **BS date pairing**: every AD Date input auto-gets a paired "(BS)"
   nepaliDatePicker with two-way sync (`js:182-265`); the AD control is the
   payload source of truth.
5. **Exclusive bundles**: filling one bundle clears competing bundles in the
   same `exclusive_set` and drops their mandatory markers (`js:297-353`).
6. **Auto-build** — no Generate button; a 400 ms-debounced regen fires once
   company + all mandatory inputs are filled, calling `instantiate_document`
   and loading the HTML into a contenteditable A4-ish editor with a formatting
   toolbar (bold/italic/lists/alignment/image-insert-as-data-URI).
7. **Actions menu**: *Print (letterhead paper)* → `download_pdf(name, 0)`;
   *Print (with letterhead)* → `download_pdf(name, 1)`; *Email* → recipient
   prompt (blank = auto-resolve via `default_recipient_field`). Every action
   saves a Generated Document first. PDFs open in a synchronously-opened tab
   via blob URL (popup-block and insecure-download-banner safe).

Generated Document form: "Edit in Generator" button routes back to the page;
read-only sandboxed-iframe preview from `get_generated_document_html`.
Document Template form: "Preview" button renders with stub data in a dialog.

## 5. Security

- Every endpoint checks permissions (`check_permission`): read for
  instantiate/preview/html, write for save, email for send
  (`api.py:123,156,183,255,291,315`).
- **SQL injection**: inputs are always parameterized (`%(name)s`); query text
  is admin-authored only. `_assert_safe_select` (`providers.py:210-221`)
  additionally enforces: single statement (no `;`), must start
  `SELECT`/`WITH`, and a forbidden-keyword regex
  (insert/update/delete/drop/…/into outfile/load data).
- Python sources run in `safe_exec`; Jinja context never exposes raw `frappe`.
- `_scrub` (`api.py:34-36`) strips `<script>` tags from saved HTML; rendered
  output is only shown in sandboxed iframes and PDFs. (Lenient regex — inline
  event handlers survive; mitigated by the sandbox.)
- ⚠️ Input `reqd` is client-side only; a crafted API call can pass a partial
  payload (queries just receive `None`).
- wkhtmltopdf runs with `enable-local-file-access`, but the HTML is
  self-contained (data-URI images).

## 6. The two bundled templates (fixture)

`Customer Balance Confirmation` and `Vendor Balance Confirmation` — exported
via `hooks.py:274-281`. Both: all companies, Portrait, subject
`"Transaction & Balance Confirmation - {{ company }}"`, header_height 32 /
footer_height 16, header = logo + company name + VAT no, footer = company
tel/email/website from a `contact` source.

Inputs (both): party Link (`customer` / `supplier`, reqd) + **either**
`fiscal_year` **or** `from_date`+`to_date` (exclusive_set `period`; picking a
Fiscal Year auto-fills the dates server-side).

Data sources (4 SQL each): `party` (name/tax_id/address from
Customer/Supplier), `balances` (opening/closing from GL Entry —
`SUM(debit-credit)` before from_date / up to to_date, incl. `is_opening`),
`txn` (period taxable / VAT / TDS / total from Sales Invoice or Purchase
Invoice — customer TDS is literal 0; vendor uses
`SUM(custom_total_tds_amount)`), `contact` (Company phone/email/website).

Body: BS-date letterhead, "To" block, underlined subject with FY label or BS
date range, figures table (vendor version adds a TDS column), 7-day
confirmation paragraph, two-column signature block using `user.signature`,
`org.stamp` (columns swapped between the two templates).

## 7. Authoring a new template (admin runbook)

1. Role: Document Template Manager (or System Manager). New Document Template.
2. Name, Companies (empty = all), Orientation, Is Active.
3. Inputs: fieldname/label/type/options/reqd; `exclusive_group`+`exclusive_set`
   for either/or choices; name an input `fiscal_year` to get auto date-fill;
   Date inputs get BS pickers automatically.
4. Data sources: SQL (single read-only SELECT with `%(input)s` params — columns
   become `data.<name>.row.<col>` / iterable `.rows`) or Python (`params` in,
   `result` out).
5. Body HTML+Jinja using the context of §3; use `.bordered` tables and the
   `.row`/`.col-*` grid for print-safe layout.
6. Header/Footer HTML + heights (mm) matched to the pre-printed letterhead
   band; blank falls back to the linked Letter Head.
7. Email subject + Default Recipient Field (+ Target DocType for
   auto-resolution).
8. One-time site assets (created by patches): `Company.custom_document_stamp`,
   `Employee.custom_signature_image`, `Employee.custom_document_user` (the
   signatory User link).
9. Save (validates Jinja) → **Preview** (stub data) → generate from the
   Document Generator page.

## 8. Patches

- `create_document_generator_roles` — roles "Document Template Manager" /
  "Document Template User" (pre-model-sync).
- `cleanup_document_generator_sections` — removes the obsolete block-based
  Section doctypes (the design moved to a single HTML body; a stale
  `sections.pyc` may remain).
- `create_document_generator_image_fields` — Company stamp + Employee
  signature Attach Image fields.
- `create_document_generator_signatory_field` — `Employee.custom_document_user`.

Tests: `test_document_template.py` (Jinja validation rejects bad templates),
`test_generated_document.py` (Sent-without-recipients throws).

## 9. Troubleshooting

- **Template save hangs / 504s on the VPS (but not on dev)** — a WAF/proxy is
  flagging the SQL in the save request body as an injection attack. Saving does
  not run the data-source SQL, so this is purely the request layer. Fix by
  whitelisting `/api/method/frappe.desk.form.save.savedocs`. Full playbook:
  [`../document_template_save_hangs_vps.md`](../document_template_save_hangs_vps.md).
