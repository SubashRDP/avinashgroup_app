import frappe


def patch_repost_valuation_disable_error_email():
	"""
	Patch `erpnext.stock.doctype.repost_item_valuation.repost_item_valuation.get_recipients`
	so it returns no recipients.

	`get_recipients` is used only by `notify_error_to_stock_managers`, which sends the
	"Error while reposting item valuation" email when a repost fails. With no recipients,
	`frappe.sendmail` becomes a no-op, so the email is never sent. The repost still marks
	itself Failed and records the traceback in its error_log — only the email is suppressed.

	The repost runs in a background job, so this is wired through `before_job` (and
	`before_request` for the desk-triggered path).
	"""
	from erpnext.stock.doctype.repost_item_valuation import repost_item_valuation as riv

	if getattr(riv, "_avinashgroup_repost_error_email_disabled", False):
		return

	def get_recipients():
		return []

	riv.get_recipients = get_recipients
	riv._avinashgroup_repost_error_email_disabled = True
