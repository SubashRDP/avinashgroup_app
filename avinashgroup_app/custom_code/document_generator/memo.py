# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Backend for the Memo Generator page (avinash_group_app/page/memo_generator).

The page is the memo version of the Document Generator. You pick a memo template
(Document Template with Is Memo ticked), edit the memo, and watch the paper update.
"Generate Memo" then saves it as a Memo Log and shows the final paper, with its
Memo No and approval table.

The paper HTML is the same Jinja file the "Memo Log" print format uses
(templates/print_formats/memo_log.html), so the preview and the real print
cannot drift apart.

Deliberately narrow: this only creates or updates DRAFT Memo Logs. Approval
(Submit for Approval / Approve) happens on the Memo Log form through the
Dynamic Approval workflow, not here.
"""

import json

import frappe
from frappe import _

MEMO_TEMPLATE_FILE = "avinashgroup_app/templates/print_formats/memo_log.html"

# Memo Log fields the page is allowed to set.
EDITABLE_FIELDS = (
	"memo_template",
	"company",
	"posting_date",
	"custom_department",
	"memo_title",
	"memo_to",
	"memo_from",
	"memo_cc",
	"subject",
	"text_above",
	"text_below",
	"table_rows",
	"table_columns",
	"table_data",
)


@frappe.whitelist()
def get_memo_template(template):
	"""Memo text and table setup of a memo template, used to fill the page."""
	t = frappe.get_doc("Document Template", template)
	if not t.is_memo:
		frappe.throw(_("{0} is not a memo template.").format(template))

	rows = max(int(t.memo_table_rows or 0), 0)
	cols = max(int(t.memo_table_columns or 0), 0)
	headings = [h.strip() for h in (t.memo_table_headers or "").split("\n") if h.strip()]
	grid = [["" for _c in range(cols)] for _r in range(rows)]
	if rows:
		for c, heading in enumerate(headings[:cols]):
			grid[0][c] = heading

	return {
		"memo_title": t.memo_title or "Internal Memo",
		"memo_to": t.memo_to or "",
		"memo_from": t.memo_from or "",
		"memo_cc": t.memo_cc or "",
		"subject": t.memo_subject or "",
		"text_above": t.memo_text_above or "",
		"text_below": t.memo_text_below or "",
		"table_rows": rows,
		"table_columns": cols,
		"table_data": json.dumps(grid),
	}


@frappe.whitelist()
def preview_memo(data, name=None):
	"""Paper HTML for unsaved values. Shows no approval table, because the box
	prints only on an approved memo.
	With `name` (the Memo Log form's live preview), it starts from that saved
	memo so the Memo No stays; the unsaved values are laid on top, nothing is saved."""
	if name and frappe.db.exists("Memo Log", name):
		doc = frappe.get_doc("Memo Log", name)
		doc.check_permission("read")
	else:
		doc = frappe.new_doc("Memo Log")
	_apply(doc, data)
	doc.set_table_data()
	return render_memo_html(doc)


@frappe.whitelist()
def generate_memo(data, name=None):
	"""Save the page values as a Memo Log. Makes a new one, or updates `name`
	if it is still a draft. Returns the name, Memo No and final paper HTML."""
	if name and frappe.db.exists("Memo Log", name):
		doc = frappe.get_doc("Memo Log", name)
		if doc.docstatus != 0 or (doc.get("workflow_state") or "Draft") != "Draft":
			frappe.throw(_("Memo {0} was already sent for approval and cannot be changed.").format(name))
		_apply(doc, data)
		doc.save()
	else:
		doc = frappe.new_doc("Memo Log")
		_apply(doc, data)
		doc.insert()

	return {
		"name": doc.name,
		"memo_no": doc.custom_branch_name or doc.name,
		"approval_rule": doc.approval_rule,
		"html": render_memo_html(doc),
	}


@frappe.whitelist()
def get_memo_html(name):
	"""Paper HTML of a saved Memo Log, for the Generate Memo button on its form.
	Uses the stored values, so the approval box shows once the memo is approved."""
	doc = frappe.get_doc("Memo Log", name)
	doc.check_permission("read")
	return render_memo_html(doc)


def render_memo_html(doc):
	"""The memo paper as HTML, from the same template as the print format."""
	return frappe.render_template(MEMO_TEMPLATE_FILE, {"doc": doc})


def _apply(doc, data):
	values = json.loads(data) if isinstance(data, str) else (data or {})
	for field in EDITABLE_FIELDS:
		if field in values:
			doc.set(field, values.get(field))
