"""
Nepali Date Utility Functions - CORRECTED VERSION
==================================================
"""

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
    
    Example:
        If today is 2081-10-01 (1st Magh):
        - Returns: (2081-09-01 to 2081-09-30) in Gregorian dates
        
        If today is 2081-10-15 (15th Magh):
        - Returns: (2081-09-01 to 2081-09-30) in Gregorian dates
        - NOT (2081-09-01 to 2081-10-14) ❌
    """
    today_nepali = get_today_nepali_date()
    
    # Calculate previous month
    prev_month = today_nepali.month - 1
    prev_year = today_nepali.year
    
    # Handle year rollover (if current month is Baisakh/month 1)
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
    
    # ✅ First day of previous Nepali month
    prev_month_start_nepali = nepali_datetime.date(prev_year, prev_month, 1)
    start_date = prev_month_start_nepali.to_datetime_date()
    
    # ✅ FIXED: Last day of previous Nepali month
    # Get first day of CURRENT month, then subtract 1 day
    current_month_first_nepali = nepali_datetime.date(today_nepali.year, today_nepali.month, 1)
    end_date = current_month_first_nepali.to_datetime_date() - timedelta(days=1)
    
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


# ============================================================================
# TEST FUNCTION TO VERIFY THE FIX
# ============================================================================

def test_get_previous_month():
    """
    Test function to verify get_previous_nepali_month_dates() works correctly
    Run this to see the difference between old and new logic
    """
    
    print("\n" + "="*70)
    print("TESTING get_previous_nepali_month_dates()")
    print("="*70)
    
    today_nepali = get_today_nepali_date()
    print(f"\n📅 Today (Nepali): {today_nepali}")
    print(f"📅 Today (Gregorian): {today_nepali.to_datetime_date()}")
    print(f"📅 Is 1st of month?: {is_first_of_nepali_month()}")
    
    print("\n" + "-"*70)
    print("PREVIOUS MONTH CALCULATION:")
    print("-"*70)
    
    start_date, end_date = get_previous_nepali_month_dates()
    
    # Convert back to Nepali for verification
    start_nepali = nepali_datetime.date.from_datetime_date(start_date)
    end_nepali = nepali_datetime.date.from_datetime_date(end_date)
    
    print(f"\n✅ Start Date:")
    print(f"   - Gregorian: {start_date}")
    print(f"   - Nepali: {start_nepali} ({get_nepali_month_name(start_nepali.month)} {start_nepali.day})")
    
    print(f"\n✅ End Date:")
    print(f"   - Gregorian: {end_date}")
    print(f"   - Nepali: {end_nepali} ({get_nepali_month_name(end_nepali.month)} {end_nepali.day})")
    
    # Verify the logic
    print("\n" + "-"*70)
    print("VERIFICATION:")
    print("-"*70)
    
    # Check 1: Start should be 1st of previous month
    if start_nepali.day == 1:
        print(f"✅ Start date is 1st of {get_nepali_month_name(start_nepali.month)}")
    else:
        print(f"❌ ERROR: Start date is NOT 1st (it's {start_nepali.day})")
    
    # Check 2: End should be last day of previous month
    prev_month = today_nepali.month - 1 if today_nepali.month > 1 else 12
    if end_nepali.month == prev_month:
        print(f"✅ End date is in previous month ({get_nepali_month_name(end_nepali.month)})")
    else:
        print(f"❌ ERROR: End date is NOT in previous month")
        print(f"   Expected month: {prev_month}, Got: {end_nepali.month}")
    
    # Check 3: End should be exactly one day before current month starts
    current_month_first = nepali_datetime.date(today_nepali.year, today_nepali.month, 1)
    expected_end = current_month_first.to_datetime_date() - timedelta(days=1)
    
    if end_date == expected_end:
        print(f"✅ End date is last day of previous Nepali month")
    else:
        print(f"❌ ERROR: End date mismatch")
        print(f"   Expected: {expected_end}")
        print(f"   Got: {end_date}")
    
    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70 + "\n")


# ============================================================================
# COMPARISON: OLD vs NEW LOGIC
# ============================================================================

def compare_old_vs_new_logic():
    """
    Show the difference between old (buggy) and new (fixed) logic
    """
    
    today_nepali = get_today_nepali_date()
    
    print("\n" + "="*70)
    print("COMPARISON: OLD vs NEW LOGIC")
    print("="*70)
    print(f"\nToday: {today_nepali} ({get_nepali_month_name(today_nepali.month)} {today_nepali.day})")
    
    # OLD LOGIC (BUGGY)
    print("\n📛 OLD LOGIC (Your original code):")
    print("-"*70)
    prev_month = today_nepali.month - 1 if today_nepali.month > 1 else 12
    prev_year = today_nepali.year if today_nepali.month > 1 else today_nepali.year - 1
    
    prev_month_start_nepali = nepali_datetime.date(prev_year, prev_month, 1)
    old_start = prev_month_start_nepali.to_datetime_date()
    old_end = today_nepali.to_datetime_date() - timedelta(days=1)  # ❌ BUG: Just yesterday
    
    old_end_nepali = nepali_datetime.date.from_datetime_date(old_end)
    
    print(f"Start: {old_start} → {nepali_datetime.date.from_datetime_date(old_start)}")
    print(f"End:   {old_end} → {old_end_nepali}")
    
    if old_end_nepali.month == today_nepali.month:
        print(f"❌ PROBLEM: End date is in CURRENT month ({get_nepali_month_name(old_end_nepali.month)})")
        print(f"   This happens when today is NOT the 1st of the month!")
    else:
        print(f"✅ End date is in previous month (works when run on 1st only)")
    
    # NEW LOGIC (FIXED)
    print("\n✅ NEW LOGIC (Fixed version):")
    print("-"*70)
    new_start, new_end = get_previous_nepali_month_dates()
    new_end_nepali = nepali_datetime.date.from_datetime_date(new_end)
    
    print(f"Start: {new_start} → {nepali_datetime.date.from_datetime_date(new_start)}")
    print(f"End:   {new_end} → {new_end_nepali}")
    print(f"✅ End date is ALWAYS last day of previous Nepali month")
    print(f"   Works correctly regardless of which day it's run!")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    # Run tests if executed directly
    test_get_previous_month()
    compare_old_vs_new_logic()