# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""One row per physical print of a Sales Invoice — who printed which copy, when.

Rows are inserted only by print_count.before_print (server-side, on an actual
print — never on preview). Together with the custom_print_count counter this is
the IRD-required print audit trail; the Invoice Activity Report renders these
rows as "Printed" events.
"""

from frappe.model.document import Document


class SalesInvoicePrintLog(Document):
	pass
