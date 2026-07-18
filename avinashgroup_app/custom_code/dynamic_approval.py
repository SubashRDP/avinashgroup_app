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

# Pinned setting name + group — injected on first submission so subsequent
# lookups skip criteria scanning entirely (2 DB queries instead of N+3).
APPROVAL_SETTING_FIELD  = "custom_approval_setting"
APPROVAL_SECTION_FIELD  = "custom_approval_section"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Notification templates  — default (fallback) Email Template names
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Each Dynamic Approval Setting may link its own Email Template per notification
# type; when the link is blank we fall back to these auto-provisioned defaults.
TEMPLATE_APPROVAL = "Dynamic Approval Request"    # forward → next approver
TEMPLATE_PROGRESS = "Dynamic Approval Progress"   # backward → "X has approved"
TEMPLATE_FINAL    = "Dynamic Approval Final"      # backward → "fully approved"
TEMPLATE_REJECT   = "Dynamic Approval Rejected"   # backward → "rejected by X"

# Notification config columns on Dynamic Approval Setting — fetched alongside the
# core config and carried through to _dispatch_notifications().
_NOTIFY_FIELDS = [
	"enable_approval_notification", "email_template",
	"enable_progress_notification", "progress_email_template",
	"enable_final_notification", "final_email_template",
	"enable_reject_notification", "reject_email_template",
]


def _is_managed_doctype(doc):
	"""
	A doctype is managed by Dynamic Approval only if `setup_workflow` has created
	its driver field. The doc-event hooks are registered on "*", so this cheap,
	DB-free meta check is the gate that keeps us from touching any other doctype's
	workflow (e.g. the Material Request One-Line Approver) and avoids a config DB
	scan on every save of every doctype in the system.
	"""
	return bool(doc and doc.meta.has_field(CURRENT_APPROVER_FIELD))


@frappe.whitelist()
def has_approval_config(doctype, company):
	"""Check if a Dynamic Approval Setting exists for this doctype + company.
	Called from client JS to toggle visibility of approval fields."""
	if not doctype or not company:
		return False
	return bool(frappe.db.get_all(
		"Dynamic Approval Setting",
		filters={"document_type": doctype, "company": company, "is_active": 1},
		limit=1,
	))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DB helpers  — always read directly from DB, no caching
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _get_config_for_doc(doc):
	"""
	Fast path  — setting + section already pinned on the doc (injected on first submission):
	            2 DB queries, no criteria scanning.
	Slow path  — first time: scan all settings for this company+doctype, score sections
	            by criteria count, pick best match, then pin setting+section on the doc.
	"""
	pinned_setting = doc.get(APPROVAL_SETTING_FIELD)
	pinned_section = doc.get(APPROVAL_SECTION_FIELD)

	if pinned_setting and pinned_section:
		return _fetch_config_by_section(pinned_setting, pinned_section)

	# ── Slow path: criteria scan ──────────────────────────────────
	company = doc.get("company")
	if not company:
		return None

	settings = frappe.get_all(
		"Dynamic Approval Setting",
		filters={"document_type": doc.doctype, "company": company, "is_active": 1},
		fields=["name", "approver_table_fieldname", "current_level_fieldname", *_NOTIFY_FIELDS],
	)
	if not settings:
		return None

	setting_names = [s.name for s in settings]

	all_criteria = frappe.get_all(
		"Dynamic Approval Match Criteria",
		filters={"parent": ("in", setting_names), "parenttype": "Dynamic Approval Setting"},
		fields=["parent", "section", "field_name", "field_value"],
	)
	all_approvers = frappe.get_all(
		"Dynamic Approval Fixed Approver",
		filters={"parent": ("in", setting_names), "parenttype": "Dynamic Approval Setting"},
		fields=["parent", "section", "approver", "approver_name"],
		order_by="idx",
	)

	# Group by (setting_name, section)
	criteria_map = {}
	for c in all_criteria:
		criteria_map.setdefault(c.parent, {}).setdefault(c.section or "", []).append(c)

	approver_map = {}
	for a in all_approvers:
		approver_map.setdefault(a.parent, {}).setdefault(a.section or "", []).append(a)

	for setting in settings:
		sname = setting.name
		criteria_by_section = criteria_map.get(sname, {})
		approvers_by_section = approver_map.get(sname, {})

		all_sections = set(criteria_by_section.keys()) | set(approvers_by_section.keys())
		if not all_sections:
			all_sections = {""}  # no rows at all = single catch-all section

		best_section = None
		best_score = -1

		for sec in all_sections:
			criteria = criteria_by_section.get(sec, [])
			# A section with zero criteria matches nothing.
			if not criteria:
				continue

			if all(
				str(doc.get(c.field_name) or "").strip() == str(c.field_value or "").strip()
				for c in criteria
			):
				score = len(criteria)
				if score > best_score:
					best_score = score
					best_section = sec

		if best_section is None:
			continue

		# Pin setting + section on the doc so future calls skip this scan
		doc.set(APPROVAL_SETTING_FIELD, sname)
		doc.set(APPROVAL_SECTION_FIELD, best_section)

		fixed = approvers_by_section.get(best_section, [])
		return {
			"name": sname,
			"approver_table_fieldname": setting.approver_table_fieldname,
			"current_level_fieldname": setting.current_level_fieldname,
			"fixed_approvers": fixed,
			**{f: setting.get(f) for f in _NOTIFY_FIELDS},
		}

	return None


def _fetch_config_by_section(setting_name, section):
	"""Fast path: fetch a specific setting + its approvers for a known section."""
	rows = frappe.get_all(
		"Dynamic Approval Setting",
		filters={"name": setting_name, "is_active": 1},
		fields=["name", "approver_table_fieldname", "current_level_fieldname", *_NOTIFY_FIELDS],
		limit=1,
	)
	if not rows:
		return None
	setting = rows[0]

	fixed = frappe.get_all(
		"Dynamic Approval Fixed Approver",
		filters={"parent": setting_name, "parenttype": "Dynamic Approval Setting", "section": section},
		fields=["section", "approver", "approver_name"],
		order_by="idx",
	)
	return {
		"name": setting_name,
		"approver_table_fieldname": setting.approver_table_fieldname,
		"current_level_fieldname": setting.current_level_fieldname,
		"fixed_approvers": fixed,
		**{f: setting.get(f) for f in _NOTIFY_FIELDS},
	}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Core level logic  (union: doc table  +  Setting fixed approvers)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_total_levels(doc, config):
	"""
	Total levels  =  rows in the doc's approval table
	              +  fixed approvers in Dynamic Approval Setting.
	"""
	table_field = config["approver_table_fieldname"]
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


def validate(doc, method=None):
	"""
	When Pending Approval:
	  1. Only the current approver (or Administrator) may save.
	  2. Already-approved rows (level < current_level) cannot be changed or deleted.

	Workflow transitions are exempt from rule 1:
	  - Submit for Approval (Draft → Pending) — workflow_state has changed
	  - Intermediate Approve (Pending → Pending, level++) — flagged by before_workflow_action
	"""
	if not _is_managed_doctype(doc):
		return
	config = _get_config_for_doc(doc)
	if not config:
		return
	if doc.is_new():
		return
	if frappe.session.user == "Administrator":
		return

	# Once rejected the document is frozen — no field edits by anyone (Admin excepted
	# above). Allow the reject transition itself, which flips workflow_state → Rejected
	# on this very save (DB still holds the prior "Pending Approval" state, so
	# has_value_changed is True); every later save while Rejected is blocked.
	if doc.get("workflow_state") == "Rejected":
		if not doc.has_value_changed("workflow_state"):
			frappe.throw(
				_("This document has been rejected and is now read-only. No changes are allowed.")
			)
		return

	if doc.get("workflow_state") != "Pending Approval":
		return

	# Allow the workflow transition that brought the doc INTO Pending
	# (Submit for Approval). DB still has old state at this point.
	if doc.has_value_changed("workflow_state"):
		pass
	# Allow the intermediate Approve transition (level increment).
	elif doc.flags.get("approval_level_changed"):
		pass
	else:
		# Plain save while Pending — only the current approver may proceed.
		# Read from DB: before_workflow_action overwrites the in-memory field
		# during transitions, but for plain saves the DB value is authoritative.
		current_approver = frappe.db.get_value(doc.doctype, doc.name, CURRENT_APPROVER_FIELD) or doc.get(CURRENT_APPROVER_FIELD)
		if frappe.session.user != current_approver:
			approver_name = (
				frappe.db.get_value("User", current_approver, "full_name") or current_approver
				if current_approver else _("the assigned approver")
			)
			frappe.throw(
				_("This document is pending approval. Only {0} (the current approver) may make changes.").format(approver_name)
			)

	# Current approver cannot modify already-approved rows
	level_field = config["current_level_fieldname"]
	current_level = cint(doc.get(level_field) or 0)
	if current_level <= 1:
		return

	table_field = config["approver_table_fieldname"]
	saved_rows = {
		cint(r["level"]): r["approver"]
		for r in frappe.db.get_all(
			"Dynamic Approval Approver",
			filters={"parent": doc.name, "parenttype": doc.doctype, "parentfield": table_field},
			fields=["level", "approver"],
		)
	}
	current_rows = {cint(r.level): r.approver for r in (doc.get(table_field) or [])}

	for level, approver in saved_rows.items():
		if level >= current_level:
			continue  # Not yet approved — current approver may still change these
		if level not in current_rows:
			frappe.throw(
				_("Cannot delete approver at Level {0} — this level has already been approved.").format(level)
			)
		if current_rows[level] != approver:
			frappe.throw(
				_("Cannot change approver at Level {0} — this level has already been approved.").format(level)
			)


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
	# Hook is registered on "*". Never touch a doctype we don't manage —
	# otherwise the no-config branch below could auto-submit, say, a Material
	# Request whose own workflow happens to use a "Submit for Approval" action.
	if not _is_managed_doctype(doc):
		return

	config = _get_config_for_doc(doc)

	# Frappe sets doc.workflow_action before calling this hook.
	action = action or doc.get("workflow_action")
	if not action:
		return

	# No config for this company → auto-approve on Submit instead of stranding
	# the doc in Pending Approval with uninitialised level fields (which would
	# leave only Reject visible — even for Administrator).
	if not config:
		if action == "Submit for Approval":
			doc.workflow_state = "Approved"
			doc.docstatus = 1
			_log_approval_history(doc, "Auto-approved (no matching approval rule)")
		elif action == "Approve":
			_log_approval_history(doc, "Approved (no matching approval rule)")
		elif action == "Reject":
			doc.flags.is_rejection = True
			_log_approval_history(doc, "Rejected")
		return

	level_field = config["current_level_fieldname"]
	table_field = config["approver_table_fieldname"]

	if action == "Submit for Approval":
		total = _get_total_levels(doc, config)
		if not total:
			# No approvers configured — fall back to Administrator as the sole approver
			total = 1
			approver = "Administrator"
		else:
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
		
		# Record which level this action just approved + whether it's the last one,
		# so on_update can fire the progress / final notifications.
		doc.flags.approved_level = current_level
		doc.flags.approval_is_final = current_level >= total

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


def on_update(doc, method=None):
	"""
	1. Re-sync current approver when the hierarchy table is edited while Pending Approval.
	   Uses frappe.db.set_value (direct DB write) so the change is never lost regardless
	   of what happened in the save cycle.
	2. Send email notification when the level changes via a workflow action.
	"""
	if not _is_managed_doctype(doc):
		return
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

	# ── 2. Email notifications (approval-request / progress / final) ─────
	_dispatch_notifications(doc, config)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Notification
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _dispatch_notifications(doc, config):
	"""
	Fire the three optional, independently-configured notifications based on the
	flags set during before_workflow_action and the per-flow config on the Setting:

	  1. Approval request → the next approver, on submit + each intermediate approve
	     (flag: approval_level_changed).
	  2. Progress ("X approved") → everyone who already approved, on each
	     intermediate approve (flag: approved_level set, not final).
	  3. Final ("fully approved") → everyone who approved, on the final approve
	     (flag: approved_level set, is final).

	Each type is gated by its own enable checkbox and may specify its own Email
	Template (blank → built-in default). Nothing sends unless a flag is set, so a
	plain save in Pending Approval never emails.
	"""
	level_field = config["current_level_fieldname"]

	# ── 1. Approval request → next approver ──────────────────────────────
	if getattr(doc.flags, "approval_level_changed", False) and config.get("enable_approval_notification"):
		if doc.get("workflow_state") == "Pending Approval":
			current_level = cint(doc.get(level_field))
			approver_user = doc.get(CURRENT_APPROVER_FIELD)
			if current_level and approver_user:
				approver_name = frappe.db.get_value("User", approver_user, "full_name") or approver_user
				ctx = _notification_context(doc, approver_name=approver_name, current_level=current_level)
				_send_templated_email(
					[approver_user],
					config.get("email_template") or TEMPLATE_APPROVAL,
					TEMPLATE_APPROVAL,
					ctx,
					doc,
				)

	# ── 2. Rejected → maker (always) + already-approved earlier levels (if enabled) ──
	if getattr(doc.flags, "is_rejection", False):
		current_level = cint(doc.get(level_field))
		actor_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
		# The maker (doc owner) is ALWAYS notified on rejection, regardless of the
		# per-flow toggle — excluded only when the maker is also the rejecter (no
		# self-mail). Approvers of levels below the rejecting one are added only when
		# the flow enables reject notifications; the rejecter and any future/higher
		# level are never included (the helper only walks levels 1..upto).
		recipients = []
		owner = doc.get("owner")
		if owner and owner != frappe.session.user:
			recipients.append(owner)
		if config.get("enable_reject_notification"):
			for u in _collect_previous_approvers(doc, config, current_level - 1):
				if u not in recipients:
					recipients.append(u)
		if recipients:
			ctx = _notification_context(doc, approver_name=actor_name, current_level=current_level)
			_send_templated_email(
				recipients,
				config.get("reject_email_template") or TEMPLATE_REJECT,
				TEMPLATE_REJECT,
				ctx,
				doc,
			)

	# ── 3 + 4. Progress / final ──────────────────────────────────────────
	approved_level = getattr(doc.flags, "approved_level", None)
	if not approved_level:
		return

	is_final = bool(getattr(doc.flags, "approval_is_final", False))
	actor_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
	total_levels = cint(doc.get(TOTAL_LEVELS_FIELD))
	approvers = _collect_previous_approvers(doc, config, approved_level)

	ctx = _notification_context(
		doc,
		approver_name=actor_name,
		current_level=approved_level,
		approved_level=approved_level,
		total_levels=total_levels,
		is_final=is_final,
	)

	# ── 3. Progress ("X approved at level N") → already-approved approvers only.
	# The creator is deliberately NOT mailed per step (only the final outcome).
	if not is_final:
		if approvers and config.get("enable_progress_notification"):
			_send_templated_email(
				approvers,
				config.get("progress_email_template") or TEMPLATE_PROGRESS,
				TEMPLATE_PROGRESS,
				ctx,
				doc,
			)
		return

	# ── 4. Final ("fully approved") → the creator (owner) is ALWAYS notified of the
	# outcome, regardless of the per-flow toggle (mirrors the mandatory reject mail).
	# Already-approved approvers are added only when the final toggle is enabled.
	# Owner excluded only when the creator is themselves the final approver.
	recipients = []
	owner = doc.get("owner")
	if owner and owner != frappe.session.user:
		recipients.append(owner)
	if config.get("enable_final_notification"):
		for u in approvers:
			if u not in recipients:
				recipients.append(u)
	if recipients:
		_send_templated_email(
			recipients,
			config.get("final_email_template") or TEMPLATE_FINAL,
			TEMPLATE_FINAL,
			ctx,
			doc,
		)


def _notification_context(doc, approver_name="", current_level=0, approved_level=0,
						  total_levels=0, is_final=False):
	"""Jinja render context shared by all notification templates."""
	return {
		"doc": doc,
		"docname": doc.name,
		"doctype_label": _(doc.doctype),
		"doc_link": frappe.utils.get_url_to_form(doc.doctype, doc.name),
		"approver_name": approver_name,
		"current_level": current_level,
		"approved_level": approved_level or current_level,
		"total_levels": total_levels or cint(doc.get(TOTAL_LEVELS_FIELD)),
		"is_final": is_final,
	}


def _collect_previous_approvers(doc, config, upto_level):
	"""
	Deduped list of approver User IDs for levels 1..upto_level (everyone who has
	already approved), excluding the acting user — nobody gets a "you approved"
	mail about their own just-completed action.
	"""
	acting_user = frappe.session.user
	seen = set()
	recipients = []
	for lvl in range(1, cint(upto_level) + 1):
		approver = _get_effective_approver_at_level(doc, lvl, config)
		if not approver or approver == acting_user or approver in seen:
			continue
		seen.add(approver)
		recipients.append(approver)
	return recipients


def _send_templated_email(recipients, template_name, fallback_template, context, doc):
	"""
	Render an Email Template and mail it to `recipients` (User IDs). Each recipient
	is skipped unless their User record has an email and is enabled. Falls back to
	the built-in default template if the linked one is missing. All failures are
	logged, never raised — a broken template must not block the approval save.
	"""
	# Resolve recipients → real email addresses, honouring the "has email" gate
	# and de-duplicating (distinct users may share an address).
	emails = []
	for user in recipients:
		email, enabled = frappe.db.get_value("User", user, ["email", "enabled"]) or (None, 0)
		if email and enabled and email not in emails:
			emails.append(email)
	if not emails:
		return

	try:
		_ensure_email_templates()
		if not frappe.db.exists("Email Template", template_name):
			template_name = fallback_template
		rendered = frappe.get_doc("Email Template", template_name).get_formatted_email(context)
		frappe.sendmail(
			recipients=emails,
			subject=rendered["subject"],
			message=rendered["message"],
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			now=False,
		)
	except Exception:
		frappe.log_error(
			title=f"Dynamic Approval: email failed for {doc.name}",
			message=frappe.get_traceback(),
		)


def _ensure_email_templates():
	"""
	Create-only provisioning of the three default Email Templates. Never overwrites
	an existing one, so admin edits (and per-flow custom templates) survive
	re-running Setup Workflow. Mirrors _ensure_history_doctype's idempotent style.
	"""
	defaults = {
		TEMPLATE_APPROVAL: {
			"subject": "{{ doctype_label }} {{ docname }} — Your Approval Required (Level {{ current_level }})",
			"response_html": (
				"<p>Dear {{ approver_name }},</p>"
				"<p>{{ doctype_label }} <b>{{ docname }}</b> is awaiting your approval "
				"at Level {{ current_level }}.</p>"
				"<p><a href=\"{{ doc_link }}\">Click here to approve or reject</a></p>"
			),
		},
		TEMPLATE_PROGRESS: {
			"subject": "{{ doctype_label }} {{ docname }} — Approved at Level {{ approved_level }}",
			"response_html": (
				"<p>Hello,</p>"
				"<p><b>{{ approver_name }}</b> has approved {{ doctype_label }} "
				"<b>{{ docname }}</b> at Level {{ approved_level }} of {{ total_levels }}.</p>"
				"<p><a href=\"{{ doc_link }}\">Click here to open</a></p>"
			),
		},
		TEMPLATE_FINAL: {
			"subject": "{{ doctype_label }} {{ docname }} — Fully Approved",
			"response_html": (
				"<p>Hello,</p>"
				"<p>{{ doctype_label }} <b>{{ docname }}</b> has been fully approved "
				"(all {{ total_levels }} levels). The final approval was made by "
				"<b>{{ approver_name }}</b>.</p>"
				"<p><a href=\"{{ doc_link }}\">Click here to open</a></p>"
			),
		},
		TEMPLATE_REJECT: {
			"subject": "{{ doctype_label }} {{ docname }} — Rejected",
			"response_html": (
				"<p>Hello,</p>"
				"<p>{{ doctype_label }} <b>{{ docname }}</b> was <b>rejected</b> by "
				"<b>{{ approver_name }}</b> at Level {{ current_level }}.</p>"
				"<p><a href=\"{{ doc_link }}\">Click here to open</a></p>"
			),
		},
	}
	for name, body in defaults.items():
		if frappe.db.exists("Email Template", name):
			continue
		frappe.get_doc({
			"doctype": "Email Template",
			"name": name,
			"subject": body["subject"],
			"use_html": 1,
			"response_html": body["response_html"],
		}).insert(ignore_permissions=True)


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
	_ensure_email_templates()
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
	"""Create approval custom fields on the target doctype if missing."""

	# 0a. Hidden Link — pinned approval setting (fast-path lookup)
	if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": APPROVAL_SETTING_FIELD}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": doctype,
			"fieldname": APPROVAL_SETTING_FIELD,
			"fieldtype": "Link",
			"options": "Dynamic Approval Setting",
			"label": "Approval Setting",
			"hidden": 1,
			"no_copy": 1,
			"print_hide": 1,
			"insert_after": "amended_from",
		}).insert(ignore_permissions=True)

	# 0b. Hidden Data — pinned approval section name
	if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": APPROVAL_SECTION_FIELD}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": doctype,
			"fieldname": APPROVAL_SECTION_FIELD,
			"fieldtype": "Data",
			"label": "Approval Section",
			"hidden": 1,
			"no_copy": 1,
			"print_hide": 1,
			"insert_after": APPROVAL_SETTING_FIELD,
		}).insert(ignore_permissions=True)

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

	# Intermediate: current approver, AND more levels remain.
	# doc.lf > 0 guard prevents false match when level not yet initialised (0 == 0 bug).
	# Admin override: Administrator can advance only when there is a "next" level
	# (i.e. tf is initialised and lf < tf). Otherwise admin's Approve falls through
	# to approve_final (which also accepts uninitialised fields).
	approve_more = (
		f'(doc.{af} == frappe.session.user and doc.{lf} > 0 and doc.{tf} > 0 and doc.{lf} < doc.{tf})'
		f' or (frappe.session.user == "Administrator" and doc.{tf} > 0 and doc.{lf} < doc.{tf})'
	)
	# Final: last level reached, OR Administrator on a doc with no level data
	# (covers stranded docs where _get_config_for_doc returned None at submit).
	approve_final = (
		f'(doc.{af} == frappe.session.user and doc.{lf} > 0 and doc.{tf} > 0 and doc.{lf} == doc.{tf})'
		f' or (frappe.session.user == "Administrator" and (doc.{tf} == 0 or doc.{lf} == doc.{tf}))'
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

	# Some submittable doctypes gate their own submission on a native `status`
	# field — e.g. HRMS Leave Application throws unless status is Approved/Rejected
	# before submit. When the target has such a status field, bridge
	# workflow_state → status so reaching Approved/Rejected also sets it.
	status_df = frappe.get_meta(doctype).get_field("status")
	bridge_status = bool(
		status_df
		and status_df.fieldtype == "Select"
		and "Approved" in (status_df.options or "")
		and "Rejected" in (status_df.options or "")
	)

	approved_state = {"state": "Approved", "doc_status": "1", "allow_edit": "All", "send_email": 0, "permissions": permissions}
	rejected_state = {"state": "Rejected", "doc_status": "0", "allow_edit": "All", "send_email": 0, "permissions": permissions}
	if bridge_status:
		approved_state.update({"update_field": "status", "update_value": "Approved"})
		rejected_state.update({"update_field": "status", "update_value": "Rejected"})

	# send_email: 0 on every state disables Frappe's native "please-act" workflow email —
	# it fans out to every user holding the transition's role ("All"), which would notify
	# future/higher approvers. Notifications are handled solely by _dispatch_notifications,
	# which is level-scoped. This is the per-state gate; send_email_alert below is the other.
	states = [
		{"state": "Draft",            "doc_status": "0", "allow_edit": "All", "send_email": 0, "permissions": permissions},
		{"state": "Pending Approval", "doc_status": "0", "allow_edit": "All", "send_email": 0, "permissions": permissions},
		approved_state,
		rejected_state,
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
		# Match the create branch: keep the native workflow email off so re-running
		# Setup Workflow never re-enables the "please-act" fan-out to future approvers.
		wf.send_email_alert = 0
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
