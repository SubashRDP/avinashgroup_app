"""Backfill the is_synced / is_realtime checkboxes on CBMS Bill and CBMS Bill Return.

is_synced falls straight out of sync_status. is_realtime is recovered from the CBMS
Sync Log: the "Synced" log row for a record carries the triggered_from that produced
it, so a bill that reached IRD on the invoice submit is realtime and one that only got
through on a retry or a manual Sync Now is not.

Records synced before the sync log existed, or whose log rows were pruned, keep
is_realtime = 0 — the flag is a claim about how the bill reached IRD, and an unproven
claim must not be made.
"""

import frappe


def execute():
	for doctype in ("CBMS Bill", "CBMS Bill Return"):
		table = f"tab{doctype}"

		frappe.db.sql(
			f"""
			UPDATE `{table}`
			SET is_synced = CASE WHEN sync_status = 'Synced' THEN 1 ELSE 0 END,
			    is_realtime = 0
			"""
		)

		# Latest Synced log row per record wins: a record can be logged more than once
		# (Held, Failed, then Synced), and only the one that actually landed counts.
		frappe.db.sql(
			f"""
			UPDATE `{table}` AS doc
			JOIN (
				SELECT log.cbms_ref, log.triggered_from
				FROM `tabCBMS Sync Log` AS log
				JOIN (
					SELECT cbms_ref, MAX(creation) AS creation
					FROM `tabCBMS Sync Log`
					WHERE operation = 'Synced' AND cbms_ref_doctype = %(doctype)s
					GROUP BY cbms_ref
				) AS latest
				  ON latest.cbms_ref = log.cbms_ref AND latest.creation = log.creation
				WHERE log.operation = 'Synced' AND log.cbms_ref_doctype = %(doctype)s
			) AS synced_log
			  ON synced_log.cbms_ref = doc.name
			SET doc.is_realtime = 1
			WHERE doc.sync_status = 'Synced' AND synced_log.triggered_from = 'Submit'
			""",
			{"doctype": doctype},
		)
