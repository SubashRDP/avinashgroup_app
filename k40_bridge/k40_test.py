"""Offline regression tests for the k40_bridge HTMS/HAMS reader and helpers.

These do NOT need Windows, pywin32 or an Access database: the only thing that
touches the .mdb is HtmsClient._query, which we override with canned rows. That
lets the personID->Emp_no mapping, the non-person/unmapped skipping, the date
filtering and the timestamp parsing all be exercised on Linux/CI.

Run directly:      python3 k40_test.py
Or under pytest:   pytest k40_test.py
"""

import logging
from datetime import date, datetime

import k40_bridge as kb


# ── A test double: HtmsClient with the Access layer replaced by in-memory rows.
class FakeHtms(kb.HtmsClient):
    def __init__(self, emp_rows, pub_rows):
        super().__init__({"type": "htms", "db_folder": "/fake"})
        self._emp_rows = emp_rows          # list of [Emp_Id, Emp_no]
        self._pub_rows = pub_rows          # list of [personID, eventDate, eventTime]

    def probe_network(self):
        return True

    def _year_files(self, date_from, date_to):
        return ["/fake/HAMS_2026.mdb"]

    def _read_table(self, db_path, table, columns):
        return self._emp_rows if table == "Emp" else self._pub_rows


EMP = [
    ["0000000005", "005"],
    ["0000000077", "077"],
    ["0000000128", "135"],   # three different people share Emp_no 135
    ["0000000129", "135"],
    ["0000000130", "135"],
]

PUB = [
    ["0000000005", "2026/06/25", "08:58:48"],   # -> 005
    ["0000000005", "2026/06/25", "17:05:24"],   # -> 005
    ["0000000077", "2026/06/26", "09:00:00"],   # -> 077
    ["", "2026/06/26", "09:00:00"],             # non-person (empty) -> skip
    ["0000000000", "2026/06/26", "09:00:00"],   # all-zero personID -> skip
    ["0000000999", "2026/06/26", "09:00:00"],   # unmapped -> skip
]


def _by_user(records):
    out = {}
    for r in records:
        out.setdefault(r.user_id, []).append(r.timestamp)
    return out


def test_emp_map_and_duplicate_warning(caplog=None):
    c = FakeHtms(EMP, PUB)
    handler = _CaptureHandler()
    logging.getLogger("k40_bridge").addHandler(handler)
    try:
        mp = c._emp_map()
    finally:
        logging.getLogger("k40_bridge").removeHandler(handler)
    assert mp["0000000005"] == "005"
    assert mp["0000000128"] == "135"
    # the duplicate Emp_no (135) must have produced a warning naming it
    assert any("135" in m and "shared" in m for m in handler.messages), handler.messages


def test_fetch_maps_skips_and_parses():
    c = FakeHtms(EMP, PUB)
    records, status = c._fetch_attendance()
    assert status == "OK"
    by_user = _by_user(records)
    # empty, all-zero and unmapped personIDs are dropped; only 005 (x2) + 077
    assert set(by_user) == {"005", "077"}, by_user
    assert len(by_user["005"]) == 2
    assert by_user["005"][0] == datetime(2026, 6, 25, 8, 58, 48)


def test_date_filter():
    c = FakeHtms(EMP, PUB)
    records, status = c._fetch_attendance(date_from=date(2026, 6, 26))
    assert status == "OK"
    # only the 06-26 punch (077) survives; the 06-25 005 punches are filtered out
    assert {r.user_id for r in records} == {"077"}


def test_parse_dt_formats():
    p = kb.HtmsClient._parse_dt
    assert p("2026/06/25", "08:58:48") == datetime(2026, 6, 25, 8, 58, 48)
    assert p("2026-06-25", "08:58") == datetime(2026, 6, 25, 8, 58, 0)
    # native datetime-like objects (as ADO returns date/time columns)
    assert p(datetime(2026, 6, 25), datetime(1899, 12, 30, 7, 30, 5)) == datetime(2026, 6, 25, 7, 30, 5)
    assert p(None, "08:00:00") is None
    # unparseable time falls back to midnight of the parsed date (never crashes)
    assert p("2026/06/25", "garbage") == datetime(2026, 6, 25, 0, 0, 0)


def test_registry_has_htms_software_source():
    meta = kb.integration_meta("htms")
    assert meta and meta["category"] == "software"
    assert meta["client"] is kb.HtmsClient
    # device_address shows the folder for software sources, host:port for devices
    assert kb.device_address({"type": "htms", "db_folder": "/x/HTMS-86"}) == "/x/HTMS-86"
    assert kb.device_address({"type": "zkteco", "ip": "1.2.3.4", "port": 4370}) == "1.2.3.4:4370"


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage() % () if not record.args else record.getMessage())


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    return passed == len(tests)


if __name__ == "__main__":
    import sys
    sys.exit(0 if _run_all() else 1)
