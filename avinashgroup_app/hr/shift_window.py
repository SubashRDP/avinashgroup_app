"""A check-in window of 0 means the whole day, not "only at the shift's minute".

HRMS attaches a punch to a shift only inside [start − Begin check-in before
shift start, end + Allow check-out after shift end]. Left at 0 — as NGI's
9:00–5:00 shift was — the window is exactly 9:00 to 17:00, so a tap at 8:58 or
17:30 belonged to no shift: 461 punches since Shrawan sat unlinked as
"offshift", and days the person worked showed Absent, or Half Day off one
stray punch. The company's rule (user, 2026-10-15): coming in that day is
legitimate whenever it happens; presence is decided by the day, while pay and
overtime still follow the shift (lateness and overtime are measured against the
shift's own start and end, never against this window).

So, for a day shift (start before end), a 0 on either side stretches that side
of the window to the edge of the calendar day: 00:00 before, 23:59:59 after. A
non-zero value is HRMS's own rule, unchanged; an overnight shift is left to
HRMS, since its day boundary is the point of the window. The rule is applied
where HRMS reads the two fields (`get_shift_type`, which both
`get_shift_details` and the window maths in `get_shift_timings` use), so every
HRMS path — checkin shift fetch, auto attendance — agrees, and the app's own
window helpers call `window_minutes` below.

A whole-day window ends at midnight, so auto attendance marks such a day once
the shift's Last Sync of Checkin passes midnight, not at 5 pm.

Applied by `patch_whole_day_window` (hooks before_request / before_job).
"""

import frappe
from frappe.utils import cint, get_time

DAY_SECONDS = 24 * 60 * 60


def _seconds(t) -> int:
	t = get_time(t)
	return t.hour * 3600 + t.minute * 60 + t.second


def window_minutes(shift_type) -> tuple[float, float]:
	"""(minutes before start, minutes after end) the shift accepts punches, with 0 = to the day's edge."""
	before = cint(shift_type.get("begin_check_in_before_shift_start_time"))
	after = cint(shift_type.get("allow_check_out_after_shift_end_time"))
	start, end = _seconds(shift_type.get("start_time")), _seconds(shift_type.get("end_time"))
	if start >= end:  # overnight: HRMS's rule
		return before, after
	if not before:
		before = start / 60
	if not after:
		after = (DAY_SECONDS - 1 - end) / 60
	return before, after


def patch_whole_day_window():
	"""Make HRMS's shift lookups use `window_minutes`. Idempotent."""
	from hrms.hr.doctype.shift_assignment import shift_assignment

	if getattr(shift_assignment.get_shift_type, "_whole_day_window", False):
		return
	original = shift_assignment.get_shift_type

	def get_shift_type(shift_type_name):
		shift_type = original(shift_type_name)
		if not shift_type:
			return shift_type
		shift_type = frappe._dict(shift_type)
		before, after = window_minutes(shift_type)
		shift_type.begin_check_in_before_shift_start_time = before
		shift_type.allow_check_out_after_shift_end_time = after
		return shift_type

	get_shift_type._whole_day_window = True
	shift_assignment.get_shift_type = get_shift_type
