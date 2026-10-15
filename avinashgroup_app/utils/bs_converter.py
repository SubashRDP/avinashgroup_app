"""Exact AD ↔ BS conversion for every process, whenever it was started.

rdp_common_app.utils.bs_boundaries — payroll months, leave credit, BS dates on
every HR form — converts through the `nepali_date_converter` package. That
package fixes "today" once, at import: the English anchor from the server clock
(UTC here) and the Nepali anchor from `nepali_datetime.now()` (Nepal time), then
converts every date by its distance from those anchors. Between 18:15 and 24:00
UTC the two anchors are different days, so a worker started in that window
converts every date one day wrong for as long as it lives: on 15 Oct 2026 the
BS leave accrual credited "Ashwin month end 2026-10-15" — a day early — because
its worker read 15 Oct as Ashwin 30 (it is Ashwin 29) and 1 Kartik as 15 Oct
(it is 17 Oct).

`patch_converter` replaces the package's two functions with `nepali_datetime`'s
own calendar lookups, which have no anchor. Same names, same "YYYY-MM-DD"
strings, so bs_boundaries and anything else calling them is unchanged.
Idempotent; applied in hooks before_request and before_job.
"""

import datetime

import nepali_datetime


def english_to_nepali_converter(year, month, day):
	return nepali_datetime.date.from_datetime_date(datetime.date(year, month, day)).strftime("%Y-%m-%d")


def nepali_to_english_converter(year, month, day):
	return nepali_datetime.date(year, month, day).to_datetime_date().strftime("%Y-%m-%d")


english_to_nepali_converter._exact = True


def patch_converter():
	import nepali_date_converter

	if getattr(nepali_date_converter.english_to_nepali_converter, "_exact", False):
		return
	nepali_date_converter.english_to_nepali_converter = english_to_nepali_converter
	nepali_date_converter.nepali_to_english_converter = nepali_to_english_converter
