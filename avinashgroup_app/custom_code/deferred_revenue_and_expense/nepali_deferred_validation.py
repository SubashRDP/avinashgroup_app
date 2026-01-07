"""
Nepali Deferred Accounting - COMPREHENSIVE VALIDATION & TESTING
================================================================
This module provides multiple layers of validation to ensure accounting accuracy:
1. Pre-execution validation
2. Real-time booking validation
3. Post-execution reconciliation
4. Audit trail verification
"""
import frappe
from frappe import _
from frappe.utils import flt, getdate, date_diff, cint
import nepali_datetime
from datetime import timedelta
from collections import defaultdict


class NepaliDeferredValidator:
	"""
	Main validator class that performs comprehensive checks
	"""
	
	def __init__(self, doc, item):
		self.doc = doc
		self.item = item
		self.errors = []
		self.warnings = []
		self.info = []
		
	def validate_all(self):
		"""Run all validation checks"""
		self.validate_dates()
		self.validate_amounts()
		self.validate_accounts()
		self.validate_nepali_calendar_logic()
		
		return {
			'valid': len(self.errors) == 0,
			'errors': self.errors,
			'warnings': self.warnings,
			'info': self.info
		}
	
	def validate_dates(self):
		"""Validate date fields"""
		if not self.item.service_start_date:
			self.errors.append("Service start date is missing")
			
		if not self.item.service_end_date:
			self.errors.append("Service end date is missing")
			
		if self.item.service_start_date and self.item.service_end_date:
			if self.item.service_start_date > self.item.service_end_date:
				self.errors.append(
					f"Service start date ({self.item.service_start_date}) "
					f"cannot be after end date ({self.item.service_end_date})"
				)
		
		# Check if dates are too far in future (sanity check)
		if self.item.service_end_date:
			end_nepali = nepali_datetime.date.from_datetime_date(self.item.service_end_date)
			if end_nepali.year > nepali_datetime.date.today().year + 10:
				self.warnings.append(
					f"Service end date is more than 10 years in future: {end_nepali}"
				)
	
	def validate_amounts(self):
		"""Validate amount fields"""
		if not self.item.amount or self.item.amount <= 0:
			self.errors.append(f"Item amount must be positive, got: {self.item.amount}")
			
		if not self.item.base_net_amount or self.item.base_net_amount <= 0:
			self.errors.append(f"Base net amount must be positive, got: {self.item.base_net_amount}")
			
		# Check for unreasonably large amounts (sanity check)
		if self.item.base_net_amount > 1000000000:  # 1 billion
			self.warnings.append(
				f"Base net amount is very large: {self.item.base_net_amount}"
			)
	
	def validate_accounts(self):
		"""Validate account setup"""
		if self.doc.doctype == "Sales Invoice":
			if not self.item.deferred_revenue_account:
				self.errors.append("Deferred revenue account is not set")
			if not self.item.income_account:
				self.errors.append("Income account is not set")
		else:
			if not self.item.deferred_expense_account:
				self.errors.append("Deferred expense account is not set")
			if not self.item.expense_account:
				self.errors.append("Expense account is not set")
	
	def validate_nepali_calendar_logic(self):
		"""Validate Nepali calendar conversions"""
		try:
			start_nepali = nepali_datetime.date.from_datetime_date(self.item.service_start_date)
			end_nepali = nepali_datetime.date.from_datetime_date(self.item.service_end_date)
			
			# Check if conversion back matches
			start_back = start_nepali.to_datetime_date()
			if start_back != self.item.service_start_date:
				self.errors.append(
					f"Nepali date conversion mismatch for start date: "
					f"{self.item.service_start_date} -> {start_nepali} -> {start_back}"
				)
			
			self.info.append(
				f"Service period: {start_nepali} to {end_nepali} "
				f"({end_nepali.year - start_nepali.year} years, "
				f"{(end_nepali.year - start_nepali.year) * 12 + (end_nepali.month - start_nepali.month) + 1} months)"
			)
			
		except Exception as e:
			self.errors.append(f"Nepali calendar conversion error: {str(e)}")


class BookingReconciler:
	"""
	Reconciles and validates all bookings for an invoice
	"""
	
	def __init__(self, doc):
		self.doc = doc
		self.discrepancies = []
		
	def reconcile_all_items(self):
		"""Reconcile all items in the invoice"""
		enable_check = "enable_deferred_revenue" if self.doc.doctype == "Sales Invoice" else "enable_deferred_expense"
		deferred_account = "deferred_revenue_account" if self.doc.doctype == "Sales Invoice" else "deferred_expense_account"
		
		results = []
		
		for item in self.doc.get("items"):
			if item.get(enable_check):
				result = self.reconcile_item(item, deferred_account)
				results.append(result)
		
		return results
	
	def reconcile_item(self, item, deferred_account):
		"""
		Reconcile a single item - verify that sum of GL entries equals item amount
		"""
		# Get all GL entries for this item
		gl_entries = frappe.db.sql("""
			SELECT 
				posting_date,
				debit,
				credit,
				debit_in_account_currency,
				credit_in_account_currency,
				account,
				against_voucher
			FROM `tabGL Entry`
			WHERE voucher_type = %s
				AND voucher_no = %s
				AND voucher_detail_no = %s
				AND is_cancelled = 0
			ORDER BY posting_date
		""", (self.doc.doctype, self.doc.name, item.name), as_dict=True)
		
		# Also check Journal Entries
		je_entries = frappe.db.sql("""
			SELECT 
				p.posting_date,
				c.debit,
				c.credit,
				c.debit_in_account_currency,
				c.credit_in_account_currency,
				c.account,
				p.name as against_voucher
			FROM `tabJournal Entry` p
			INNER JOIN `tabJournal Entry Account` c ON p.name = c.parent
			WHERE c.reference_type = %s
				AND c.reference_name = %s
				AND c.reference_detail_no = %s
				AND p.docstatus = 1
			ORDER BY p.posting_date
		""", (self.doc.doctype, self.doc.name, item.name), as_dict=True)
		
		all_entries = gl_entries + je_entries
		
		# Calculate totals
		deferred_account_name = item.get(deferred_account)
		income_expense_account = item.income_account if self.doc.doctype == "Sales Invoice" else item.expense_account
		
		deferred_debits = sum(e.debit for e in all_entries if e.account == deferred_account_name)
		deferred_credits = sum(e.credit for e in all_entries if e.account == deferred_account_name)
		
		income_debits = sum(e.debit for e in all_entries if e.account == income_expense_account)
		income_credits = sum(e.credit for e in all_entries if e.account == income_expense_account)
		
		# Expected totals
		expected_amount = flt(item.base_net_amount, 2)
		
		if self.doc.doctype == "Sales Invoice":
			# Revenue: Debit Deferred Revenue, Credit Income
			actual_deferred = flt(deferred_debits - deferred_credits, 2)
			actual_income = flt(income_credits - income_debits, 2)
		else:
			# Expense: Credit Deferred Expense, Debit Expense
			actual_deferred = flt(deferred_credits - deferred_debits, 2)
			actual_income = flt(income_debits - income_credits, 2)
		
		# Check for discrepancies
		diff_deferred = abs(actual_deferred - expected_amount)
		diff_income = abs(actual_income - expected_amount)
		
		result = {
			'item': item.item_code,
			'expected_amount': expected_amount,
			'actual_deferred': actual_deferred,
			'actual_income': actual_income,
			'diff_deferred': diff_deferred,
			'diff_income': diff_income,
			'entries_count': len(all_entries),
			'entries': all_entries,
			'balanced': diff_deferred < 0.01 and diff_income < 0.01,  # Allow 1 paisa difference for rounding
			'service_start': item.service_start_date,
			'service_end': item.service_end_date
		}
		
		if not result['balanced']:
			self.discrepancies.append({
				'item': item.item_code,
				'message': f"Amount mismatch: Expected {expected_amount}, "
						   f"Deferred: {actual_deferred}, Income: {actual_income}"
			})
		
		return result


class NepaliMonthBoundaryValidator:
	"""
	Validates that all GL entries are posted on correct Nepali month boundaries
	"""
	
	def __init__(self, doc):
		self.doc = doc
		self.violations = []
	
	def validate_all_items(self):
		"""Validate all items"""
		enable_check = "enable_deferred_revenue" if self.doc.doctype == "Sales Invoice" else "enable_deferred_expense"
		
		results = []
		for item in self.doc.get("items"):
			if item.get(enable_check):
				result = self.validate_item_boundaries(item)
				results.append(result)
		
		return results
	
	def validate_item_boundaries(self, item):
		"""
		Validate that each GL entry represents exactly one Nepali month
		(or the final partial period)
		"""
		# Get all GL entries
		gl_entries = frappe.db.sql("""
			SELECT posting_date
			FROM `tabGL Entry`
			WHERE voucher_type = %s
				AND voucher_no = %s
				AND voucher_detail_no = %s
				AND is_cancelled = 0
			ORDER BY posting_date
		""", (self.doc.doctype, self.doc.name, item.name), as_dict=True)
		
		violations = []
		prev_date = None
		
		for entry in gl_entries:
			posting_date = entry.posting_date
			posting_nepali = nepali_datetime.date.from_datetime_date(posting_date)
			
			# Check if this is last day of Nepali month OR service end date
			is_month_end = self.is_nepali_month_end(posting_date)
			is_service_end = (posting_date == item.service_end_date)
			
			if not (is_month_end or is_service_end):
				violations.append({
					'posting_date': posting_date,
					'posting_nepali': str(posting_nepali),
					'issue': 'Not on Nepali month boundary',
					'is_month_end': is_month_end,
					'is_service_end': is_service_end
				})
			
			# Verify gap from previous entry
			if prev_date:
				prev_nepali = nepali_datetime.date.from_datetime_date(prev_date)
				
				# Should be exactly one Nepali month apart (or less for final entry)
				month_diff = (posting_nepali.year - prev_nepali.year) * 12 + \
							 (posting_nepali.month - prev_nepali.month)
				
				if month_diff > 1:
					violations.append({
						'posting_date': posting_date,
						'prev_date': prev_date,
						'issue': f'Gap of {month_diff} months detected',
						'expected': 1
					})
			
			prev_date = posting_date
		
		return {
			'item': item.item_code,
			'entries_count': len(gl_entries),
			'violations': violations,
			'valid': len(violations) == 0
		}
	
	def is_nepali_month_end(self, gregorian_date):
		"""Check if a Gregorian date is the last day of a Nepali month"""
		nepali_date = nepali_datetime.date.from_datetime_date(gregorian_date)
		
		# Get first day of next Nepali month
		if nepali_date.month == 12:
			next_month_first = nepali_datetime.date(nepali_date.year + 1, 1, 1)
		else:
			next_month_first = nepali_datetime.date(nepali_date.year, nepali_date.month + 1, 1)
		
		# Last day of current month is day before next month
		month_last = next_month_first.to_datetime_date() - timedelta(days=1)
		
		return gregorian_date == month_last


class ProgressTracker:
	"""
	Tracks progress of deferred accounting to detect incomplete processing
	"""
	
	@staticmethod
	def get_item_status(doc, item):
		"""Get processing status of an item"""
		from avinashgroup_app.utils.nepali_date import get_today_nepali_date
		from erpnext.accounts.deferred_revenue import get_already_booked_amount
		
		already_booked, _ = get_already_booked_amount(doc, item)
		total_amount = item.base_net_amount
		remaining = total_amount - already_booked
		
		completion_pct = (already_booked / total_amount * 100) if total_amount > 0 else 0
		
		# Calculate expected completion
		today = getdate()
		service_days = date_diff(item.service_end_date, item.service_start_date) + 1
		
		if today >= item.service_end_date:
			expected_pct = 100.0
		elif today <= item.service_start_date:
			expected_pct = 0.0
		else:
			elapsed_days = date_diff(today, item.service_start_date) + 1
			expected_pct = (elapsed_days / service_days * 100)
		
		# Get latest booking date
		latest_gl = frappe.db.sql("""
			SELECT MAX(posting_date) as latest
			FROM `tabGL Entry`
			WHERE voucher_type = %s
				AND voucher_no = %s
				AND voucher_detail_no = %s
				AND is_cancelled = 0
		""", (doc.doctype, doc.name, item.name), as_dict=True)
		
		latest_booking = latest_gl[0].latest if latest_gl and latest_gl[0].latest else None
		
		# Detect stale processing
		is_stale = False
		if latest_booking:
			today_nepali = get_today_nepali_date()
			latest_nepali = nepali_datetime.date.from_datetime_date(latest_booking)
			
			month_diff = (today_nepali.year - latest_nepali.year) * 12 + \
						 (today_nepali.month - latest_nepali.month)
			
			# If more than 2 months behind and not completed
			if month_diff > 2 and completion_pct < 100:
				is_stale = True
		
		return {
			'item': item.item_code,
			'total_amount': total_amount,
			'booked_amount': already_booked,
			'remaining_amount': remaining,
			'completion_pct': round(completion_pct, 2),
			'expected_pct': round(expected_pct, 2),
			'behind_schedule': completion_pct < expected_pct - 5,  # 5% tolerance
			'latest_booking': latest_booking,
			'is_stale': is_stale,
			'service_start': item.service_start_date,
			'service_end': item.service_end_date
		}


# ============================================================================
# VALIDATION HOOKS
# ============================================================================

def validate_before_booking(doc, item):
	"""
	Run before processing any item - prevents bad data from being processed
	"""
	validator = NepaliDeferredValidator(doc, item)
	result = validator.validate_all()
	
	if not result['valid']:
		error_msg = "\n".join(result['errors'])
		frappe.throw(
			_("Cannot process deferred accounting for item {0}:\n{1}").format(
				item.item_code, error_msg
			)
		)
	
	# Log warnings
	for warning in result['warnings']:
		frappe.log_error(
			title=f"Deferred Accounting Warning - {doc.name}",
			message=warning
		)
	
	return result


def reconcile_after_booking(doc):
	"""
	Run after processing entire invoice - verifies all bookings are correct
	"""
	reconciler = BookingReconciler(doc)
	results = reconciler.reconcile_all_items()
	
	# Check for any unbalanced items
	errors = []
	for result in results:
		if not result['balanced']:
			errors.append(
				f"Item {result['item']}: Expected {result['expected_amount']}, "
				f"Got Deferred={result['actual_deferred']}, Income={result['actual_income']}"
			)
	
	if errors:
		error_msg = "\n".join(errors)
		frappe.log_error(
			title=f"Deferred Accounting Reconciliation Failed - {doc.name}",
			message=error_msg
		)
		frappe.throw(_("Reconciliation failed:\n{0}").format(error_msg))
	
	return results


def validate_nepali_boundaries(doc):
	"""
	Validate that all GL entries are on proper Nepali month boundaries
	"""
	validator = NepaliMonthBoundaryValidator(doc)
	results = validator.validate_all_items()
	
	# Check for violations
	violations = []
	for result in results:
		if not result['valid']:
			violations.extend(result['violations'])
	
	if violations:
		frappe.log_error(
			title=f"Nepali Month Boundary Violations - {doc.name}",
			message=frappe.as_json(violations, indent=2)
		)
	
	return results


# ============================================================================
# REPORTING FUNCTIONS
# ============================================================================

def generate_deferred_accounting_report(company=None, from_date=None, to_date=None):
	"""
	Generate comprehensive report on deferred accounting status
	"""
	filters = {"docstatus": 1}
	if company:
		filters["company"] = company
	
	# Get all sales invoices with deferred revenue
	sales_invoices = frappe.get_all(
		"Sales Invoice",
		filters=filters,
		fields=["name", "customer", "posting_date", "company"]
	)
	
	# Get all purchase invoices with deferred expense
	purchase_invoices = frappe.get_all(
		"Purchase Invoice",
		filters=filters,
		fields=["name", "supplier", "posting_date", "company"]
	)
	
	report_data = {
		'sales_invoices': [],
		'purchase_invoices': [],
		'summary': {
			'total_deferred_revenue': 0,
			'total_booked_revenue': 0,
			'total_deferred_expense': 0,
			'total_booked_expense': 0,
			'items_behind_schedule': 0,
			'stale_items': 0
		}
	}
	
	# Process sales invoices
	for si in sales_invoices:
		doc = frappe.get_doc("Sales Invoice", si.name)
		
		for item in doc.get("items"):
			if item.enable_deferred_revenue:
				status = ProgressTracker.get_item_status(doc, item)
				status['invoice'] = si.name
				status['customer'] = si.customer
				
				report_data['sales_invoices'].append(status)
				report_data['summary']['total_deferred_revenue'] += status['total_amount']
				report_data['summary']['total_booked_revenue'] += status['booked_amount']
				
				if status['behind_schedule']:
					report_data['summary']['items_behind_schedule'] += 1
				if status['is_stale']:
					report_data['summary']['stale_items'] += 1
	
	# Process purchase invoices
	for pi in purchase_invoices:
		doc = frappe.get_doc("Purchase Invoice", pi.name)
		
		for item in doc.get("items"):
			if item.enable_deferred_expense:
				status = ProgressTracker.get_item_status(doc, item)
				status['invoice'] = pi.name
				status['supplier'] = pi.supplier
				
				report_data['purchase_invoices'].append(status)
				report_data['summary']['total_deferred_expense'] += status['total_amount']
				report_data['summary']['total_booked_expense'] += status['booked_amount']
				
				if status['behind_schedule']:
					report_data['summary']['items_behind_schedule'] += 1
				if status['is_stale']:
					report_data['summary']['stale_items'] += 1
	
	return report_data


def check_all_deferred_accounting_health():
	"""
	Run comprehensive health check on all deferred accounting
	Returns health report with issues found
	"""
	report = generate_deferred_accounting_report()
	
	issues = []
	
	# Check for stale items
	if report['summary']['stale_items'] > 0:
		issues.append({
			'severity': 'high',
			'type': 'stale_processing',
			'message': f"{report['summary']['stale_items']} items have not been processed in over 2 months"
		})
	
	# Check for items behind schedule
	if report['summary']['items_behind_schedule'] > 0:
		issues.append({
			'severity': 'medium',
			'type': 'behind_schedule',
			'message': f"{report['summary']['items_behind_schedule']} items are behind expected schedule"
		})
	
	# Verify all bookings balance
	all_docs = []
	for item in report['sales_invoices']:
		doc = frappe.get_doc("Sales Invoice", item['invoice'])
		if doc not in all_docs:
			all_docs.append(doc)
	
	for item in report['purchase_invoices']:
		doc = frappe.get_doc("Purchase Invoice", item['invoice'])
		if doc not in all_docs:
			all_docs.append(doc)
	
	for doc in all_docs:
		reconciler = BookingReconciler(doc)
		results = reconciler.reconcile_all_items()
		
		for result in results:
			if not result['balanced']:
				issues.append({
					'severity': 'critical',
					'type': 'unbalanced',
					'invoice': doc.name,
					'item': result['item'],
					'message': f"Amounts don't balance: Expected {result['expected_amount']}, "
							   f"Deferred {result['actual_deferred']}, Income {result['actual_income']}"
				})
	
	health_status = 'healthy' if len(issues) == 0 else 'unhealthy'
	
	return {
		'status': health_status,
		'issues': issues,
		'summary': report['summary'],
		'timestamp': frappe.utils.now()
	}


# ============================================================================
# TESTING FUNCTIONS
# ============================================================================

def run_comprehensive_tests():
	"""
	Run all validation tests and generate report
	"""
	frappe.logger().info("=" * 60)
	frappe.logger().info("COMPREHENSIVE DEFERRED ACCOUNTING VALIDATION")
	frappe.logger().info("=" * 60)
	
	# 1. Health Check
	frappe.logger().info("\n1. Running Health Check...")
	health = check_all_deferred_accounting_health()
	frappe.logger().info(f"   Status: {health['status'].upper()}")
	frappe.logger().info(f"   Issues Found: {len(health['issues'])}")
	
	for issue in health['issues']:
		frappe.logger().info(f"   [{issue['severity'].upper()}] {issue['message']}")
	
	# 2. Boundary Validation
	frappe.logger().info("\n2. Validating Nepali Month Boundaries...")
	
	# Get sample of invoices
	invoices = frappe.get_all("Sales Invoice", 
		filters={"docstatus": 1}, 
		limit=10
	)
	
	boundary_issues = 0
	for inv in invoices:
		doc = frappe.get_doc("Sales Invoice", inv.name)
		results = validate_nepali_boundaries(doc)
		
		for result in results:
			if not result['valid']:
				boundary_issues += len(result['violations'])
	
	frappe.logger().info(f"   Boundary Violations: {boundary_issues}")
	
	# 3. Generate Full Report
	frappe.logger().info("\n3. Generating Comprehensive Report...")
	report = generate_deferred_accounting_report()
	
	frappe.logger().info(f"\n   SUMMARY:")
	frappe.logger().info(f"   Revenue - Total: {report['summary']['total_deferred_revenue']}, "
						 f"Booked: {report['summary']['total_booked_revenue']}")
	frappe.logger().info(f"   Expense - Total: {report['summary']['total_deferred_expense']}, "
						 f"Booked: {report['summary']['total_booked_expense']}")
	frappe.logger().info(f"   Behind Schedule: {report['summary']['items_behind_schedule']}")
	frappe.logger().info(f"   Stale Items: {report['summary']['stale_items']}")
	
	frappe.logger().info("=" * 60)
	frappe.logger().info("VALIDATION COMPLETE")
	frappe.logger().info("=" * 60)
	
	return {
		'health': health,
		'boundary_issues': boundary_issues,
		'report': report
	}
