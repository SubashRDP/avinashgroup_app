def suppress_delete_feed(doc, method=None):
	"""
	Stop deletes from recording a site-wide "Deleted" activity entry.

	Stock Frappe calls `insert_feed(doc)` from `delete_doc` (frappe/model/delete_doc.py:179)
	on every successful delete, for every doctype. It inserts a Comment row with
	comment_type="Deleted", subject "<Doctype> <name>" and the deleter's full name — an
	announcement of the deletion that is scoped to neither the document (it is gone) nor
	any user.

	Frappe's own opt-out is the `no_feed_on_delete` attribute, which `insert_feed` checks
	before doing anything (delete_doc.py:505); the framework sets it on the controllers of
	Communication, File, Comment, DocShare, Deleted Document and Data Import Log. This
	handler sets the same attribute on every doctype, from a wildcard `on_trash` doc_event —
	`on_trash` runs on the very object that is passed to `insert_feed` later in the same
	`delete_doc` call, so the flag is in place by the time it is read.

	Nothing else is affected. The delete itself, `doc.notify_update()` (the realtime list
	refresh), and the Deleted Document snapshot that backs restore all still run. The audit
	trail is unchanged: `add_to_deleted_document` keeps the full document JSON, so who
	deleted what is still answerable from Deleted Document.

	Two paths still write a feed, both harmless:
	  - `DocType` deletes, which take a separate branch that never runs `on_trash`
	    (developer_mode only).
	  - `delete_doc(..., ignore_on_trash=True)`, used only by app uninstall, where
	    `frappe.flags.in_uninstall` already short-circuits `insert_feed`.
	"""
	doc.no_feed_on_delete = True
