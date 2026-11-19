# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Memo Log: one Internal Memo (To/From/CC, subject, text, a free-size table,
and an approval block), made from a Document Template with Is Memo ticked,
usually through the Memo Generator page (page/memo_generator).

Why: memos were typed in Word, and the sign-off row (Requested / Forwarded /
Checked / Reviewed / Verified / Approved By) was filled by hand. Here the same
people come from Dynamic Approval Setting and approve in the system.

Approval:
- Memo Log is submittable and runs on the shared engine in
  custom_code/dynamic_approval.py, with its OWN Dynamic Approval Settings
  (Document Type = Memo Log, one per company). Memo Log is in the engine's
  NO_CONDITION_DOCTYPES: a section with approvers and no match criteria applies
  to every memo of that company. A section whose criteria match still wins.
  No setting for the company = Submit for Approval auto-approves (engine).
  The workflow and approval fields are set up by
  patches/setup_memo_log_approval.py.
- The printed approver list asks the engine for its config (_get_config_for_doc),
  so the paper always shows the same people the workflow will ask. The paper
  shows it only after the final approval (see the print template).
- While Draft, the list is rebuilt on every save and the engine's pinned rule is
  cleared, so a changed department picks the right rule. From Submit for
  Approval onward, the pinned rule is kept.
- On Pending Approval the memo is shared with its approvers (read/write/submit),
  because approvers usually have no Memo Log role.

Boundary:
- The memo number (custom_branch_name) comes from Numbering Configuration
  (custom_code/Override/naming_series.py), not from here.
- The middle table is one JSON grid (table_data), so cell values cannot be
  filtered or reported on.

See docs/memo-log.md.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document

from avinashgroup_app.custom_code.dynamic_approval import (
	APPROVAL_SECTION_FIELD,
	APPROVAL_SETTING_FIELD,
	_get_config_for_doc,
	_get_user_rows,
)

# The engine's "Approval Hierarchy" table (extra approvers). Same name as on the
# Purchase Order settings; created by patches/setup_memo_log_approval.py.
HIERARCHY_TABLE_FIELD = "custom_approval_approvers"

# Column headings of the printed approval table, by position.
# The first column is always the requester, the last is always "Approved By".
FIRST_LABEL = "Requested By"
LAST_LABEL = "Approved By"
MIDDLE_LABELS = ["Forwarded By", "Checked By", "Reviewed By", "Verified By"]

# The memo's own content. It can be changed only while the memo is Draft; from
# Submit for Approval onward it is locked for everyone (approvers too).
CONTENT_FIELDS = (
	"memo_template",
	"company",
	"posting_date",
	"custom_created_by",
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


class MemoLog(Document):
	def validate(self):
		self.block_edits_after_draft()
		self.set_table_data()
		self.clear_extra_approvers()
		self.set_approvers()

	def block_edits_after_draft(self):
		"""Throw if the memo content is changed after it left Draft. Workflow
		saves (Approve / Reject) pass, because they change no content field.
		To fix a mistake: Reject, then Amend (a new draft)."""
		before = self.get_doc_before_save()
		if not before or (before.get("workflow_state") or "Draft") == "Draft":
			return
		changed = [
			self.meta.get_label(f)
			for f in CONTENT_FIELDS
			if str(self.get(f) if self.get(f) is not None else "") != str(before.get(f) if before.get(f) is not None else "")
		]
		if changed:
			frappe.throw(
				_("This memo is {0} and can no longer be changed ({1}). To correct it, Reject it and then Amend.").format(
					_(before.get("workflow_state")), ", ".join(changed)
				),
				title=_("Memo is locked"),
			)

	def clear_extra_approvers(self):
		"""Only the approval rule decides who approves a memo, so the engine's
		Approval Hierarchy table (extra approvers added by the creator) is kept
		empty. The table is hidden on the form; this also covers API/import.
		Drafts only: once sent for approval, the levels are already counted."""
		if self.docstatus == 0 and (self.get("workflow_state") or "Draft") == "Draft":
			if self.meta.has_field(HIERARCHY_TABLE_FIELD):
				self.set(HIERARCHY_TABLE_FIELD, [])

	def on_update(self):
		self.share_with_approvers()

	def share_with_approvers(self):
		"""Once sent for approval, share the memo with everyone in its approver list.
		Approvers come from Purchase Order rules, so many of them have no Memo Log
		role. Without this they could not open the memo from the approval email,
		nor press Approve (which needs write + submit)."""
		if self.get("workflow_state") != "Pending Approval":
			return
		creator = self.custom_created_by or self.owner
		for row in self.approvers or []:
			if not row.user or row.user in (creator, "Administrator"):
				continue
			frappe.share.add_docshare(
				self.doctype,
				self.name,
				user=row.user,
				read=1,
				write=1,
				submit=1,
				flags={"ignore_share_permission": True},
			)

	def get_table_grid(self):
		"""The table as a list of rows (row 0 = headings). Used by the print format."""
		try:
			grid = json.loads(self.table_data or "[]")
		except ValueError:
			return []
		return grid if isinstance(grid, list) else []

	def set_table_data(self):
		"""Keep table_data a rows x columns grid (list of lists of strings).
		Row 0 is the heading row."""
		rows = max(int(self.table_rows or 0), 0)
		cols = max(int(self.table_columns or 0), 0)
		try:
			grid = json.loads(self.table_data or "[]")
		except ValueError:
			grid = []
		if not isinstance(grid, list):
			grid = []

		clean = []
		for r in range(rows):
			old_row = grid[r] if r < len(grid) and isinstance(grid[r], list) else []
			clean.append([str(old_row[c]) if c < len(old_row) and old_row[c] is not None else "" for c in range(cols)])
		self.table_data = json.dumps(clean)

	def set_approvers(self):
		"""Fill the printed approver list: the creator, then the approvers the
		Dynamic Approval engine will ask, in order. No rule matched = empty list,
		so the printed memo has no approval table. Runs on drafts only; a
		submitted memo keeps its list."""
		if self.docstatus != 0:
			return

		# Not yet sent for approval: forget the engine's pinned rule so it re-scans
		# with the current Created By + Department.
		if (self.get("workflow_state") or "Draft") == "Draft":
			self.set(APPROVAL_SETTING_FIELD, None)
			self.set(APPROVAL_SECTION_FIELD, None)

		self.approval_rule = ""
		self.set("approvers", [])

		config = _get_config_for_doc(self)
		if not config:
			return

		self.approval_rule = self.get(APPROVAL_SECTION_FIELD) or ""
		users = [self.custom_created_by or self.owner]
		users += [row.approver for row in _get_user_rows(self, config) if row.approver]
		users += [row.approver for row in config["fixed_approvers"] if row.approver]

		labels = approval_labels(len(users))
		for label, user in zip(labels, users):
			full_name = frappe.db.get_value("User", user, "full_name") or user
			self.append(
				"approvers",
				{
					"label": label,
					"user": user,
					"full_name": full_name,
					"designation": get_designation(user, full_name, self.company),
				},
			)


def approval_labels(count):
	"""Headings for `count` columns: Requested By, middle labels, Approved By."""
	if count <= 0:
		return []
	if count == 1:
		return [FIRST_LABEL]
	middle_count = count - 2
	middle = MIDDLE_LABELS[:middle_count]
	# More approvers than named middle labels: extra ones are "Checked By".
	middle += ["Checked By"] * (middle_count - len(middle))
	return [FIRST_LABEL] + middle + [LAST_LABEL]


def get_designation(user, full_name, company):
	"""Designation of the Employee linked to this user. Many Employees have no
	user_id set, so fall back to the Employee with the same name in this company.
	Blank if neither is found."""
	designation = frappe.db.get_value("Employee", {"user_id": user}, "designation")
	if not designation and full_name:
		designation = frappe.db.get_value(
			"Employee", {"employee_name": full_name, "company": company, "status": "Active"}, "designation"
		)
	return designation or ""
