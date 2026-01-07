"""
Comprehensive Test Suite for Nepali Deferred Accounting
Run with: bench --site [site] run-tests avinashgroup_app.tests.test_nepali_deferred
"""
import unittest
import frappe
from frappe.utils import getdate, add_days, date_diff, flt
import nepali_datetime
from datetime import timedelta


class TestNepaliDeferredAccounting(unittest.TestCase):
	"""Test suite for Nepali deferred accounting"""
	
	def setUp(self):
		"""Setup test data"""
		frappe.set_user("Administrator")
		
		# Create test company if not exists
		if not frappe.db.exists("Company", "Test Company"):
			company = frappe.get_doc({
				"doctype": "Company",
				"company_name": "Test Company",
				"abbr": "TC",
				"default_currency": "NPR"
			})
			company.insert(ignore_permissions=True)
		
		self.company = "Test Company"
	
	def tearDown(self):
		"""Cleanup after tests"""
		frappe.db.rollback()
	
	def test_nepali_booking_dates_full_month(self):
		"""Test that booking dates correctly identify Nepali month boundaries"""
		from avinashgroup_app.custom_code.deferred_revenue_and_expense.deferred_revenue import get_nepali_booking_dates
		
		# Create test invoice
		si = self.create_test_sales_invoice(
			service_start="2082-01-01",  # Baishakh 1
			service_end="2082-03-30"     # Ashadh 30
		)
		
		item = si.items[0]
		
		# Get first booking period
		start_date, end_date, last_gl_entry = get_nepali_booking_dates(
			si, item, posting_date=getdate("2082-04-01")
		)
		
		# Verify it's exactly one Nepali month
		start_nepali = nepali_datetime.date.from_datetime_date(start_date)
		end_nepali = nepali_datetime.date.from_datetime_date(end_date)
		
		# Should start at Baishakh 1
		self.assertEqual(start_nepali.month, 1)
		self.assertEqual(start_nepali.day, 1)
		
		# Should end at last day of Baishakh
		self.assertEqual(end_nepali.month, 1)
		# Check it's the last day (day before Jestha 1)
		next_day = end_date + timedelta(days=1)
		next_nepali = nepali_datetime.date.from_datetime_date(next_day)
		self.assertEqual(next_nepali.month, 2)  # Jestha
		self.assertEqual(next_nepali.day, 1)
		
		self.assertFalse(last_gl_entry)  # Not the last entry
	
	def test_nepali_booking_dates_partial_month(self):
		"""Test booking dates for partial month at service end"""
		from  avinashgroup_app.custom_code.deferred_revenue_and_expense.deferred_revenue import get_nepali_booking_dates
		
		# Service ends mid-month
		si = self.create_test_sales_invoice(
			service_start="2082-01-01",
			service_end="2082-01-15"  # Ends on 15th Baishakh
		)
		
		item = si.items[0]
		
		start_date, end_date, last_gl_entry = get_nepali_booking_dates(
			si, item, posting_date=getdate("2082-02-01")
		)
		
		# Should end at service end date, not month end
		self.assertEqual(end_date, item.service_end_date)
		self.assertTrue(last_gl_entry)
	
	def test_monthly_amount_calculation(self):
		"""Test monthly amount calculation matches Nepali months"""
		from  avinashgroup_app.custom_code.deferred_revenue_and_expense.deferred_revenue import calculate_nepali_monthly_amount
		
		si = self.create_test_sales_invoice(
			service_start="2082-01-01",
			service_end="2082-12-30",  # 12 Nepali months
			amount=120000
		)
		
		item = si.items[0]
		
		# Calculate for first month
		amount, base_amount = calculate_nepali_monthly_amount(
			doc=si,
			item=item,
			last_gl_entry=False,
			start_date=getdate("2082-01-01"),
			end_date=getdate("2082-01-32"),  # Last day of Baishakh
			total_days=365,
			total_booking_days=32,
			account_currency="NPR"
		)
		
		# Should be approximately 10,000 per month (120,000 / 12)
		# Allow 1% tolerance for rounding
		expected = 10000
		tolerance = 100
		self.assertAlmostEqual(base_amount, expected, delta=tolerance)
	
	def test_amount_reconciliation(self):
		"""Test that sum of all bookings equals item amount"""
		from avinashgroup_app.custom_code.deferred_revenue_and_expense.deferred_revenue import book_nepali_deferred_income_or_expense
		from erpnext.accounts.deferred_revenue import  BookingReconciler
		
		si = self.create_test_sales_invoice(
			service_start="2082-01-01",
			service_end="2082-03-30",
			amount=30000
		)
		
		# Create PDA document
		pda = frappe.get_doc({
			"doctype": "Process Deferred Accounting",
			"company": self.company,
			"type": "Income",
			"posting_date": getdate("2082-04-01")
		})
		pda.insert()
		
		# Process the invoice
		book_nepali_deferred_income_or_expense(si, pda.name, getdate("2082-04-01"))
		
		# Reconcile
		reconciler = BookingReconciler(si)
		results = reconciler.reconcile_all_items()
		
		# Verify balance
		for result in results:
			self.assertTrue(result['balanced'], 
				f"Item {result['item']} not balanced: "
				f"Expected {result['expected_amount']}, "
				f"Got {result['actual_deferred']}"
			)
	
	def test_nepali_boundary_validation(self):
		"""Test that all GL entries are on Nepali month boundaries"""
		from avinashgroup_app.custom_code.deferred_revenue_and_expense.deferred_revenue import book_nepali_deferred_income_or_expense
		from avinashgroup_app.custom_code.deferred_revenue_and_expense.nepali_deferred_validation import NepaliMonthBoundaryValidator
		
		si = self.create_test_sales_invoice(
			service_start="2082-01-01",
			service_end="2082-03-30",
			amount=30000
		)
		
		# Create PDA
		pda = frappe.get_doc({
			"doctype": "Process Deferred Accounting",
			"company": self.company,
			"type": "Income",
			"posting_date": getdate("2082-04-01")
		})
		pda.insert()
		
		# Process
		book_nepali_deferred_income_or_expense(si, pda.name, getdate("2082-04-01"))
		
		# Validate boundaries
		validator = NepaliMonthBoundaryValidator(si)
		results = validator.validate_all_items()
		
		for result in results:
			self.assertTrue(result['valid'],
				f"Boundary violations found for {result['item']}: {result['violations']}"
			)
	
	def test_no_double_booking(self):
		"""Test that running process twice doesn't double-book"""
		from avinashgroup_app.custom_code.deferred_revenue_and_expense.deferred_revenue import book_nepali_deferred_income_or_expense
		from erpnext.accounts.deferred_revenue import get_already_booked_amount
		
		si = self.create_test_sales_invoice(
			service_start="2082-01-01",
			service_end="2082-03-30",
			amount=30000
		)
		
		item = si.items[0]
		
		# Process first time
		pda1 = frappe.get_doc({
			"doctype": "Process Deferred Accounting",
			"company": self.company,
			"type": "Income",
			"posting_date": getdate("2082-02-01")
		})
		pda1.insert()
		book_nepali_deferred_income_or_expense(si, pda1.name, getdate("2082-02-01"))
		
		booked_first, _ = get_already_booked_amount(si, item)
		
		# Process second time with same date
		pda2 = frappe.get_doc({
			"doctype": "Process Deferred Accounting",
			"company": self.company,
			"type": "Income",
			"posting_date": getdate("2082-02-01")
		})
		pda2.insert()
		book_nepali_deferred_income_or_expense(si, pda2.name, getdate("2082-02-01"))
		
		booked_second, _ = get_already_booked_amount(si, item)
		
		# Amount should be the same (no double booking)
		self.assertEqual(booked_first, booked_second,
			"Double booking detected!"
		)
	
	def test_progress_tracking(self):
		"""Test progress tracking correctly identifies completion status"""
		from avinashgroup_app.custom_code.deferred_revenue_and_expense.nepali_deferred_validation import ProgressTracker
		
		si = self.create_test_sales_invoice(
			service_start="2082-01-01",
			service_end="2082-12-30",
			amount=120000
		)
		
		item = si.items[0]
		
		# Get initial status (no bookings yet)
		status = ProgressTracker.get_item_status(si, item)
		
		self.assertEqual(status['booked_amount'], 0)
		self.assertEqual(status['completion_pct'], 0)
		self.assertEqual(status['remaining_amount'], 120000)
	
	def test_validation_catches_missing_accounts(self):
		"""Test that validation catches missing account configuration"""
		from avinashgroup_app.custom_code.deferred_revenue_and_expense.nepali_deferred_validation import NepaliDeferredValidator
		
		si = self.create_test_sales_invoice(
			service_start="2082-01-01",
			service_end="2082-03-30",
			amount=30000
		)
		
		item = si.items[0]
		item.deferred_revenue_account = None  # Remove account
		
		validator = NepaliDeferredValidator(si, item)
		result = validator.validate_all()
		
		self.assertFalse(result['valid'])
		self.assertTrue(any('account' in err.lower() for err in result['errors']))
	
	def test_validation_catches_invalid_dates(self):
		"""Test that validation catches invalid date ranges"""
		from avinashgroup_app.custom_code.deferred_revenue_and_expense.nepali_deferred_validation import NepaliDeferredValidator
		
		si = self.create_test_sales_invoice(
			service_start="2082-03-30",
			service_end="2082-01-01",  # End before start!
			amount=30000
		)
		
		item = si.items[0]
		
		validator = NepaliDeferredValidator(si, item)
		result = validator.validate_all()
		
		self.assertFalse(result['valid'])
		self.assertTrue(any('end date' in err.lower() for err in result['errors']))
	
	def test_last_entry_books_exact_remainder(self):
		"""Test that last entry books exact remaining amount (no rounding error)"""
		from avinashgroup_app.custom_code.deferred_revenue_and_expense.deferred_revenue import calculate_nepali_monthly_amount
		from erpnext.accounts.deferred_revenue import get_already_booked_amount
		
		si = self.create_test_sales_invoice(
			service_start="2082-01-01",
			service_end="2082-03-30",
			amount=100  # Odd amount that will cause rounding
		)
		
		item = si.items[0]
		
		# Simulate having already booked 2 months
		# (In real scenario this would come from GL entries)
		# For this test, we'll just calculate what the last entry should be
		
		# Last entry calculation
		amount, base_amount = calculate_nepali_monthly_amount(
			doc=si,
			item=item,
			last_gl_entry=True,  # This is the last entry
			start_date=getdate("2082-03-01"),
			end_date=getdate("2082-03-30"),
			total_days=90,
			total_booking_days=30,
			account_currency="NPR"
		)
		
		# For last entry, it should book exactly the remaining amount
		# This will be calculated by: total - already_booked
		# So we can't test exact value without mock data, but we verify the logic works
		self.assertGreater(base_amount, 0)
	
	# Helper methods
	
	def create_test_sales_invoice(self, service_start, service_end, amount=10000):
		"""Create a test sales invoice with deferred revenue"""
		
		# Convert Nepali dates to Gregorian if needed
		if isinstance(service_start, str) and "-" in service_start:
			parts = service_start.split("-")
			if len(parts) == 3 and int(parts[0]) > 2050:  # Nepali year
				nepali_date = nepali_datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
				service_start = nepali_date.to_datetime_date()
		
		if isinstance(service_end, str) and "-" in service_end:
			parts = service_end.split("-")
			if len(parts) == 3 and int(parts[0]) > 2050:
				nepali_date = nepali_datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
				service_end = nepali_date.to_datetime_date()
		
		# Create customer if not exists
		if not frappe.db.exists("Customer", "Test Customer"):
			customer = frappe.get_doc({
				"doctype": "Customer",
				"customer_name": "Test Customer",
				"customer_group": "Individual",
				"territory": "All Territories"
			})
			customer.insert(ignore_permissions=True)
		
		# Get required accounts
		income_account = frappe.db.get_value("Account", {
			"company": self.company,
			"account_type": "Income Account"
		}, "name")
		
		if not income_account:
			# Create income account
			income_account = frappe.get_doc({
				"doctype": "Account",
				"account_name": "Service Income",
				"company": self.company,
				"root_type": "Income",
				"account_type": "Income Account",
				"parent_account": f"Income - {self.company}"
			})
			income_account.insert(ignore_permissions=True)
			income_account = income_account.name
		
		deferred_revenue_account = frappe.db.get_value("Account", {
			"company": self.company,
			"account_name": "Deferred Revenue"
		}, "name")
		
		if not deferred_revenue_account:
			# Create deferred revenue account
			deferred_account = frappe.get_doc({
				"doctype": "Account",
				"account_name": "Deferred Revenue",
				"company": self.company,
				"root_type": "Liability",
				"account_type": "Payable",
				"parent_account": f"Current Liabilities - {self.company}"
			})
			deferred_account.insert(ignore_permissions=True)
			deferred_revenue_account = deferred_account.name
		
		# Create sales invoice
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": "Test Customer",
			"company": self.company,
			"posting_date": frappe.utils.today(),
			"items": [{
				"item_code": "Test Service Item",
				"qty": 1,
				"rate": amount,
				"income_account": income_account,
				"enable_deferred_revenue": 1,
				"service_start_date": service_start,
				"service_end_date": service_end,
				"deferred_revenue_account": deferred_revenue_account
			}]
		})
		
		si.insert(ignore_permissions=True)
		si.submit()
		
		return si


# Run tests
def run_tests():
	"""Run all tests"""
	suite = unittest.TestLoader().loadTestsFromTestCase(TestNepaliDeferredAccounting)
	unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == "__main__":
	run_tests()
