import unittest
from unittest.mock import patch
import frappe

# Import your report function
from avinashgroup_app.avinas_group_app.report.avinas_vehicle_expense.vehicle_expense_report import (
    execute,
    get_pi_conditions,
    get_je_conditions,
    get_columns,
)


class TestVehicleExpenseReport(unittest.TestCase):

    def test_get_columns(self):
        columns = get_columns()
        # Check that columns have expected fieldnames
        expected_fieldnames = ["vehicle_no", "fuel", "repair", "others"]
        self.assertEqual([col["fieldname"] for col in columns], expected_fieldnames)

    def test_pi_conditions(self):
        filters = {
            "company": "My Company",
            "period_start_date": "2025-01-01",
            "period_end_date": "2025-12-31",
            "vehicle_no": "V123"
        }
        conditions = get_pi_conditions(filters)
        # Conditions should contain all filters
        self.assertIn("pi.company = %(company)s", conditions)
        self.assertIn("pi.posting_date >= %(period_start_date)s", conditions)
        self.assertIn("pi.posting_date <= %(period_end_date)s", conditions)
        self.assertIn("pic.custom_subtype = %(vehicle_no)s", conditions)

    def test_je_conditions(self):
        filters = {
            "company": "My Company",
            "period_start_date": "2025-01-01",
            "period_end_date": "2025-12-31",
            "vehicle_no": "V123"
        }
        conditions = get_je_conditions(filters)
        self.assertIn("je.company = %(company)s", conditions)
        self.assertIn("je.posting_date >= %(period_start_date)s", conditions)
        self.assertIn("je.posting_date <= %(period_end_date)s", conditions)
        self.assertIn("jea.custom_subtype = %(vehicle_no)s", conditions)

    @patch("frappe.db.sql")
    def test_execute_returns_columns_and_data(self, mock_sql):
        # Mock the database result
        mock_sql.return_value = [
            {"vehicle_no": "V123", "fuel": 1000, "repair": 500, "others": 200}
        ]
        filters = {
            "company": "My Company",
            "period_start_date": "2025-01-01",
            "period_end_date": "2025-12-31",
        }

        columns, data = execute(filters)
        
        # Columns are correct
        self.assertEqual([col["fieldname"] for col in columns], ["vehicle_no", "fuel", "repair", "others"])
        # Data matches mocked DB result
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["vehicle_no"], "V123")
        self.assertEqual(data[0]["fuel"], 1000)
        self.assertEqual(data[0]["repair"], 500)
        self.assertEqual(data[0]["others"], 200)

if __name__ == "__main__":
    unittest.main()
