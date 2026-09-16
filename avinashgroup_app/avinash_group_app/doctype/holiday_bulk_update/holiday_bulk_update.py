"""One screen that writes many holidays into many Holiday Lists.

Seven companies, each with a common list and a women-only copy — fourteen lists
for FY 83/84. Typing a festival calendar, or a holiday the government announces
mid-year, into all of them by hand is where a list gets missed; the miss surfaces
in payroll, when everyone on that list is marked Absent on a day the rest of the
group had off.

Fill the Holidays table once, tick "Women Only" on the rows that are (Teej,
International Women's Day), choose the companies, and press Apply. Remove Holiday
takes the same rows out again.

The writing itself lives in `avinashgroup_app.hr.holiday_lists`; this controller
only validates the form and records what the last run did.

Deliberately narrow: it edits Holiday List rows only. Attendance already marked
for a date is NOT re-marked — Attendance Fix owns that — and no Holiday List is
ever created or deleted here.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from avinashgroup_app.hr.holiday_lists import apply_holiday_change


class HolidayBulkUpdate(Document):
	def validate(self):
		self.validate_duplicate_dates()

	def validate_duplicate_dates(self):
		"""The same date twice in the table would be applied twice, and the second
		pass would report itself as already present. Cheaper to refuse it here."""
		seen = set()
		for row in self.holidays:
			key = (row.holiday_date, row.women_only)
			if key in seen:
				frappe.throw(_("Row {0}: {1} is listed twice").format(row.idx, row.holiday_date))
			seen.add(key)

	@frappe.whitelist()
	def apply(self):
		"""Write every row to the chosen lists and return the per-list report."""
		if not self.holidays:
			frappe.throw(_("Add at least one holiday"))

		companies = None if self.all_companies else [d.company for d in self.companies]
		if not self.all_companies and not companies:
			frappe.throw(_("Select at least one company"))

		changed, skipped = [], []
		for row in self.holidays:
			report = apply_holiday_change(
				action=self.action,
				holiday_date=row.holiday_date,
				description=row.description,
				companies=companies,
				# A women-only day belongs in the (Women) copy alone; every other
				# day goes into both, so the women's list stays a superset.
				scope="women" if row.women_only else "both",
			)
			label = f"{row.holiday_date} {row.description}"
			changed += [f"{label} → {line}" for line in report["changed"]]
			skipped += [f"{label} → {line}" for line in report["skipped"]]

		self.db_set("last_applied_on", now_datetime(), update_modified=False)
		self.db_set(
			"result",
			f"{self.action}: {len(changed)} list rows changed, {len(skipped)} skipped",
			update_modified=False,
		)
		frappe.db.commit()
		return {"changed": changed, "skipped": skipped}
