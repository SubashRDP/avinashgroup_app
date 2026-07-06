"""End-to-end tests for the biometric checkin → attendance pipeline.

Covers:
- punches map to the employee of the sending device's company, and every
  Employee Checkin gets `custom_company` stamped
- IN/OUT alternation and idempotent re-sync in process_attendance_records
- manual/API-created checkins get company via fetch_from
- duplicate attendance_device_id within one company is blocked
- Attendance hooks: shift deviation fields and late-arrival Half Day rule

process_attendance_records() commits, so this suite cleans up its own
records explicitly in tearDownClass instead of relying on rollback.

Run:
    bench --site avinas1 run-tests --app avinashgroup_app \
        --module avinashgroup_app.biometric.test_attendance_pipeline
"""

from datetime import datetime, timedelta

import frappe
from frappe.tests.utils import FrappeTestCase

from avinashgroup_app.biometric.utils import process_attendance_records

DEVICE_USER_ID = "9901"  # deliberately identical in both companies
SERIAL_A = "TEST-BIO-DEV-A"
SERIAL_B = "TEST-BIO-DEV-B"


class TestAttendancePipeline(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        companies = frappe.get_all("Company", pluck="name", order_by="creation", limit=2)
        assert len(companies) >= 2, "test needs two companies on the site"
        cls.company_a, cls.company_b = companies[0], companies[1]

        # shift first: emp_a gets it as default_shift at insert time, because
        # HRMS caches Employee.default_shift per-process (db.get_value cache=True)
        # and a later db.set_value would not be seen by fetch_shift in this run
        cls.shift = cls._make_shift()
        cls.emp_a = cls._make_employee(cls.company_a, DEVICE_USER_ID, default_shift=cls.shift.name)
        cls.emp_b = cls._make_employee(cls.company_b, DEVICE_USER_ID)
        cls.device_a = cls._make_device("Test Bio Device A", SERIAL_A, cls.company_a)
        cls.device_b = cls._make_device("Test Bio Device B", SERIAL_B, cls.company_b)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        for emp in (cls.emp_a.name, cls.emp_b.name):
            for dt in ("Employee Checkin", "Attendance"):
                for name in frappe.get_all(dt, filters={"employee": emp}, pluck="name"):
                    doc = frappe.get_doc(dt, name)
                    if doc.docstatus == 1:
                        doc.flags.ignore_permissions = True
                        doc.cancel()
                    frappe.delete_doc(dt, name, force=True, ignore_permissions=True)
            frappe.delete_doc("Employee", emp, force=True, ignore_permissions=True)
        for dev in ("Test Bio Device A", "Test Bio Device B"):
            if frappe.db.exists("Biometric Device", dev):
                frappe.delete_doc("Biometric Device", dev, force=True, ignore_permissions=True)
        if cls.shift and frappe.db.exists("Shift Type", cls.shift.name):
            frappe.delete_doc("Shift Type", cls.shift.name, force=True, ignore_permissions=True)
        frappe.db.commit()
        super().tearDownClass()

    @classmethod
    def _make_employee(cls, company, device_id, default_shift=None):
        emp = frappe.new_doc("Employee")
        emp.first_name = "Biometric Pipeline Test"
        emp.gender = "Male"
        emp.date_of_birth = "1990-01-01"
        emp.date_of_joining = "2024-01-01"
        emp.company = company
        emp.status = "Active"
        emp.attendance_device_id = device_id
        emp.default_shift = default_shift
        emp.insert(ignore_permissions=True)
        return emp

    @classmethod
    def _make_device(cls, device_name, serial, company):
        if frappe.db.exists("Biometric Device", device_name):
            return frappe.get_doc("Biometric Device", device_name)
        dev = frappe.new_doc("Biometric Device")
        dev.device_name = device_name
        dev.device_serial = serial
        dev.company = company
        dev.enabled = 1
        dev.insert(ignore_permissions=True)
        return dev

    @classmethod
    def _make_shift(cls):
        shift = frappe.new_doc("Shift Type")
        shift.custom_company = cls.company_a
        shift.start_time = "09:00:00"
        shift.end_time = "17:00:00"
        shift.insert(ignore_permissions=True)
        return shift

    def _checkins(self, employee, date_str):
        return frappe.get_all(
            "Employee Checkin",
            filters={
                "employee": employee,
                "time": ["between", [f"{date_str} 00:00:00", f"{date_str} 23:59:59"]],
            },
            fields=["name", "time", "log_type", "custom_company", "device_id"],
            order_by="time asc",
        )

    def test_punch_maps_to_device_company_and_stamps_company(self):
        day = "2026-06-01"
        result = process_attendance_records(
            [{"user_id": DEVICE_USER_ID, "timestamp": f"{day} 09:05:00"}],
            device_identifier=SERIAL_A,
        )
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["synced"], 1)

        rows_a = self._checkins(self.emp_a.name, day)
        self.assertEqual(len(rows_a), 1)
        self.assertEqual(rows_a[0].custom_company, self.company_a)
        self.assertEqual(rows_a[0].device_id, SERIAL_A)
        # the same work-number in the other company must NOT get a checkin
        self.assertEqual(self._checkins(self.emp_b.name, day), [])

        # same user_id via company B's device lands on company B's employee
        process_attendance_records(
            [{"user_id": DEVICE_USER_ID, "timestamp": f"{day} 09:06:00"}],
            device_identifier=SERIAL_B,
        )
        rows_b = self._checkins(self.emp_b.name, day)
        self.assertEqual(len(rows_b), 1)
        self.assertEqual(rows_b[0].custom_company, self.company_b)

    def test_alternation_and_idempotency(self):
        day = "2026-06-02"
        batch = [
            {"user_id": DEVICE_USER_ID, "timestamp": f"{day} 09:00:00"},
            {"user_id": DEVICE_USER_ID, "timestamp": f"{day} 13:00:00"},
            {"user_id": DEVICE_USER_ID, "timestamp": f"{day} 14:00:00"},
            {"user_id": DEVICE_USER_ID, "timestamp": f"{day} 17:05:00"},
        ]
        process_attendance_records(batch, device_identifier=SERIAL_A)
        rows = self._checkins(self.emp_a.name, day)
        self.assertEqual([r.log_type for r in rows], ["IN", "OUT", "IN", "OUT"])
        self.assertTrue(all(r.custom_company == self.company_a for r in rows))

        # re-sending the same batch must not duplicate anything
        process_attendance_records(batch, device_identifier=SERIAL_A)
        self.assertEqual(len(self._checkins(self.emp_a.name, day)), 4)

        # a late-arriving earlier punch slots in and downstream rows flip
        process_attendance_records(
            [{"user_id": DEVICE_USER_ID, "timestamp": f"{day} 08:30:00"}],
            device_identifier=SERIAL_A,
        )
        rows = self._checkins(self.emp_a.name, day)
        self.assertEqual([r.log_type for r in rows], ["IN", "OUT", "IN", "OUT", "IN"])

    def test_duplicate_punches_within_threshold_collapse(self):
        # SERIAL_A device uses the default Duplicate Threshold of 1 minute.
        day = "2026-06-08"
        # One physical IN fired 3 times in 5s, and one OUT fired twice.
        batch = [
            {"user_id": DEVICE_USER_ID, "timestamp": f"{day} 09:00:01"},
            {"user_id": DEVICE_USER_ID, "timestamp": f"{day} 09:00:03"},
            {"user_id": DEVICE_USER_ID, "timestamp": f"{day} 09:00:05"},
            {"user_id": DEVICE_USER_ID, "timestamp": f"{day} 17:30:00"},
            {"user_id": DEVICE_USER_ID, "timestamp": f"{day} 17:30:02"},
        ]
        process_attendance_records(batch, device_identifier=SERIAL_A)
        rows = self._checkins(self.emp_a.name, day)
        # Only the first punch of each burst survives -> one IN, one OUT.
        self.assertEqual(
            [r.time.strftime("%H:%M:%S") for r in rows], ["09:00:01", "17:30:00"]
        )
        self.assertEqual([r.log_type for r in rows], ["IN", "OUT"])

        # Re-sending the same burst stays idempotent (nothing new inserted).
        process_attendance_records(batch, device_identifier=SERIAL_A)
        self.assertEqual(len(self._checkins(self.emp_a.name, day)), 2)

        # A genuine separate punch >1 min after the kept IN is NOT collapsed.
        process_attendance_records(
            [{"user_id": DEVICE_USER_ID, "timestamp": f"{day} 09:02:00"}],
            device_identifier=SERIAL_A,
        )
        self.assertEqual(len(self._checkins(self.emp_a.name, day)), 3)

    def test_manual_checkin_gets_company_via_fetch_from(self):
        checkin = frappe.new_doc("Employee Checkin")
        checkin.employee = self.emp_a.name
        checkin.time = "2026-06-03 10:00:00"
        checkin.log_type = "IN"
        checkin.insert(ignore_permissions=True)
        self.assertEqual(checkin.custom_company, self.company_a)

    def test_duplicate_device_id_in_same_company_is_blocked(self):
        clone = frappe.new_doc("Employee")
        clone.first_name = "Biometric Clash Test"
        clone.gender = "Male"
        clone.date_of_birth = "1991-01-01"
        clone.date_of_joining = "2024-01-01"
        clone.company = self.company_a
        clone.status = "Active"
        clone.attendance_device_id = DEVICE_USER_ID
        with self.assertRaises(frappe.ValidationError):
            clone.insert(ignore_permissions=True)

    def test_attendance_shift_deviation_fields(self):
        att = frappe.new_doc("Attendance")
        att.employee = self.emp_a.name
        att.company = self.company_a
        att.attendance_date = "2026-06-04"
        att.status = "Present"
        att.shift = self.shift.name
        att.in_time = "2026-06-04 09:20:00"   # 20 min late
        att.out_time = "2026-06-04 16:30:00"  # 30 min early
        att.insert(ignore_permissions=True)
        self.assertEqual(att.custom_late_entry, 20 * 60)
        self.assertEqual(att.custom_early_entry, 0)
        self.assertEqual(att.custom_early_exit, 30 * 60)
        self.assertEqual(att.custom_late_exit, 0)

    def test_zz_auto_attendance_marks_present_from_punches(self):
        """Full pipeline: device punches → checkins with shift → HRMS auto
        attendance marks a submitted Present Attendance with our hooks applied.

        Named test_zz_* so it runs last — it flips the shared shift to
        auto-attendance mode.
        """
        day = "2026-06-10"
        shift = frappe.get_doc("Shift Type", self.shift.name)
        shift.enable_auto_attendance = 1
        shift.process_attendance_after = day
        shift.last_sync_of_checkin = "2026-06-11 00:00:00"
        shift.save(ignore_permissions=True)

        try:
            process_attendance_records(
                [
                    {"user_id": DEVICE_USER_ID, "timestamp": f"{day} 09:10:00"},
                    {"user_id": DEVICE_USER_ID, "timestamp": f"{day} 17:20:00"},
                ],
                device_identifier=SERIAL_A,
            )
            rows = frappe.get_all(
                "Employee Checkin",
                filters={
                    "employee": self.emp_a.name,
                    "time": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]],
                },
                fields=["name", "time", "log_type", "shift", "shift_actual_end"],
                order_by="time asc",
            )
            self.assertEqual([r.log_type for r in rows], ["IN", "OUT"])
            self.assertEqual(
                [r.shift for r in rows],
                [shift.name, shift.name],
                f"checkins did not resolve the shift: {rows}",
            )

            shift.reload()
            shift.process_auto_attendance()

            att = frappe.db.get_value(
                "Attendance",
                {"employee": self.emp_a.name, "attendance_date": day},
                ["name", "status", "docstatus", "working_hours",
                 "custom_late_entry", "custom_late_exit", "company"],
                as_dict=True,
            )
            self.assertIsNotNone(att, "auto attendance did not create an Attendance row")
            self.assertEqual(att.status, "Present")
            self.assertEqual(att.docstatus, 1)
            self.assertAlmostEqual(att.working_hours, 8.17, places=1)
            self.assertEqual(att.custom_late_entry, 10 * 60)   # 09:10 vs 09:00
            self.assertEqual(att.custom_late_exit, 20 * 60)    # 17:20 vs 17:00
            self.assertEqual(att.company, self.company_a)

            # punches got linked to the attendance row
            linked = frappe.get_all(
                "Employee Checkin",
                filters={"employee": self.emp_a.name, "attendance": att.name},
                pluck="name",
            )
            self.assertEqual(len(linked), 2)
        finally:
            frappe.db.set_value(
                "Shift Type", self.shift.name, "enable_auto_attendance", 0
            )

    def test_late_arrival_cutoff_forces_half_day(self):
        frappe.db.set_value(
            "Shift Type", self.shift.name, "custom_late_arrival_cutoff_time", "10:30:00"
        )
        frappe.clear_cache(doctype="Shift Type")
        try:
            att = frappe.new_doc("Attendance")
            att.employee = self.emp_a.name
            att.company = self.company_a
            att.attendance_date = "2026-06-05"
            att.status = "Present"
            att.shift = self.shift.name
            att.in_time = "2026-06-05 10:40:00"  # after cutoff
            att.out_time = "2026-06-05 17:00:00"
            att.insert(ignore_permissions=True)
            self.assertEqual(att.status, "Half Day")
            self.assertEqual(att.leave_type, "Leave Without Pay")
        finally:
            frappe.db.set_value(
                "Shift Type", self.shift.name, "custom_late_arrival_cutoff_time", None
            )
            frappe.clear_cache(doctype="Shift Type")
