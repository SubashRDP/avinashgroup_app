"""The half-month `slot` timeline shared by the CEO Dashboard's fact tables.

api.py puts every sales row on a slot: 24 per fiscal year (two per fiscal
month, Shrawan first), oldest year first, where the late half of the
"data through" month holds only the days after the data-through day (see
api.py). Purchases, returns and branch rows must land on the same slots so the
page can window them with the same arrays, so the rule lives here once.
(api._build and buying._build still carry their own copies; they predate this
module.)
"""

from frappe.utils import getdate

from avinashgroup_app.ceo_dashboard import api


def slotter(years, through):
	"""Return slot(date) for `years` (newest first, as api._fiscal_years gives
	them) and the data-through day. Results are memoised per date."""
	starts = [getdate(y.year_start_date) for y in years]
	bs = api._BS()
	thr_fm, thr_day = bs(through)
	memo = {}

	def slot(d):
		s = memo.get(d)
		if s is None:
			y = next(i for i, start in enumerate(starts) if d >= start)
			fm, day = bs(d)
			late = 1 if fm == thr_fm and day > thr_day else 0
			s = memo[d] = (len(years) - 1 - y) * api.SLOTS_PER_YEAR + (fm - 1) * 2 + late
		return s

	return slot
