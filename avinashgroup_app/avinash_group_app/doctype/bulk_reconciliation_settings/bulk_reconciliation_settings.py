import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

from erpnext.accounts.doctype.process_payment_reconciliation.process_payment_reconciliation import (
	pause_job_for_doc,
	trigger_job_for_doc,
)

SETTINGS = "Bulk Reconciliation Settings"
ACCOUNTS_SETTINGS = "Accounts Settings"
PPR = "Process Payment Reconciliation"


class BulkReconciliationSettings(Document):
	def validate(self):
		if cint(self.interval_hours) < 1:
			frappe.throw(_("Run Every (Hours) must be at least 1"))

		# Each switch-on starts a new window, so entries from before it stay out.
		# A Stop stays in place until Resume, which also restarts what Stop paused.
		if self.enabled and self.has_value_changed("enabled"):
			self.started_from = now_datetime()


@frappe.whitelist()
def stop_auto_run():
	"""Stop button: stops all reconciliation.

	- the scheduled job does nothing (is_stopped)
	- Queued entries are not started: Auto Reconcile Payments is unticked
	- Running entries are paused; each finishes its current small batch first

	Pressing it again while stopped pauses any entry that started since.
	"""
	check_permission()
	settings = frappe.get_single(SETTINGS)

	if not settings.is_stopped:
		settings.auto_reconcile_was_on = cint(
			frappe.db.get_single_value(ACCOUNTS_SETTINGS, "auto_reconcile_payments")
		)

	# Untick first and commit, so ERPNext's 15-minute job starts nothing new
	# while the Running list below is read.
	frappe.db.set_single_value(ACCOUNTS_SETTINGS, "auto_reconcile_payments", 0)
	frappe.db.commit()

	running = frappe.get_all(PPR, filters={"docstatus": 1, "status": "Running"}, pluck="name", order_by="name")
	for name in running:
		pause_job_for_doc(name)

	paused = names_from_text(settings.paused_by_stop)
	paused += [name for name in running if name not in paused]

	frappe.db.set_single_value(
		SETTINGS,
		{
			"is_stopped": 1,
			"auto_reconcile_was_on": settings.auto_reconcile_was_on,
			"paused_by_stop": "\n".join(paused),
		},
	)
	return _("Stopped. {0} running entries paused. Queued entries will wait until Resume.").format(len(running))


@frappe.whitelist()
def resume_auto_run():
	"""Resume button: undoes Stop.

	- Auto Reconcile Payments is ticked again, only if it was ticked before Stop
	- the entries Stop paused are started again (older Paused entries are left alone)
	- the scheduled job runs again; Started From is not changed, so entries
	  made while stopped are picked up too
	"""
	check_permission()
	settings = frappe.get_single(SETTINGS)
	paused = names_from_text(settings.paused_by_stop)

	resumed = 0
	left_paused = []
	if settings.auto_reconcile_was_on:
		frappe.db.set_single_value(ACCOUNTS_SETTINGS, "auto_reconcile_payments", 1)
		frappe.db.commit()
		for name in paused:
			if frappe.db.get_value(PPR, name, "status") == "Paused":
				trigger_job_for_doc(name)
				# ERPNext queues the job before commit; commit now so the
				# worker reads Running, not the old Paused.
				frappe.db.commit()
				resumed += 1
	else:
		left_paused = paused

	frappe.db.set_single_value(
		SETTINGS,
		{"is_stopped": 0, "auto_reconcile_was_on": 0, "paused_by_stop": ""},
	)

	if left_paused:
		return _(
			"Resumed. Auto Reconcile Payments was off before Stop, so it stays off and these entries stay Paused: {0}"
		).format(", ".join(left_paused))
	return _("Resumed. {0} paused entries started again.").format(resumed)


@frappe.whitelist()
def turn_on_suppliers():
	"""Reconcile Suppliers button: scheduled runs also do suppliers, counting
	supplier invoices and payments made from now on."""
	frappe.has_permission(SETTINGS, "write", throw=True)
	frappe.db.set_single_value(SETTINGS, {"reconcile_suppliers": 1, "suppliers_started_from": now_datetime()})
	return _("Suppliers will be reconciled from the next scheduled run.")


@frappe.whitelist()
def turn_off_suppliers():
	"""Reconciling Suppliers button (when on): scheduled runs stop making supplier batches.
	Supplier entries already Queued or Running are not touched."""
	frappe.has_permission(SETTINGS, "write", throw=True)
	frappe.db.set_single_value(SETTINGS, "reconcile_suppliers", 0)
	return _("Stopped reconciling suppliers. Only customers will be reconciled from the next scheduled run.")


def check_permission():
	frappe.has_permission(SETTINGS, "write", throw=True)
	frappe.has_permission(ACCOUNTS_SETTINGS, "write", throw=True)


def names_from_text(text):
	return [line.strip() for line in (text or "").splitlines() if line.strip()]
