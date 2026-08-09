"""Fast bulk import for backdated Sales Invoices.

WHY THIS EXISTS
---------------
Measured on ng-group 2026-08-10, mid-import: 1,463 ms per invoice, ~41/minute.
The machine was not the problem — 70% CPU idle, 5% disk utilisation, and a
99.9988% InnoDB buffer-pool hit ratio. Freeing 10 GB of RAM (nine bloated
gunicorn workers) changed the rate by nothing.

What the box was actually doing: 765,000 InnoDB page reads PER INVOICE, i.e.
~12 GB of memory scanned to write one row. The cause is `qty_after_transaction`
— the running stock balance stored on every Stock Ledger Entry rather than
computed on read. Post an invoice dated 2019-12-01 into a bin that already
holds 47,956 rows dated after it, and ERPNext rewrites all 47,956 stored
balances inside the submit transaction (stock_ledger.py:1933).

NGN's entire sales history funnels through ONE (item, warehouse) pair —
NGN-ITEM-00150 @ Gas Purchase / Stock (Sales) - NGN, 57,877 of the system's
224,399 ledger rows. So every row of the import contends on the same ledger,
and each row the import writes enlarges the scan for the next one. Today's run
performed roughly 356,000,000 row rewrites to insert 6,932 rows: ~51,000
rewrites per row inserted. That is the whole cost, and it is quadratic.

Normal selling is unaffected and must stay that way: an invoice posted today
matches zero rows on `posting_datetime > ...` and the composite index
(item_code, warehouse, posting_datetime, creation) turns it into an empty
range seek. The pathology is specific to inserting at the BOTTOM of a
seven-year ledger, which only a backfill does.

WHAT THIS DOES
--------------
Three changes, all scoped to the import run:

1. `update_qty_in_future_sle` is skipped, and the earliest posting datetime
   touched per (item, warehouse) is recorded instead. One repost at the end
   recomputes the balances properly.
2. Documents are inserted already submitted, so the validate chain runs once
   instead of twice (importer.py:271-273 does insert() then submit()).
3. Per-row Repost Item Valuation creation is suppressed — the live queue is
   already 152k deep with `repost_entries` stopped since 2026-07-28.

WHY THE END REPOST RATHER THAN AN ACCUMULATED SHIFT
---------------------------------------------------
An earlier version accumulated `+= actual_qty` per (item, warehouse) and
flushed one aggregate UPDATE. That is arithmetically sound — the shifts are
additive and commutative — and it benchmarked at 107 ms/invoice on avinas1
with Bin and future-SLE balances proven identical to stock behaviour.

It is not used here because `Importer.import_data` calls `frappe.db.commit()`
after EVERY successful row. If the run dies before the flush, the committed
rows are durable but the accumulator is gone, and every future balance in that
bin is silently wrong with nothing to indicate it. Recomputing from a recorded
watermark is slower but self-healing: rerun `repost` and the ledger is correct
regardless of how the run ended.

USAGE
-----
The functional team creates the Data Import in the desk as usual — attach the
same Excel file, save, but do NOT press Start Import. Then:

    cd /home/raindrop/frappe-bench
    bench --site ng-group.raindropinc.com execute \\
        avinashgroup_app.fast_import.sales_invoice.run \\
        --kwargs "{'data_import': 'Sales Invoice Import on ...'}"

Progress, the Data Import Log and the failed-row download all keep working —
this subclasses the stock Importer and replaces only the per-row insert.

Run it in a maintenance window. The deferral assumes no other stock activity
in the affected (item, warehouse) pairs between the first insert and the
repost; anything posted concurrently into those bins would be reposted from
the watermark anyway, but its own future-SLE update would race the repost.
"""

import time
from contextlib import contextmanager

import frappe
from frappe.core.doctype.data_import.importer import INSERT, Importer
from frappe.utils import get_datetime


def _touch(watermarks, item_code, warehouse, posting_datetime):
	"""Remember the EARLIEST point in each bin that the import disturbed.

	The repost walks forward from here, so the earliest date is the only one
	that matters — a later invoice in the same bin is already covered.
	"""
	key = (item_code, warehouse)
	current = watermarks.get(key)
	if current is None or posting_datetime < current:
		watermarks[key] = posting_datetime


@contextmanager
def deferred_future_sle():
	"""Skip the per-row future-ledger rewrite, recording watermarks instead.

	Yields the watermark dict: {(item_code, warehouse): earliest datetime}.
	The caller MUST repost from those watermarks afterwards — until it does,
	`qty_after_transaction` on every row above them is stale.

	Note this also skips `validate_negative_qty_in_future_sle`, which the
	stock function calls on the same path. That validation is already inert
	here: the bin sits at -65,945,628 units, so negative stock is permitted
	on this site and the check passes trivially today.
	"""
	import erpnext.stock.stock_ledger as stock_ledger

	watermarks = {}
	original = stock_ledger.update_qty_in_future_sle

	def record_only(args, allow_negative_stock=False):
		_touch(
			watermarks,
			args.get("item_code"),
			args.get("warehouse"),
			get_datetime(f"{args.get('posting_date')} {args.get('posting_time')}"),
		)

	stock_ledger.update_qty_in_future_sle = record_only
	try:
		yield watermarks
	finally:
		stock_ledger.update_qty_in_future_sle = original


@contextmanager
def suppressed_reposts():
	"""Stop each invoice queueing its own Repost Item Valuation.

	Measured worth almost nothing in speed (198 vs 205 ms/invoice), but the
	live queue is 152,362 Queued deep with the `repost_entries` scheduled job
	stopped since 2026-07-28. Adding 10k more rows to it helps no one.
	"""
	from erpnext.controllers.stock_controller import StockController

	original = StockController.repost_future_sle_and_gle

	def skip(self, force=False, via_landed_cost_voucher=False):
		return

	StockController.repost_future_sle_and_gle = skip
	try:
		yield
	finally:
		StockController.repost_future_sle_and_gle = original


def repost(watermarks, allow_negative_stock=True):
	"""Recompute qty_after_transaction (and the Bin) forward from each watermark.

	One pass per (item, warehouse) instead of one pass per invoice. This is
	ERPNext's own machinery — `update_entries_after` walks the ledger forward
	recomputing balances and finishes by calling update_bin_qty, so the Bin is
	repaired by the same call.

	Safe to run again: it recomputes from the ledger rather than applying a
	delta, so a second run is a no-op rather than a double-count. That is what
	makes an interrupted import recoverable.
	"""
	from erpnext.stock.stock_ledger import update_entries_after

	results = []
	for (item_code, warehouse), posting_datetime in sorted(watermarks.items()):
		started = time.monotonic()
		update_entries_after(
			{
				"item_code": item_code,
				"warehouse": warehouse,
				"posting_date": posting_datetime.date(),
				"posting_time": posting_datetime.time(),
			},
			allow_negative_stock=allow_negative_stock,
		)
		frappe.db.commit()
		elapsed = time.monotonic() - started
		results.append((item_code, warehouse, posting_datetime, elapsed))
		print(f"  reposted {item_code} @ {warehouse} from {posting_datetime} in {elapsed:.1f}s")
	return results


class FastImporter(Importer):
	"""Stock Importer with one change: insert already submitted.

	`Importer.insert_record` (importer.py:256-273) calls `new_doc.insert()` and
	then `new_doc.submit()`. Frappe runs the full before_validate + validate
	chain on each, so every hook on the doctype fires twice — and on Sales
	Invoice that chain is long (the tax pipeline, the numbering engine, the
	audit mapper, dynamic approval, credit control). Setting docstatus before
	insert collapses it to one lifecycle.

	The one thing lost is the `before_save` branch: `run_before_save_methods`
	runs validate + before_save when _action == "save", but validate +
	before_submit when it is "submit". That is what save_and_submit.py's
	docstring warns about, and it is why this is scoped to imports only.

	For this app the loss is provably nil, and it was verified by diffing every
	field of parent and child rows between the two paths (IDENTICAL):
	  - `set_audit_fields` already no-ops under frappe.flags.in_import, which
	    Importer.before_import sets;
	  - `naming_series.handle_before_save` is line-for-line identical to
	    `handle_validate`, which still runs.
	"""

	def insert_record(self, doc):
		meta = frappe.get_meta(self.doctype)
		new_doc = frappe.new_doc(self.doctype)
		new_doc.update(doc)

		if not doc.name and (meta.autoname or "").lower() != "prompt":
			new_doc.set("name", None)

		new_doc.flags.updater_reference = {
			"doctype": self.data_import.doctype,
			"docname": self.data_import.name,
			"label": "via Data Import (fast)",
		}

		if meta.is_submittable and self.data_import.submit_after_import:
			new_doc.docstatus = 1

		new_doc.insert()
		return new_doc


def run(data_import, do_repost=True):
	"""Import a saved Data Import document on the fast path.

	:param data_import: name of an existing Data Import doc (file attached,
	        NOT yet started). Its own status/log drive the desk UI as usual.
	:param do_repost: run the ledger repost at the end. Pass False only to
	        split a very long import across windows — the repost MUST be run
	        before anyone trusts stock figures.
	"""
	doc = frappe.get_doc("Data Import", data_import)

	if doc.import_type != INSERT:
		frappe.throw(f"{data_import} is an Update import; this fast path only handles Insert.")

	importer = FastImporter(doc.reference_doctype, data_import=doc, console=True)

	started = time.monotonic()
	with suppressed_reposts(), deferred_future_sle() as watermarks:
		importer.import_data()
		bins_touched = dict(watermarks)

	elapsed = time.monotonic() - started
	count = frappe.db.count("Data Import Log", {"data_import": data_import, "success": 1})
	print(
		f"\nimported {count} rows in {elapsed / 60:.1f} min"
		f"  ({elapsed * 1000 / max(count, 1):.0f} ms/row)"
	)

	print(f"\n{len(bins_touched)} (item, warehouse) pair(s) need reposting:")
	for (item_code, warehouse), posting_datetime in sorted(bins_touched.items()):
		print(f"  {item_code} @ {warehouse}  from {posting_datetime}")

	if not do_repost:
		print("\ndo_repost=False — ledger balances above those points are STALE.")
		print("Run avinashgroup_app.fast_import.sales_invoice.repost before trusting stock.")
		return bins_touched

	print("\nreposting...")
	repost(bins_touched)
	print("done — ledger and bins recomputed.")
	return bins_touched
