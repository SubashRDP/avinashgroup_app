"""Tests for hr/punch_correction.py — First IN / Last OUT from Monthly Attendance BS.

Covers:
- a one-punch day gets its missing OUT added, and the attendance is re-marked
  from both punches (hours, deviations), stamped as corrected
- moving a device punch keeps the device's reading, and a second correction
  keeps the FIRST reading rather than the corrected one
- refusals: today, OUT before IN, a punch left outside the new IN/OUT, no reason
- a time outside the shift's check-in window still counts (the day's punches
  are pinned to the rostered shift), with a warning
- the report reads the stamps back (get_edited_days)
- a shift correction: one Shift Assignment covering exactly the chosen days,
  the day re-marked on it, nothing outside the range changed
- every correction writes an Attendance Correction Log entry
- the same re-mark from the Employee Checkin form (attendance_sync hooks):
  a punch added by hand marks the day and is stamped; a linked punch can be
  moved and the day follows; a deleted punch re-marks what is left

Runs inside the test transaction (no commits), so FrappeTestCase's rollback
cleans up.

Run:
    bench --site avinas1 run-tests --app avinashgroup_app \
        --module avinashgroup_app.hr.test_punch_correction
"""

from datetime import datetime

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from avinashgroup_app.hr.punch_correction import correct_day, get_edited_days


class TestPunchCorrection(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = frappe.get_all("Company", pluck="name", order_by="creation", limit=1)[0]
		shift = frappe.new_doc("Shift Type")
		shift.custom_company = company
		shift.start_time = "09:00:00"
		shift.end_time = "17:00:00"
		shift.begin_check_in_before_shift_start_time = 60
		shift.allow_check_out_after_shift_end_time = 60
		shift.insert(ignore_permissions=True)
		cls.shift = shift

		late = frappe.new_doc("Shift Type")
		late.custom_company = company
		late.start_time = "12:00:00"
		late.end_time = "20:00:00"
		late.begin_check_in_before_shift_start_time = 60
		late.allow_check_out_after_shift_end_time = 60
		late.insert(ignore_permissions=True)
		cls.late_shift = late

		emp = frappe.new_doc("Employee")
		emp.first_name = "Punch Correction Test"
		emp.gender = "Male"
		emp.date_of_birth = "1990-01-01"
		emp.date_of_joining = "2024-01-01"
		emp.company = company
		emp.status = "Active"
		emp.default_shift = shift.name
		emp.insert(ignore_permissions=True)
		cls.employee = emp.name
		cls.days_used = 0

	def setUp(self):
		# FrappeTestCase rolls back once per class, not per test, so every test
		# takes a day of its own.
		type(self).days_used += 1
		self.day = getdate(add_days(today(), -2 - self.days_used))

	def _punch(self, clock, by_hand=False):
		"""A punch as the device pipeline stores it, or (by_hand) as the form does."""
		ck = frappe.new_doc("Employee Checkin")
		ck.employee = self.employee
		ck.time = datetime.combine(self.day, datetime.strptime(clock, "%H:%M").time())
		ck.log_type = "IN"
		frappe.flags.in_biometric_day_reconcile = not by_hand
		try:
			ck.insert(ignore_permissions=True)
		finally:
			frappe.flags.in_biometric_day_reconcile = False
		return ck.name

	def _punches(self):
		return frappe.get_all(
			"Employee Checkin",
			filters={"employee": self.employee, "time": ("between", [f"{self.day} 00:00:00", f"{self.day} 23:59:59"])},
			fields=["name", "time", "log_type", "custom_time_edited", "custom_original_time", "custom_edit_reason"],
			order_by="time asc",
		)

	def test_missing_out_is_added_and_day_remarked(self):
		self._punch("09:05")
		result = correct_day(self.employee, self.day, "09:05", "17:00", "Forgot to punch out")

		punches = self._punches()
		self.assertEqual([(p.time.strftime("%H:%M"), p.log_type) for p in punches], [("09:05", "IN"), ("17:00", "OUT")])
		added = punches[1]
		self.assertTrue(added.custom_time_edited)
		self.assertIsNone(added.custom_original_time)  # no device reading behind it
		self.assertEqual(added.custom_edit_reason, "Forgot to punch out")
		self.assertFalse(punches[0].custom_time_edited)  # untouched device punch

		att = frappe.get_doc("Attendance", result["attendance"])
		self.assertEqual(att.docstatus, 1)
		self.assertAlmostEqual(att.working_hours, 7.9, places=1)
		self.assertEqual(att.custom_late_entry, 300)  # 5 minutes late, in seconds

	def test_second_correction_keeps_the_device_reading(self):
		self._punch("09:00")
		self._punch("16:10")
		correct_day(self.employee, self.day, "09:00", "16:40", "first")
		correct_day(self.employee, self.day, "09:00", "17:00", "second")

		out = self._punches()[-1]
		self.assertEqual(out.time.strftime("%H:%M"), "17:00")
		self.assertEqual(out.custom_original_time.strftime("%H:%M"), "16:10")
		self.assertEqual(out.custom_edit_reason, "second")
		self.assertEqual(len(self._punches()), 2)  # moved, not added beside

	def test_single_late_punch_is_taken_as_out(self):
		self._punch("17:05")
		correct_day(self.employee, self.day, "09:00", "17:05", "Missed IN at the gate")
		punches = self._punches()
		self.assertEqual([p.time.strftime("%H:%M") for p in punches], ["09:00", "17:05"])
		self.assertFalse(punches[1].custom_time_edited)  # the device's 17:05 kept as is

	def test_refusals(self):
		self._punch("09:00")
		self._punch("12:00")
		self._punch("17:00")
		cases = [
			(getdate(today()), "09:00", "17:00", "r"),  # today
			(self.day, "17:00", "09:00", "r"),  # OUT before IN
			(self.day, "12:30", "17:00", "r"),  # the 12:00 punch would stay first
			(self.day, "09:00", "17:30", " "),  # no reason
		]
		for day, in_time, out_time, reason in cases:
			with self.subTest(in_time=in_time, out_time=out_time, day=day):
				self.assertRaises(frappe.ValidationError, correct_day, self.employee, day, in_time, out_time, reason)

	def test_time_outside_window_counts(self):
		self._punch("09:00")
		self._punch("17:00")
		result = correct_day(self.employee, self.day, "07:00", "17:00", "Came early for stock count")
		att = frappe.get_doc("Attendance", result["attendance"])
		self.assertEqual(att.in_time.strftime("%H:%M"), "07:00")
		self.assertAlmostEqual(att.working_hours, 10.0, places=1)
		self.assertTrue(any("07:00" in w for w in result["warnings"]))

	def test_report_reads_the_stamps(self):
		self._punch("09:20")
		self._punch("17:00")
		correct_day(self.employee, self.day, "09:00", "17:00", "Device clock was slow")
		notes = get_edited_days([self.employee], self.day, self.day)[(self.employee, self.day)]
		self.assertEqual(len(notes), 1)
		note = next(iter(notes.values()))
		self.assertIn("09:20", note)
		self.assertIn("Device clock was slow", note)

	# ── the Employee Checkin form (biometric/attendance_sync hooks) ──

	def _attendance(self):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.employee, "attendance_date": self.day, "docstatus": 1},
			["name", "status", "in_time", "out_time", "working_hours"],
			as_dict=True,
		)

	def test_form_add_marks_the_day_and_stamps(self):
		self._punch("09:00", by_hand=True)
		self._punch("17:00", by_hand=True)
		att = self._attendance()
		self.assertEqual(att.status, "Present")
		self.assertEqual(att.out_time.strftime("%H:%M"), "17:00")
		for p in self._punches():
			self.assertTrue(p.custom_time_edited)
			self.assertIsNone(p.custom_original_time)

	def test_form_move_of_linked_punch_follows(self):
		self._punch("09:00", by_hand=True)
		out = self._punch("16:00", by_hand=True)
		self.assertEqual(self._attendance().out_time.strftime("%H:%M"), "16:00")

		ck = frappe.get_doc("Employee Checkin", out)
		self.assertTrue(ck.attendance)  # linked: HRMS alone would refuse the move
		ck.time = datetime.combine(self.day, datetime.strptime("17:30", "%H:%M").time())
		ck.save(ignore_permissions=True)

		att = self._attendance()
		self.assertEqual(att.out_time.strftime("%H:%M"), "17:30")
		moved = frappe.get_doc("Employee Checkin", out)
		self.assertEqual(moved.attendance, att.name)
		# Added by hand, so there was never a device reading to keep.
		self.assertIsNone(moved.custom_original_time)
		self.assertEqual(moved.custom_edit_reason, "Edited on Employee Checkin form")

	def test_form_delete_remarks_what_is_left(self):
		self._punch("09:00", by_hand=True)
		self._punch("12:00", by_hand=True)
		last = self._punch("17:00", by_hand=True)
		frappe.delete_doc("Employee Checkin", last, ignore_permissions=True)
		self.assertEqual(self._attendance().out_time.strftime("%H:%M"), "12:00")

	def test_device_ingest_is_not_treated_as_a_correction(self):
		self._punch("09:00")
		self.assertFalse(self._punches()[0].custom_time_edited)
		self.assertIsNone(self._attendance())

	# ── shift correction and the log ──

	def test_shift_correction_covers_only_the_day(self):
		self._punch("12:00")
		self._punch("20:00")
		result = correct_day(self.employee, self.day, reason="Rostered wrongly", shift=self.late_shift.name)

		att = frappe.get_doc("Attendance", result["attendance"])
		self.assertEqual(att.shift, self.late_shift.name)
		self.assertEqual(att.custom_late_entry, 0)  # on time for 12-8, 3 h late for 9-5

		covering = frappe.get_all(
			"Shift Assignment",
			filters={"employee": self.employee, "docstatus": 1, "shift_type": self.late_shift.name},
			fields=["start_date", "end_date", "custom_shift_corrected", "custom_corrected_from_shift"],
		)
		self.assertEqual(len(covering), 1)
		self.assertEqual((getdate(covering[0].start_date), getdate(covering[0].end_date)), (self.day, self.day))
		self.assertTrue(covering[0].custom_shift_corrected)
		self.assertEqual(covering[0].custom_corrected_from_shift, self.shift.name)
		# the day before keeps the default shift
		from avinashgroup_app.hr.overtime import get_shift_window

		self.assertEqual(get_shift_window(self.employee, add_days(self.day, -1))[0], self.shift.name)

	def test_shift_correction_needs_a_reason(self):
		self._punch("12:00")
		self.assertRaises(
			frappe.ValidationError, correct_day, self.employee, self.day, reason=" ", shift=self.late_shift.name
		)

	def test_every_correction_is_logged(self):
		self._punch("09:10")
		correct_day(self.employee, self.day, "09:10", "17:00", "Forgot to punch out")
		entries = frappe.get_all(
			"Attendance Correction Log",
			filters={"employee": self.employee, "attendance_date": self.day},
			fields=["correction_type", "source", "old_value", "new_value", "reason", "done_by", "attendance"],
		)
		self.assertEqual(len(entries), 1)
		entry = entries[0]
		self.assertEqual(entry.correction_type, "Punch Added")
		self.assertEqual(entry.source, "Monthly Attendance BS")
		self.assertEqual(entry.new_value, "OUT 17:00")
		self.assertEqual(entry.reason, "Forgot to punch out")
		self.assertEqual(entry.done_by, frappe.session.user)
		self.assertTrue(entry.attendance)
