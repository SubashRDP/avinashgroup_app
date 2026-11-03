"""Shift Early Closure, many days at once: a month sheet, and an Excel import.

Closing early is rarely a one-off — a festival week, a strike, load-shedding
days — and one dialog per day meant typing the company, the date and the
reason over and over. The sheet lists every day of a BS month already filled
in (miti, weekday, AD date, the company's holidays, closures already made,
days whose salary is already paid), so HR types only a closing time on the
days that closed early. One shift at a time, the way HR closes them; one
reason at the top covers every row left without its own.

The same sheet comes out as an .xlsx template with the month's days on it,
and an .xlsx / .csv in that shape — or any sheet with a Date or Miti column
and a Closed At column — fills the sheet back in. Nothing is saved until the
sheet is submitted, so an import can be checked first.

Each filled day becomes its own Shift Early Closure through
shift_early_closure.make_closure — the doctype's own rules, nothing bypassed —
in its own savepoint: a day refused (already closed, salary paid, time outside
every shift) is reported on its row and the other days still go through.

Front end: public/js/shift_early_closure_sheet.js.
"""

import datetime
import io
import re

import frappe
from frappe import _
from frappe.utils import add_days, getdate, strip_html, today

from avinashgroup_app.avinash_group_app.doctype.salary_assignment_upload.salary_assignment_upload import (
	read_table,
	text,
)
from avinashgroup_app.hr.bs_calendar import month_of_date
from avinashgroup_app.hr.bs_dates import to_miti
from avinashgroup_app.hr.shift_early_closure import CLOSURE_ROLES, closures_between, make_closure
from avinashgroup_app.payroll.special_payout import REGULAR_SLIPS
from avinashgroup_app.utils.bs_converter import nepali_to_english_converter

SHEET = "Early Closures"
COLUMNS = ("Miti", "Date (AD)", "Day", "Note", "Closed At", "Reason", "Shift")

# Header spellings read back from an uploaded sheet (lower-cased).
DATE_HEADERS = ("date (ad)", "date", "ad date", "closure date")
MITI_HEADERS = ("miti", "date (bs)", "bs date", "nepali date")
TIME_HEADERS = ("closed at", "close at", "closing time", "time")
REASON_HEADERS = ("reason",)
SHIFT_HEADERS = ("shifts", "shift")

# A year this high is Bikram Sambat, not AD (BS runs about 56-57 years ahead).
BS_YEAR_FROM = 2050


def _hhmm(value):
	return str(value)[:5] if value else ""


@frappe.whitelist()
def month_sheet(company: str, date: str | None = None) -> dict:
	"""Every day of the BS month holding `date` (default today), with what is
	already known about it: holiday, closures made, salary already paid."""
	frappe.only_for(CLOSURE_ROLES)
	month = month_of_date(company, date or today())
	start, end = month.start_date, month.end_date

	holidays = {}
	holiday_list = _holiday_list(company, start, end)
	if holiday_list:
		for h in frappe.get_all(
			"Holiday",
			filters={"parent": holiday_list, "holiday_date": ("between", [start, end])},
			fields=["holiday_date", "description"],
		):
			holidays[getdate(h.holiday_date)] = strip_html(h.description or "").strip() or _("Holiday")

	closures = closures_between(company, start, end)

	paid = []
	for slip in frappe.get_all(
		"Salary Slip",
		filters={"company": company, "docstatus": 1, "start_date": ("<=", end), "end_date": (">=", start), **REGULAR_SLIPS},
		fields=["start_date", "end_date"],
		distinct=True,
	):
		paid.append((getdate(slip.start_date), getdate(slip.end_date)))

	rows = []
	day = start
	while day <= end:
		rows.append(
			{
				"date": str(day),
				"miti": to_miti(day) or "",
				"weekday": day.strftime("%a"),
				"holiday": holidays.get(day, ""),
				"paid": any(a <= day <= b for a, b in paid),
				"closures": [
					{
						"name": c.name,
						"close_at": _hhmm(c.close_at),
						"reason": c.reason,
						"shifts": sorted(c.shifts or []),
					}
					for c in closures.get((company, day), [])
				],
			}
		)
		day = add_days(day, 1)

	return {
		"company": company,
		"label": month.label,
		"from_date": str(start),
		"to_date": str(end),
		"rows": rows,
	}


def _holiday_list(company, start, end):
	"""The company's Holiday List for these dates: its default when that covers
	them, else the newest list tagged with the company (custom_company) that
	does. Most companies here have no default and one list per fiscal year."""
	overlaps = {"from_date": ("<=", end), "to_date": (">=", start)}
	default = frappe.get_cached_value("Company", company, "default_holiday_list")
	if default and frappe.db.exists("Holiday List", {"name": default, **overlaps}):
		return default
	if not frappe.db.has_column("Holiday List", "custom_company"):
		return default
	return frappe.db.get_value(
		"Holiday List", {"custom_company": company, **overlaps}, "name", order_by="from_date desc"
	) or default


@frappe.whitelist()
def close_days(company: str, rows, reason: str | None = None, shifts=None) -> list:
	"""Submit a Shift Early Closure for every row with a closing time.

	rows: [{date, close_at, reason?, shifts?}]. A row's own reason and shifts
	win; otherwise the sheet-wide ones apply. Returns, per row, the closure
	made ({date, name, updated}) or why not ({date, error}).
	"""
	frappe.only_for(CLOSURE_ROLES)
	rows = frappe.parse_json(rows) or []
	shifts = frappe.parse_json(shifts) if isinstance(shifts, str) else (shifts or [])

	results = []
	# make_closure's per-day "n rows re-measured" alert, times thirty, is noise;
	# the sheet reports each day itself.
	muted = frappe.flags.mute_messages
	frappe.flags.mute_messages = True
	try:
		for row in rows:
			if not row.get("close_at"):
				continue
			why = (row.get("reason") or reason or "").strip()
			frappe.db.savepoint("early_closure_day")
			try:
				doc = make_closure(company, row["date"], row["close_at"], why, row.get("shifts") or shifts)
				results.append({"date": row["date"], "name": doc.name, "updated": doc.attendance_updated})
			except Exception as e:
				frappe.db.rollback(save_point="early_closure_day")
				message = strip_html(str(e)).strip() or _("Could not be saved")
				results.append({"date": row["date"], "error": message})
	finally:
		frappe.flags.mute_messages = muted
		frappe.local.message_log = []
	return results


@frappe.whitelist()
def download_template(company: str, date: str | None = None, shift: str | None = None):
	"""The month sheet as .xlsx for one shift: fill Closed At (and Reason) on the
	days that closed. A day that shift is already closed on says so."""
	from openpyxl import Workbook
	from openpyxl.styles import Font, PatternFill

	sheet = month_sheet(company, date)
	wb = Workbook()
	ws = wb.active
	ws.title = SHEET
	ws.append(COLUMNS)
	for r in sheet["rows"]:
		done = next((c for c in r["closures"] if not c["shifts"] or not shift or shift in c["shifts"]), None)
		note = (
			_("Already closed early ({0})").format(done["name"]) if done
			else _("Salary paid") if r["paid"]
			else r["holiday"]
		)
		ws.append(
			[
				r["miti"],
				getdate(r["date"]),
				r["weekday"],
				note,
				done["close_at"] if done else "",
				done["reason"] if done else "",
				shift or "",
			]
		)

	for cell in ws[1]:
		cell.font = Font(bold=True)
		cell.fill = PatternFill("solid", fgColor="DDEBF7")
	for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
		row[0].number_format = "yyyy-mm-dd"
	for col, width in zip("ABCDEFG", (12, 12, 6, 28, 10, 40, 26)):
		ws.column_dimensions[col].width = width
	ws.freeze_panes = "A2"

	out = io.BytesIO()
	wb.save(out)
	abbr = frappe.get_cached_value("Company", company, "abbr")
	frappe.response.filename = f"Early Closures - {abbr} - {sheet['label']}{' - ' + shift if shift else ''}.xlsx"
	frappe.response.filecontent = out.getvalue()
	frappe.response.type = "binary"


@frappe.whitelist()
def read_file(file_url: str) -> dict:
	"""Rows of an uploaded .xlsx / .csv: {rows: [{date, close_at, reason, shifts}], errors}.

	Only lines with a closing time count; the template's other days are blank.
	The date is the Date (AD) column, else the Miti column. Nothing is saved.
	"""
	frappe.only_for(CLOSURE_ROLES)
	table = read_table(file_url)
	if not table:
		frappe.throw(_("The file is empty."))

	header = [text(c).lower() for c in table[0]]

	def col(names):
		return next((i for i, h in enumerate(header) if h in names), None)

	c_date, c_miti, c_time = col(DATE_HEADERS), col(MITI_HEADERS), col(TIME_HEADERS)
	c_reason, c_shifts = col(REASON_HEADERS), col(SHIFT_HEADERS)
	if c_time is None or (c_date is None and c_miti is None):
		frappe.throw(_("The first row must name a Date (or Miti) column and a Closed At column."))

	def cell(cells, i):
		return cells[i] if i is not None and i < len(cells) else None

	rows, errors = [], []
	for line, cells in enumerate(table[1:], start=2):
		raw_time = cell(cells, c_time)
		if text(raw_time) == "":
			continue
		day = _parse_date(cell(cells, c_date)) or _parse_date(cell(cells, c_miti))
		close_at = _parse_time(raw_time)
		if not day:
			errors.append(_("Row {0}: no date it could read").format(line))
			continue
		if not close_at:
			errors.append(_("Row {0}: '{1}' is not a time").format(line, text(raw_time)))
			continue
		shifts = [s.strip() for s in text(cell(cells, c_shifts)).split(",") if s.strip()]
		rows.append({"date": str(day), "close_at": close_at, "reason": text(cell(cells, c_reason)), "shifts": shifts})
	return {"rows": rows, "errors": errors}


def _parse_date(value):
	"""An AD date from a date cell, or a "YYYY-MM-DD" string in AD or BS."""
	if value is None or text(value) == "":
		return None
	if isinstance(value, datetime.datetime):
		return value.date()
	if isinstance(value, datetime.date):
		return value
	m = re.match(r"^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text(value))
	if not m:
		return None
	y, mo, d = (int(x) for x in m.groups())
	try:
		if y >= BS_YEAR_FROM:
			return getdate(nepali_to_english_converter(y, mo, d))
		return datetime.date(y, mo, d)
	except Exception:
		return None


def _parse_time(value):
	"""'HH:MM:00' from a time cell, an Excel day fraction, or text like 14:00 / 2 PM."""
	if isinstance(value, datetime.datetime):
		value = value.time()
	if isinstance(value, datetime.time):
		return value.strftime("%H:%M:00")
	if isinstance(value, (int, float)) and 0 < value < 1:
		minutes = round(value * 24 * 60)
		return f"{minutes // 60:02d}:{minutes % 60:02d}:00"
	m = re.match(r"^\s*(\d{1,2})(?:[:.](\d{2}))?(?::\d{2})?\s*([ap]\.?m\.?)?\s*$", text(value), re.I)
	if not m:
		return None
	hour, minute, half = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
	if half.startswith("p") and hour < 12:
		hour += 12
	if half.startswith("a") and hour == 12:
		hour = 0
	if hour > 23 or minute > 59 or (m.group(2) is None and not half):
		return None
	return f"{hour:02d}:{minute:02d}:00"
