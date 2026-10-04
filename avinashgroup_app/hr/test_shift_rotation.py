"""Tests for hr/shift_rotation.py — moving staff between the rotational shifts.

Covers:
- the month-after-month rotation the stock screens refuse (there, back, there)
- only rotational shifts, of the person's own company, as source and as target
- one refusal does not stop the others in the same run
- moving back from the same date undoes the move and leaves one assignment
- a dated shift change still ahead of the person is refused, not overwritten
- a rotation into days already lived re-marks them on the new shift
- a rotation into a paid month is refused
- a bounded period (set_period / set_periods, the Shift Roster's Apply): resumes the
  old shift after it, joins back into one assignment, works around a change booked
  later, refuses a fixed or empty day anywhere in the range, paid months, bad input;
  re-marks only its own lived days; batch order and isolation
- the candidate list, and the permission check

Everything is built inside one transaction (own companies' employees, own Shift
Types, own assignments) and rolled back by FrappeTestCase, so nothing is left on
the site. `rotational_shifts` is the only reader of `Shift Type.custom_in_rotation`
and is replaced here, so the suite also runs on a site not yet migrated.

Run: bench run-tests fails at bootstrap on the dev bench; the runner is in
docs/shift-rotation.md ("Tests").
"""

from datetime import datetime, time
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from hrms.hr.doctype.shift_assignment_tool.shift_assignment_tool import create_shift_assignment

from avinashgroup_app.avinash_group_app.doctype.attendance_fix.attendance_fix import reconcile_employee_day
from avinashgroup_app.hr import shift_rotation
from avinashgroup_app.hr.overtime import get_shift_window

YEAR_START = "2026-07-17"  # 1 Shrawan 2083, when everybody's standing assignment begins


class TestShiftRotation(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		companies = frappe.get_all("Company", pluck="name", order_by="creation", limit=2)
		assert len(companies) >= 2, "test needs two companies on the site"
		cls.company, cls.other_company = companies

		cls.morning = cls._make_shift(cls.company, "06:00:00", "14:00:00")
		cls.evening = cls._make_shift(cls.company, "12:00:00", "20:00:00")
		cls.day = cls._make_shift(cls.company, "09:00:00", "18:00:00")  # fixed
		cls.elsewhere = cls._make_shift(cls.other_company, "12:00:00", "20:00:00")
		cls.rotational = {
			cls.company: [cls.morning, cls.evening],
			cls.other_company: [cls.elsewhere],
		}
		patcher = patch.object(
			shift_rotation, "rotational_shifts", side_effect=lambda company: cls.rotational.get(company, [])
		)
		patcher.start()
		cls.addClassCleanup(patcher.stop)

		# Month starts ahead of today, so no attendance is involved unless a test asks.
		cls.month_1 = add_days(today(), 20)
		cls.month_2 = add_days(today(), 50)
		cls.month_3 = add_days(today(), 80)

	@classmethod
	def _make_shift(cls, company, start, end):
		shift = frappe.new_doc("Shift Type")
		shift.update(
			{
				"custom_company": company,
				"start_time": start,
				"end_time": end,
				"enable_auto_attendance": 1,
				"determine_check_in_and_check_out": "Alternating entries as IN and OUT during the same shift",
				"working_hours_calculation_based_on": "First Check-in and Last Check-out",
				"begin_check_in_before_shift_start_time": 120,
				"allow_check_out_after_shift_end_time": 120,
				"enable_late_entry_marking": 1,
				"late_entry_grace_period": 0,
				"process_attendance_after": YEAR_START,
			}
		)
		shift.insert(ignore_permissions=True)
		return shift.name

	def setUp(self):
		# Other tests' refusals and "re-marking in the background" notes.
		frappe.clear_messages()

	def _employee(self, shift, company=None):
		"""A fresh employee holding one open-ended assignment on `shift` since the year began."""
		company = company or self.company
		emp = frappe.new_doc("Employee")
		emp.update(
			{
				"first_name": "Shift Rotation Test",
				"gender": "Male",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2024-01-01",
				"company": company,
				"status": "Active",
			}
		)
		emp.insert(ignore_permissions=True)
		if shift:
			create_shift_assignment(emp.name, company, shift, YEAR_START, None, "Active")
		return emp.name

	def _pieces(self, employee):
		"""The live roster as [(shift, start, end)], earliest first."""
		return [
			(a.shift_type, str(a.start_date), str(a.end_date) if a.end_date else None)
			for a in frappe.get_all(
				"Shift Assignment",
				filters={"employee": employee, "docstatus": 1, "status": "Active"},
				fields=["shift_type", "start_date", "end_date"],
				order_by="start_date",
			)
		]

	def _rotate(self, to_shift, from_date, employees, company=None):
		return shift_rotation.rotate(company or self.company, to_shift, from_date, employees)

	# ───────────────────────────────────────────────── the monthly rotation ──

	def test_rotates_month_after_month(self):
		emp = self._employee(self.morning)

		result = self._rotate(self.evening, self.month_1, [emp])
		self.assertEqual([m["employee"] for m in result["moved"]], [emp])
		self.assertEqual(result["refused"], [])
		self.assertEqual(
			self._pieces(emp),
			[
				(self.morning, YEAR_START, add_days(self.month_1, -1)),
				(self.evening, self.month_1, None),
			],
		)

		# The way back, a month later: the step a second Shift Request is refused.
		self.assertEqual(self._rotate(self.morning, self.month_2, [emp])["refused"], [])
		self.assertEqual(self._rotate(self.evening, self.month_3, [emp])["refused"], [])
		self.assertEqual(
			self._pieces(emp),
			[
				(self.morning, YEAR_START, add_days(self.month_1, -1)),
				(self.evening, self.month_1, add_days(self.month_2, -1)),
				(self.morning, self.month_2, add_days(self.month_3, -1)),
				(self.evening, self.month_3, None),
			],
		)
		# The roster every report and the attendance job read, day by day.
		self.assertEqual(get_shift_window(emp, add_days(self.month_1, -1))[0], self.morning)
		self.assertEqual(get_shift_window(emp, self.month_1)[0], self.evening)
		self.assertEqual(get_shift_window(emp, add_days(self.month_2, 5))[0], self.morning)
		self.assertEqual(get_shift_window(emp, add_days(self.month_3, 200))[0], self.evening)

	def test_many_at_once_and_one_refusal_does_not_stop_the_rest(self):
		movers = [self._employee(self.morning) for _ in range(3)]
		fixed = self._employee(self.day)
		frappe.clear_messages()

		result = self._rotate(self.evening, self.month_1, [movers[0], fixed, movers[1], movers[2], movers[0]])

		self.assertEqual([m["employee"] for m in result["moved"]], movers)  # the duplicate moved once
		self.assertEqual([r["employee"] for r in result["refused"]], [fixed])
		self.assertIn("does not take part in rotation", result["refused"][0]["reason"])
		self.assertIn(self.day, result["refused"][0]["reason"])
		for emp in movers:
			self.assertEqual(self._pieces(emp)[-1], (self.evening, self.month_1, None))
		self.assertEqual(self._pieces(fixed), [(self.day, YEAR_START, None)])
		self.assertEqual(frappe.get_message_log(), [], "a refusal must not leave a popup behind")

	# ─────────────────────────────────────────────────────── the restriction ──

	def test_fixed_shift_cannot_be_the_target(self):
		emp = self._employee(self.morning)
		with self.assertRaises(shift_rotation.ShiftRotationError) as refused:
			self._rotate(self.day, self.month_1, [emp])
		self.assertIn("does not take part in rotation", str(refused.exception))
		self.assertEqual(self._pieces(emp), [(self.morning, YEAR_START, None)])

	def test_another_companys_shift_cannot_be_the_target(self):
		emp = self._employee(self.morning)
		with self.assertRaises(shift_rotation.ShiftRotationError) as refused:
			self._rotate(self.elsewhere, self.month_1, [emp])
		self.assertIn(self.other_company, str(refused.exception))
		self.assertEqual(self._pieces(emp), [(self.morning, YEAR_START, None)])

	def test_another_companys_employee_is_refused(self):
		outsider = self._employee(self.elsewhere, company=self.other_company)
		result = self._rotate(self.evening, self.month_1, [outsider])
		self.assertEqual(result["moved"], [])
		self.assertIn("belongs to", result["refused"][0]["reason"])
		self.assertEqual(self._pieces(outsider), [(self.elsewhere, YEAR_START, None)])

	def test_person_without_a_shift_or_already_there_is_refused(self):
		unrostered = self._employee(None)
		already = self._employee(self.evening)
		result = self._rotate(self.evening, self.month_1, [unrostered, already])
		reasons = {r["employee"]: r["reason"] for r in result["refused"]}
		self.assertEqual(result["moved"], [])
		self.assertIn("does not take part in rotation", reasons[unrostered])
		self.assertIn("already on", reasons[already])

	def test_dated_change_ahead_is_refused_not_overwritten(self):
		emp = self._employee(self.morning)
		self._rotate(self.evening, self.month_2, [emp])
		before = self._pieces(emp)

		result = self._rotate(self.evening, self.month_1, [emp])  # earlier than the move already booked
		self.assertEqual(result["moved"], [])
		self.assertIn("dated shift change", result["refused"][0]["reason"])
		self.assertEqual(self._pieces(emp), before)

	# ───────────────────────────────────────────────────── changing it again ──

	def test_moving_back_from_the_same_date_undoes_the_move(self):
		emp = self._employee(self.morning)
		self._rotate(self.evening, self.month_1, [emp])
		self._rotate(self.morning, self.month_1, [emp])

		self.assertEqual(self._pieces(emp), [(self.morning, YEAR_START, None)])
		# The rotated piece is kept, cancelled, as the record that it happened.
		self.assertEqual(
			frappe.db.count("Shift Assignment", {"employee": emp, "shift_type": self.evening, "docstatus": 2}), 1
		)
		# And the person can be rotated again afterwards.
		self.assertEqual(self._rotate(self.evening, self.month_1, [emp])["refused"], [])
		self.assertEqual(self._pieces(emp)[-1], (self.evening, self.month_1, None))

	# ─────────────────────────────────────────────── days already lived ──

	def _punch(self, employee, day, hour, minute):
		checkin = frappe.new_doc("Employee Checkin")
		checkin.update({"employee": employee, "time": datetime.combine(getdate(day), time(hour, minute))})
		checkin.insert(ignore_permissions=True)
		return checkin.name

	def _attendance(self, employee, day):
		return frappe.db.get_value(
			"Attendance",
			{"employee": employee, "attendance_date": day, "docstatus": 1},
			["name", "status", "shift", "late_entry", "custom_late_entry"],
			as_dict=True,
		)

	def test_backdated_rotation_remarks_lived_days_on_the_new_shift(self):
		emp = self._employee(self.morning)
		day = getdate(add_days(today(), -3))
		self._punch(emp, day, 11, 58)
		self._punch(emp, day, 20, 3)
		reconcile_employee_day(
			frappe.get_doc("Shift Type", self.morning),
			emp,
			day,
			holiday_dates=frozenset(),
			counters={"attendance_created_or_updated": 0, "absent_rows_deleted": 0, "checkins_relinked": 0},
			log_lines=[],
			include_skipped=True,
			mark_absent_when_no_checkins=False,
		)
		before = self._attendance(emp, day)
		self.assertEqual(before.shift, self.morning)
		self.assertGreater(before.custom_late_entry, 5 * 3600, "six hours late on the morning shift")

		result = self._rotate(self.evening, str(day), [emp])
		frappe.clear_messages()  # the "attendance re-marked" note
		self.assertEqual(result["refused"], [])

		after = self._attendance(emp, day)
		self.assertEqual(after.shift, self.evening)
		self.assertEqual(after.status, "Present")
		self.assertEqual(after.custom_late_entry, 0, "11:58 is on time for 12 PM")
		self.assertEqual(
			set(frappe.get_all("Employee Checkin", {"employee": emp}, pluck="shift")), {self.evening}
		)

	def test_rotation_into_a_paid_month_is_refused(self):
		emp = self._employee(self.morning)
		start = getdate(add_days(today(), -10))
		slip = frappe.new_doc("Salary Slip")
		slip.update(
			{
				"name": f"TEST-ROTATION-SLIP-{emp}",
				"employee": emp,
				"company": self.company,
				"posting_date": today(),
				"start_date": add_days(start, -20),
				"end_date": add_days(start, 5),
				"docstatus": 1,
			}
		)
		slip.db_insert()

		result = self._rotate(self.evening, str(start), [emp])
		self.assertEqual(result["moved"], [])
		self.assertIn("already been paid", result["refused"][0]["reason"])
		self.assertEqual(self._pieces(emp), [(self.morning, YEAR_START, None)])

	# ────────────────────────────────────────── a bounded period (the roster) ──

	def _period(self, employee, shift, start, end, company=None):
		return shift_rotation.set_period(company or self.company, employee, shift, start, end)

	def _last_day(self, start):
		return add_days(start, 29)

	def test_period_in_the_middle_resumes_the_old_shift_after_it(self):
		emp = self._employee(self.morning)
		end = self._last_day(self.month_1)

		done = self._period(emp, self.evening, self.month_1, end)
		self.assertEqual(done["from_shifts"], [self.morning])
		self.assertEqual((done["start"], done["end"], done["shift"]), (str(getdate(self.month_1)), str(getdate(end)), self.evening))
		self.assertEqual(
			self._pieces(emp),
			[
				(self.morning, YEAR_START, add_days(self.month_1, -1)),
				(self.evening, self.month_1, end),
				(self.morning, add_days(end, 1), None),
			],
		)
		self.assertEqual(get_shift_window(emp, add_days(self.month_1, 5))[0], self.evening)
		self.assertEqual(get_shift_window(emp, add_days(end, 1))[0], self.morning)

	def test_painting_back_leaves_one_assignment(self):
		emp = self._employee(self.morning)
		end = self._last_day(self.month_1)
		self._period(emp, self.evening, self.month_1, end)
		self._period(emp, self.morning, self.month_1, end)

		self.assertEqual(self._pieces(emp), [(self.morning, YEAR_START, None)])
		self.assertEqual(
			frappe.db.count("Shift Assignment", {"employee": emp, "shift_type": self.evening, "docstatus": 2}), 1,
			"the replaced piece is kept, cancelled",
		)

	def test_period_works_around_a_change_booked_later(self):
		# `rotate` refuses this ("a dated shift change"); a bounded period does not touch it.
		emp = self._employee(self.morning)
		self._rotate(self.evening, self.month_3, [emp])
		end = self._last_day(self.month_1)

		self._period(emp, self.evening, self.month_1, end)
		self.assertEqual(
			self._pieces(emp),
			[
				(self.morning, YEAR_START, add_days(self.month_1, -1)),
				(self.evening, self.month_1, end),
				(self.morning, add_days(end, 1), add_days(self.month_3, -1)),
				(self.evening, self.month_3, None),
			],
		)

	def test_period_across_a_change_moves_its_edge(self):
		emp = self._employee(self.morning)
		self._rotate(self.evening, self.month_2, [emp])
		end = add_days(self.month_2, 9)

		done = self._period(emp, self.morning, self.month_1, end)
		self.assertEqual(done["from_shifts"], [self.morning, self.evening])
		self.assertEqual(
			self._pieces(emp),
			[(self.morning, YEAR_START, end), (self.evening, add_days(end, 1), None)],
		)

	def test_period_onto_a_day_off_rotation_or_no_shift_is_refused(self):
		fixed = self._employee(self.day)
		unrostered = self._employee(None)
		end = self._last_day(self.month_1)
		with self.assertRaises(shift_rotation.ShiftRotationError) as refused:
			self._period(fixed, self.evening, self.month_1, end)
		self.assertIn("does not take part in rotation", str(refused.exception))
		with self.assertRaises(shift_rotation.ShiftRotationError) as refused:
			self._period(unrostered, self.evening, self.month_1, end)
		self.assertIn("no shift", str(refused.exception))
		with self.assertRaises(shift_rotation.ShiftRotationError):
			self._period(self._employee(self.morning), self.day, self.month_1, end)  # fixed target
		self.assertEqual(self._pieces(fixed), [(self.day, YEAR_START, None)])

	def test_one_fixed_day_inside_the_range_refuses_the_whole_range(self):
		emp = self._employee(self.morning)
		# Ten days on the day shift in the middle of month 1, by a dated assignment.
		middle = add_days(self.month_1, 10)
		self._period_raw(emp, self.day, middle, add_days(middle, 9))
		before = self._pieces(emp)
		with self.assertRaises(shift_rotation.ShiftRotationError) as refused:
			self._period(emp, self.evening, self.month_1, self._last_day(self.month_1))
		self.assertIn(self.day, str(refused.exception))
		self.assertEqual(self._pieces(emp), before)

	def _period_raw(self, employee, shift, start, end):
		"""A dated assignment cut into the standing one, the way a Shift Request leaves it."""
		standing = frappe.get_all(
			"Shift Assignment", {"employee": employee, "docstatus": 1, "end_date": ("is", "not set")}, pluck="name"
		)[0]
		frappe.db.set_value("Shift Assignment", standing, "end_date", add_days(start, -1))
		original = frappe.db.get_value("Shift Assignment", standing, "shift_type")
		create_shift_assignment(employee, self.company, shift, start, end, "Active")
		create_shift_assignment(employee, self.company, original, add_days(end, 1), None, "Active")

	def test_period_bad_input_is_refused(self):
		emp = self._employee(self.morning)
		outsider = self._employee(self.elsewhere, company=self.other_company)
		end = self._last_day(self.month_1)
		cases = [
			((emp, self.morning, self.month_1, end), "already on"),
			((emp, self.evening, end, self.month_1), "before it starts"),
			((emp, self.evening, self.month_1, None), "first and the last day"),
			((outsider, self.evening, self.month_1, end), "belongs to"),
		]
		for args, words in cases:
			with self.subTest(words=words):
				with self.assertRaises(shift_rotation.ShiftRotationError) as refused:
					self._period(*args)
				self.assertIn(words, str(refused.exception))
		self.assertEqual(self._pieces(emp), [(self.morning, YEAR_START, None)])

	def test_period_into_a_paid_month_is_refused(self):
		emp = self._employee(self.morning)
		start = getdate(add_days(today(), -10))
		frappe.get_doc(
			{
				"doctype": "Salary Slip",
				"name": f"TEST-PERIOD-SLIP-{emp}",
				"employee": emp,
				"company": self.company,
				"posting_date": today(),
				"start_date": add_days(start, -20),
				"end_date": add_days(start, 5),
				"docstatus": 1,
			}
		).db_insert()
		with self.assertRaises(frappe.ValidationError) as refused:
			self._period(emp, self.evening, start, add_days(start, 20))
		self.assertIn("already been paid", str(refused.exception))
		self.assertEqual(self._pieces(emp), [(self.morning, YEAR_START, None)])

	def test_backdated_period_remarks_only_its_own_days(self):
		emp = self._employee(self.morning)
		day = getdate(add_days(today(), -3))
		next_day = add_days(day, 1)
		for d in (day, next_day):
			self._punch(emp, d, 11, 58)
			self._punch(emp, d, 20, 3)
			self._reconcile(emp, d)
		self.assertGreater(self._attendance(emp, day).custom_late_entry, 5 * 3600)

		self._period(emp, self.evening, day, day)
		frappe.clear_messages()

		after = self._attendance(emp, day)
		self.assertEqual(after.shift, self.evening)
		self.assertEqual(after.custom_late_entry, 0, "11:58 is on time for 12 PM")
		untouched = self._attendance(emp, next_day)
		self.assertEqual(untouched.shift, self.morning, "the day after the period is still mornings")
		self.assertEqual(self._pieces(emp)[-1], (self.morning, str(next_day), None))

	def _reconcile(self, employee, day):
		reconcile_employee_day(
			frappe.get_doc("Shift Type", self.morning),
			employee,
			day,
			holiday_dates=frozenset(),
			counters={"attendance_created_or_updated": 0, "absent_rows_deleted": 0, "checkins_relinked": 0},
			log_lines=[],
			include_skipped=True,
			mark_absent_when_no_checkins=False,
		)

	def test_set_periods_runs_in_date_order_and_one_refusal_does_not_stop_the_rest(self):
		a, b = self._employee(self.morning), self._employee(self.morning)
		fixed = self._employee(self.day)
		m1_end, m2_end = self._last_day(self.month_1), self._last_day(self.month_2)
		frappe.clear_messages()

		result = shift_rotation.set_periods(
			self.company,
			frappe.as_json(
				[
					# Sent out of order: month 2 before month 1 for the same person.
					{"employee": a, "shift": self.evening, "start": str(self.month_2), "end": str(m2_end)},
					{"employee": fixed, "shift": self.evening, "start": str(self.month_1), "end": str(m1_end)},
					{"employee": a, "shift": self.evening, "start": str(self.month_1), "end": str(m1_end)},
					{"employee": b, "shift": self.evening, "start": str(self.month_1), "end": str(m2_end)},
				]
			),
		)
		self.assertEqual(
			[(m["employee"], m["start"]) for m in result["moved"]],
			[(a, str(self.month_1)), (b, str(self.month_1)), (a, str(self.month_2))],
		)
		self.assertEqual([r["employee"] for r in result["refused"]], [fixed])
		self.assertIn("does not take part in rotation", result["refused"][0]["reason"])
		self.assertEqual(result["refused"][0]["shift"], self.evening)
		self.assertTrue(result["refused"][0]["employee_name"])
		self.assertEqual(frappe.get_message_log(), [], "a refusal must not leave a popup behind")

		# Month 2 starts the day after month 1 ends, so `a`'s two evening runs join into one.
		self.assertEqual(
			self._pieces(a),
			[
				(self.morning, YEAR_START, add_days(self.month_1, -1)),
				(self.evening, self.month_1, m2_end),
				(self.morning, add_days(m2_end, 1), None),
			],
		)
		for day in (self.month_1, self.month_2, m2_end):
			self.assertEqual(get_shift_window(a, day)[0], self.evening)
			self.assertEqual(get_shift_window(b, day)[0], self.evening)
		self.assertEqual(get_shift_window(a, add_days(m2_end, 1))[0], self.morning)

	# ──────────────────────────────────────────────────────────── the desk ──

	def test_preview_lists_only_staff_on_the_other_rotational_shifts(self):
		on_morning = self._employee(self.morning)
		on_evening = self._employee(self.evening)
		on_day = self._employee(self.day)
		outsider = self._employee(self.elsewhere, company=self.other_company)

		listed = shift_rotation.preview(self.company, self.evening, self.month_1)
		names = {row["employee"]: row["from_shift"] for row in listed["employees"]}
		self.assertEqual(names.get(on_morning), self.morning)
		for absent in (on_evening, on_day, outsider):
			self.assertNotIn(absent, names)
		self.assertEqual(listed["shifts"], [self.morning, self.evening])

		# After the move the person is a candidate for the way back, not for this way.
		self._rotate(self.evening, self.month_1, [on_morning])
		again = {r["employee"] for r in shift_rotation.preview(self.company, self.evening, self.month_1)["employees"]}
		back = {r["employee"] for r in shift_rotation.preview(self.company, self.morning, self.month_1)["employees"]}
		self.assertNotIn(on_morning, again)
		self.assertIn(on_morning, back)

	def test_preview_defaults_to_the_first_day_of_the_next_bs_month(self):
		from rdp_common_app.utils.bs_boundaries import ad_to_bs

		listed = shift_rotation.preview(self.company, self.evening)
		start = getdate(listed["from_date"])
		self.assertGreater(start, getdate(today()))
		self.assertEqual(ad_to_bs(start).day, 1)
		self.assertTrue(listed["from_miti"].startswith("1 "))

	def test_needs_shift_assignment_permission(self):
		emp = self._employee(self.morning)
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				self._rotate(self.evening, self.month_1, [emp])
			with self.assertRaises(frappe.PermissionError):
				shift_rotation.preview(self.company, self.evening, self.month_1)
			with self.assertRaises(frappe.PermissionError):
				shift_rotation.set_periods(
					self.company,
					[{"employee": emp, "shift": self.evening, "start": self.month_1, "end": self.month_2}],
				)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(self._pieces(emp), [(self.morning, YEAR_START, None)])
