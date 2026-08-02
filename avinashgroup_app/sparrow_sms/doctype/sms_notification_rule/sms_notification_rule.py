# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# Many doctypes hold a phone number in a plain Data field with no "Phone"
# options set (Sales Invoice.contact_mobile is one), so name matching has to
# back up the metadata.
PHONE_NAME_HINTS = ("mobile", "phone", "contact_no", "whatsapp")

# Customer.mobile_no is "Read Only" (it is fetched from the primary contact),
# so restricting to Data/Phone would hide the single most useful path there is.
PHONE_FIELDTYPES = ("Data", "Phone", "Small Text", "Read Only")


def _is_phone_field(df):
	if df.fieldtype not in PHONE_FIELDTYPES:
		return False
	if (df.options or "") in ("Phone", "Mobile"):
		return True
	return any(hint in (df.fieldname or "").lower() for hint in PHONE_NAME_HINTS)


@frappe.whitelist()
def get_recipient_field_options(document_type):
	"""Phone-number fields reachable from `document_type`, as a Select option list.

	Two kinds:
	  - direct       "contact_mobile"
	  - through link "customer.mobile_no"

	The link hop is the point of this: a Sales Invoice carries no customer phone
	number of its own, so the number has to be read off the linked Customer.
	"""
	if not document_type or not frappe.db.exists("DocType", document_type):
		return []

	options = []
	meta = frappe.get_meta(document_type)

	for df in meta.fields:
		if _is_phone_field(df):
			options.append({"value": df.fieldname, "label": f"{df.fieldname} ({df.label or df.fieldname})"})

	for df in meta.fields:
		if df.fieldtype not in ("Link", "Dynamic Link") or not df.options:
			continue

		# A Dynamic Link's target is only known per-document, so offer the
		# doctypes it is actually pointed at rather than guessing one.
		target_doctypes = []
		if df.fieldtype == "Link":
			target_doctypes = [df.options]
		else:
			link_df = meta.get_field(df.options)
			if link_df and link_df.fieldtype == "Select":
				target_doctypes = [o for o in (link_df.options or "").split("\n") if o.strip()]

		for target in target_doctypes:
			if not frappe.db.exists("DocType", target):
				continue
			for target_df in frappe.get_meta(target).fields:
				if not _is_phone_field(target_df):
					continue
				options.append(
					{
						"value": f"{df.fieldname}.{target_df.fieldname}",
						"label": f"{df.fieldname}.{target_df.fieldname} ({df.label or df.fieldname} → {target_df.label or target_df.fieldname})",
					}
				)

	# Stable, de-duplicated: direct fields first, then link hops.
	seen, unique = set(), []
	for option in options:
		if option["value"] not in seen:
			seen.add(option["value"])
			unique.append(option)
	return unique


class SMSNotificationRule(Document):
	def validate(self):
		if not self.recipients:
			frappe.throw(_("Add at least one Phone Number Field."))

		meta = frappe.get_meta(self.document_type)

		if self.event == "On Submit" and not meta.is_submittable:
			frappe.throw(
				_("{0} is not submittable, so the On Submit event will never fire.").format(
					frappe.bold(self.document_type)
				)
			)

		for row in self.recipients:
			self._validate_path(meta, row)

	def _validate_path(self, meta, row):
		path = (row.recipient_field or "").strip()
		root = path.split(".")[0]

		df = meta.get_field(root)
		if not df:
			frappe.throw(
				_("Row {0}: {1} has no field {2}.").format(
					row.idx, frappe.bold(self.document_type), frappe.bold(root)
				)
			)

		if "." not in path:
			return

		if df.fieldtype == "Dynamic Link":
			# Target doctype varies per document; resolved at send time.
			return

		if df.fieldtype != "Link":
			frappe.throw(
				_("Row {0}: {1} is not a link field, so {2} cannot be read through it.").format(
					row.idx, frappe.bold(root), frappe.bold(path)
				)
			)

		leaf = path.split(".", 1)[1]
		if not frappe.get_meta(df.options).has_field(leaf):
			frappe.throw(
				_("Row {0}: {1} has no field {2}.").format(
					row.idx, frappe.bold(df.options), frappe.bold(leaf)
				)
			)

	def on_update(self):
		clear_rule_cache()

	def on_trash(self):
		clear_rule_cache()


def clear_rule_cache():
	"""Drop the doctype gate and the per-doctype rule lists.

	The dispatcher is registered on "*", so it runs on every document event in
	the system. It leans on this cache to bail out without a DB hit; any rule
	edit must therefore invalidate it or the change won't take effect.
	"""
	from avinashgroup_app.sparrow_sms.sms_dispatch import CACHE_KEY_DOCTYPES, CACHE_KEY_RULES

	frappe.cache().delete_value(CACHE_KEY_DOCTYPES)
	frappe.cache().delete_keys(CACHE_KEY_RULES)
