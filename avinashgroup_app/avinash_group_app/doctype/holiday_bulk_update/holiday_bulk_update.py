"""One screen that writes a holiday into whichever Holiday Lists you choose.

Seven companies, each with a common list and a women-only copy — fourteen lists
for FY 83/84. A holiday announced mid-year, or a festival date the client
corrects, otherwise has to be typed into every one of them by hand; the list that
gets missed surfaces in payroll, when everyone on it is marked Absent on a day the
rest of the group had off.

Put the date and the name on this document, leave "All Holiday Lists" ticked for
the whole group, or untick it and pick the lists — a women-only day takes only the
(Women) lists, a single branch's festival only that company's two. Remove Holiday
takes the same date back out.

The writing lives in `avinashgroup_app.hr.holiday_lists`; this controller holds
the form and records what the last run did.

Deliberately narrow: Holiday List rows only. Attendance already marked for the
date is left to Attendance Fix, and no Holiday List is created or deleted here.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from avinashgroup_app.hr.holiday_lists import apply_holiday_change


class HolidayBulkUpdate(Document):
	def validate(self):
		if not self.all_holiday_lists and not self.holiday_lists:
			frappe.throw(_("Choose the Holiday Lists, or tick All Holiday Lists"))

	@frappe.whitelist()
	def apply(self):
		"""Write the holiday to the chosen lists and return the per-list report."""
		chosen = None if self.all_holiday_lists else [d.holiday_list for d in self.holiday_lists]

		report = apply_holiday_change(
			action=self.action,
			holiday_date=self.holiday_date,
			description=self.description,
			holiday_lists=chosen,
		)

		self.db_set("last_applied_on", now_datetime(), update_modified=False)
		self.db_set(
			"result",
			f"{self.action} {self.holiday_date}: "
			f"{len(report['changed'])} list(s) changed, {len(report['skipped'])} skipped",
			update_modified=False,
		)
		frappe.db.commit()
		return report
