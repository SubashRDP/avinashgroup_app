# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

"""One portal login per dealer, linked to every customer record the dealer buys under.

Why this exists
---------------
Every portal page (Place Order, Customer Statement, /me, notifications,
announcements) finds "which customers is this login" through ERPNext's
`Portal User` child table on Customer. Stock ERPNext only lets you edit that
table from the Customer side, so giving one dealer access meant: create a
User by hand, set Website User, add the Customer role, then open *each* of the
dealer's customer records (a dealer often has two or three, under different
names in different locations) and add the same user to its Portal Users tab,
then tell them a password. On avinas1 3 of 3,999 customers had ever been set up.

This record turns that around: one record per *login*, with a table of the
customers it covers. Saving it creates or updates the User and writes the
Portal User rows; removing a customer from the table removes its row.

Passwords
---------
Frappe keeps only a one-way hash (in `__Auth`), so nobody — staff, admin, us —
can ever read a password back. `issue_password` generates a random one, sets
it, and texts it to the dealer through Sparrow SMS. The Sparrow SMS Log row is
written with the password masked. Only when the SMS could not be sent (SMS
off, no credit, gateway down, or "Send Password by SMS" unticked) is the
password shown once to the operator so they can hand it over.

The dealer logs in with their mobile number: that needs System Settings
"Allow Login using Mobile Number" (patch `enable_login_with_mobile_number`).

Deliberately NOT done here
--------------------------
- The Customer documents are never saved. Portal User rows are inserted and
  deleted directly, so Customer validations (credit control, duplicate-party
  checks, ...) on old customer data can never block giving someone access.
- One customer belongs to at most one login. A second login for the same
  customer is refused with the name of the login that already has it — two
  people sharing a customer's statement should be a deliberate choice, not an
  accident of typing the customer into two records.
- A staff (System User) account is never turned into a portal login.
- Deleting this record disables the User and removes its Portal User rows; the
  User itself is kept so its history (orders placed, logins) still resolves.
"""

import re
import secrets

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_url, now_datetime
from frappe.utils.password import update_password

from avinashgroup_app.sparrow_sms.sms_dispatch import normalize_mobile, send_sms

# Nepali mobile numbers: 10 digits starting 9 (97x/98x/96x). Landlines can't
# receive the password SMS, so they are refused as a login.
NEPALI_MOBILE_RE = re.compile(r"^9\d{9}$")

# Frappe's User is keyed by email. Dealers mostly have none, so a placeholder
# under a reserved TLD (RFC 2606 ".invalid" can never resolve) is used; the
# dealer never types it — they log in with the mobile number.
PLACEHOLDER_EMAIL_DOMAIN = "portal.invalid"

PORTAL_ROLE = "Customer"  # ERPNext's portal role; desk_access=0

# Password shape "Kemaro-4827": easy to read out over the phone or type on a
# keypad, no look-alike letters, ~36 bits — well above the site's password
# policy (score 2). Consonants exclude l/q/x/c, vowels exclude o-vs-0 risk by
# keeping digits in their own block.
_CONSONANTS = "bdfghjkmnprstvwz"
_VOWELS = "aeiu"

SMS_TEMPLATE = (
	"Avinash Group customer portal\n"
	"Login: {url}\n"
	"Mobile: {mobile}\n"
	"Password: {password}"
)
PASSWORD_MASK = "********"


class CustomerPortalAccess(Document):
	@property
	def last_login(self):
		return frappe.db.get_value("User", self.user, "last_login") if self.user else None

	def onload(self):
		self.set_onload("login_with_mobile", login_with_mobile_enabled())

	# ── validation ──────────────────────────────────────────────────────────

	def autoname(self):
		# Named by the mobile number, normalised first so "984-1234567" and
		# "9841234567" can't become two records. Runs before validate.
		self._validate_mobile()
		self.name = self.mobile_no

	def validate(self):
		self._validate_mobile()
		if self.email:
			self.email = self.email.strip().lower()

		# User first: the Portal Users check below must know which login is ours.
		self._resolve_user()
		self._validate_customers()

	def _validate_mobile(self):
		self.mobile_no = normalize_mobile(self.mobile_no)
		if not NEPALI_MOBILE_RE.match(self.mobile_no or ""):
			frappe.throw(
				_("Mobile No must be a 10-digit Nepali mobile number starting with 9, e.g. 9841234567."),
				title=_("Invalid Mobile No"),
			)

	def _validate_customers(self):
		seen = set()
		for row in self.customers:
			if row.customer in seen:
				frappe.throw(_("Row {0}: {1} is listed twice.").format(row.idx, frappe.bold(row.customer)))
			seen.add(row.customer)

		if not seen:
			return

		# Already in another login's record?
		other = frappe.get_all(
			"Customer Portal Access Customer",
			filters={"parenttype": self.doctype, "parent": ["!=", self.name or ""], "customer": ["in", list(seen)]},
			fields=["customer", "parent"],
		)
		for row in other:
			frappe.throw(
				_("{0} already has portal access through login {1}. Remove it there first.").format(
					frappe.bold(row.customer), frappe.bold(row.parent)
				),
				title=_("Customer already linked"),
			)

		# Linked to some other user by hand, on the Customer's own Portal Users tab?
		legacy = frappe.get_all(
			"Portal User",
			filters={"parenttype": "Customer", "parent": ["in", list(seen)], "user": ["!=", self.user or ""]},
			fields=["parent", "user"],
		)
		for row in legacy:
			frappe.throw(
				_(
					"{0} is already linked to the login {1} on the customer's Portal Users tab. "
					"Remove that row on the Customer first, or use that login here."
				).format(frappe.bold(row.parent), frappe.bold(row.user)),
				title=_("Customer already linked"),
			)

	def _resolve_user(self):
		"""Find the User this record drives — an existing one with the same
		mobile or email is adopted rather than duplicated."""
		if self.user:
			return

		candidates = set()
		if self.email:
			if frappe.db.exists("User", self.email):
				candidates.add(self.email)
		candidates.update(frappe.get_all("User", filters={"mobile_no": self.mobile_no}, pluck="name"))
		placeholder = placeholder_email(self.mobile_no)
		if frappe.db.exists("User", placeholder):
			candidates.add(placeholder)

		if len(candidates) > 1:
			frappe.throw(
				_("Both {0} already exist as users. Fix the duplicate users first.").format(
					", ".join(frappe.bold(c) for c in sorted(candidates))
				)
			)
		if not candidates:
			return

		existing = candidates.pop()
		if frappe.db.get_value("User", existing, "user_type") == "System User":
			frappe.throw(
				_("{0} is a staff (desk) account and cannot be used as a customer portal login.").format(
					frappe.bold(existing)
				),
				title=_("Staff account"),
			)
		taken_by = frappe.db.get_value(self.doctype, {"user": existing, "name": ["!=", self.name or ""]})
		if taken_by:
			frappe.throw(_("User {0} is already managed by {1}.").format(existing, taken_by))
		self.user = existing

	# ── side effects ────────────────────────────────────────────────────────

	def on_update(self):
		self._sync_user()
		self._sync_portal_users()

	def on_trash(self):
		if not self.user:
			return
		frappe.db.delete("Portal User", {"parenttype": "Customer", "user": self.user})
		if frappe.db.get_value("User", self.user, "enabled"):
			user = frappe.get_doc("User", self.user)
			user.enabled = 0
			user.save(ignore_permissions=True)
			frappe.sessions.clear_sessions(self.user, force=True)

	def _sync_user(self):
		if not self.user:
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": self.email or placeholder_email(self.mobile_no),
					"first_name": self.full_name,
					"mobile_no": self.mobile_no,
					"user_type": "Website User",
					"send_welcome_email": 0,
					"enabled": cint(self.enabled),
					"roles": [{"role": PORTAL_ROLE}],
				}
			)
			# Sales Managers manage portal logins but have no User permission.
			user.insert(ignore_permissions=True)
			self.db_set("user", user.name, update_modified=False)
			return

		user = frappe.get_doc("User", self.user)
		was_enabled = cint(user.enabled)
		user.enabled = cint(self.enabled)
		user.first_name = self.full_name
		user.mobile_no = self.mobile_no
		if PORTAL_ROLE not in [r.role for r in user.roles]:
			user.append("roles", {"role": PORTAL_ROLE})
		user.save(ignore_permissions=True)

		if was_enabled and not user.enabled:
			# Disabling must also end the sessions already open on their phone.
			frappe.sessions.clear_sessions(self.user, force=True)

	def _sync_portal_users(self):
		"""Make the Customers' Portal Users tabs match this record's table —
		without saving the Customer documents (see module docstring)."""
		wanted = {row.customer for row in self.customers}
		current = set(
			frappe.get_all(
				"Portal User", filters={"parenttype": "Customer", "user": self.user}, pluck="parent"
			)
		)

		for customer in current - wanted:
			frappe.db.delete("Portal User", {"parenttype": "Customer", "parent": customer, "user": self.user})

		for customer in wanted - current:
			idx = (
				frappe.db.sql(
					"SELECT IFNULL(MAX(idx), 0) FROM `tabPortal User` WHERE parenttype='Customer' AND parent=%s",
					customer,
				)[0][0]
				+ 1
			)
			row = frappe.get_doc(
				{
					"doctype": "Portal User",
					"parent": customer,
					"parenttype": "Customer",
					"parentfield": "portal_users",
					"user": self.user,
					"idx": idx,
				}
			)
			row.name = frappe.generate_hash(length=10)
			row.db_insert()

		for customer in wanted ^ current:
			frappe.clear_document_cache("Customer", customer)


def placeholder_email(mobile_no: str) -> str:
	return f"{mobile_no}@{PLACEHOLDER_EMAIL_DOMAIN}"


def generate_password() -> str:
	word = "".join(secrets.choice(_CONSONANTS) + secrets.choice(_VOWELS) for _ in range(3))
	digits = "".join(secrets.choice("23456789") for _ in range(4))
	return f"{word.capitalize()}-{digits}"


@frappe.whitelist()
def issue_password(name: str) -> dict:
	"""Set a fresh random password on the login and text it to the dealer.

	Called by the form's "Send New Password" button, and automatically after the
	first save. Returns {"sms_sent": bool, "password": str | None, "message": str};
	`password` is only filled when the SMS did not go out, so the operator can
	hand it over — it is never stored anywhere readable.
	"""
	doc = frappe.get_doc("Customer Portal Access", name)
	doc.check_permission("write")
	if not doc.user:
		frappe.throw(_("Save the record first."))
	if not doc.enabled:
		frappe.throw(_("Portal access is disabled for this login. Enable it first."))

	password = generate_password()
	update_password(doc.user, password, logout_all_sessions=True)
	doc.db_set("password_sent_on", now_datetime(), update_modified=False)
	doc.add_comment("Info", _("New portal password issued by {0}").format(frappe.session.user))
	# Commit before the 5s HTTP call: the password must be live before the
	# dealer reads the SMS, and no lock is held across the gateway call.
	frappe.db.commit()

	sms_sent = False
	if cint(doc.send_password_by_sms):
		text = SMS_TEMPLATE.format(url=get_url("/login"), mobile=doc.mobile_no, password=password)
		sms_sent = send_sms(
			doc.mobile_no,
			text,
			reference=f"{doc.doctype} {doc.name}",
			context={
				# The log keeps the text with the password masked.
				"message": text.replace(password, PASSWORD_MASK),
				"reference_doctype": doc.doctype,
				"reference_name": doc.name,
				"party_name": doc.full_name,
				"sent_via": "Portal Password",
			},
		)

	if sms_sent:
		return {
			"sms_sent": True,
			"password": None,
			"message": _("A new password was sent by SMS to {0}.").format(doc.mobile_no),
		}
	reason = (
		_("SMS sending is off for this login.")
		if not cint(doc.send_password_by_sms)
		else _("The SMS could not be sent — see Sparrow SMS Log.")
	)
	return {"sms_sent": False, "password": password, "message": reason}


@frappe.whitelist()
def access_for_customer(customer: str) -> dict:
	"""For the Customer form button: the login record covering this customer,
	or what to prefill a new one with."""
	frappe.has_permission("Customer Portal Access", "read", throw=True)
	name = frappe.db.get_value(
		"Customer Portal Access Customer", {"parenttype": "Customer Portal Access", "customer": customer}, "parent"
	)
	if name:
		return {"name": name}
	values = frappe.db.get_value("Customer", customer, ["customer_name", "custom_mobile_number"], as_dict=True) or {}
	return {
		"name": None,
		"full_name": values.get("customer_name"),
		"mobile_no": normalize_mobile(values.get("custom_mobile_number")),
		"legacy_user": frappe.db.get_value(
			"Portal User", {"parenttype": "Customer", "parent": customer}, "user"
		),
	}


def login_with_mobile_enabled() -> bool:
	return bool(cint(frappe.db.get_single_value("System Settings", "allow_login_using_mobile_number")))
