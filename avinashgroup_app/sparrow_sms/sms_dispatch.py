"""Generic, config-driven SMS dispatch via Sparrow SMS.

Which doctypes send an SMS, on which event, to whom, and with what text is
defined entirely by `SMS Notification Rule` records — nothing here is
doctype-specific.

The handlers below are registered on `"*"` in hooks.py, so they run on every
document event in the system. Following the same discipline as
`custom_code/dynamic_approval.py`, the first thing each one does is a cached,
usually DB-free check that this doctype has any rule at all; unconfigured
doctypes cost one cache read and return.

Non-negotiable rule, same as CBMS/sales_invoice_hooks.py: nothing here may ever
block or fail the document it is attached to. Every handler is wrapped, the
HTTP call runs only after the transaction commits, and a failed direct attempt
falls back to the background queue.
"""

import re

import frappe
import requests
from frappe.core.doctype.sms_settings.sms_settings import create_sms_log

DEFAULT_SPARROW_SMS_URL = "https://api.sparrowsms.com/v2/sms/"
SEND_TIMEOUT = 5

CACHE_KEY_DOCTYPES = "sparrow_sms_rule_doctypes"
CACHE_KEY_RULES = "sparrow_sms_rules::"

RULE_FIELDS = (
	"name",
	"document_type",
	"event",
	"company",
	"condition",
	"message_template",
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Transport
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def normalize_mobile(value):
	"""Bare digits, Nepali country code dropped. Empty string if nothing usable.

	Numbers arrive as operators typed them into Address: tab- and space-padded,
	or written "984-5900625". Sparrow rejects anything that is not bare digits,
	so the raw value fails with a bare `1007` that reads like a bad number.
	"""
	digits = re.sub(r"\D", "", str(value or ""))
	if len(digits) == 13 and digits.startswith("977"):
		digits = digits[3:]
	return digits


def send_sms(receiver, message, reference=None):
	"""One direct attempt against Sparrow. Never raises."""
	# Normalise here rather than at each call site: this is the one choke point
	# every send passes through, and it is also what gets written to SMS Log,
	# so the log records the number actually dialled.
	receiver = normalize_mobile(receiver)
	if not receiver:
		frappe.log_error(
			title=f"Sparrow SMS: no usable number for {reference}",
			message="Recipient contained no digits after normalisation.",
		)
		return False

	try:
		settings = frappe.get_cached_doc("Sparrow SMS Settings")
		api_url = settings.api_url or DEFAULT_SPARROW_SMS_URL
		response = requests.post(
			api_url,
			data={
				"token": settings.token,
				"from": settings.sender_identity,
				"to": receiver,
				"text": message,
			},
			timeout=SEND_TIMEOUT,
		)
		ok = response.status_code == 200 and response.json().get("response_code") == 200
	except Exception:
		frappe.log_error(
			title=f"Sparrow SMS: send failed for {reference}",
			message=frappe.get_traceback(),
		)
		return False

	create_sms_log(
		{"message": message.encode("utf-8"), "receiver_list": [receiver]},
		[receiver] if ok else [],
	)
	if not ok:
		frappe.log_error(
			title=f"Sparrow SMS: gateway rejected send for {reference}",
			message=response.text,
		)
	return ok


def _first_send_after_commit(receiver, message, reference):
	try:
		if send_sms(receiver, message, reference=reference):
			return
		try:
			frappe.enqueue(
				"avinashgroup_app.sparrow_sms.sms_dispatch.send_sms",
				queue="default",
				timeout=60,
				receiver=receiver,
				message=message,
				reference=reference,
			)
		except Exception:
			frappe.log_error(
				title=f"Sparrow SMS: fallback enqueue failed for {reference}",
				message=frappe.get_traceback(),
			)
	finally:
		# This runs from frappe.db.after_commit, i.e. the request's COMMIT has
		# already happened. The SMS Log row written by send_sms (and any error
		# logged along the way) therefore sits in a fresh transaction that
		# nothing else will commit, and is discarded at teardown — the send goes
		# out leaving no trace. Commit it explicitly.
		try:
			frappe.db.commit()
		except Exception:
			pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Rule lookup  — cached, because "*" hooks run on every save
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _configured_doctypes():
	"""Set of doctypes that have at least one enabled rule.

	This is the gate that keeps the "*" hooks cheap. Invalidated by
	`SMS Notification Rule.on_update` / `on_trash`.
	"""
	cached = frappe.cache().get_value(CACHE_KEY_DOCTYPES)
	if cached is not None:
		return set(cached)

	try:
		doctypes = [
			r.document_type
			for r in frappe.get_all(
				"SMS Notification Rule",
				filters={"enabled": 1},
				fields=["document_type"],
				distinct=True,
			)
		]
	except Exception:
		# The table does not exist yet — first install, or a migrate that is
		# still creating it while "*" hooks already fire. Do not cache this.
		return set()

	frappe.cache().set_value(CACHE_KEY_DOCTYPES, doctypes)
	return set(doctypes)


def _rules_for(doctype, event):
	key = f"{CACHE_KEY_RULES}{doctype}::{event}"
	cached = frappe.cache().get_value(key)
	if cached is not None:
		return cached

	rules = frappe.get_all(
		"SMS Notification Rule",
		filters={"enabled": 1, "document_type": doctype, "event": event},
		fields=list(RULE_FIELDS),
	)

	# Child rows in one query, kept in grid order — the fallback chain depends on it.
	if rules:
		paths = frappe.get_all(
			"SMS Recipient Field",
			filters={"parent": ("in", [r["name"] for r in rules]), "parenttype": "SMS Notification Rule"},
			fields=["parent", "recipient_field"],
			order_by="parent asc, idx asc",
		)
		by_parent = {}
		for row in paths:
			by_parent.setdefault(row["parent"], []).append(row["recipient_field"])
		for rule in rules:
			rule["recipient_paths"] = by_parent.get(rule["name"], [])

	frappe.cache().set_value(key, rules)
	return rules


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Evaluation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class _NoNulls:
	"""Attribute proxy that renders an unset field as empty, never "None".

	Jinja prints a Python None as the literal "None", so a template naming a
	field the document happens not to carry produces "your invoice None of Rs.
	None". Templates are written by operators against fields they believe exist,
	and an SMS is not the place to discover otherwise.

	Only used for rendering. Conditions keep the real document, where None and
	False have to mean what they say.
	"""

	def __init__(self, doc):
		self._doc = doc

	def __getattr__(self, key):
		value = getattr(self._doc, key, None)
		return "" if value is None else value

	def __getitem__(self, key):
		return self.__getattr__(key)


def _condition_passes(rule, doc):
	condition = (rule.get("condition") or "").strip()
	if not condition:
		return True
	try:
		return bool(frappe.safe_eval(condition, None, {"doc": doc, "frappe": frappe._dict()}))
	except Exception:
		frappe.log_error(
			title=f"Sparrow SMS: bad condition on rule {rule.get('name')}",
			message=frappe.get_traceback(),
		)
		return False


def _resolve_path(doc, path):
	"""Read one recipient path off `doc`.

	`contact_mobile`      -> doc.contact_mobile
	`customer.mobile_no`  -> Customer[doc.customer].mobile_no
	"""
	path = (path or "").strip()
	if not path:
		return None

	if "." not in path:
		return doc.get(path)

	link_field, leaf = path.split(".", 1)
	link_value = doc.get(link_field)
	if not link_value:
		return None

	df = doc.meta.get_field(link_field)
	if not df:
		return None

	# On a Dynamic Link, `options` names the field holding the target doctype
	# (Payment Entry.party -> party_type), not the doctype itself.
	target_doctype = doc.get(df.options) if df.fieldtype == "Dynamic Link" else df.options
	if not target_doctype:
		return None

	if not frappe.get_meta(target_doctype).has_field(leaf):
		return None

	return frappe.db.get_value(target_doctype, link_value, leaf)


def _resolve_recipient(rule, doc):
	"""First recipient path that yields a value wins.

	Test Mobile No deliberately has no say here. It used to short-circuit this
	function, which meant every automatic send went to one handset while the log
	still read as a success — a redirect indistinguishable from working. It now
	belongs to the Send Test SMS button on Sparrow SMS Settings and nothing else.
	"""
	for path in rule.get("recipient_paths") or []:
		value = _resolve_path(doc, path)
		if value:
			return value

	return None


def _dispatch(doc, event):
	# Never message anyone because of a migrate, an install, a patch or a bulk
	# import. A 1M-row Sales Invoice import would otherwise queue 1M SMS.
	if (
		frappe.flags.in_migrate
		or frappe.flags.in_install
		or frappe.flags.in_patch
		or frappe.flags.in_import
		or frappe.flags.in_test
	):
		return

	if doc.doctype not in _configured_doctypes():
		return

	if not frappe.db.get_single_value("Sparrow SMS Settings", "enabled"):
		return

	for rule in _rules_for(doc.doctype, event):
		try:
			if rule.get("company") and doc.get("company") != rule["company"]:
				continue

			if not _condition_passes(rule, doc):
				continue

			receiver = _resolve_recipient(rule, doc)
			if not receiver:
				frappe.log_error(
					title=f"Sparrow SMS: no mobile number for {doc.name}",
					message=f"Rule {rule['name']} matched but no recipient could be resolved.",
				)
				continue

			message = frappe.render_template(
				rule.get("message_template") or "", {"doc": _NoNulls(doc)}
			)
			if not message.strip():
				continue

			reference = f"{doc.name} ({rule['name']})"
			frappe.db.after_commit.add(
				lambda r=receiver, m=message, ref=reference: _first_send_after_commit(r, m, ref)
			)
		except Exception:
			frappe.log_error(
				title=f"Sparrow SMS: rule {rule.get('name')} failed for {doc.name}",
				message=frappe.get_traceback(),
			)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Doc event handlers  — registered on "*"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def on_submit(doc, method=None):
	_dispatch(doc, "On Submit")


def on_cancel(doc, method=None):
	_dispatch(doc, "On Cancel")


def after_insert(doc, method=None):
	_dispatch(doc, "After Insert")


def on_update(doc, method=None):
	_dispatch(doc, "On Update")
