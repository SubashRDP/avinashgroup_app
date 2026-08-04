"""Finish moving the Sparrow SMS token off the Password fieldtype it started on.

`token` was a Password field until 8fcb45d. Frappe keeps a Password value in
`__Auth` and leaves a placeholder of literal asterisks — `"*" * len(value)`,
see base_document._save_passwords — in the document row itself. Changing the
fieldtype to Data does not undo either half: the real token stays stranded in
`__Auth`, and the asterisks stay in `tabSingles` as an ordinary Data value.

Nothing masks anything after that. The desk renders the asterisks that are
genuinely stored, which reads as a filled-in password box, and sms_dispatch
posts that same asterisk string to Sparrow as the token — so every send is
rejected while the settings look correctly configured. avinasdemo sat in
exactly this state with 36 asterisks saved.

Three things, on every site, so a deploy fixes it without anyone re-keying a
credential:

  - move the real token out of `__Auth` into the field, unless someone has
    already re-entered a good one by hand, in which case theirs wins;
  - clear the placeholder when there is nothing in `__Auth` to recover, so an
    empty field looks empty instead of set;
  - force the DocField to Data, for sites whose doctype sync was skipped
    because their `modified` was not older than the JSON's.

Recovery is best-effort by design: if the site's encryption_key has been
rotated since the token was saved, the decrypt fails and we clear the
placeholder rather than leave a value that cannot work.
"""

import frappe
from frappe.utils.password import get_decrypted_password, remove_encrypted_password

DOCTYPE = "Sparrow SMS Settings"
FIELDNAME = "token"


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	frappe.db.sql(
		"""
		UPDATE `tabDocField`
		SET fieldtype = 'Data'
		WHERE parent = %(doctype)s AND fieldname = %(fieldname)s AND fieldtype = 'Password'
		""",
		{"doctype": DOCTYPE, "fieldname": FIELDNAME},
	)

	# A Single's __Auth row is keyed by the doctype name, which is also its docname.
	recovered = get_decrypted_password(DOCTYPE, DOCTYPE, FIELDNAME, raise_exception=False)
	stored = frappe.db.get_single_value(DOCTYPE, FIELDNAME)
	is_placeholder = bool(stored) and set(stored) == {"*"}

	if recovered:
		if is_placeholder or not stored:
			frappe.db.set_single_value(DOCTYPE, FIELDNAME, recovered)
		remove_encrypted_password(DOCTYPE, DOCTYPE, FIELDNAME)
	elif is_placeholder:
		frappe.db.set_single_value(DOCTYPE, FIELDNAME, None)

	frappe.clear_cache(doctype=DOCTYPE)
