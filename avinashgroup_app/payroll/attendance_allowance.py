"""Calculator: Attendance + per-employee rates → Additional Salary drafts.

Per Payroll Entry:
1. List Salary Components where `custom_is_attendance_driven = 1` and not disabled.
2. For each (employee, component), evaluate the component's condition against the
   employee's submitted Attendance rows in the period and sum the qty.
3. Multiply qty × rate (employee override row → component default fallback).
4. Create an Additional Salary draft per (employee, component, payroll_date),
   tagged with `custom_source = "Nepal HRMS Attendance Allowance"`. Idempotent —
   prior drafts with the same tag are deleted before recreating.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

SOURCE_TAG = "Nepal HRMS Attendance Allowance"

# Statuses that are *not* "present" full-day. Half Day is excluded because it's
# weighted at 0.5 separately; Absent/On Leave aren't worked days at all.
_NON_PRESENT_STATUSES = frozenset({"Absent", "On Leave", "Half Day"})


def get_present_statuses() -> tuple:
	"""Return tuple of Attendance.status values that count as a full present day.

	Derived from the Attendance doctype's `status` Select options minus the
	well-known non-present statuses, so adding a new status (e.g. via Custom
	Field) doesn't require code changes here.
	"""
	options = frappe.get_meta("Attendance").get_field("status").options or ""
	statuses = [s.strip() for s in options.split("\n") if s.strip()]
	return tuple(s for s in statuses if s not in _NON_PRESENT_STATUSES)


@frappe.whitelist()
def trigger_for_payroll_entry(payroll_entry: str) -> dict:
	pe = frappe.get_doc("Payroll Entry", payroll_entry)
	if pe.docstatus == 2:
		frappe.throw(_("Cannot calculate allowances for a cancelled Payroll Entry."))
	result = create_additional_salaries(pe)
	return {
		"payroll_entry": pe.name,
		"created": len(result["created"]),
		"skipped": len(result["skipped"]),
		"records": result["created"],
		"skipped_records": result["skipped"],
	}


def create_additional_salaries(payroll_entry) -> dict:
	if isinstance(payroll_entry, str):
		payroll_entry = frappe.get_doc("Payroll Entry", payroll_entry)

	start_date = getdate(payroll_entry.start_date)
	end_date = getdate(payroll_entry.end_date)
	payroll_date = end_date
	company = payroll_entry.company

	components = get_attendance_driven_components()
	if not components:
		return {"created": [], "skipped": []}

	employees = [row.employee for row in (payroll_entry.employees or [])]
	if not employees:
		employees = _employees_in_payroll_entry(payroll_entry)

	created: list[dict] = []
	skipped: list[dict] = []
	for employee in employees:
		emp_doc = frappe.get_cached_doc("Employee", employee)
		emp_overrides = _get_employee_overrides(employee)
		for sc in components:
			if _skip_for_ot_eligibility(emp_doc, sc):
				continue
			rate = _resolve_rate(emp_overrides, sc)
			if rate is None:
				continue
			qty = _qty_for_employee(employee, sc, start_date, end_date)
			if qty <= 0:
				continue
			amount = flt(qty * rate, 2)
			if amount <= 0:
				continue

			savepoint = f"naa_{employee}_{sc.name}".replace("-", "_").replace(" ", "_")[:60]
			frappe.db.savepoint(savepoint)
			try:
				_delete_existing_draft(employee, sc.name, payroll_date)
				doc = _make_additional_salary(
					employee=employee,
					salary_component=sc,
					amount=amount,
					payroll_date=payroll_date,
					company=company,
					qty=qty,
					rate=rate,
				)
				created.append({
					"employee": employee,
					"salary_component": sc.name,
					"qty": qty,
					"rate": rate,
					"amount": amount,
					"additional_salary": doc.name,
				})
			except Exception as e:
				frappe.db.rollback(save_point=savepoint)
				skipped.append({
					"employee": employee,
					"salary_component": sc.name,
					"qty": qty,
					"rate": rate,
					"amount": amount,
					"reason": str(e),
				})
				frappe.log_error(
					message=frappe.get_traceback(),
					title=f"Nepal HRMS Attendance Allowance: {employee}/{sc.name}",
				)

	frappe.db.commit()
	if skipped:
		frappe.msgprint(
			_("{0} record(s) skipped (see Error Log for details).").format(len(skipped)),
			indicator="orange",
			alert=True,
		)
	return {"created": created, "skipped": skipped}


def _qty_for_employee(employee: str, sc, start_date, end_date) -> float:
	rows = _attendance_rows(employee, start_date, end_date)
	if not rows:
		return 0.0

	total = 0.0
	matched_any = False
	for row in rows:
		contribution = evaluate_rule(row, sc, employee)
		if contribution > 0:
			matched_any = True
			total += contribution

	if (sc.custom_unit or "Per Day") == "Flat per Period":
		return 1.0 if matched_any else 0.0
	return total


def evaluate_rule(row, sc, employee: str) -> float:
	condition = sc.custom_condition_type
	status = row.status
	working_hours = flt(row.working_hours)
	unit = sc.custom_unit or "Per Day"
	present_statuses = get_present_statuses()

	if condition == "Status = Present":
		if status in present_statuses:
			return _per_unit(unit, day=1.0, hours=working_hours)
		if status == "Half Day":
			return _per_unit(unit, day=0.5, hours=working_hours)
		return 0.0

	if condition == "Status = Half Day":
		return 1.0 if status == "Half Day" else 0.0

	if condition == "Worked on Holiday":
		if not row.custom_worked_on_holiday:
			return 0.0
		if status not in present_statuses and status != "Half Day":
			return 0.0
		return _per_unit(unit, day=1.0, hours=working_hours)

	if condition in ("Early Entry Before", "Late Stay After", "Late Arrival After"):
		offset_seconds = flt(sc.custom_time_offset_hours) * 3600.0
		if condition == "Early Entry Before":
			seconds = flt(row.custom_early_entry)
		elif condition == "Late Stay After":
			seconds = flt(row.custom_late_exit)
		else:
			seconds = flt(row.custom_late_entry)
		if seconds <= 0 or seconds < offset_seconds:
			return 0.0
		return _per_unit(unit, day=1.0, hours=seconds / 3600.0)

	return 0.0


def _per_unit(unit: str, day: float, hours: float) -> float:
	if unit == "Per Hour":
		return flt(hours)
	if unit == "Flat per Period":
		return 1.0 if day > 0 else 0.0
	return flt(day)


def _employee_holiday_list(employee: str) -> str:
	emp = frappe.get_cached_doc("Employee", employee)
	if emp.holiday_list:
		return emp.holiday_list
	company = emp.company
	if not company:
		return ""
	return frappe.db.get_value("Company", company, "default_holiday_list") or ""


def set_holiday_flag(doc, _method=None):
	"""doc_event hook on Attendance.validate.

	Auto-populates the read-only `custom_worked_on_holiday` checkbox by checking
	whether the attendance_date matches a Holiday row in the employee's
	Holiday List (or the company's default Holiday List if the employee has none).
	"""
	if not (doc.employee and doc.attendance_date):
		doc.custom_worked_on_holiday = 0
		return

	emp = frappe.get_cached_doc("Employee", doc.employee)
	holiday_list = emp.holiday_list or (
		frappe.db.get_value("Company", emp.company, "default_holiday_list")
		if emp.company else None
	)

	doc.custom_worked_on_holiday = int(
		holiday_list and frappe.db.exists("Holiday", {
			"parent": holiday_list,
			"holiday_date": doc.attendance_date,
		})
	)


@frappe.whitelist()
def recompute_holiday_flags(start_date=None, end_date=None) -> dict:
	"""Re-evaluate `custom_worked_on_holiday` on existing Attendance rows.

	Run after editing a Holiday List, or as a one-time backfill on patch install.
	If no dates passed, scans every Attendance row.
	"""
	filters = {}
	if start_date and end_date:
		filters["attendance_date"] = ["between", [start_date, end_date]]
	rows = frappe.get_all(
		"Attendance",
		filters=filters,
		fields=["name", "employee", "attendance_date", "custom_worked_on_holiday"],
	)
	updated = 0
	for r in rows:
		if not r.employee or not r.attendance_date:
			continue
		holiday_list = _employee_holiday_list(r.employee)
		new_flag = 0
		if holiday_list and frappe.db.exists(
			"Holiday",
			{"parent": holiday_list, "holiday_date": r.attendance_date},
		):
			new_flag = 1
		if (r.custom_worked_on_holiday or 0) != new_flag:
			frappe.db.set_value(
				"Attendance",
				r.name,
				"custom_worked_on_holiday",
				new_flag,
				update_modified=False,
			)
			updated += 1
	frappe.db.commit()
	return {"scanned": len(rows), "updated": updated}


def _skip_for_ot_eligibility(emp_doc, sc) -> bool:
	if sc.custom_condition_type in ("Late Stay After", "Early Entry Before"):
		return not bool(getattr(emp_doc, "custom_ot_eligibility", 0))
	return False


def get_attendance_driven_components() -> list:
	names = frappe.get_all(
		"Salary Component",
		filters={"custom_is_attendance_driven": 1, "disabled": 0},
		pluck="name",
	)
	return [frappe.get_cached_doc("Salary Component", n) for n in names]


def _attendance_rows(employee: str, start_date, end_date) -> list:
	return frappe.get_all(
		"Attendance",
		filters={
			"employee": employee,
			"attendance_date": ["between", [start_date, end_date]],
			"docstatus": 1,
		},
		fields=[
			"name",
			"attendance_date",
			"status",
			"working_hours",
			"custom_worked_on_holiday",
			"custom_late_entry",
			"custom_early_entry",
			"custom_early_exit",
			"custom_late_exit",
		],
	)


def _get_employee_overrides(employee: str) -> dict:
	rows = frappe.get_all(
		"Employee Attendance Allowance",
		filters={"parent": employee, "parenttype": "Employee"},
		fields=["salary_component", "rate", "eligible", "effective_from"],
	)
	return {r.salary_component: r for r in rows}


def _resolve_rate(emp_overrides: dict, sc):
	override = emp_overrides.get(sc.name)
	if override:
		if not override.get("eligible"):
			return None
		rate = flt(override.get("rate"))
		if rate:
			return rate
	default_rate = flt(getattr(sc, "custom_default_rate", 0))
	return default_rate if default_rate else None


def _employees_in_payroll_entry(pe) -> list:
	return frappe.get_all(
		"Payroll Employee Detail",
		filters={"parent": pe.name, "parenttype": "Payroll Entry"},
		pluck="employee",
	)


def _delete_existing_draft(employee: str, salary_component: str, payroll_date) -> None:
	existing = frappe.get_all(
		"Additional Salary",
		filters={
			"employee": employee,
			"salary_component": salary_component,
			"payroll_date": payroll_date,
			"docstatus": 0,
			"custom_source": SOURCE_TAG,
		},
		pluck="name",
	)
	for name in existing:
		frappe.delete_doc("Additional Salary", name, force=True, ignore_permissions=True)


def _make_additional_salary(
	employee: str,
	salary_component,
	amount: float,
	payroll_date,
	company: str,
	qty: float,
	rate: float,
):
	doc = frappe.new_doc("Additional Salary")
	doc.employee = employee
	doc.salary_component = salary_component.name
	doc.amount = amount
	doc.payroll_date = payroll_date
	doc.company = company
	doc.type = salary_component.type or "Earning"
	doc.is_recurring = 0
	doc.overwrite_salary_structure_amount = 0
	doc.custom_source = SOURCE_TAG
	doc.notes = (
		f"Auto-generated by Nepal HRMS attendance allowance calculator. "
		f"qty={qty} × rate={rate} = {amount} "
		f"(condition: {salary_component.custom_condition_type}, unit: {salary_component.custom_unit or 'Per Day'})"
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc
