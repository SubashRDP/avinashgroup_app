"""Stop a Shift Type save from inventing a Late Arrival Cutoff.

`custom_late_arrival_cutoff_time` is an optional Time field: blank means "this
shift has no absolute cutoff", and a time means "anyone whose first check-in is
after this has worked half a day, whatever their hours say". Saving the form
fills the blank one with the clock time of the save, so a shift nobody intended
to restrict comes out of an ordinary 09:49 edit restricting everybody from 09:49.

It is not a small bug. On the first run of test attendance it cost 2,423 of 2,808
days a half day, and demo-nggroup is still carrying a stray 09:49 today.

`year_setup` used to blank the field after creating each Shift Type, which
covered the shifts it made and nothing else. Now that the hours are HR's to enter
in the desk, the guard has to live where every save passes — here.

What counts as invented: the field changed in this save, to within a minute or so
of the clock. A cutoff a person actually means is typed for a reason — 09:30,
10:00 — and the odds of meaning exactly the minute you pressed Save are slim. The
trade is deliberate: blanking a real cutoff typed at its own minute is visible on
the form and retyped in seconds, while a cutoff nobody entered is invisible and
found in a month of wrong pay.

`biometric.attendance_override` keeps its own defence — a cutoff at or before the
shift's start cannot mean "late" — which catches the same artifact on a shift
starting later in the day. This catches the ones that slip past it.
"""

import frappe
from frappe.utils import get_datetime, now_datetime

#: How close to the save's own clock time counts as the form having filled it in.
INVENTED_WITHIN_SECONDS = 90

FIELD = "custom_late_arrival_cutoff_time"


def clear_invented_late_cutoff(doc, method=None):
	"""Hook: Shift Type validate."""
	cutoff = doc.get(FIELD)
	if not cutoff:
		return
	if not doc.is_new() and not doc.has_value_changed(FIELD):
		return

	now = now_datetime()
	# Both sides as a time on the same day, so this compares clock to clock.
	entered = get_datetime(f"{now.date()} {cutoff}")
	if abs((entered - now).total_seconds()) <= INVENTED_WITHIN_SECONDS:
		doc.set(FIELD, None)
