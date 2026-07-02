# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Add a covering index on GL Entry for aggregated financial-statement sums.

The Consolidated Financial Statement Hierarchy report computes per-account
balances with a single ``SUM(...) GROUP BY account, company`` query over
GL Entry. Without an index that covers every referenced column, MariaDB has
to read the full clustered rows (~2s for ~500k entries); with it, the query
is an index-only scan in index order (no temp table / filesort) and runs in
a few hundred milliseconds.

Column order matters: (company, account, posting_date) lets the optimizer
prune by company, group without sorting, and evaluate the opening/period
posting-date buckets from the key; the remaining columns are there purely to
keep the scan index-only. Total key size ~2.9KB, under InnoDB's 3072-byte
limit for DYNAMIC row format. Idempotent: skips if the index already exists.
"""

import frappe

INDEX_NAME = "fin_stmt_agg_index"

COLUMNS = [
	"company",
	"account",
	"posting_date",
	"is_cancelled",
	"finance_book",
	"voucher_type",
	"debit",
	"credit",
	"debit_in_account_currency",
	"credit_in_account_currency",
	"account_currency",
]


def execute():
	already_indexed = frappe.db.sql(
		"SHOW INDEX FROM `tabGL Entry` WHERE Key_name = %s", INDEX_NAME
	)
	if already_indexed:
		return

	frappe.db.add_index("GL Entry", COLUMNS, index_name=INDEX_NAME)
