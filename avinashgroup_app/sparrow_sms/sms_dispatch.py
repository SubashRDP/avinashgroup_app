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

Every attempt — including the ones that never reach the gateway, because the
customer has no phone number on file or the network was down — lands as one
`Sparrow SMS Log` row carrying the customer, the time, the reference document
(the Sales Invoice) and the exact text sent. That row is the answer to "did
this customer get their invoice SMS", and it is written whether the answer is
yes or no.
"""

import re

import frappe
import requests
from frappe.utils import cint, now_datetime

from avinashgroup_app.sparrow_sms.doctype.sparrow_sms_log.sparrow_sms_log import (
	create_log,
	update_log,
)

DEFAULT_SPARROW_SMS_URL = "https://api.sparrowsms.com/v2/sms/"
SEND_TIMEOUT = 5

CACHE_KEY_DOCTYPES = "sparrow_sms_rule_doctypes"
CACHE_KEY_RULES = "sparrow_sms_rules::"

# Sparrow has been seen to name these differently across accounts, and a log
# that quietly drops the credit count is worse than one that tries a few keys.
MESSAGE_ID_KEYS = ("message_id", "msg_id", "id")
CREDIT_CONSUMED_KEYS = ("credit_consumed", "credits_consumed", "consumed")
CREDIT_REMAINING_KEYS = ("credit_available", "credit_remaining", "remaining_credit", "balance")

# Small Text columns; the gateway occasionally returns an HTML error page.
MAX_STORED_RESPONSE = 2000

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


def _first(payload, keys):
	for key in keys:
		if payload.get(key) not in (None, ""):
			return payload[key]
	return None


def _call_gateway(receiver, message):
	"""One HTTP attempt. Returns (ok, fields to record on the log row).

	Never raises: an unreachable gateway is a failed SMS, not a failed invoice.
	"""
	result = {}

	try:
		settings = frappe.get_cached_doc("Sparrow SMS Settings")
		response = requests.post(
			settings.api_url or DEFAULT_SPARROW_SMS_URL,
			data={
				"token": settings.token,
				"from": settings.sender_identity,
				"to": receiver,
				"text": message,
			},
			timeout=SEND_TIMEOUT,
		)
	except Exception as exception:
		# The traceback is worth keeping for a transport failure — it separates
		# a DNS problem from a timeout from a TLS error.
		frappe.log_error(
			title="Sparrow SMS: could not reach the gateway",
			message=frappe.get_traceback(),
		)
		result["error"] = f"Could not reach Sparrow: {exception}"[:500]
		return False, result

	result["gateway_response"] = (response.text or "")[:MAX_STORED_RESPONSE]

	try:
		payload = response.json()
	except Exception:
		payload = None
	if not isinstance(payload, dict):
		payload = {}

	message_id = _first(payload, MESSAGE_ID_KEYS)
	if message_id is not None:
		result["message_id"] = str(message_id)[:140]
	result["credit_consumed"] = cint(_first(payload, CREDIT_CONSUMED_KEYS))
	result["credit_remaining"] = cint(_first(payload, CREDIT_REMAINING_KEYS))

	ok = response.status_code == 200 and payload.get("response_code") == 200
	if not ok:
		result["error"] = _describe_rejection(response, payload)

	return ok, result


def _describe_rejection(response, payload):
	"""One line an operator can act on, from whatever Sparrow sent back."""
	parts = [f"HTTP {response.status_code}"]

	code = payload.get("response_code")
	if code is not None:
		parts.append(f"response_code {code}")

	detail = payload.get("response") or payload.get("message")
	if detail:
		parts.append(str(detail))
	elif response.text:
		parts.append(response.text.strip()[:200])

	return " — ".join(parts)[:500]


def send_sms(receiver, message, reference=None, log=None, context=None):
	"""One direct attempt against Sparrow, always logged. Never raises.

	`log` names an existing `Sparrow SMS Log` row to record the outcome on —
	that is how a queued retry updates the row its first attempt created instead
	of writing a second one. Without it a row is created here, which is the path
	the Send Test SMS button and the Sales Invoice SMS Test page take.
	"""
	# Normalise here rather than at each call site: this is the one choke point
	# every send passes through, and it is also what gets written to the log, so
	# the log records the number actually dialled.
	raw = receiver
	receiver = normalize_mobile(receiver)

	context = dict(context or {})
	context.setdefault("raw_mobile_no", str(raw or "")[:140])
	context.setdefault("message", message)
	context["mobile_no"] = receiver

	if not log:
		log = create_log(status="Queued", **context)

	if not receiver:
		update_log(
			log,
			status="Failed",
			sent_at=now_datetime(),
			error=f"No digits in the phone number {raw!r} — nothing to dial.",
		)
		return False

	attempts = cint(frappe.db.get_value("Sparrow SMS Log", log, "attempts")) if log else 0
	ok, result = _call_gateway(receiver, message)

	update_log(
		log,
		status="Sent" if ok else "Failed",
		sent_at=now_datetime(),
		attempts=attempts + 1,
		**result,
	)
	return ok


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Post-commit send
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _process_after_commit(context, message, reference):
	"""Log the attempt, then make it. Runs after the document's COMMIT.

	Everything here runs in a fresh transaction that nothing else will commit,
	and would be discarded at teardown — so each step commits explicitly. The
	log row is committed *before* the gateway call so that a message the
	gateway hangs on still leaves a Queued row behind, and so that the naming
	series lock is not held across a five-second HTTP request.
	"""
	try:
		error = context.pop("error", None)
		log = create_log(status="Failed" if error else "Queued", error=error, **context)
		frappe.db.commit()

		if error:
			# Nothing to dial — the row is the whole point of this branch.
			return

		# The raw number, not the normalised one: send_sms normalises again
		# (idempotently), and if there is nothing dialable in it the error it
		# writes then names what the document actually held.
		receiver = context.get("raw_mobile_no")

		if send_sms(receiver, message, reference=reference, log=log):
			return

		try:
			frappe.enqueue(
				"avinashgroup_app.sparrow_sms.sms_dispatch.send_sms",
				queue="default",
				timeout=60,
				receiver=receiver,
				message=message,
				reference=reference,
				log=log,
			)
		except Exception:
			frappe.log_error(
				title=f"Sparrow SMS: fallback enqueue failed for {reference}",
				message=frappe.get_traceback(),
			)
	except Exception:
		frappe.log_error(
			title=f"Sparrow SMS: dispatch failed after commit for {reference}",
			message=frappe.get_traceback(),
		)
	finally:
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
	"""First recipient path that yields a value wins. Returns (value, path).

	The path comes back with the value because the log records it: when an SMS
	goes to a stale number, the next question is always which field it was read
	from.

	Test Mobile No deliberately has no say here. It used to short-circuit this
	function, which meant every automatic send went to one handset while the log
	still read as a success — a redirect indistinguishable from working. It now
	belongs to the Send Test SMS button on Sparrow SMS Settings and nothing else.
	"""
	for path in rule.get("recipient_paths") or []:
		value = _resolve_path(doc, path)
		if value:
			return value, path

	return None, None


# Doctype-agnostic, in the order a document is most likely to carry them. The
# link is what makes Party a filterable dropdown rather than a typed-in string;
# the name is what keeps the list readable, because customers here are named by
# series (NGI-CUS-00200) and a link column would show only that.
PARTY_FIELDS = (
	("Customer", "customer", "customer_name"),
	("Supplier", "supplier", "supplier_name"),
	("Employee", "employee", "employee_name"),
	("Lead", "lead", "lead_name"),
)


def _party(doc):
	"""Whoever the document is about: (party_type, party, party_name).

	Sales Invoice gives ("Customer", "NGI-CUS-00200", "A M Kirana Store").
	"""
	# Payment Entry and friends already say who the party is, and say it in the
	# same two fields this log uses.
	if doc.get("party_type") and doc.get("party"):
		party_type, party = doc.get("party_type"), doc.get("party")
		name = doc.get("party_name") or frappe.db.get_value(
			party_type, party, frappe.get_meta(party_type).get_title_field()
		)
		return party_type, party, str(name or party)[:140]

	for party_type, link_field, name_field in PARTY_FIELDS:
		party = doc.get(link_field)
		if party:
			return party_type, party, str(doc.get(name_field) or party)[:140]

	# No party link to be had — fall back to whatever the document calls itself.
	for fieldname in ("customer_name", "supplier_name", "employee_name", "full_name", "title"):
		value = doc.get(fieldname)
		if value:
			return None, None, str(value)[:140]

	return None, None, None


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

			message = frappe.render_template(
				rule.get("message_template") or "", {"doc": _NoNulls(doc)}
			)
			if not message.strip():
				continue

			receiver, path = _resolve_recipient(rule, doc)

			party_type, party, party_name = _party(doc)

			context = {
				"sent_via": "Automatic",
				"reference_doctype": doc.doctype,
				"reference_name": doc.name,
				"company": doc.get("company"),
				"party_type": party_type,
				"party": party,
				"party_name": party_name,
				"notification_rule": rule["name"],
				"recipient_field": path,
				"raw_mobile_no": str(receiver or "")[:140],
				"mobile_no": normalize_mobile(receiver),
				"message": message,
			}

			if not receiver:
				# Logged rather than dropped: "this customer has no phone number
				# on file" is the single most common reason an invoice SMS never
				# arrives, and it has to be visible next to the ones that did.
				context["error"] = (
					f"No phone number could be read from {doc.doctype} {doc.name}. "
					f"Rule {rule['name']} tried: {', '.join(rule.get('recipient_paths') or []) or '(none configured)'}."
				)

			reference = f"{doc.name} ({rule['name']})"
			frappe.db.after_commit.add(
				lambda c=context, m=message, ref=reference: _process_after_commit(c, m, ref)
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
