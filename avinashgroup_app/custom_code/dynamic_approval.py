# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Constants  — hidden field names written on the target doctype
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Stores the User ID of whoever must act at the current level.
# Workflow conditions read this directly — no DB call needed at eval time.
CURRENT_APPROVER_FIELD = "custom_current_approver"

# Total levels = user-defined rows + fixed approvers from Setting.
# Stored on the doc so conditions can compare without any DB query.
TOTAL_LEVELS_FIELD = "custom_total_approval_levels"


@frappe.whitelist()
def has_approval_config(doctype, company):
	"""Check if a Dynamic Approval Setting exists for this doctype + company.
	Called from client JS to toggle visibility of approval fields."""
	if not doctype or not company:
		return False
	return bool(frappe.db.exists("Dynamic Approval Setting", {
		"document_type": doctype,
		"company": company,
		"is_active": 1,
	}))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DB helpers  — always read directly from DB, no caching
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _get_department_fieldname(doctype):
	"""Return the department fieldname for a doctype — checks custom_department then department."""
	meta = frappe.get_meta(doctype)
	if meta.has_field("custom_department"):
		return "custom_department"
	if meta.has_field("department"):
		return "department"
	return None


def _get_config(doctype, company, department=None, has_department=False):
	"""Fetch the Dynamic Approval Setting for a doctype + company. Always reads from DB."""
	if not company:
		return None

	setting = frappe.get_all(
		"Dynamic Approval Setting",
		filters={"document_type": doctype, "company": company, "is_active": 1},
		fields=["name", "approver_table_fieldname", "current_level_fieldname"],
		limit=1,
	)

	if not setting:
		return None

	setting = setting[0]
	fixed_all = frappe.get_all(
		"Dynamic Approval Fixed Approver",
		filters={"parent": setting.name, "parenttype": "Dynamic Approval Setting"},
		fields=["approver", "approver_name", "department"],
		order_by="idx",
	)

	if has_department:
		# Doctype has a department field — filter by it; blank department rows = global fallback
		fixed = [f for f in fixed_all if not f.department or f.department == department]
	else:
		# Doctype has no department — use all fixed approvers as a flat global sequence
		fixed = fixed_all

	return {
		"name": setting.name,
		"approver_table_fieldname": setting.approver_table_fieldname,
		"current_level_fieldname": setting.current_level_fieldname,
		"fixed_approvers": fixed,
	}


def _get_config_for_doc(doc):
	"""Get config using the doc's company/department (reads from DB directly)."""
	dept_field = _get_department_fieldname(doc.doctype)
	return _get_config(
		doc.doctype,
		doc.get("company"),
		department=doc.get(dept_field) if dept_field else None,
		has_department=bool(dept_field),
	)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Core level logic  (union: doc table  +  Setting fixed approvers)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_total_levels(doc, config):
	"""
	Total levels  =  rows in the doc's approval table
	              +  fixed approvers in Dynamic Approval Setting.
	"""
	table_field = config["approver_table_fieldname"]
	user_count = len([r for r in doc.get(table_field) or [] if not getattr(r, "flags", {}).get("__islocal")]) # actually just len
	# To handle deleted rows safely if they exist in doc, they usually lack docstatus=2 in memory but frappe usually cleanly removes them from doc.get
	user_count = len(doc.get(table_field) or [])
	return user_count + len(config["fixed_approvers"])


def _get_user_rows(doc, config):
	"""Return the approval hierarchy rows from the doc (ordered by idx)."""
	table_field = config["approver_table_fieldname"]
	rows = doc.get(table_field) or []
	return sorted(rows, key=lambda x: cint(x.idx))


def _get_effective_approver_at_level(doc, level, config):
	"""
	Return the approver User ID at the given level.
	"""
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Doc-event hooks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _log_approval_history(doc, action):
	if not doc.meta.has_field("custom_approval_history"):
		return
	doc.append("custom_approval_history", {
		"action": action,
		"user": frappe.session.user,
		"user_name": frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user,
		"timestamp": frappe.utils.now_datetime()
	})


def before_save(doc, method=None):
	"""Hook for initial creation logging"""
	if doc.is_new():
		_log_approval_history(doc, "Created")


def before_workflow_action(doc, method=None, action=None):
	"""
	Central hook: validates, manages levels, and updates the two hidden fields
	that drive workflow conditions.

	Hidden fields written here:
	  CURRENT_APPROVER_FIELD  — User ID of the current level approver
	  TOTAL_LEVELS_FIELD      — total number of levels (doc rows + fixed)

	Workflow conditions use only these doc fields + frappe.session.user,
	which is all that Frappe's safe_eval exposes in workflow context.

	Execution order (Frappe internals):
	  1. Frappe evaluates transition conditions  ← reads doc fields from DB
	  2. Frappe picks matching transition
	  3. THIS hook fires  ← we update the fields for the NEXT state
	  4. workflow_state is updated on the doc
	  5. doc.save() → before_save → on_update
	"""
	config = _get_config_for_doc(doc)

	# Frappe sets doc.workflow_action before calling this hook.
	action = action or doc.get("workflow_action")
	if not action:
		return

	# No config for this company → let the document pass through without approval logic
	if not config:
		return

	level_field = config["current_level_fieldname"]
	table_field = config["approver_table_fieldname"]

	if action == "Submit for Approval":
		total = _get_total_levels(doc, config)
		if not total:
			frappe.throw(
				_("Please add at least one approver in the Approval Hierarchy before submitting.")
			)
		approver = _get_effective_approver_at_level(doc, 1, config)
		doc.set(level_field, 1)
		doc.set(TOTAL_LEVELS_FIELD, total)
		doc.set(CURRENT_APPROVER_FIELD, approver)
		doc.flags.approval_level_changed = True
		_log_approval_history(doc, "Submitted for Approval")

	elif action == "Approve":
		current_level = cint(doc.get(level_field) or 1)
		
		# Always recompute total from the dirty doc child table, never trust the client's hidden field value
		total = _get_total_levels(doc, config)
		
		# Check how many user levels actually exist in the table vs the highest level so far
		# Wait! A more robust approach: Find all 'level's in the current table + fixed
		
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

	elif action == "Reject":
		doc.flags.is_rejection = True
		_log_approval_history(doc, "Rejected")

	elif action == "Resubmit":
		total = _get_total_levels(doc, config)
		approver = _get_effective_approver_at_level(doc, 1, config)
		doc.set(level_field, 1)
		doc.set(TOTAL_LEVELS_FIELD, total)
		doc.set(CURRENT_APPROVER_FIELD, approver)
		doc.flags.approval_level_changed = True
		_log_approval_history(doc, "Resubmitted for Approval")


def on_update(doc, method=None):
	"""
	1. Re-sync current approver when the hierarchy table is edited while Pending Approval.
	   Uses frappe.db.set_value (direct DB write) so the change is never lost regardless
	   of what happened in the save cycle.
	2. Send email notification when the level changes via a workflow action.
	"""
	config = _get_config_for_doc(doc)
	if not config:
		return

	# ── 1. Re-sync approver + total whenever doc is saved in Pending Approval ──
	if doc.get("workflow_state") == "Pending Approval":
		level_field = config["current_level_fieldname"]
		current_level = cint(doc.get(level_field) or 0)

		if current_level:
			total = _get_total_levels(doc, config)
			# Do NOT clamp current_level tightly to total!
			# If someone deletes an ALREADY APPROVED earlier row, the length decreases.
			# But if we merely clamp down, we ask the WRONG, ALREADY APPROVED person again!
			# Instead, if the level is wildly beyond total, clamp it. Otherwise let it be.
			# Wait. To truly fix "deletion skips/repeats", we update the 'level' column 
			# sequentially so it always matches 1..N indices.
			
			user_rows = _get_user_rows(doc, config)
			# Enforce 'level' = idx to maintain deterministic hierarchy
			for i, row in enumerate(user_rows):
				expected_level = i + 1
				if cint(row.level) != expected_level:
					row.level = expected_level
					row.db_update()
			
			approver = _get_effective_approver_at_level(doc, current_level, config)

			# If someone deleted the CURRENT approver's row, or an EARLIER row,
			# the doc shifted. By realigning level = idx, we keep the document moving linearly.
			# If current_level > total now (e.g. they deleted the final steps), clamp.
			if total and current_level > total:
				current_level = total
				approver = _get_effective_approver_at_level(doc, current_level, config)

			# Always write — avoids stale values after row additions/deletions
			updates = {TOTAL_LEVELS_FIELD: total}
			if approver:
				updates[CURRENT_APPROVER_FIELD] = approver
			updates[level_field] = current_level

			frappe.db.set_value(doc.doctype, doc.name, updates, update_modified=False)

	# ── 2. Email notification on level change ────────────────────────────
	if getattr(doc.flags, "approval_level_changed", False):
		_send_approval_notification(doc, config)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Notification
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _send_approval_notification(doc, config):
	"""Email the approver whose turn it now is."""
	level_field = config["current_level_fieldname"]
	current_level = cint(doc.get(level_field))
	current_state = doc.get("workflow_state")

	if not current_level or current_state != "Pending Approval":
		return

	approver_user = doc.get(CURRENT_APPROVER_FIELD)
	if not approver_user:
		return

	approver_name = (
		frappe.db.get_value("User", approver_user, "full_name") or approver_user
	)
	doc_link = frappe.utils.get_url_to_form(doc.doctype, doc.name)
	is_rejection = getattr(doc.flags, "is_rejection", False)

	if is_rejection:
		subject = _("{0} {1} — Rejected, Awaiting Your Re-review (Level {2})").format(
			doc.doctype, doc.name, current_level
		)
		message = _(
			"<p>Dear {0},</p>"
			"<p>{1} <b>{2}</b> was rejected and is back for review at Level {3}.</p>"
			"<p><a href=\"{4}\">Click here to open</a></p>"
		).format(approver_name, doc.doctype, doc.name, current_level, doc_link)
	else:
		subject = _("{0} {1} — Your Approval Required (Level {2})").format(
			doc.doctype, doc.name, current_level
		)
		message = _(
			"<p>Dear {0},</p>"
			"<p>{1} <b>{2}</b> is awaiting your approval at Level {3}.</p>"
			"<p><a href=\"{4}\">Click here to approve or reject</a></p>"
		).format(approver_name, doc.doctype, doc.name, current_level, doc_link)

	try:
		frappe.sendmail(
			recipients=[approver_user],
			subject=subject,
			message=message,
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			now=False,
		)
	except Exception:
		frappe.log_error(
			title=f"Dynamic Approval: email failed for {doc.name}",
			message=frappe.get_traceback(),
		)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Workflow setup  (called from Dynamic Approval Setting JS)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@frappe.whitelist()
def setup_workflow(config_name):
	"""Idempotent — safe to call multiple times."""
	frappe.only_for("System Manager")

	config_doc = frappe.get_doc("Dynamic Approval Setting", config_name)
	doctype = config_doc.document_type
	table_field = config_doc.approver_table_fieldname
	level_field = config_doc.current_level_fieldname

	_ensure_history_doctype()
	_ensure_custom_fields(doctype, level_field, table_field)
	_create_or_update_workflow(doctype, level_field)

	frappe.db.commit()
	frappe.msgprint(_("Workflow setup complete for {0}").format(doctype), alert=True)

def _ensure_history_doctype():
	doctype_name = "Dynamic Approval History"
	if not frappe.db.exists("DocType", doctype_name):
		frappe.get_doc({
			"doctype": "DocType",
			"name": doctype_name,
			"module": "Avinash Group App",
			"custom": 1,
			"istable": 1,
			"editable_grid": 1,
			"fields": [
				{"fieldname": "action", "fieldtype": "Data", "label": "Action", "in_list_view": 1, "reqd": 0, "columns": 2},
				{"fieldname": "user", "fieldtype": "Link", "options": "User", "label": "User", "in_list_view": 1, "reqd": 0, "columns": 3},
				{"fieldname": "user_name", "fieldtype": "Data", "label": "User Name", "in_list_view": 1, "fetch_from": "user.full_name", "read_only": 0, "columns": 3},
				{"fieldname": "timestamp", "fieldtype": "Datetime", "label": "Date and Time", "in_list_view": 1, "reqd": 0, "columns": 2}
			],
			"permissions": [],
		}).insert(ignore_permissions=True)


def _ensure_custom_fields(doctype, level_field, table_field):
	"""Create the four approval custom fields on the target doctype if missing."""

	# 1. Hidden Int — current approval level
	if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": level_field}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": doctype,
			"fieldname": level_field,
			"fieldtype": "Int",
			"label": "Current Approval Level",
			"hidden": 1,
			"no_copy": 1,
			"print_hide": 1,
			"insert_after": "amended_from",
		}).insert(ignore_permissions=True)

	# 2. Hidden Data — current approver User ID (drives workflow conditions)
	if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": CURRENT_APPROVER_FIELD}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": doctype,
			"fieldname": CURRENT_APPROVER_FIELD,
			"fieldtype": "Data",
			"label": "Current Approver",
			"hidden": 1,
			"no_copy": 1,
			"print_hide": 1,
			"insert_after": level_field,
		}).insert(ignore_permissions=True)

	# 3. Hidden Int — total approval levels (drives workflow conditions)
	if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": TOTAL_LEVELS_FIELD}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": doctype,
			"fieldname": TOTAL_LEVELS_FIELD,
			"fieldtype": "Int",
			"label": "Total Approval Levels",
			"hidden": 1,
			"no_copy": 1,
			"print_hide": 1,
			"insert_after": CURRENT_APPROVER_FIELD,
		}).insert(ignore_permissions=True)

	# 4. Section break — Approval Hierarchy
	section_hierarchy = "custom_section_approval_hierarchy"
	if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": section_hierarchy}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": doctype,
			"fieldname": section_hierarchy,
			"fieldtype": "Section Break",
			"label": "Approval Hierarchy",
			"insert_after": TOTAL_LEVELS_FIELD,
		}).insert(ignore_permissions=True)
	else:
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": section_hierarchy}, "insert_after", TOTAL_LEVELS_FIELD)
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": section_hierarchy}, "label", "Approval Hierarchy")
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": section_hierarchy}, "hidden", 0)

	# 5. Approval hierarchy table — user fills this before submitting
	if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": table_field}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": doctype,
			"fieldname": table_field,
			"fieldtype": "Table",
			"label": "Approval Hierarchy",
			"options": "Dynamic Approval Approver",
			"allow_on_submit": 1,
			"hidden": 0,
			"read_only": 0,
			"insert_after": section_hierarchy,
		}).insert(ignore_permissions=True)
	else:
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": table_field}, "insert_after", section_hierarchy)
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": table_field}, "allow_on_submit", 1)
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": table_field}, "hidden", 0)
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": table_field}, "read_only", 0)

	# 6. Section break — Approval History
	section_history = "custom_section_approval_history"
	if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": section_history}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": doctype,
			"fieldname": section_history,
			"fieldtype": "Section Break",
			"label": "Approval History",
			"insert_after": table_field,
		}).insert(ignore_permissions=True)
	else:
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": section_history}, "insert_after", table_field)
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": section_history}, "label", "Approval History")
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": section_history}, "hidden", 0)

	# 7. History Table — the log timeline
	history_table_field = "custom_approval_history"
	if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": history_table_field}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": doctype,
			"fieldname": history_table_field,
			"fieldtype": "Table",
			"label": "Approval History",
			"options": "Dynamic Approval History",
			"allow_on_submit": 1,
			"hidden": 0,
			"read_only": 0,
			"insert_after": section_history,
		}).insert(ignore_permissions=True)
	else:
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": history_table_field}, "insert_after", section_history)
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": history_table_field}, "allow_on_submit", 1)
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": history_table_field}, "hidden", 0)
		frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": history_table_field}, "read_only", 0)


def _create_or_update_workflow(doctype, level_field):
	"""
	Build the sequential approval workflow using only doc fields in conditions.

	Frappe's workflow safe_eval only exposes:
	  frappe.db.get_value, frappe.db.get_list, frappe.session, frappe.utils
	It does NOT expose frappe.get_attr — so conditions must use doc.field comparisons only.

	Solution: pre-compute current approver + total levels into hidden doc fields
	(CURRENT_APPROVER_FIELD, TOTAL_LEVELS_FIELD) in before_workflow_action.
	Conditions then just compare those fields to frappe.session.user.
	"""
	af = CURRENT_APPROVER_FIELD   # custom_current_approver
	tf = TOTAL_LEVELS_FIELD       # custom_total_approval_levels
	lf = level_field              # custom_current_approval_level

	# Intermediate: current user is the listed approver (or Admin) AND more levels remain
	# doc.lf > 0 guard prevents false match when level not yet initialised (0 == 0 bug)
	approve_more = (
		f'(doc.{af} == frappe.session.user or frappe.session.user == "Administrator")'
		f' and doc.{lf} > 0 and doc.{tf} > 0 and doc.{lf} < doc.{tf}'
	)
	# Final: current user is the listed approver (or Admin) AND this IS the last level
	approve_final = (
		f'(doc.{af} == frappe.session.user or frappe.session.user == "Administrator")'
		f' and doc.{lf} > 0 and doc.{tf} > 0 and doc.{lf} == doc.{tf}'
	)
	# Reject: current user is the listed approver or Admin
	can_reject = (
		f'doc.{af} == frappe.session.user or frappe.session.user == "Administrator"'
	)

	# DYNAMICALLY find everyone who has access to this DocType normally.
	# This ensures the POs are VISIBLE to your team without hardcoding names.
	doc_roles = frappe.get_all("DocPerm", filters={"parent": doctype}, fields=["role"], distinct=True)
	role_list = [r.role for r in doc_roles if r.role not in ("All", "Guest")]
	if not role_list:
		role_list = ["System Manager"]
	
	permissions = [{"role": role} for role in role_list]

	states = [
		{"state": "Draft",            "doc_status": "0", "allow_edit": "All", "permissions": permissions},
		{"state": "Pending Approval", "doc_status": "0", "allow_edit": "All", "permissions": permissions},
		{"state": "Approved",         "doc_status": "1", "allow_edit": "All", "permissions": permissions},
		{"state": "Rejected",         "doc_status": "0", "allow_edit": "All", "permissions": permissions},
	]

	transitions = [
		# Submission
		{
			"state": "Draft", "action": "Submit for Approval",
			"next_state": "Pending Approval", "allowed": "All", "condition": "",
		},
		# Intermediate approval — self-transition, level++ in before_workflow_action
		{
			"state": "Pending Approval", "action": "Approve",
			"next_state": "Pending Approval", "allowed": "All",
			"condition": approve_more,
		},
		# Final approval → Approved (docstatus = 1)
		{
			"state": "Pending Approval", "action": "Approve",
			"next_state": "Approved", "allowed": "All",
			"condition": approve_final,
		},
		# Rejection
		{
			"state": "Pending Approval", "action": "Reject",
			"next_state": "Rejected", "allowed": "All",
			"condition": can_reject,
		},
		# Resubmit after rejection
		{
			"state": "Rejected", "action": "Resubmit",
			"next_state": "Pending Approval", "allowed": "All", "condition": "",
		},
	]

	# Auto-create any Workflow State or Workflow Action Master that this
	# workflow references but does not yet exist in the DB.
	# This mirrors how Frappe's own workflow builder works — it never requires
	# you to pre-create states/actions; it creates them on the fly.
	for s in states:
		if not frappe.db.exists("Workflow State", s["state"]):
			frappe.get_doc({
				"doctype": "Workflow State",
				"workflow_state_name": s["state"],
			}).insert(ignore_permissions=True)

	for t in transitions:
		if not frappe.db.exists("Workflow Action Master", t["action"]):
			frappe.get_doc({
				"doctype": "Workflow Action Master",
				"workflow_action_name": t["action"],
			}).insert(ignore_permissions=True)

	existing = frappe.get_all(
		"Workflow",
		filters={"document_type": doctype, "is_active": 1},
		pluck="name",
		limit=1,
	)

	if existing:
		wf = frappe.get_doc("Workflow", existing[0])
		wf.states = []
		wf.transitions = []
		for s in states:
			wf.append("states", s)
		for t in transitions:
			wf.append("transitions", t)
		wf.is_active = 1
		wf.save(ignore_permissions=True)
		frappe.msgprint(_("Updated existing workflow: {0}").format(wf.name), alert=True)
	else:
		wf = frappe.get_doc({
			"doctype": "Workflow",
			"workflow_name": f"{doctype} Approval Workflow",
			"document_type": doctype,
			"is_active": 1,
			"send_email_alert": 0,
			"states": states,
			"transitions": transitions,
		})
		wf.insert(ignore_permissions=True)
		frappe.msgprint(_("Created workflow: {0}").format(wf.name), alert=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Whitelisted API  (called from client scripts)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@frappe.whitelist()
def is_current_approver(doctype, docname):
	"""Return True if the current session user may act at the current approval level."""
	approver = frappe.db.get_value(doctype, docname, CURRENT_APPROVER_FIELD)
	if not approver:
		return False
	return approver == frappe.session.user or frappe.session.user == "Administrator"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Utilities
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cint(value):
	"""Safe int conversion."""
	try:
		return int(value)
	except (TypeError, ValueError):
		return 0
