"""Two Excel imports for attendance HR keeps on paper or in a sheet.

1. Field Duty rows (hr/field_duty.py): who was away on official work, which
   day, from when to when, where. The rows fill a draft Field Duty; HR checks
   it and submits, so the doctype's own rules decide what counts.

2. Punches for people with no device (manual-entry staff, a device that was
   down): employee, date, IN, OUT. Each row goes through the desk's own
   correction (hr/punch_correction.correct_day): the punches are added marked as
   entered by hand with the reason given, the day is re-marked, and an
   Attendance Correction Log row says who did it. A refused row (a paid month,
   a leave day, no shift) is reported on its line and the rest still go in.

Both read .xlsx or .csv (salary_assignment_upload.read_table) and accept dates
in AD or BS and times as cells, Excel fractions or text (09:05, 5 PM)
(shift_early_closure_sheet._parse_date / _parse_time). Reading never saves.
The employee is the Employee ID, or a name that matches exactly one active
employee of the company.

Front end: Field Duty form (field_duty.js, "Import from Excel") and Monthly
Attendance BS ("Import Punches").
"""

import io

import frappe
from frappe import _
from frappe.utils import getdate, strip_html, today

from avinashgroup_app.avinash_group_app.doctype.salary_assignment_upload.salary_assignment_upload import read_table, text
from avinashgroup_app.hr.field_duty import DUTY_ROLES
from avinashgroup_app.hr.punch_correction import CORRECTION_ROLES
from avinashgroup_app.hr.shift_early_closure_sheet import _parse_date, _parse_time

EMPLOYEE_HEADERS = ("employee", "employee id", "id", "employee code")
NAME_HEADERS = ("employee name", "name")
DATE_HEADERS = ("date (ad)", "date", "ad date")
MITI_HEADERS = ("miti", "date (bs)", "bs date")

DUTY_COLUMNS = ("Employee", "Employee Name", "Date (AD)", "Miti", "From", "To", "Place", "Purpose")
PUNCH_COLUMNS = ("Employee", "Employee Name", "Date (AD)", "Miti", "IN", "OUT")


# ───────────────────────────────────────────────────────────── shared ──


def _workbook(columns, company, title):
	from openpyxl import Workbook
	from openpyxl.styles import Font, PatternFill

	wb = Workbook()
	ws = wb.active
	ws.title = title
	ws.append(columns)
	for e in frappe.get_all("Employee", filters={"company": company, "status": "Active"}, fields=["name", "employee_name"], order_by="name"):
		ws.append([e.name, e.employee_name] + [""] * (len(columns) - 2))
	for cell in ws[1]:
		cell.font = Font(bold=True)
		cell.fill = PatternFill("solid", fgColor="DDEBF7")
	for col, width in zip("ABCDEFGH", (16, 26, 12, 12, 9, 9, 18, 30)):
		ws.column_dimensions[col].width = width
	ws.freeze_panes = "C2"
	out = io.BytesIO()
	wb.save(out)
	return out.getvalue()


def _send(content, name):
	frappe.response.filename = name
	frappe.response.filecontent = content
	frappe.response.type = "binary"


def _reader(file_url):
	table = read_table(file_url)
	if not table:
		frappe.throw(_("The file is empty."))
	header = [text(c).lower() for c in table[0]]

	def col(*names):
		return next((i for i, h in enumerate(header) if h in names), None)

	def cell(cells, i):
		return cells[i] if i is not None and i < len(cells) else None

	return table, col, cell


def _employee_finder(company):
	ids = set(frappe.get_all("Employee", filters={"company": company}, pluck="name"))
	by_name = {}
	for e in frappe.get_all("Employee", filters={"company": company, "status": "Active"}, fields=["name", "employee_name"]):
		by_name.setdefault(" ".join((e.employee_name or "").lower().split()), []).append(e.name)

	def find(emp_cell, name_cell):
		emp = text(emp_cell)
		if emp in ids:
			return emp, None
		hits = by_name.get(" ".join(text(name_cell or emp_cell).lower().split()), [])
		if len(hits) == 1:
			return hits[0], None
		if len(hits) > 1:
			return None, _("'{0}' is more than one employee; give the Employee ID").format(text(name_cell or emp_cell))
		return None, _("no {0} employee '{1}'").format(company, emp or text(name_cell))

	return find


# ───────────────────────────────────────────────────────────── field duty ──


@frappe.whitelist()
def download_field_duty_template(company: str):
	"""Every active employee of the company on a row: copy a row per day of duty and fill it in."""
	frappe.only_for(DUTY_ROLES)
	abbr = frappe.get_cached_value("Company", company, "abbr")
	_send(_workbook(DUTY_COLUMNS, company, "Field Duty"), f"Field Duty - {abbr}.xlsx")


@frappe.whitelist()
def read_field_duty_file(file_url: str, company: str) -> dict:
	"""Rows for a Field Duty from an uploaded sheet: {rows: [...], errors: [...]}. Nothing is saved.

	Only lines with a date and both times count; the template's other rows are blank."""
	frappe.only_for(DUTY_ROLES)
	table, col, cell = _reader(file_url)
	c_emp, c_name = col(*EMPLOYEE_HEADERS), col(*NAME_HEADERS)
	c_date, c_miti = col(*DATE_HEADERS), col(*MITI_HEADERS)
	c_from, c_to = col("from", "from time", "start"), col("to", "to time", "end")
	c_place, c_purpose = col("place", "location"), col("purpose", "work", "reason")
	if (c_emp is None and c_name is None) or (c_date is None and c_miti is None) or c_from is None or c_to is None:
		frappe.throw(_("The first row must name Employee, Date (or Miti), From and To columns."))
	find = _employee_finder(company)
	rows, errors = [], []
	for line, cells in enumerate(table[1:], start=2):
		raw_from, raw_to = cell(cells, c_from), cell(cells, c_to)
		day = _parse_date(cell(cells, c_date)) or _parse_date(cell(cells, c_miti))
		if text(raw_from) == "" and text(raw_to) == "" and not day:
			continue
		emp, problem = find(cell(cells, c_emp), cell(cells, c_name))
		start, end = _parse_time(raw_from), _parse_time(raw_to)
		problem = problem or (not day and _("no date it could read")) or (not start and _("From '{0}' is not a time").format(text(raw_from))) \
			or (not end and _("To '{0}' is not a time").format(text(raw_to)))
		if problem:
			errors.append(_("Row {0}: {1}").format(line, problem))
			continue
		rows.append({"employee": emp, "duty_date": str(day), "from_time": start, "to_time": end,
			"place": text(cell(cells, c_place)), "purpose": text(cell(cells, c_purpose))})
	return {"rows": rows, "errors": errors}


# ───────────────────────────────────────────────────────────── punches ──


@frappe.whitelist()
def download_punch_template(company: str):
	"""Every active employee of the company on a row: copy a row per day and fill in IN and OUT."""
	frappe.only_for(CORRECTION_ROLES)
	abbr = frappe.get_cached_value("Company", company, "abbr")
	_send(_workbook(PUNCH_COLUMNS, company, "Punches"), f"Punches - {abbr}.xlsx")


@frappe.whitelist()
def read_punch_file(file_url: str, company: str) -> dict:
	"""Days to enter from an uploaded sheet: {rows: [{employee, employee_name, date, in_time, out_time}], errors}.
	Nothing is saved. A line needs a date and both IN and OUT."""
	frappe.only_for(CORRECTION_ROLES)
	table, col, cell = _reader(file_url)
	c_emp, c_name = col(*EMPLOYEE_HEADERS), col(*NAME_HEADERS)
	c_date, c_miti = col(*DATE_HEADERS), col(*MITI_HEADERS)
	c_in, c_out = col("in", "in time", "first in"), col("out", "out time", "last out")
	if (c_emp is None and c_name is None) or (c_date is None and c_miti is None) or c_in is None or c_out is None:
		frappe.throw(_("The first row must name Employee, Date (or Miti), IN and OUT columns."))
	find = _employee_finder(company)
	rows, errors, seen = [], [], set()
	for line, cells in enumerate(table[1:], start=2):
		raw_in, raw_out = cell(cells, c_in), cell(cells, c_out)
		day = _parse_date(cell(cells, c_date)) or _parse_date(cell(cells, c_miti))
		if text(raw_in) == "" and text(raw_out) == "" and not day:
			continue
		emp, problem = find(cell(cells, c_emp), cell(cells, c_name))
		t_in, t_out = _parse_time(raw_in), _parse_time(raw_out)
		problem = problem or (not day and _("no date it could read")) or (not t_in and _("IN '{0}' is not a time").format(text(raw_in))) \
			or (not t_out and _("OUT '{0}' is not a time").format(text(raw_out))) \
			or (t_out <= t_in and _("OUT {0} is not after IN {1}").format(t_out[:5], t_in[:5])) \
			or ((emp, day) in seen and _("{0} on {1} is on the sheet twice").format(emp, day)) \
			or (day >= getdate(today()) and _("{0} is not over yet; only past days are entered").format(day))
		if problem:
			errors.append(_("Row {0}: {1}").format(line, problem))
			continue
		seen.add((emp, day))
		rows.append({"employee": emp, "employee_name": frappe.db.get_value("Employee", emp, "employee_name"),
			"date": str(day), "in_time": t_in, "out_time": t_out})
	return {"rows": rows, "errors": errors}


@frappe.whitelist(methods=["POST"])
def import_punches(rows, reason: str) -> list:
	"""Enter each day through punch_correction.correct_day, each in its own savepoint.
	Returns one line per row: {employee, date, ok, status | error}."""
	from avinashgroup_app.hr.punch_correction import correct_day

	frappe.only_for(CORRECTION_ROLES)
	reason = strip_html(reason or "").strip()
	if not reason:
		frappe.throw(_("Give a reason. It is kept on the punches and in the Attendance Correction Log."), title=_("Reason Required"))
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	out = []
	for r in rows or []:
		frappe.db.savepoint("punch_import")
		try:
			res = correct_day(r["employee"], r["date"], in_time=r["in_time"], out_time=r["out_time"], reason=reason)
			out.append({"employee": r["employee"], "date": r["date"], "ok": True, "status": res.get("status"),
				"warnings": res.get("warnings") or []})
		except Exception as e:
			frappe.db.rollback(save_point="punch_import")
			out.append({"employee": r["employee"], "date": r["date"], "ok": False,
				"error": strip_html(str(e)) or repr(e)})
		frappe.local.message_log = []
	return out
