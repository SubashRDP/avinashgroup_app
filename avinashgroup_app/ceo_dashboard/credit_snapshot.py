"""Credit-control snapshot for the CEO Dashboard's "Credit and dues" section.

Credit control (custom_code/SalesInvoice/credit_control.py) decides, per
customer, whether a Sales Invoice may be saved: too many unpaid bills, the
oldest unpaid bill too old, or too much owed, after netting off advances,
credit notes and unlinked journal credits. It keeps no record of who is on
hold; it works the position out live, one customer at a time.

The CEO wants that picture group-wide: how many customers are on hold and why,
how much is owed and how old it is, how much advance customers hold. Working
it out for every customer with limits took 459 s on demo-nggroup (3,507
customers, ~4 queries each), far too slow for a page load. So this module
works it out in the background and saves the answer to a JSON file in the
site's private folder; the dashboard reads the file.

Deliberately reuses credit_control._credit_state instead of re-deriving the
rules in bulk SQL: the dashboard must say exactly what the invoice form says
("on hold" here == the form would refuse a bill), and the FIFO/advance rules in
that module are subtle (see its comments). If credit control changes, this
follows automatically.

Boundaries:
- Read-only on business data; the only write is the snapshot file.
- "As of" is the dashboard's "data through" day (today on a live site), so a
  data copy whose billing stops early does not age every bill by the gap.
- Registered as a cron job in hooks.py (every 4 hours at :20, off the hour so
  it does not pile onto the hourly jobs); `refresh` enqueues one on demand.

See docs/ceo-dashboard.md.
"""

import json
import os
import time

import frappe
from frappe import _
from frappe.utils import getdate, now, today

from avinashgroup_app.custom_code.SalesInvoice.credit_control import _credit_state

# Who may ask for a fresh snapshot from the page (it costs minutes of DB time).
REFRESH_ROLES = ("System Manager", "Accounts Manager")

# blocked_by as stored in the snapshot (small ints keep the file small).
BLOCK_CODES = {None: 0, "count": 1, "days": 2, "amount": 3}

JOB_ID = "ceo_dashboard_credit_snapshot"


def _path():
	return frappe.get_site_path("private", "ceo_dashboard", "credit_snapshot.json")


def _as_of():
	"""The dashboard's "data through" day for the current fiscal year."""
	from avinashgroup_app.ceo_dashboard import api

	fy = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ("<=", today()), "year_end_date": (">=", today()), "disabled": 0},
		["year_start_date"],
	)
	if not fy:
		return getdate(today())
	companies = tuple(frappe.get_all("Company", pluck="name"))
	return api._data_through(getdate(fy), getdate(today()), companies)


def build():
	"""Work out every limited customer's credit position and save the file.
	Runs from the scheduler / a background job; returns the row count."""
	started = time.time()
	as_of = _as_of()
	abbr = dict(frappe.get_all("Company", fields=["name", "abbr"], as_list=True))
	customers = frappe.db.sql(
		"""SELECT name FROM `tabCustomer`
		WHERE disabled = 0
			AND (custom_bill_count > 0 OR custom_days_limit > 0 OR custom_amount_limit > 0)""",
		pluck=True,
	)
	# The company a customer belongs to: its receivable Party Account, else the
	# company of its latest bill.
	company_of = dict(frappe.db.sql(
		"""SELECT parent, MIN(company) FROM `tabParty Account`
		WHERE parenttype = 'Customer' GROUP BY parent"""
	))
	rows = []
	for code in customers:
		try:
			s = _credit_state(code, as_of=as_of)
		except Exception:
			frappe.log_error(title="CEO dashboard credit snapshot", message=f"Customer {code}\n{frappe.get_traceback()}")
			continue
		co = company_of.get(code) or frappe.db.get_value(
			"Sales Invoice", {"customer": code, "docstatus": 1}, "company", order_by="posting_date desc"
		)
		rows.append([
			code,
			abbr.get(co, ""),
			BLOCK_CODES.get(s.get("blocked_by"), 0),
			round(s["outstanding"]),
			round(s["leftover_advance"]),
			round(s["exposure"]),
			round(s.get("amount_limit") or 0),
			int(s["days_used"]),
			int(s.get("days_limit") or 0),
			int(s["unpaid_count"]),
			int(s.get("bill_limit") or 0),
			s["oldest_date"],
		])
	out = {
		"as_of": as_of.isoformat(),
		"built": now(),
		"seconds": round(time.time() - started),
		# [code, company abbr, blocked (0 no / 1 bills / 2 days / 3 amount), owed,
		#  advance left, exposure, amount limit, days used, days limit,
		#  unpaid bills, bill limit, oldest unpaid bill AD]
		"rows": rows,
	}
	path = _path()
	os.makedirs(os.path.dirname(path), exist_ok=True)
	tmp = path + ".tmp"
	with open(tmp, "w") as f:
		json.dump(out, f, separators=(",", ":"))
	os.replace(tmp, path)   # readers never see a half-written file
	return len(rows)


def _enqueue():
	from frappe.utils.background_jobs import is_job_enqueued

	if is_job_enqueued(JOB_ID):
		return False
	frappe.enqueue(
		"avinashgroup_app.ceo_dashboard.credit_snapshot.build",
		queue="long",
		timeout=3600,
		job_id=JOB_ID,
		deduplicate=True,
	)
	return True


def scheduled_build():
	"""hooks.py cron entry. Cron jobs run on the default queue, whose timeout
	is shorter than a build (~8 min), so this only hands the work to the long
	queue."""
	_enqueue()


def load():
	"""The saved snapshot, or None when it has never been built."""
	try:
		with open(_path()) as f:
			return json.load(f)
	except FileNotFoundError:
		return None
	except ValueError:
		frappe.log_error(title="CEO dashboard credit snapshot", message=f"Unreadable file {_path()}")
		return None


@frappe.whitelist()
def get_credit():
	"""The saved snapshot for the dashboard, limited to the user's companies,
	with each customer's name, segment and inter-company flag."""
	from avinashgroup_app.ceo_dashboard import api

	frappe.only_for(api.ROLES)
	companies = api._companies()
	snap = load()
	can_refresh = bool(set(frappe.get_roles()) & set(REFRESH_ROLES))
	if not snap:
		return {"missing": True, "can_refresh": can_refresh}
	allowed = {c["abbr"] for c in companies}
	rows = [r for r in snap["rows"] if r[1] in allowed]
	group_names = [api._name_tokens(n) for n in frappe.get_all("Company", pluck="name")]
	info = {}
	if rows:
		for name, cname, group, internal in frappe.db.sql(
			"""SELECT c.name, c.customer_name, IFNULL(cg.customer_group_name, ''), c.is_internal_customer
			FROM `tabCustomer` c LEFT JOIN `tabCustomer Group` cg ON cg.name = c.customer_group
			WHERE c.name IN %s""",
			(tuple(r[0] for r in rows),),
		):
			info[name] = (cname, api._segment(group), 1 if internal or api._is_group_company(cname, group_names) else 0)
	return {
		"as_of": snap["as_of"],
		"as_of_label": api._bs_label(getdate(snap["as_of"])),
		"built": snap["built"],
		"can_refresh": can_refresh,
		# [code, name, segment, inter-company, company abbr, blocked (0 / 1 bills / 2 days / 3 amount),
		#  owed, advance left, exposure, amount limit, days used, days limit, unpaid bills,
		#  bill limit, oldest unpaid AD]
		"rows": [[r[0], *info.get(r[0], (r[0], len(api.SEGMENTS) - 1, 0)), *r[1:]] for r in rows],
	}


@frappe.whitelist(methods=["POST"])
def refresh():
	"""Queue a fresh snapshot (one at a time). Returns the job state."""
	frappe.only_for(REFRESH_ROLES)
	return {"queued": True, "already": not _enqueue()}
