"""
Integration module to add validation hooks to Nepali deferred accounting
This ensures validations run automatically during processing
"""
import frappe
from frappe import _


def integrate_validation_hooks():
	"""
	Patches the main deferred accounting functions to include validation
	Call this in hooks.py: after_install
	"""
	from avinashgroup_app.custom_code.deferred_revenue_and_expense import deferred_revenue as nepali_deferred
	from avinashgroup_app.custom_code.deferred_revenue_and_expense import nepali_deferred_validation as validator
	
	# Store original functions
	original_book_function = nepali_deferred.book_nepali_deferred_income_or_expense
	original_process_function = nepali_deferred.process_nepali_deferred_accounting
	
	def validated_book_function(doc, deferred_process, posting_date=None):
		"""Wrapper that adds validation before and after booking"""
		
		enable_check = "enable_deferred_revenue" if doc.doctype == "Sales Invoice" else "enable_deferred_expense"
		
		# PRE-VALIDATION: Check each item before processing
		for item in doc.get("items"):
			if item.get(enable_check):
				try:
					validator.validate_before_booking(doc, item)
				except Exception as e:
					frappe.log_error(
						title=f"Pre-validation failed - {doc.name}",
						message=str(e)
					)
					raise
		
		# Run original function
		result = original_book_function(doc, deferred_process, posting_date)
		
		# POST-VALIDATION: Reconcile after processing
		try:
			reconciliation_results = validator.reconcile_after_booking(doc)
			boundary_results = validator.validate_nepali_boundaries(doc)
			
			# Log success
			frappe.logger().info(
				f"✓ Validation passed for {doc.name}: "
				f"{len(reconciliation_results)} items reconciled"
			)
			
		except Exception as e:
			frappe.log_error(
				title=f"Post-validation failed - {doc.name}",
				message=str(e)
			)
			# Don't raise - log error but don't block processing
		
		return result
	
	def validated_process_function():
		"""Wrapper that adds health check before processing"""
		
		# PRE-CHECK: Run health check
		frappe.logger().info("Running pre-processing health check...")
		health = validator.check_all_deferred_accounting_health()
		
		if health['status'] == 'unhealthy':
			critical_issues = [i for i in health['issues'] if i['severity'] == 'critical']
			if critical_issues:
				error_msg = "Critical issues detected in deferred accounting:\n"
				for issue in critical_issues:
					error_msg += f"- {issue['message']}\n"
				
				frappe.log_error(
					title="Deferred Accounting - Critical Issues Detected",
					message=error_msg
				)
				frappe.msgprint(
					_("Critical issues detected. Check Error Log for details."),
					indicator='red'
				)
		
		# Run original function
		result = original_process_function()
		
		# POST-CHECK: Generate report
		frappe.logger().info("Generating post-processing report...")
		report = validator.generate_deferred_accounting_report()
		
		# Log summary
		frappe.logger().info(
			f"Processing complete. "
			f"Revenue: {report['summary']['total_booked_revenue']}/{report['summary']['total_deferred_revenue']}, "
			f"Expense: {report['summary']['total_booked_expense']}/{report['summary']['total_deferred_expense']}"
		)
		
		return result
	
	# Monkey patch the functions
	nepali_deferred.book_nepali_deferred_income_or_expense = validated_book_function
	nepali_deferred.process_nepali_deferred_accounting = validated_process_function
	
	frappe.logger().info("✓ Validation hooks integrated successfully")


# Add this to hooks.py:
# after_install = [
#     "avinashgroup_app.deferred_accounting.validation_integration.integrate_validation_hooks"
# ]
