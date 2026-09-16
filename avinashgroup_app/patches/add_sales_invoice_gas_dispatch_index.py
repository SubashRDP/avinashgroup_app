"""Add a (company, posting_date, customer) index on Sales Invoice for Gas Dispatch (Quota).

The report sums a fiscal year of LP Gas quantity for one company. Sales Invoice
ships with single-column indexes only, so the year+company filter could not be
answered from an index and MariaDB read every invoice row (252,088 on mysite1,
~71s per run). With this index, and the report's invoice-first join order, the
same run measured ~27s on the same machine.

Idempotent: skips if the index already exists.
"""

import frappe

INDEX_NAME = "gas_dispatch_company_posting_customer"


def execute():
	already_indexed = frappe.db.sql(
		"SHOW INDEX FROM `tabSales Invoice` WHERE Key_name = %s", INDEX_NAME
	)
	if already_indexed:
		return

	frappe.db.add_index("Sales Invoice", ["company", "posting_date", "customer"], index_name=INDEX_NAME)
