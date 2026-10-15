"""Leave encashment: unused leave paid at year end or at separation, on the slip.

Policy minute 3.7 (2026-09-15), confirmed by the user 2026-10-13: in the
fiscal year's last month (Ashadh) the leave remaining on every encashable type
is worked out and encashed on the Ashadh slip; carry forward is off, so nothing
crosses into the new year. Only types with Allow Encashment are touched. HRMS has the document for it — Leave Encashment,
which takes the balance of an allocation, caps it by the Leave Type's
Maximum Encashable Leaves, and on submit writes an Additional Salary on the
Leave Type's Earning Component — but three things in stock HRMS do not fit here:

  1. Its rate is one figure per Salary Structure
     (`leave_encashment_amount_per_day`). Here a structure is shared by a whole
     company and the pay is on each person's assignment, so one figure would pay
     a driver and a manager the same day's rate. `price_encashment` replaces it:
     per-day rate = the person's monthly basic (assignment `base`) ÷ the Leave
     Type's Encashment Days per Month (blank = the actual days of the BS month
     the encashment is dated in, as overtime does since 2026-10-12).
  2. It encashes on any date. Here encashment happens at two moments only, each
     switched per Leave Type: Year End (dated the allocation's last day) and
     Separation (dated the relieving date). Anything else is refused, so a
     mid-year encashment cannot be paid by mistake.
  3. Its Additional Salary is a plain one-off: no tax in its own month, and the
     encashment never records it (`additional_salary` stays blank in v15.49, so
     cancelling the encashment left the payment standing). `mark_additional_salary`
     and `link_additional_salary` fix both.

HR's entry point is the Payroll Entry that pays it, the same as the Dashain
allowance: tick "Pay Leave Encashment" on the entry. Making its slips
(payroll/payroll_entry.py `prepare_payroll_inputs`) makes and submits, for the
entry's employees, what falls in that month — the remaining balance on each
encashable type, dated the allocation's last day, when the month is the year's
last (Ashadh); and for anyone relieved in the month, their balance dated the
relieving date — and writes the totals to the entry's Payroll Inputs Log.
Submitting writes the Additional Salary the slip reads. Running again leaves
submitted ones alone, and `price_encashment` refuses a second encashment of an
allocation. `encash_for_payroll_entry` still drafts without submitting, for a
look before the month is run.

A one-off separation can still be made on the stock form (New, dated the
relieving date); this module prices it and checks the type allows it the same way.

Every rule is data: which types (Allow Encashment), the earning component, the
day cap (Maximum / Non-Encashable Leaves), the divisor, and the two occasions
are Leave Type fields (patch setup_leave_encashment). HR Settings' Auto Leave
Encashment stays off: it would make drafts on allocation expiry for every type
without these checks.

The other direction is recovery (user, 2026-10-15: leave may be taken before
it is credited, "what is calculated is in the end of the year it does not pass
the allocated days other wise deduction"). Casual and Sick Leave allow a
negative balance, capped at the year's figure by hr/leave_ceiling.py. At the
same two moments, a balance below zero — someone who took 33 days in three
months and left with 8.25 earned — is days paid as leave but never earned:
`recover_month` deducts them, at the same per-day rate, as a submitted
"Leave Recovery" Additional Salary on that month's slip. The balance counts the
month's credit still due on that day when the BS-month-end accrual has not run
yet (the Ashadh payroll is usually made before the last day), so a year that
ends square is never charged.

Boundary: HRMS refuses an encashment for an employee who is no longer Active, so
a leaver's encashment must be made before their status is set to Left (the
relieving date is enough). Payment through a Payment Entry instead of the slip
(HRMS's Pay via Payment Entry) is priced the same way and otherwise left to HRMS.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, strip_html

from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on
from hrms.hr.doctype.leave_encashment.leave_encashment import LeaveEncashment

from avinashgroup_app.payroll.allowance import current_assignment

SOURCE_TAG = "Leave Encashment"
RECOVERY_COMPONENT = "Leave Recovery"
RECOVERY_SOURCE = "Leave Recovery"
YEAR_END = "Year End"
SEPARATION = "Separation"


def _bs_month_days(on_date) -> int:
	from rdp_common_app.utils.bs_boundaries import ad_to_bs, get_bs_month_days

	bs = ad_to_bs(getdate(on_date))
	return get_bs_month_days(bs.year, bs.month)


def per_day_rate(employee: str, leave_type: str, on_date) -> tuple:
	"""(monthly basic, divisor, rate per day) for this person and type on `on_date`."""
	basic = flt((current_assignment(employee, on_date) or {}).get("base"))
	divisor = flt(frappe.get_cached_value("Leave Type", leave_type, "custom_encashment_days_per_month")) or _bs_month_days(
		on_date
	)
	return basic, divisor, (basic / divisor if divisor else 0.0)


def occasion_for(doc) -> str | None:
	"""Year End when dated the allocation's last day, Separation when dated the relieving date."""
	date = getdate(doc.encashment_date)
	to_date = doc.leave_allocation and frappe.db.get_value("Leave Allocation", doc.leave_allocation, "to_date")
	if to_date and getdate(to_date) == date:
		return YEAR_END
	relieving = frappe.db.get_value("Employee", doc.employee, "relieving_date")
	if relieving and getdate(relieving) == date:
		return SEPARATION
	return None


def price_encashment(doc, method=None):
	"""Check the occasion is switched on, and price the days at the person's own basic.

	Hook: doc_events → Leave Encashment → validate (after HRMS's own, which has
	already set the balance, the capped days and its structure-rate amount).
	Throws for a date that is neither the allocation's end nor the relieving
	date, and for an occasion the Leave Type does not allow.
	"""
	if doc.docstatus == 2:
		return
	# HRMS's balance does not subtract an earlier encashment of the same
	# allocation, so a second one would pay the same days twice.
	twice = frappe.db.exists(
		"Leave Encashment",
		{"leave_allocation": doc.leave_allocation, "docstatus": 1, "name": ("!=", doc.name)},
	)
	if doc.leave_allocation and twice:
		frappe.throw(_("{0} already encashes this allocation ({1}).").format(twice, doc.leave_allocation))
	occasion = occasion_for(doc)
	if not occasion:
		frappe.throw(
			_(
				"Leave is encashed at year end (date it {0}, the allocation's last day) or at separation "
				"(date it the employee's relieving date)."
			).format(frappe.db.get_value("Leave Allocation", doc.leave_allocation, "to_date") or "")
		)
	field = "custom_encash_at_year_end" if occasion == YEAR_END else "custom_encash_at_separation"
	if not frappe.get_cached_value("Leave Type", doc.leave_type, field):
		frappe.throw(_("{0} is not encashed at {1} (Leave Type setting).").format(doc.leave_type, occasion.lower()))

	basic, divisor, rate = per_day_rate(doc.employee, doc.leave_type, doc.encashment_date)
	if not basic:
		frappe.throw(_("{0} has no salary assignment on {1}, so there is no basic to price the days at.").format(
			doc.employee, doc.encashment_date
		))
	doc.custom_occasion = occasion
	doc.custom_monthly_basic = basic
	doc.custom_days_per_month = divisor
	doc.custom_rate_per_day = flt(rate, 2)
	doc.encashment_amount = flt(flt(doc.encashment_days) * rate, 2)


def mark_additional_salary(doc, method=None):
	"""An encashment's Additional Salary is taxed in its own month and tagged.

	Hook: doc_events → Additional Salary → validate. Touches only rows whose
	ref_doctype is Leave Encashment.
	"""
	if doc.ref_doctype != "Leave Encashment":
		return
	doc.deduct_full_tax_on_selected_payroll_date = 1
	doc.custom_source = SOURCE_TAG


def link_additional_salary(doc, method=None):
	"""Record the Additional Salary on its encashment, so cancelling one cancels the other.

	Hook: doc_events → Additional Salary → on_submit.
	"""
	if doc.ref_doctype == "Leave Encashment" and doc.ref_docname:
		frappe.db.set_value("Leave Encashment", doc.ref_docname, "additional_salary", doc.name, update_modified=False)


def refresh_slip(doc, method=None):
	"""Re-save the person's draft slip covering the encashment date.

	Hook: doc_events → Leave Encashment → on_submit, on_cancel.
	"""
	if doc.pay_via_payment_entry:
		return
	from avinashgroup_app.payroll.attendance_allowance import refresh_slips_covering

	refresh_slips_covering([doc.employee], doc.encashment_date)


def leave_period_for(company: str, allocation: str, on_date) -> str | None:
	"""The allocation's Leave Period, or the company's period covering the date (Leave Encashment requires one)."""
	return frappe.db.get_value("Leave Allocation", allocation, "leave_period") or frappe.db.get_value(
		"Leave Period",
		{"company": company, "from_date": ("<=", getdate(on_date)), "to_date": (">=", getdate(on_date))},
		"name",
	)


def encashable_leave_types() -> list:
	return frappe.get_all(
		"Leave Type",
		filters={"allow_encashment": 1},
		fields=["name", "earning_component", "custom_encash_at_year_end", "custom_encash_at_separation"],
	)


def due_encashments(employees: list, start_date, end_date) -> list:
	"""[(employee, leave_type, allocation, encashment_date, occasion)] falling in the month."""
	start_date, end_date = getdate(start_date), getdate(end_date)
	relieving = dict(
		frappe.get_all(
			"Employee", filters={"name": ("in", employees or [""])}, fields=["name", "relieving_date"], as_list=True
		)
	)
	due = []
	for lt in encashable_leave_types():
		for alloc in frappe.get_all(
			"Leave Allocation",
			filters={"employee": ("in", employees or [""]), "leave_type": lt.name, "docstatus": 1,
				"from_date": ("<=", end_date), "to_date": (">=", start_date)},
			fields=["name", "employee", "from_date", "to_date"],
		):
			left = relieving.get(alloc.employee)
			left = getdate(left) if left else None
			if lt.custom_encash_at_separation and left and start_date <= left <= end_date and getdate(alloc.from_date) <= left <= getdate(alloc.to_date):
				due.append((alloc.employee, lt.name, alloc.name, left, SEPARATION))
			elif lt.custom_encash_at_year_end and start_date <= getdate(alloc.to_date) <= end_date and not (left and left < getdate(alloc.to_date)):
				due.append((alloc.employee, lt.name, alloc.name, getdate(alloc.to_date), YEAR_END))
	return due


@frappe.whitelist()
def encash_for_payroll_entry(payroll_entry: str) -> dict:
	"""Draft the Leave Encashments that fall in this Payroll Entry's month, for its employees.

	The "Leave Encashment" button on the Payroll Entry (public/js/payroll_entry.js),
	beside "Dashain Allowance": both yearly payments start from the payroll that
	pays them. In Ashadh, every allocation of an Allow Encashment type that ends
	in the month is encashed at Year End, dated its last day; in any month,
	someone whose relieving date falls in it is encashed at Separation, dated
	that day. So the Additional Salary rides this entry's slips.

	Explicit action, pressed by HR; drafts made earlier are rebuilt, submitted
	ones are left alone. Refused before the month starts: its final leave credit
	is not in yet. Throws for a cancelled entry or one without employees.
	"""
	pe = frappe.get_doc("Payroll Entry", payroll_entry)
	pe.check_permission("read")
	frappe.has_permission("Leave Encashment", "create", throw=True)
	if pe.docstatus == 2:
		frappe.throw(_("This Payroll Entry is cancelled."))

	start_date, end_date = getdate(pe.start_date), getdate(pe.end_date)
	if getdate() < start_date:
		frappe.throw(_("Leave encashment for this month opens on {0}, its first day.").format(start_date))

	employees = [r.employee for r in pe.employees]
	if not employees:
		frappe.throw(_("The Payroll Entry has no employees yet: press Get Employees first."))

	currency = frappe.get_cached_value("Company", pe.company, "default_currency")
	result = encash_month(pe.company, currency, employees, start_date, end_date)
	result["period"] = {"from": start_date, "to": end_date}
	return result


def encash_month(company: str, currency: str, employees: list, start_date, end_date, occasions=(YEAR_END, SEPARATION)) -> dict:
	"""Draft Leave Encashments for these employees for the month start_date..end_date.

	Returns {"created": [review rows], "left_out": [...], "total": amount}.
	"""
	created, left_out = [], []
	for employee, leave_type, allocation, date, occasion in due_encashments(employees, start_date, end_date):
		if occasion not in occasions:
			continue
		existing = frappe.get_all(
			"Leave Encashment",
			filters={"employee": employee, "leave_type": leave_type, "leave_allocation": allocation, "docstatus": ("<", 2)},
			fields=["name", "docstatus"],
		)
		if any(e.docstatus == 1 for e in existing):
			left_out.append({"employee": employee, "leave_type": leave_type, "reason": _("already encashed")})
			continue
		for e in existing:
			frappe.delete_doc("Leave Encashment", e.name, ignore_permissions=True)

		savepoint = "leave_encashment_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(savepoint)
		try:
			leave_period = leave_period_for(company, allocation, date)
			if not leave_period:
				frappe.throw(_("No Leave Period for {0} covers {1} (hr/year_setup.py makes one per year)").format(company, date))
			doc = frappe.get_doc(
				{
					"doctype": "Leave Encashment",
					"leave_period": leave_period,
					"employee": employee,
					"leave_type": leave_type,
					"leave_allocation": allocation,
					"encashment_date": date,
					"company": company,
					"currency": currency,
				}
			)
			doc.flags.ignore_permissions = True
			doc.insert()
			if flt(doc.encashment_days) <= 0 or flt(doc.encashment_amount) <= 0:
				frappe.delete_doc("Leave Encashment", doc.name, ignore_permissions=True)
				left_out.append({"employee": employee, "leave_type": leave_type, "reason": _("no balance to encash")})
				continue
			created.append(
				{
					"name": doc.name,
					"employee": employee,
					"employee_name": doc.employee_name,
					"leave_type": leave_type,
					"occasion": occasion,
					"balance": doc.leave_balance,
					"days": doc.encashment_days,
					"rate": doc.custom_rate_per_day,
					"amount": doc.encashment_amount,
				}
			)
		except Exception as e:
			frappe.db.rollback(save_point=savepoint)
			frappe.clear_last_message()
			left_out.append({"employee": employee, "leave_type": leave_type, "reason": strip_html(str(e))})
			frappe.log_error(title=f"Leave encashment for {employee}/{leave_type}", message=frappe.get_traceback())

	frappe.clear_messages()
	return {
		"created": created,
		"left_out": left_out,
		"total": flt(sum(c["amount"] for c in created), 2),
	}


def recover_month(company: str, employees: list, start_date, end_date) -> dict:
	"""Deduct leave taken beyond what was earned, for settlements falling in the month.

	Same occasions as `encash_month` (relieving date or the allocation's last day
	in the month). For each one whose balance is below zero, posts and submits a
	"Leave Recovery" Additional Salary for the days short × the per-day rate.
	Re-running replaces this month's own rows; a person whose slip for the month
	is already submitted is left alone. Returns {"made", "left_out", "total"}.
	"""
	made, left_out = [], []
	if not frappe.db.exists("Salary Component", RECOVERY_COMPONENT):
		return {"made": made, "left_out": left_out, "total": 0}
	for employee, leave_type, allocation, date, occasion in due_encashments(employees, start_date, end_date):
		if _slip_submitted(employee, date):
			left_out.append({"employee": employee, "leave_type": leave_type, "reason": _("salary slip already submitted")})
			continue
		_clear_recovery(employee, allocation, date)
		short = -settlement_balance(employee, leave_type, allocation, date)
		if short <= 0:
			continue
		basic, divisor, rate = per_day_rate(employee, leave_type, date)
		if not rate:
			left_out.append({"employee": employee, "leave_type": leave_type, "reason": _("no salary assignment to price the days")})
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Additional Salary",
				"employee": employee,
				"company": company,
				"salary_component": RECOVERY_COMPONENT,
				"type": "Deduction",
				"amount": flt(short * rate, 2),
				"payroll_date": date,
				"overwrite_salary_structure_amount": 0,
				"ref_doctype": "Leave Allocation",
				"ref_docname": allocation,
				"custom_source": RECOVERY_SOURCE,
				"custom_quantity": short,
				"custom_rate": rate,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		made.append(
			{"name": doc.name, "employee": employee, "leave_type": leave_type, "occasion": occasion,
				"days": short, "rate": flt(rate, 2), "amount": doc.amount}
		)
	return {"made": made, "left_out": left_out, "total": flt(sum(m["amount"] for m in made), 2)}


class SettlementLeaveEncashment(LeaveEncashment):
	"""HRMS's Leave Encashment, whose balance counts the month's credit still due.

	Settlement is dated the allocation's last day or the relieving date — the
	BS month end, the very day the month's instalment is credited, at midnight.
	A Payroll Entry run that afternoon saw the balance without it: the recovery
	path added it (`settlement_balance`) and the encashment did not, so the two
	disagreed by one month's credit. Done in `set_leave_balance`, which HRMS calls
	on every validate, so actual encashable days and the submit-time check agree.
	Registered in hooks.override_doctype_class.
	"""

	def set_leave_balance(self):
		super().set_leave_balance()
		allocation = self.leave_allocation or (self.get_leave_allocation() or {}).get("name")
		if allocation and self.encashment_date:
			self.leave_balance = flt(self.leave_balance) + _credit_still_due(
				allocation, self.leave_type, self.encashment_date
			)


def settlement_balance(employee: str, leave_type: str, allocation: str, on_date) -> float:
	"""Leave left on the settlement day: HRMS's balance plus the month's credit still due."""
	balance = flt(get_leave_balance_on(employee, leave_type, getdate(on_date)))
	return balance + _credit_still_due(allocation, leave_type, on_date)


def _credit_still_due(allocation: str, leave_type: str, on_date) -> float:
	"""The BS-month-end instalment for `on_date`'s month, when that is today's credit day and it has not run.

	Worked out by the accrual itself (hr/utils `_credit_instalment`, dry run), so
	the figure is exactly what the job would credit that night.
	"""
	from avinashgroup_app.hr.utils import _credit_instalment, _get_policy_details, _is_accrual_day
	from rdp_common_app.utils.bs_boundaries import get_bs_month_start

	on_date = getdate(on_date)
	lt = frappe.get_cached_doc("Leave Type", leave_type)
	if not lt.is_earned_leave or not _is_accrual_day(lt, on_date):
		return 0.0
	alloc = frappe.get_doc("Leave Allocation", allocation)
	# A month-end credit is a ledger entry dated inside the month; the
	# allocation's own opening entry (dated its first day) is not one.
	month_start = max(getdate(get_bs_month_start(on_date)), getdate(frappe.utils.add_days(alloc.from_date, 1)))
	if frappe.db.exists(
		"Leave Ledger Entry",
		{"transaction_name": allocation, "transaction_type": "Leave Allocation", "docstatus": 1, "leaves": (">", 0),
			"from_date": ("between", [month_start, on_date])},
	):
		return 0.0
	annual, joined = _get_policy_details(alloc, leave_type)
	if annual is None:
		return 0.0
	row = _credit_instalment(alloc, annual, lt, joined, on_date, dry_run=True)
	return flt(row["credited"]) if row else 0.0


def _slip_submitted(employee: str, on_date) -> bool:
	return bool(
		frappe.db.exists(
			"Salary Slip",
			{"employee": employee, "docstatus": 1, "start_date": ("<=", on_date), "end_date": (">=", on_date)},
		)
	)


def _clear_recovery(employee: str, allocation: str, on_date):
	"""Cancel and delete this settlement's earlier recovery, dropping its line from a draft slip."""
	for row in frappe.get_all(
		"Additional Salary",
		filters={"employee": employee, "ref_doctype": "Leave Allocation", "ref_docname": allocation,
			"payroll_date": on_date, "custom_source": RECOVERY_SOURCE, "docstatus": ("<", 2)},
		fields=["name", "docstatus"],
	):
		frappe.db.sql(
			"""delete sd from `tabSalary Detail` sd
			join `tabSalary Slip` ss on ss.name = sd.parent and sd.parenttype = 'Salary Slip'
			where sd.additional_salary = %s and ss.docstatus = 0""",
			row.name,
		)
		if row.docstatus == 1:
			doc = frappe.get_doc("Additional Salary", row.name)
			doc.flags.ignore_permissions = True
			doc.cancel()
		frappe.delete_doc("Additional Salary", row.name, force=True, ignore_permissions=True)
