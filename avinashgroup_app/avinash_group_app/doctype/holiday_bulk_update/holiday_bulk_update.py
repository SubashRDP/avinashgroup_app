"""One screen that writes a holiday into whichever Holiday Lists you choose.

Seven companies, each with a common list and a women-only copy — fourteen lists
for FY 83/84. A holiday announced mid-year, or a festival date the client
corrects, otherwise has to be typed into every one of them by hand; the list that
gets missed surfaces in payroll, when everyone on it is marked Absent on a day the
rest of the group had off.

Put the date and the name on this document, leave "All Holiday Lists" ticked for
the whole group, or untick it and pick the lists — a women-only day takes only the
(Women) lists, a single branch's festival only that company's two.

The writing lives in `avinashgroup_app.hr.holiday_lists`; this controller holds
the form and records what the last run did.

Deliberately narrow: this screen only ADDS. Taking a holiday out again is done on
the Holiday List itself, where the row can be seen in context before it goes.
For a date already past, attendance marked that day is brought in line
(hr/holiday_backdate.py): worked-on-holiday flags set, stale Absent rows cleared,
paid months skipped and named. No Holiday List is created or deleted here.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from avinashgroup_app.hr.holiday_backdate import follow_up
from avinashgroup_app.hr.holiday_lists import apply_holiday_change


class HolidayBulkUpdate(Document):
	def validate(self):
		if not self.all_holiday_lists and not self.holiday_lists:
			frappe.throw(_("Choose the Holiday Lists, or tick All Holiday Lists"))

	def chosen_lists(self):
		"""None means every Holiday List."""
		return None if self.all_holiday_lists else [d.holiday_list for d in self.holiday_lists]

	@frappe.whitelist()
	def apply(self):
		"""Write the holiday to the chosen lists and return the per-list report."""
		report = apply_holiday_change(
			action="Add Holiday",
			holiday_date=self.holiday_date,
			description=self.description,
			holiday_lists=self.chosen_lists(),
		)

		# Every chosen list that now carries the date, whether this run added it or
		# an earlier one did: the attendance follow-up is safe to repeat.
		lists = self.chosen_lists() or frappe.get_all("Holiday List", pluck="name")
		lists = frappe.get_all(
			"Holiday",
			filters={"parent": ("in", lists), "holiday_date": self.holiday_date},
			pluck="parent",
			distinct=True,
		)
		report["attendance"] = follow_up(self.holiday_date, lists)

		att = report["attendance"]
		result = (
			f"Added {self.holiday_date}: "
			f"{len(report['changed'])} list(s) changed, {len(report['skipped'])} skipped"
		)
		if att["worked"] or att["absent_cleared"] or att["paid_skipped"]:
			result += (
				f"; attendance: {len(att['worked'])} marked worked on holiday, "
				f"{len(att['absent_cleared'])} Absent cleared, {len(att['paid_skipped'])} skipped (paid)"
			)
		self.db_set("last_applied_on", now_datetime(), update_modified=False)
		self.db_set("result", result, update_modified=False)
		frappe.db.commit()
		return report
