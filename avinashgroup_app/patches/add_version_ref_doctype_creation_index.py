import frappe


def execute():
	"""Index tabVersion(ref_doctype, creation).

	The Invoice Activity Report filters Version rows by
	`ref_doctype='Sales Invoice' AND creation BETWEEN ...`. The existing
	(ref_doctype, docname) index matches ~every row (almost all versions are Sales
	Invoice versions), so the creation range was resolved by scanning the whole
	table (~200k+ rows) on every run. A composite index on (ref_doctype, creation)
	turns that into a range lookup.
	"""
	frappe.db.add_index("Version", ["ref_doctype", "creation"], index_name="ref_doctype_creation_index")
