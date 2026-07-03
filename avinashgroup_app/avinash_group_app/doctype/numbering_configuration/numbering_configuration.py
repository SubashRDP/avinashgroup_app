# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document

from avinashgroup_app.custom_code.Override.naming_series import (
	_build_from_segments,
	_rule_dict_from_config,
	_rule_matches,
)


class NumberingConfiguration(Document):
	def autoname(self):
		"""Readable, collision-free name: DocType - <company abbr> - <hash>."""
		parts = [self.document_type or "Rule"]
		if self.company:
			parts.append(frappe.get_cached_value("Company", self.company, "abbr") or self.company)
		self.name = " - ".join(parts) + " - " + frappe.generate_hash(length=5)

	def validate(self):
		self.validate_segments()
		self.validate_condition_fields()
		self.validate_legacy_cutover()

	def validate_legacy_cutover(self):
		if not self.legacy_upto:
			self.legacy_source_field = None
			return
		if not self.legacy_source_field:
			frappe.throw(
				_("Pick the <b>Legacy Source Field</b> — the field the old number is copied from up to {0}.").format(
					frappe.utils.formatdate(self.legacy_upto)
				),
				title=_("Legacy Source Field Required"),
			)
		if self.document_type and not frappe.get_meta(self.document_type).has_field(self.legacy_source_field):
			frappe.throw(
				_("'{0}' is not a field on {1}.").format(self.legacy_source_field, self.document_type)
			)

	def on_update(self):
		self.ensure_target_field_no_copy()
		self.ensure_target_field_indexed()

	def ensure_target_field_no_copy(self):
		"""Generated numbers must not survive Duplicate/Amend — mark the target
		field no_copy so copies start blank and get a fresh number on save."""
		if not (self.document_type and self.target_field):
			return

		custom_field = frappe.db.get_value(
			"Custom Field", {"dt": self.document_type, "fieldname": self.target_field}
		)
		if custom_field:
			if not frappe.db.get_value("Custom Field", custom_field, "no_copy"):
				frappe.db.set_value("Custom Field", custom_field, "no_copy", 1)
				frappe.clear_cache(doctype=self.document_type)
		else:
			# standard field -> property setter
			meta = frappe.get_meta(self.document_type)
			df = meta.get_field(self.target_field)
			if df and not df.no_copy:
				from frappe.custom.doctype.property_setter.property_setter import make_property_setter
				make_property_setter(
					self.document_type, self.target_field, "no_copy", 1, "Check"
				)
				frappe.clear_cache(doctype=self.document_type)

	def ensure_target_field_indexed(self):
		"""The uniqueness check queries the target field on every save; without
		a DB index that is a full table scan (seconds on large tables)."""
		if not (self.document_type and self.target_field):
			return

		custom_field = frappe.db.get_value(
			"Custom Field",
			{"dt": self.document_type, "fieldname": self.target_field},
			["name", "search_index"],
			as_dict=True,
		)
		if custom_field and not custom_field.search_index:
			frappe.db.set_value("Custom Field", custom_field.name, "search_index", 1)
		frappe.db.add_index(self.document_type, [self.target_field])

	def validate_segments(self):
		number_segments = 0
		for row in self.segments or []:
			stype = row.segment_type
			if stype == "Number":
				number_segments += 1
			elif stype in ("Static Text", "Normal / Return Code") and not (row.static_value or "").strip():
				frappe.throw(_("Segment row {0}: enter the Text (normal code).").format(row.idx))
			elif stype in ("Document Field", "Fetch from Link") and not row.field:
				frappe.throw(_("Segment row {0}: pick a Field.").format(row.idx))
			elif stype == "Fetch from Link" and not row.fetch_field:
				frappe.throw(_("Segment row {0}: enter the Fetch Field to read on the linked record.").format(row.idx))

		if number_segments > 1:
			frappe.throw(
				_("Add at most one <b>Number</b> segment (found {0}).").format(number_segments),
				title=_("Too Many Number Segments"),
			)

		if number_segments == 0:
			if not (self.segments or []):
				frappe.throw(_("Add at least one segment."), title=_("Segments Required"))
			# no Number segment = pass-through rule (copies the segment values
			# as-is, no counter) — valid, e.g. "Document Field: narration" for
			# migrated legacy invoices. Warn so a plain counter rule isn't
			# saved incomplete by accident.
			frappe.msgprint(
				_(
					"No <b>Number</b> segment: this rule copies the segment values "
					"directly (pass-through, no running counter). Intended for "
					"cases like reading the legacy number from a document field."
				),
				indicator="orange",
				alert=True,
			)

	def validate_condition_fields(self):
		if not self.document_type or not self.conditions:
			return
		meta = frappe.get_meta(self.document_type)
		for row in self.conditions:
			if row.field and not meta.has_field(row.field):
				frappe.msgprint(
					_("Condition row {0}: '{1}' is not a field on {2}.").format(
						row.idx, row.field, self.document_type
					),
					indicator="orange",
					alert=True,
				)

	@frappe.whitelist()
	def test_number(self, reference=None):
		"""Preview the number this rule would produce, without consuming the counter.

		If `reference` (an existing document name) is given, conditions/fetches are
		evaluated against that real document; otherwise a blank document is used.
		"""
		if reference:
			doc = frappe.get_doc(self.document_type, reference)
		else:
			# blank sample document, seeded with the rule's scope and today's date
			# so Company Abbr, branch fetches and Fiscal Year resolve in the preview.
			doc = frappe.new_doc(self.document_type)
			if self.company and doc.meta.has_field("company"):
				doc.company = self.company
			if self.branch and doc.meta.has_field("custom_branch"):
				doc.custom_branch = self.branch
			today = frappe.utils.nowdate()
			if doc.meta.has_field("posting_date") and not doc.get("posting_date"):
				doc.posting_date = today
			if doc.meta.has_field("transaction_date") and not doc.get("transaction_date"):
				doc.transaction_date = today

		rule = _rule_dict_from_config(self)
		return {
			"matches": bool(_rule_matches(doc, rule)),
			"number": _build_from_segments(doc, rule, commit_series=False),
		}


@frappe.whitelist()
def bulk_duplicate(source, companies):
	"""Clone a Numbering Configuration for each of the given companies."""
	if isinstance(companies, str):
		companies = json.loads(companies)

	created = []
	for company in companies:
		new_doc = frappe.copy_doc(frappe.get_doc("Numbering Configuration", source))
		new_doc.company = company
		new_doc.insert(ignore_permissions=False)
		created.append(new_doc.name)
	return created
