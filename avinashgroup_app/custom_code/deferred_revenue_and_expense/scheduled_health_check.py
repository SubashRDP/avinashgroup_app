"""
Scheduled Health Check for Nepali Deferred Accounting
Runs daily to detect issues before they become critical
"""
import frappe
from frappe import _
from frappe.utils import now, add_days, get_datetime


def daily_deferred_accounting_health_check():
	"""
	Runs daily health check and sends alerts if issues found
	Add to hooks.py:
	
	scheduler_events = {
		"daily": [
			"avinashgroup_app.deferred_accounting.scheduled_health_check.daily_deferred_accounting_health_check"
		]
	}
	"""
	from avinashgroup_app.deferred_accounting.nepali_deferred_validation import (
		check_all_deferred_accounting_health,
		generate_deferred_accounting_report
	)
	
	frappe.logger().info("=" * 60)
	frappe.logger().info("SCHEDULED: Daily Deferred Accounting Health Check")
	frappe.logger().info(f"Time: {now()}")
	frappe.logger().info("=" * 60)
	
	try:
		# Run health check
		health = check_all_deferred_accounting_health()
		
		# Generate report
		report = generate_deferred_accounting_report()
		
		# Log results
		frappe.logger().info(f"\nHealth Status: {health['status'].upper()}")
		frappe.logger().info(f"Issues Found: {len(health['issues'])}")
		
		# Categorize issues by severity
		critical_issues = [i for i in health['issues'] if i['severity'] == 'critical']
		high_issues = [i for i in health['issues'] if i['severity'] == 'high']
		medium_issues = [i for i in health['issues'] if i['severity'] == 'medium']
		
		frappe.logger().info(f"  Critical: {len(critical_issues)}")
		frappe.logger().info(f"  High: {len(high_issues)}")
		frappe.logger().info(f"  Medium: {len(medium_issues)}")
		
		# Send alerts if critical or high issues found
		if critical_issues or high_issues:
			send_health_alert(health, report, critical_issues, high_issues)
		
		# Create health check log
		create_health_check_log(health, report)
		
		frappe.logger().info("=" * 60)
		frappe.logger().info("Health Check Complete")
		frappe.logger().info("=" * 60)
		
	except Exception as e:
		frappe.log_error(
			title="Daily Health Check Failed",
			message=frappe.get_traceback()
		)


def send_health_alert(health, report, critical_issues, high_issues):
	"""Send email alert to system manager"""
	
	# Get recipients
	recipients = frappe.get_all(
		"User",
		filters={"role": "System Manager", "enabled": 1},
		fields=["email"]
	)
	
	if not recipients:
		frappe.logger().warning("No System Managers found to send health alert")
		return
	
	# Prepare email content
	subject = f"🚨 Deferred Accounting Health Alert - {len(critical_issues)} Critical, {len(high_issues)} High"
	
	message = f"""
	<h2>Deferred Accounting Health Alert</h2>
	<p><strong>Status:</strong> <span style="color: red;">{health['status'].upper()}</span></p>
	<p><strong>Time:</strong> {health['timestamp']}</p>
	
	<h3>Summary</h3>
	<table border="1" cellpadding="5" style="border-collapse: collapse;">
		<tr>
			<th>Metric</th>
			<th>Value</th>
		</tr>
		<tr>
			<td>Total Deferred Revenue</td>
			<td>{frappe.format_value(report['summary']['total_deferred_revenue'], 'Currency')}</td>
		</tr>
		<tr>
			<td>Booked Revenue</td>
			<td>{frappe.format_value(report['summary']['total_booked_revenue'], 'Currency')}</td>
		</tr>
		<tr>
			<td>Total Deferred Expense</td>
			<td>{frappe.format_value(report['summary']['total_deferred_expense'], 'Currency')}</td>
		</tr>
		<tr>
			<td>Booked Expense</td>
			<td>{frappe.format_value(report['summary']['total_booked_expense'], 'Currency')}</td>
		</tr>
		<tr style="background-color: #ffcccc;">
			<td>Items Behind Schedule</td>
			<td>{report['summary']['items_behind_schedule']}</td>
		</tr>
		<tr style="background-color: #ffcccc;">
			<td>Stale Items (>2 months)</td>
			<td>{report['summary']['stale_items']}</td>
		</tr>
	</table>
	"""
	
	# Add critical issues
	if critical_issues:
		message += "\n<h3 style='color: red;'>Critical Issues</h3><ul>"
		for issue in critical_issues:
			message += f"<li><strong>{issue['type']}</strong>: {issue['message']}</li>"
		message += "</ul>"
	
	# Add high issues
	if high_issues:
		message += "\n<h3 style='color: orange;'>High Priority Issues</h3><ul>"
		for issue in high_issues:
			message += f"<li><strong>{issue['type']}</strong>: {issue['message']}</li>"
		message += "</ul>"
	
	message += """
	<p><strong>Action Required:</strong> Please review the deferred accounting configuration and GL entries.</p>
	<p>Run the health check report for detailed analysis:
	<code>bench --site [site-name] console</code><br/>
	<code>from avinashgroup_app.deferred_accounting.nepali_deferred_validation import run_comprehensive_tests</code><br/>
	<code>run_comprehensive_tests()</code>
	</p>
	"""
	
	# Send email
	for recipient in recipients:
		try:
			frappe.sendmail(
				recipients=[recipient.email],
				subject=subject,
				message=message,
				delayed=False
			)
			frappe.logger().info(f"Alert sent to {recipient.email}")
		except Exception as e:
			frappe.log_error(
				title=f"Failed to send health alert to {recipient.email}",
				message=str(e)
			)


def create_health_check_log(health, report):
	"""Create a log document for audit trail"""
	
	try:
		log = frappe.get_doc({
			"doctype": "Error Log",
			"error": frappe.as_json(health, indent=2),
			"method": "daily_deferred_accounting_health_check",
			"creation": now()
		})
		
		# Use custom title based on health status
		if health['status'] == 'healthy':
			log.error = f"Health Check Passed - {now()}\n\n" + log.error
		else:
			log.error = f"Health Check FAILED - {len(health['issues'])} issues - {now()}\n\n" + log.error
		
		log.insert(ignore_permissions=True)
		
	except Exception as e:
		frappe.logger().error(f"Failed to create health check log: {str(e)}")


def weekly_comprehensive_validation():
	"""
	Run comprehensive validation weekly (more thorough than daily check)
	Add to hooks.py:
	
	scheduler_events = {
		"weekly": [
			"avinashgroup_app.deferred_accounting.scheduled_health_check.weekly_comprehensive_validation"
		]
	}
	"""
	from avinashgroup_app.deferred_accounting.nepali_deferred_validation import run_comprehensive_tests
	
	frappe.logger().info("=" * 60)
	frappe.logger().info("SCHEDULED: Weekly Comprehensive Validation")
	frappe.logger().info(f"Time: {now()}")
	frappe.logger().info("=" * 60)
	
	try:
		results = run_comprehensive_tests()
		
		# Send detailed report to System Managers
		send_weekly_report(results)
		
	except Exception as e:
		frappe.log_error(
			title="Weekly Comprehensive Validation Failed",
			message=frappe.get_traceback()
		)


def send_weekly_report(results):
	"""Send detailed weekly report"""
	
	recipients = frappe.get_all(
		"User",
		filters={"role": "System Manager", "enabled": 1},
		fields=["email"]
	)
	
	if not recipients:
		return
	
	health = results['health']
	report = results['report']
	
	subject = f"📊 Weekly Deferred Accounting Report - Status: {health['status'].upper()}"
	
	message = f"""
	<h2>Weekly Deferred Accounting Comprehensive Report</h2>
	<p><strong>Period:</strong> {add_days(now(), -7)} to {now()}</p>
	
	<h3>Overall Health</h3>
	<p><strong>Status:</strong> {health['status'].upper()}</p>
	<p><strong>Total Issues:</strong> {len(health['issues'])}</p>
	<p><strong>Boundary Violations:</strong> {results['boundary_issues']}</p>
	
	<h3>Financial Summary</h3>
	<table border="1" cellpadding="5" style="border-collapse: collapse;">
		<tr>
			<th>Category</th>
			<th>Total Amount</th>
			<th>Booked Amount</th>
			<th>Remaining</th>
			<th>% Complete</th>
		</tr>
		<tr>
			<td>Revenue</td>
			<td>{frappe.format_value(report['summary']['total_deferred_revenue'], 'Currency')}</td>
			<td>{frappe.format_value(report['summary']['total_booked_revenue'], 'Currency')}</td>
			<td>{frappe.format_value(report['summary']['total_deferred_revenue'] - report['summary']['total_booked_revenue'], 'Currency')}</td>
			<td>{round(report['summary']['total_booked_revenue'] / report['summary']['total_deferred_revenue'] * 100, 1) if report['summary']['total_deferred_revenue'] > 0 else 0}%</td>
		</tr>
		<tr>
			<td>Expense</td>
			<td>{frappe.format_value(report['summary']['total_deferred_expense'], 'Currency')}</td>
			<td>{frappe.format_value(report['summary']['total_booked_expense'], 'Currency')}</td>
			<td>{frappe.format_value(report['summary']['total_deferred_expense'] - report['summary']['total_booked_expense'], 'Currency')}</td>
			<td>{round(report['summary']['total_booked_expense'] / report['summary']['total_deferred_expense'] * 100, 1) if report['summary']['total_deferred_expense'] > 0 else 0}%</td>
		</tr>
	</table>
	
	<h3>Processing Status</h3>
	<ul>
		<li>Items Behind Schedule: <strong>{report['summary']['items_behind_schedule']}</strong></li>
		<li>Stale Items (>2 months): <strong>{report['summary']['stale_items']}</strong></li>
		<li>Total Revenue Items: <strong>{len(report['sales_invoices'])}</strong></li>
		<li>Total Expense Items: <strong>{len(report['purchase_invoices'])}</strong></li>
	</ul>
	"""
	
	if health['issues']:
		message += "\n<h3>Issues Detected</h3><ul>"
		for issue in health['issues']:
			severity_color = {'critical': 'red', 'high': 'orange', 'medium': 'yellow'}.get(issue['severity'], 'gray')
			message += f"<li style='color: {severity_color};'><strong>[{issue['severity'].upper()}]</strong> {issue['message']}</li>"
		message += "</ul>"
	else:
		message += "\n<p style='color: green;'><strong>✓ No issues detected. System is healthy.</strong></p>"
	
	message += """
	<hr/>
	<p><em>This is an automated report. For detailed analysis, run the comprehensive tests from bench console.</em></p>
	"""
	
	for recipient in recipients:
		try:
			frappe.sendmail(
				recipients=[recipient.email],
				subject=subject,
				message=message,
				delayed=False
			)
		except Exception as e:
			frappe.log_error(
				title=f"Failed to send weekly report to {recipient.email}",
				message=str(e)
			)
