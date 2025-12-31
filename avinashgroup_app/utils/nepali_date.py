import nepali_datetime
from datetime import timedelta
import frappe


def get_today_nepali_date():
	"""Get today's date in Nepali calendar"""
	return nepali_datetime.date.today()


def is_first_of_nepali_month():
	"""Check if today is the 1st day of Nepali month"""
	today_nepali = get_today_nepali_date()
	return today_nepali.day == 1


def get_previous_nepali_month_dates():
	"""
	Get the start and end dates of previous Nepali month in Gregorian calendar
	
	Returns:
		tuple: (start_date, end_date) in datetime.date format (Gregorian)
	"""
	today_nepali = get_today_nepali_date()
	
	# Calculate previous month
	prev_month = today_nepali.month - 1
	prev_year = today_nepali.year
	
	# Handle year rollover (if current month is Baisakh/month 1)
	if prev_month == 0:
		prev_month = 12
		prev_year -= 1
	
	# First day of previous Nepali month
	prev_month_start_nepali = nepali_datetime.date(prev_year, prev_month, 1)
	
	# Convert to Gregorian
	start_date = prev_month_start_nepali.to_datetime_date()
	
	# End date is yesterday (last day of previous Nepali month)
	end_date = today_nepali.to_datetime_date() - timedelta(days=1)
	
	return start_date, end_date


def get_nepali_month_name(month_number):
	"""
	Get Nepali month name from month number
	
	Args:
		month_number (int): Month number (1-12)
	
	Returns:
		str: Nepali month name
	"""
	month_names = {
		1: "Baisakh",
		2: "Jestha",
		3: "Ashadh",
		4: "Shrawan",
		5: "Bhadra",
		6: "Ashwin",
		7: "Kartik",
		8: "Mangsir",
		9: "Poush",
		10: "Magh",
		11: "Falgun",
		12: "Chaitra"
	}
	return month_names.get(month_number, "Unknown")


def log_nepali_date_info():
	"""Log current Nepali date information for debugging"""
	today_nepali = get_today_nepali_date()
	today_gregorian = today_nepali.to_datetime_date()
	
	frappe.logger().info(f"""
	Nepali Date Info:
	- Nepali Date: {today_nepali} ({get_nepali_month_name(today_nepali.month)} {today_nepali.day}, {today_nepali.year})
	- Gregorian Date: {today_gregorian}
	- Is 1st of Nepali Month: {is_first_of_nepali_month()}
	""")
	
	if is_first_of_nepali_month():
		start_date, end_date = get_previous_nepali_month_dates()
		frappe.logger().info(f"""
		Previous Nepali Month Period:
		- Start Date (Gregorian): {start_date}
		- End Date (Gregorian): {end_date}
		""")