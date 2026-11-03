"""Salary Structure Assignments for many people at once, from one spreadsheet.

Without it, HR makes one assignment per person through the form: pick the
structure, then fix the Allowances table row by row (payroll/allowance.py) —
195 people, 27 different allowance mixes. Data Import does not help either: a
child table there is one spreadsheet row per allowance, with the employee
repeated on each, which nobody can read or check.

So the sheet here is the shape HR already thinks in: one row per person, one
column per allowance, the cell being that person's rate.

  Download Template  every active employee of the company, pre-filled from the
                     assignment in force on From Date, so HR changes only what
                     is new; untouched rows are left out on reading.
  Filled Template    attaching it replaces the Employees table. Each row is
                     checked by building the assignment in memory and running
                     its real validate (HRMS's plus validate_assignment_allowances),
                     so a row marked Ready is one that will save.
  Submit             one submitted assignment per row; Cancel cancels them.

Rows nobody filled in (no Base, Initial Basic or allowance) and rows exactly
the same as the person's current assignment are left out, so HR fills in only
the people who change and need not delete the rest.

Cells: an allowance left blank or 0 is not given — on the assignment no row
means not paid. A column whose rate is worked out from basic (overtime) takes
Yes / No. SSF Applicable blank means Yes.

Deliberately narrow: this does not change anyone's pay mid-year with arrears
or raise a structure's rate list — that is Salary Revision, which also keeps
the person's other allowances. Here the row is the whole assignment: an
allowance not in the file is not on the new assignment.
"""

import io
import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, strip_html

from avinashgroup_app.payroll.allowance import NOT_ON_ASSIGNMENT, rate_is_computed, unit_for
from avinashgroup_app.payroll.year_rollover import tax_slab_for

SHEET = "Assignments"
EMPLOYEE, NAME, STRUCTURE, BASE, INITIAL_BASIC, SSF = (
	"Employee",
	"Employee Name",
	"Salary Structure",
	"Base",
	"Initial Basic",
	"SSF Applicable",
)
FIXED_COLUMNS = (EMPLOYEE, NAME, STRUCTURE, BASE, INITIAL_BASIC, SSF)
YES = ("yes", "y", "1", "true")
NO = ("no", "n", "0", "false")


class SalaryAssignmentUpload(Document):
	def validate(self):
		if self.upload_file and (self.is_new() or self.has_value_changed("upload_file")):
			self.read_rows_from_file()
		if not self.employees:
			frappe.throw(
				_("Nothing to upload: attach the filled template, with at least one person whose salary is new")
			)
		self.check_rows()
		self.employee_count = len(self.employees)
		self.error_count = sum(1 for row in self.employees if row.status == "Error")

	def before_submit(self):
		if self.error_count:
			frappe.throw(
				_("{0} row(s) are marked Error. Fix them in the file and attach it again.").format(self.error_count)
			)

	def on_submit(self):
		for row in self.employees:
			doc = self.build_assignment(row)
			doc.flags.ignore_permissions = True
			doc.insert()
			doc.submit()
			row.db_set({"salary_structure_assignment": doc.name, "status": "Created", "message": ""})

	def on_cancel(self):
		for row in self.employees:
			if not row.salary_structure_assignment:
				continue
			doc = frappe.get_doc("Salary Structure Assignment", row.salary_structure_assignment)
			if doc.docstatus == 1:
				doc.flags.ignore_permissions = True
				doc.cancel()
			row.db_set("status", "Ready")

	@frappe.whitelist()
	def read_file_again(self):
		"""Re-read the attached file (the same file corrected and attached under the same name)."""
		if not self.upload_file:
			frappe.throw(_("Attach the filled template first"))
		self.read_rows_from_file()
		self.save()

	# ── the file ──────────────────────────────────────────────────────────

	def read_rows_from_file(self):
		"""Replace Employees with the rows of the attached file. Throws on a header it cannot place."""
		table = read_table(self.upload_file)
		if not table:
			frappe.throw(_("The file is empty"))
		header = [str(h or "").strip() for h in table[0]]
		columns = header_columns(header)

		self.set("employees", [])
		left_out = {"blank": 0, "unchanged": 0}
		for line_no, values in enumerate(table[1:], start=2):
			cells = {header[i]: values[i] if i < len(values) else None for i in range(len(header))}
			employee = text(cells.get(columns["fixed"].get(EMPLOYEE)))
			if not employee:
				continue
			problems = []
			rates = {}
			for column, allowance in columns["allowances"].items():
				value = cells.get(column)
				if rate_is_computed(allowance):
					flag = text(value).lower()
					if flag in YES:
						rates[allowance] = 0
					elif flag and flag not in NO:
						problems.append(_("{0}: type Yes or No").format(allowance))
					continue
				rate, ok = number(value)
				if not ok:
					problems.append(_("{0}: {1} is not a number").format(allowance, text(value)))
				elif rate:
					rates[allowance] = rate

			base, base_ok = number(cells.get(columns["fixed"].get(BASE)))
			initial_basic, initial_ok = number(cells.get(columns["fixed"].get(INITIAL_BASIC)))
			if not base_ok:
				problems.append(_("Base is not a number"))
			if not initial_ok:
				problems.append(_("Initial Basic is not a number"))
			ssf = text(cells.get(columns["fixed"].get(SSF))).lower()
			if ssf and ssf not in YES + NO:
				problems.append(_("SSF Applicable: type Yes or No"))

			row = {
				"employee": employee,
				"salary_structure": text(cells.get(columns["fixed"].get(STRUCTURE))) or None,
				"base": base,
				"initial_basic": initial_basic,
				"ssf_applicable": 0 if ssf in NO else 1,
			}
			if not problems:
				if not base and not initial_basic and not rates:
					left_out["blank"] += 1  # a person in the template nobody filled in
					continue
				if self.is_unchanged(row, rates):
					left_out["unchanged"] += 1
					continue

			self.append(
				"employees",
				{
					**row,
					"allowance_rates": json.dumps(rates),
					"status": "Error" if problems else "",
					"file_error": 1 if problems else 0,
					"message": _("Line {0}: {1}").format(line_no, "; ".join(problems)) if problems else "",
				},
			)

		if any(left_out.values()):
			frappe.msgprint(
				_("Left out {0} blank row(s) and {1} row(s) the same as the person's current salary.").format(
					left_out["blank"], left_out["unchanged"]
				),
				alert=True,
			)

	def is_unchanged(self, row: dict, rates: dict) -> bool:
		"""The row says exactly what the assignment in force on From Date already says, so there is nothing to make."""
		current = frappe.db.get_value(
			"Salary Structure Assignment",
			{"employee": row["employee"], "docstatus": 1, "from_date": ["<=", getdate(self.from_date)]},
			["name", "salary_structure", "base", "custom_initial_basic", "custom_ssf_applicable"],
			as_dict=True,
			order_by="from_date desc",
		)
		if not current:
			return False
		# An allowance worked out from basic is given or not; any rate an old row carries is ignored.
		current_rates = {
			a: 0 if rate_is_computed(a) else flt(r, 2)
			for a, r in frappe.get_all(
				"Assignment Allowance",
				filters={"parent": current.name, "parenttype": "Salary Structure Assignment"},
				fields=["allowance", "rate"],
				as_list=True,
			)
		}
		return (
			(row["salary_structure"] or self.salary_structure) == current.salary_structure
			and flt(row["base"], 2) == flt(current.base, 2)
			and flt(row["initial_basic"], 2) == flt(current.custom_initial_basic, 2)
			and cint(row["ssf_applicable"]) == cint(current.custom_ssf_applicable)
			and {a: flt(r, 2) for a, r in rates.items()} == current_rates
		)

	# ── checking a row ────────────────────────────────────────────────────

	def check_rows(self):
		"""Mark each row Ready or Error by validating the assignment it would make."""
		seen = {}
		for row in self.employees:
			if row.file_error:
				continue  # the file itself was wrong on this line; nothing to build
			row.status, row.message = "Ready", ""
			if not frappe.db.exists("Employee", row.employee):
				row.status, row.message = "Error", _("No employee {0}").format(row.employee)
				continue
			row.employee_name = frappe.db.get_value("Employee", row.employee, "employee_name")
			if row.employee in seen:
				row.status, row.message = "Error", _("Also on row {0}").format(seen[row.employee])
				continue
			seen[row.employee] = row.idx
			row.salary_structure = row.salary_structure or self.salary_structure
			row.allowances = describe(rates_of(row))
			try:
				self.validate_assignment(row)
			except frappe.ValidationError as e:
				row.status, row.message = "Error", strip_html(str(e))

	def validate_assignment(self, row):
		"""Run everything an assignment's save would run, without saving it. Raises what the save would raise."""
		if frappe.db.get_value("Employee", row.employee, "company") != self.company:
			frappe.throw(_("{0} is not an employee of {1}").format(row.employee, self.company))
		missing = []
		if not row.salary_structure:
			missing.append(_("No Salary Structure: fill the cell, or the Default Salary Structure above"))
		elif frappe.db.get_value("Salary Structure", row.salary_structure, "docstatus") != 1:
			missing.append(_("Salary Structure {0} is not submitted").format(row.salary_structure))
		if flt(row.base) <= 0:
			missing.append(_("Base is missing"))
		if missing:
			frappe.throw("; ".join(missing))

		doc = self.build_assignment(row)
		messages = list(frappe.local.message_log)
		try:
			doc.run_method("validate")  # HRMS checks + doc_events (allowance rows)
		finally:
			frappe.local.message_log = messages  # HRMS's opening-entry notice, once per row

	def build_assignment(self, row):
		current = frappe.db.get_value(
			"Salary Structure Assignment",
			{"employee": row.employee, "docstatus": 1, "from_date": ["<=", getdate(self.from_date)]},
			["variable", "payroll_payable_account"],
			as_dict=True,
			order_by="from_date desc",
		) or frappe._dict()
		doc = frappe.new_doc("Salary Structure Assignment")
		doc.update(
			{
				"employee": row.employee,
				"company": self.company,
				"salary_structure": row.salary_structure,
				"from_date": self.from_date,
				"base": flt(row.base),
				"variable": flt(current.variable),
				"currency": frappe.get_cached_value("Company", self.company, "default_currency"),
				"income_tax_slab": tax_slab_for(self.company, self.from_date),
				"payroll_payable_account": current.payroll_payable_account,
				"custom_initial_basic": flt(row.initial_basic),
				"custom_ssf_applicable": cint(row.ssf_applicable),
			}
		)
		for allowance, rate in rates_of(row).items():
			doc.append("custom_allowances", {"allowance": allowance, "rate": rate})
		return doc


# ── the template ─────────────────────────────────────────────────────────


@frappe.whitelist()
def download_template(company: str, from_date: str, salary_structure: str | None = None):
	"""The sheet to fill: every active employee of `company`, as paid on `from_date`."""
	frappe.has_permission("Salary Assignment Upload", "create", throw=True)
	from openpyxl import Workbook
	from openpyxl.styles import Font, PatternFill

	allowances = template_allowances(company)
	header = list(FIXED_COLUMNS) + [allowance_header(a) for a in allowances]

	wb = Workbook()
	ws = wb.active
	ws.title = SHEET
	ws.append(header)
	for employee in frappe.get_all(
		"Employee",
		filters={"company": company, "status": "Active"},
		fields=["name", "employee_name"],
		order_by="name asc",
	):
		ws.append(template_row(employee, from_date, salary_structure, allowances))

	for cell in ws[1]:
		cell.font = Font(bold=True)
		cell.fill = PatternFill("solid", fgColor="DDEBF7")
	ws.freeze_panes = "C2"
	ws.column_dimensions["A"].width = 16
	ws.column_dimensions["B"].width = 28
	ws.column_dimensions["C"].width = 26
	for i in range(4, len(header) + 1):
		ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(14, len(header[i - 1]) + 2)

	out = io.BytesIO()
	wb.save(out)
	frappe.response.filename = f"Salary Assignment Upload - {frappe.get_cached_value('Company', company, 'abbr')}.xlsx"
	frappe.response.filecontent = out.getvalue()
	frappe.response.type = "binary"


def template_allowances(company: str) -> list[str]:
	"""Every allowance an assignment can carry: those on the company's structures first, in their order."""
	listed = frappe.db.sql(
		"""
		select r.allowance from `tabStructure Allowance Rate` r
		join `tabSalary Structure` s on s.name = r.parent
		where r.parenttype = 'Salary Structure' and s.company = %s and s.docstatus = 1
		order by s.name, r.idx
		""",
		company,
		pluck=True,
	)
	every = frappe.get_all(
		"Salary Component",
		filters={"custom_is_allowance": 1, "disabled": 0, "custom_allowance_kind": ["not in", NOT_ON_ASSIGNMENT]},
		pluck="name",
		order_by="name asc",
	)
	return list(dict.fromkeys([a for a in listed if a in every] + every))


def template_row(employee, from_date, default_structure, allowances) -> list:
	current = frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee.name, "docstatus": 1, "from_date": ["<=", getdate(from_date)]},
		["name", "salary_structure", "base", "custom_initial_basic", "custom_ssf_applicable"],
		as_dict=True,
		order_by="from_date desc",
	)
	if not current:
		return [employee.name, employee.employee_name, default_structure or "", None, None, "Yes"]
	rates = dict(
		frappe.get_all(
			"Assignment Allowance",
			filters={"parent": current.name, "parenttype": "Salary Structure Assignment"},
			fields=["allowance", "rate"],
			as_list=True,
		)
	)
	cells = []
	for allowance in allowances:
		if allowance not in rates:
			cells.append(None)
		elif rate_is_computed(allowance):
			cells.append("Yes")
		else:
			cells.append(flt(rates[allowance]))
	return [
		employee.name,
		employee.employee_name,
		current.salary_structure,
		flt(current.base),
		flt(current.custom_initial_basic) or None,
		"Yes" if cint(current.custom_ssf_applicable) else "No",
		*cells,
	]


def allowance_header(allowance: str) -> str:
	unit = unit_for(allowance)
	return f"{allowance} ({unit})" if unit else allowance


def header_columns(header: list[str]) -> dict:
	"""{"fixed": {Employee: header text, …}, "allowances": {header text: allowance}}; throws on any it cannot place."""
	fixed_by_key = {c.lower(): c for c in FIXED_COLUMNS}
	every = frappe.get_all(
		"Salary Component",
		filters={"custom_is_allowance": 1, "disabled": 0, "custom_allowance_kind": ["not in", NOT_ON_ASSIGNMENT]},
		pluck="name",
	)
	allowance_by_key = {}
	for allowance in every:
		allowance_by_key[allowance.lower()] = allowance
		allowance_by_key[allowance_header(allowance).lower()] = allowance

	fixed, allowances, unknown = {}, {}, []
	for column in header:
		key = column.lower()
		if not key:
			continue
		if key in fixed_by_key:
			fixed[fixed_by_key[key]] = column
		elif key in allowance_by_key:
			if allowance_by_key[key] in allowances.values():
				frappe.throw(_("Column {0} appears twice").format(column))
			allowances[column] = allowance_by_key[key]
		else:
			unknown.append(column)
	if unknown:
		frappe.throw(
			_("These columns are not an allowance that goes on an assignment: {0}. Download the template again.").format(
				", ".join(unknown)
			)
		)
	for required in (EMPLOYEE, BASE):
		if required not in fixed:
			frappe.throw(_("The file has no {0} column").format(required))
	return {"fixed": fixed, "allowances": allowances}


def read_table(file_url: str) -> list[list]:
	"""The attached .xlsx (sheet Assignments, else the first) or .csv as rows of cells."""
	content = frappe.get_doc("File", {"file_url": file_url}).get_content()
	if file_url.lower().endswith(".csv"):
		from frappe.utils.csvutils import read_csv_content

		return read_csv_content(content)
	if not file_url.lower().endswith(".xlsx"):
		frappe.throw(_("Attach the template as .xlsx or .csv"))
	from openpyxl import load_workbook

	wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
	ws = wb[SHEET] if SHEET in wb.sheetnames else wb.worksheets[0]
	return [list(r) for r in ws.iter_rows(values_only=True) if any(c not in (None, "") for c in r)]


# ── cells ────────────────────────────────────────────────────────────────


def text(value) -> str:
	if value is None:
		return ""
	if isinstance(value, float) and value.is_integer():
		value = int(value)
	return str(value).strip()


def number(value) -> tuple[float, bool]:
	"""(the cell as a number, whether it was one); blank is (0, True)."""
	if value is None or text(value) == "":
		return 0.0, True
	if isinstance(value, (int, float)):
		return float(value), True
	try:
		return float(text(value).replace(",", "")), True
	except ValueError:
		return 0.0, False


def rates_of(row) -> dict:
	return json.loads(row.allowance_rates or "{}")


def describe(rates: dict) -> str:
	parts = []
	for allowance, rate in rates.items():
		if rate_is_computed(allowance):
			parts.append(f"{allowance} ({unit_for(allowance)})")
		else:
			parts.append(f"{allowance}: {frappe.format(rate, {'fieldtype': 'Float'})} {unit_for(allowance)}".strip())
	return "\n".join(parts)
