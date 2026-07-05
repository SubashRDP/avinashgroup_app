"""Reusable test suite for the Document No. (custom_document_no) numbering.

Run it anytime with:

    bench --site <site> run-tests --module avinashgroup_app.test_document_numbering

Coverage, ordered small -> largest:

  01-04  scope derivation, preview, eligibility           (pure, no writes)
  05-09  auto-assign, manual, amendment, duplicate, blank  (logic)
  10-14  rule-driven scope, conditions, per-branch,        (Numbering
         rule specificity, missing-target fallback          Configuration)
  15-17  duplicate detection, delete-revert, end-to-end     (real inserts)
  18-19  concurrency: no collision, per-branch isolation    (threaded)

Isolation
---------
* Logic / rule tests run inside the FrappeTestCase transaction and are rolled
  back automatically; nothing is committed.
* Rule tests use a unique random tag segment, so their series key never
  collides with (or resets) a production counter.
* Concurrency tests must commit on their own connections; they use a unique
  series key and delete the tabSeries row they create in a cleanup step.

Fixtures are discovered dynamically (a company with an abbreviation, a fiscal
year, two branches, two accounts). Tests that need a fixture that is missing
skip themselves instead of failing, so the suite is portable across sites.
"""

import json
import threading

import frappe
from frappe.tests.utils import FrappeTestCase

from avinashgroup_app.custom_code.Override import naming_series as ns

# Configured auto-number types (see AUTO_NUMBER_CONFIG in naming_series.py).
JE_TYPE = "Bank Entry"        # Journal Entry auto-type, code BJV
JE_TYPE_OFF = "Opening Entry"  # a real JV Type that is NOT auto-numbered
PE_TYPE = "NOC Payment"        # Payment Entry auto-type with no specific
                               # production rule -> our temp rule always wins


class TestDocumentNumbering(FrappeTestCase):
    # ------------------------------------------------------------------ setup
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fy = frappe.get_all(
            "Fiscal Year", fields=["name", "year_start_date"],
            order_by="year_start_date desc", limit=1,
        )
        cls.fy = fy[0].name if fy else None
        cls.pdate = fy[0].year_start_date if fy else None

        # Pick, deterministically, the first company (with an abbreviation) whose
        # legacy custom_name numbering actually yields a value -- this skips
        # special-case companies that intentionally blank custom_name.
        cls.company = cls.abbr = None
        if cls.pdate:
            for name in frappe.get_all(
                "Company", filters={"abbr": ["is", "set"]}, order_by="name", pluck="name"
            ):
                probe = frappe.new_doc("Journal Entry")
                probe.company = name
                probe.posting_date = cls.pdate
                probe.voucher_type = "Journal Entry"
                probe.custom_p_type = JE_TYPE
                probe.custom_document_no = 1
                try:
                    ns.set_custom_name_field(probe)
                except Exception:
                    continue
                if probe.get("custom_name"):
                    cls.company = name
                    cls.abbr = frappe.get_cached_value("Company", name, "abbr")
                    break

        cls.branches = frappe.get_all("Branch", pluck="name", limit=2)
        cls.accounts = (
            frappe.get_all(
                "Account",
                filters={"company": cls.company, "is_group": 0, "disabled": 0},
                pluck="name", limit=2,
            )
            if cls.company else []
        )
        cls.has_rules = bool(frappe.db.exists("DocType", "Numbering Configuration"))

    def setUp(self):
        if not (self.company and self.abbr and self.fy):
            self.skipTest("needs a company with an abbreviation and a fiscal year")
        # Tests draw on tabSeries counters; app hooks + our own cleanup commits
        # would otherwise PERSIST those draws and pollute real counters. Snapshot
        # every docno counter now and restore it after the test (delete any the
        # test created, reset any it changed) so the suite is non-polluting.
        rows = frappe.db.sql("SELECT `name`, `current` FROM `tabSeries` WHERE `name` LIKE %s", ("docno:%",))
        self._docno_snapshot = {n: c for n, c in rows}
        self.addCleanup(self._restore_docno_counters)

    def _restore_docno_counters(self):
        rows = frappe.db.sql("SELECT `name`, `current` FROM `tabSeries` WHERE `name` LIKE %s", ("docno:%",))
        for name, cur in rows:
            snap = self._docno_snapshot.get(name)
            if snap is None:
                frappe.db.sql("DELETE FROM `tabSeries` WHERE `name`=%s", name)
            elif snap != cur:
                frappe.db.sql("UPDATE `tabSeries` SET `current`=%s WHERE `name`=%s", (snap, name))
        frappe.db.commit()

    # ---------------------------------------------------------------- helpers
    def _je(self, **kw):
        d = frappe.new_doc("Journal Entry")
        d.company = self.company
        d.posting_date = self.pdate
        d.voucher_type = "Journal Entry"
        d.custom_p_type = JE_TYPE
        for k, v in kw.items():
            setattr(d, k, v)
        return d

    def _pe(self, **kw):
        d = frappe.new_doc("Payment Entry")
        d.company = self.company
        d.posting_date = self.pdate
        d.payment_type = "Receive"
        d.custom_p_type = PE_TYPE
        for k, v in kw.items():
            setattr(d, k, v)
        return d

    def _balance(self, d):
        d.append("accounts", {"account": self.accounts[0],
                              "debit_in_account_currency": 100, "debit": 100})
        d.append("accounts", {"account": self.accounts[1],
                              "credit_in_account_currency": 100, "credit": 100})
        return d

    # Real inserts commit (app hooks commit mid-save), so FrappeTestCase's
    # rollback does NOT undo them. Every insert therefore registers an explicit
    # cleanup so the suite is safe to re-run.
    def _insert_je(self, **kw):
        d = self._je(**kw)
        self._balance(d).insert(ignore_permissions=True)
        self.addCleanup(self._force_delete, "Journal Entry", d.name)
        return d

    def _force_delete(self, doctype, name):
        if name and frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
        frappe.db.commit()

    def _cleanup_by_docno(self, docno):
        for n in frappe.get_all("Journal Entry", filters={"custom_document_no": docno}, pluck="name"):
            frappe.delete_doc("Journal Entry", n, force=1, ignore_permissions=True)
        frappe.db.commit()

    def _temp_rule(self, *, extra_segments, conditions, doctype="Payment Entry",
                   target="custom_name", separator="-", auto_document_no=0,
                   document_no_conditions=None):
        segments = list(extra_segments) + [
            {"segment_type": "Document Field", "field": "custom_document_no", "number_length": 6},
            {"segment_type": "Fiscal Year"},
        ]
        rule = frappe.get_doc({
            "doctype": "Numbering Configuration", "document_type": doctype,
            "enabled": 1, "target_field": target, "separator": separator,
            "auto_document_no": auto_document_no,
            "conditions": conditions,
            "document_no_conditions": document_no_conditions or [],
            "segments": segments,
        }).insert(ignore_permissions=True)
        ns.clear_numbering_rules_cache()
        self.addCleanup(self._drop_rule, rule.name)
        return rule

    def _drop_rule(self, name):
        if frappe.db.exists("Numbering Configuration", name):
            frappe.delete_doc("Numbering Configuration", name, force=1, ignore_permissions=True)
        frappe.db.commit()
        ns.clear_numbering_rules_cache()

    def _draw_pe(self, branch):
        d = self._pe(custom_branch=branch)
        ns.apply_document_no(d)
        return d.custom_document_no

    @staticmethod
    def _drop_series(key):
        frappe.db.sql("DELETE FROM `tabSeries` WHERE name = %s", key)
        frappe.db.commit()

    def _require(self, cond, why):
        if not cond:
            self.skipTest(why)

    # -------------------------------------------------------- 01-04  pure/scope
    def test_01_legacy_scope_shape(self):
        d = self._je()
        scope = ns._docno_scope(d)
        self.assertIsNotNone(scope)
        self.assertEqual(set(scope), {"key", "pattern", "field"})
        # When no Numbering Configuration rule matches this JE, the scope is the
        # legacy company|code|year keyed on custom_name.
        if not ns._match_numbering_rule(d):
            self.assertEqual(scope["field"], "custom_name")
            self.assertEqual(scope["key"], f"{self.abbr}|BJV|{self.fy}")
            self.assertEqual(scope["pattern"], f"{self.abbr}-BJV-%-{self.fy}%")

    def test_02_peek_is_non_reserving(self):
        a = ns.peek_next_document_no(self._je())
        b = ns.peek_next_document_no(self._je())
        self.assertIsNotNone(a)
        self.assertEqual(a, b)  # peeking twice consumes nothing

    def test_03_ineligible_type_has_no_scope(self):
        d = self._je(custom_p_type=JE_TYPE_OFF)
        self.assertIsNone(ns._docno_scope(d))
        self.assertIsNone(ns.peek_next_document_no(d))

    def test_04_missing_company_has_no_scope(self):
        d = self._je()
        d.company = None
        self.assertIsNone(ns._docno_scope(d))

    # ------------------------------------------------- 05-09  assign logic
    def test_05_auto_number_increments(self):
        d1 = self._je()
        ns.apply_document_no(d1)
        d2 = self._je()
        ns.apply_document_no(d2)
        self.assertIsNotNone(d1.custom_document_no)
        self.assertEqual(d2.custom_document_no, d1.custom_document_no + 1)

    def test_06_manual_number_is_kept(self):
        d = self._je(custom_document_no=987654, custom_document_no_manual=1)
        ns.apply_document_no(d)
        self.assertEqual(d.custom_document_no, 987654)

    def test_07_amendment_keeps_number(self):
        d = self._je(amended_from="JE-AMEND-0001",
                     custom_document_no=321, custom_document_no_manual=0)
        ns.apply_document_no(d)
        self.assertEqual(d.custom_document_no, 321)

    def test_08_duplicate_redraws_number(self):
        # New doc (no amended_from) carrying a copied number, not flagged manual.
        d = self._je(custom_document_no=321, custom_document_no_manual=0)
        ns.apply_document_no(d)
        self.assertIsNotNone(d.custom_document_no)
        self.assertNotEqual(d.custom_document_no, 321)

    def test_09_ineligible_type_blanks_field(self):
        d = self._je(custom_p_type=JE_TYPE_OFF,
                     custom_document_no=7, custom_document_no_manual=0)
        ns.apply_document_no(d)
        self.assertIsNone(d.custom_document_no)

    # ------------------------------------------- 10-14  rule-driven scope
    def test_10_rule_gives_isolated_scope(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "UT" + frappe.generate_hash(length=6)
        self._temp_rule(
            extra_segments=[
                {"segment_type": "Company Abbr"},
                {"segment_type": "Static Text", "static_value": tag},
                {"segment_type": "Fetch from Link", "field": "custom_p_type", "fetch_field": "data_hrcj"},
            ],
            conditions=[{"field": "custom_p_type", "value": PE_TYPE}],
        )
        scope = ns._docno_scope(self._pe())
        self.assertIsNotNone(scope)
        self.assertIn(tag, scope["key"])
        self.assertIn(tag, scope["pattern"])
        # Isolated scope with a fresh tag -> the very first number is 1.
        self.assertEqual(ns.peek_next_document_no(self._pe()), 1)

    def test_11_condition_selects_the_rule(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "UT" + frappe.generate_hash(length=6)
        self._temp_rule(
            extra_segments=[
                {"segment_type": "Company Abbr"},
                {"segment_type": "Static Text", "static_value": tag},
                {"segment_type": "Fetch from Link", "field": "custom_p_type", "fetch_field": "data_hrcj"},
            ],
            conditions=[{"field": "custom_p_type", "value": PE_TYPE}],
        )
        # matches for PE_TYPE
        self.assertIn(tag, ns._docno_scope(self._pe())["key"])
        # a different (configured) type does not pick up our rule's tag
        other = ns._docno_scope(self._pe(custom_p_type="Bank Customers Receipt"))
        self.assertTrue(other is None or tag not in other.get("key", ""))

    def test_12_per_branch_independent_counting(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.branches) >= 2, "needs two branches")
        b1, b2 = self.branches[0], self.branches[1]
        frappe.db.set_value("Branch", b1, "custom_abbr", "aa")
        frappe.db.set_value("Branch", b2, "custom_abbr", "bb")
        tag = "UT" + frappe.generate_hash(length=6)
        self._temp_rule(
            extra_segments=[
                {"segment_type": "Company Abbr"},
                {"segment_type": "Static Text", "static_value": tag},
                {"segment_type": "Branch Abbr"},
                {"segment_type": "Fetch from Link", "field": "custom_p_type", "fetch_field": "data_hrcj"},
            ],
            conditions=[{"field": "custom_p_type", "value": PE_TYPE}],
        )
        r1 = [self._draw_pe(b1) for _ in range(3)]
        r2 = [self._draw_pe(b2) for _ in range(3)]
        r1_more = [self._draw_pe(b1) for _ in range(2)]
        self.assertEqual(r1, [1, 2, 3])
        self.assertEqual(r2, [1, 2, 3])          # branch 2 restarts, independent
        self.assertEqual(r1_more, [4, 5])        # branch 1 continues its own run

    def test_13_more_specific_rule_wins(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag_generic = "UG" + frappe.generate_hash(length=6)
        tag_specific = "US" + frappe.generate_hash(length=6)
        self._temp_rule(
            extra_segments=[
                {"segment_type": "Company Abbr"},
                {"segment_type": "Static Text", "static_value": tag_generic},
                {"segment_type": "Fetch from Link", "field": "custom_p_type", "fetch_field": "data_hrcj"},
            ],
            conditions=[{"field": "custom_p_type", "value": PE_TYPE}],
        )
        self._temp_rule(
            extra_segments=[
                {"segment_type": "Company Abbr"},
                {"segment_type": "Static Text", "static_value": tag_specific},
                {"segment_type": "Fetch from Link", "field": "custom_p_type", "fetch_field": "data_hrcj"},
            ],
            conditions=[
                {"field": "custom_p_type", "value": PE_TYPE},
                {"field": "payment_type", "value": "Receive"},
            ],
        )
        scope = ns._docno_scope(self._pe())  # payment_type Receive -> specific wins
        self.assertIn(tag_specific, scope["key"])
        self.assertNotIn(tag_generic, scope["key"])

    def test_14_missing_target_field_falls_back(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "UT" + frappe.generate_hash(length=6)
        # target a field that does not exist on Payment Entry
        self._temp_rule(
            extra_segments=[
                {"segment_type": "Company Abbr"},
                {"segment_type": "Static Text", "static_value": tag},
                {"segment_type": "Fetch from Link", "field": "custom_p_type", "fetch_field": "data_hrcj"},
            ],
            conditions=[{"field": "custom_p_type", "value": PE_TYPE}],
            target="custom_field_that_does_not_exist",
        )
        scope = ns._docno_scope(self._pe())  # must not raise; must not use the bad rule
        self.assertTrue(scope is None or tag not in scope.get("key", ""))

    # ------------------------------------------- 15-17  real inserts (rolled back)
    def test_15_manual_duplicate_is_rejected_with_hint(self):
        self._require(len(self.accounts) >= 2, "needs two accounts")
        # random high number + cleanup -> safe to re-run even if a run is killed
        big = 800000 + int(frappe.generate_hash(length=6), 16) % 90000
        self.addCleanup(self._cleanup_by_docno, big)
        a = self._je(custom_document_no=big, custom_document_no_manual=1)
        self._balance(a).insert(ignore_permissions=True)
        b = self._je(custom_document_no=big, custom_document_no_manual=1)
        self._balance(b)
        with self.assertRaises(frappe.ValidationError) as cm:
            b.insert(ignore_permissions=True)
        self.assertIn("Next available number", str(cm.exception))

    def test_16_delete_reverts_last_number(self):
        self._require(len(self.accounts) >= 2, "needs two accounts")
        d = self._insert_je()
        scope = ns._docno_scope(d)
        key = ns._docno_series_key(d, scope)
        before = ns._series_current(key)
        self.assertEqual(before, d.custom_document_no)  # counter holds our number
        d.delete()
        frappe.db.commit()
        self.assertEqual(ns._series_current(key), before - 1)  # freed for reuse

    def test_17_end_to_end_je_insert(self):
        self._require(len(self.accounts) >= 2, "needs two accounts")
        d = self._insert_je()
        self.assertIsNotNone(d.custom_document_no)
        self.assertGreater(d.custom_document_no, 0)
        self.assertTrue(d.custom_name.startswith(f"{self.abbr}-BJV-"))
        self.assertIn(self.fy, d.custom_name)

    # ------------------------------------------------- 18-19  concurrency
    def _run_concurrent(self, assignments):
        """assignments: list of (thread_index, series_tag). Each thread draws one
        number for its tag on its own connection and commits. Returns {tag: [nums]}."""
        site = frappe.local.site
        results = {}
        barrier = threading.Barrier(len(assignments))

        def worker(i, tag):
            frappe.init(site=site)
            frappe.connect()
            frappe.set_user("Administrator")
            try:
                d = frappe.new_doc("Journal Entry")
                scope = {"key": tag, "pattern": tag + "-%", "field": "custom_name"}
                barrier.wait(timeout=30)
                n = ns._draw_next_document_no(d, scope)
                frappe.db.commit()
                results[i] = (tag, n)
            except Exception as exc:  # pragma: no cover - surfaced via assert
                results[i] = (tag, "ERR:%s" % exc)
            finally:
                frappe.destroy()

        threads = [threading.Thread(target=worker, args=(i, tag)) for i, tag in assignments]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        by_tag = {}
        for i, tag in assignments:
            self.addCleanup(self._drop_series, "docno:Journal Entry|" + tag)
        for _i, (tag, n) in results.items():
            by_tag.setdefault(tag, []).append(n)
        return by_tag

    def test_18_concurrent_saves_never_collide(self):
        tag = "CC" + frappe.generate_hash(length=8)
        n = 6
        by_tag = self._run_concurrent([(i, tag) for i in range(n)])
        nums = by_tag.get(tag, [])
        self.assertTrue(all(isinstance(x, int) for x in nums), msg=str(nums))
        self.assertEqual(sorted(nums), list(range(1, n + 1)))  # distinct 1..n, no gaps/dupes

    def test_19_concurrent_per_branch_isolation(self):
        tag_a = "CA" + frappe.generate_hash(length=8)
        tag_b = "CB" + frappe.generate_hash(length=8)
        per = 4
        assignments = [(i, tag_a) for i in range(per)] + [(per + i, tag_b) for i in range(per)]
        by_tag = self._run_concurrent(assignments)
        for tag in (tag_a, tag_b):
            nums = by_tag.get(tag, [])
            self.assertTrue(all(isinstance(x, int) for x in nums), msg=str(nums))
            self.assertEqual(sorted(nums), list(range(1, per + 1)), msg=f"{tag}: {nums}")

    # -------------------------------------------- 20  type safety (Data column)
    def test_20_max_is_numeric_not_lexicographic(self):
        # Regression: where custom_document_no is a Data (varchar) column, e.g.
        # Purchase Receipt, MAX must be numeric ("9" < "50"), not string.
        dt = "Purchase Receipt"
        self._require(frappe.db.exists("DocType", dt), "Purchase Receipt not installed")
        ftype = frappe.db.get_value(
            "Custom Field", {"dt": dt, "fieldname": "custom_document_no"}, "fieldtype"
        )
        self._require(ftype == "Data", "custom_document_no is not a Data field here")
        numeric = frappe.db.sql(
            "SELECT MAX(CAST(`custom_document_no` AS UNSIGNED)), MAX(`custom_document_no`) "
            "FROM `tab{0}` WHERE custom_document_no REGEXP '^[0-9]+$'".format(dt)
        )
        num_max, lex_max = (numeric[0] if numeric else (None, None))
        self._require(num_max is not None, "no numeric custom_document_no data to compare")
        scope = {"key": "x", "pattern": "%", "field": "custom_document_no"}
        got = ns._current_max_document_no(frappe.new_doc(dt), scope)
        self.assertEqual(got, int(num_max))                 # numeric max
        if str(lex_max) != str(num_max):                    # data actually exposes the bug
            self.assertNotEqual(str(got), str(lex_max))     # and we don't return it

    # ==================================================================
    #  STRONG REGRESSION BATTERY
    #  One guard per fixed bug + invariants + stress. Each test name says
    #  what regressing would mean.
    # ==================================================================

    def _count_db_queries(self, fn):
        orig = frappe.db.sql
        n = [0]

        def counting(*a, **k):
            n[0] += 1
            return orig(*a, **k)

        frappe.db.sql = counting
        try:
            fn()
        finally:
            frappe.db.sql = orig
        return n[0]

    # ---- bug-guard regressions ----
    def test_21_preview_handles_full_draft_payload(self):
        # Regression: the preview crashed on the whole draft because the accounts
        # child table arrived nested; it must resolve to a number.
        payload = {
            "doctype": "Journal Entry", "name": "new-je-xyz", "__islocal": 1,
            "company": self.company, "posting_date": str(self.pdate),
            "voucher_type": "Journal Entry", "custom_p_type": JE_TYPE,
            "accounts": [{"doctype": "Journal Entry Account", "idx": 1}],
        }
        got = ns.get_next_custom_document_no(doc=json.dumps(payload))
        self.assertIsInstance(got, int)
        self.assertGreater(got, 0)

    def test_22_preview_never_raises(self):
        # child table as a STRING (the exact crash), garbage, missing doctype,
        # and no args -> None, never an exception.
        weird = {"doctype": "Journal Entry", "company": self.company,
                 "posting_date": str(self.pdate), "custom_p_type": JE_TYPE,
                 "accounts": "[{\"idx\": 1}]"}
        for bad in (json.dumps(weird), "not-json", json.dumps({"x": 1}), None):
            try:
                r = ns.get_next_custom_document_no(doc=bad)
            except Exception as exc:  # pragma: no cover
                self.fail("preview raised on %r: %s" % (bad, exc))
            self.assertTrue(r is None or isinstance(r, int))

    def test_23_revert_skips_when_scope_changed(self):
        # Regression: a doc whose stored name no longer matches its current scope
        # must NOT step a series back (would gap this / corrupt another).
        d = self._je()
        scope = ns._docno_scope(d)
        key = ns._docno_series_key(d, scope)
        ns._draw_next_document_no(d, scope)
        before = ns._series_current(key)
        d.custom_document_no = before
        d.custom_name = "TOTALLY-DIFFERENT-SCOPE-000999"   # as if branch/date changed
        ns._revert_document_no_series(d)
        self.assertEqual(ns._series_current(key), before)  # untouched

    def test_24_amendment_number_stable_across_events(self):
        d = self._je(amended_from="JE-AMEND-1", custom_document_no=555, custom_document_no_manual=0)
        ns.apply_document_no(d)
        ns.apply_document_no(d)                              # validate + before_save
        self.assertEqual(d.custom_document_no, 555)

    def test_25_number_drawn_exactly_once(self):
        # apply runs on both validate and before_save; the counter must advance once.
        d = self._je()
        scope = ns._docno_scope(d)
        key = ns._docno_series_key(d, scope)
        before = ns._series_current(key)
        ns.apply_document_no(d)
        n1 = d.custom_document_no
        ns.apply_document_no(d)
        self.assertEqual(d.custom_document_no, n1)           # idempotent
        self.assertEqual(ns._series_current(key), before + 1)  # bumped once, not twice

    def test_26_preview_reserves_nothing_under_stress(self):
        d = self._je()
        scope = ns._docno_scope(d)
        key = ns._docno_series_key(d, scope)
        before = ns._series_current(key)
        peeks = {ns.peek_next_document_no(self._je()) for _ in range(30)}
        self.assertEqual(len(peeks), 1)                     # stable preview
        self.assertEqual(ns._series_current(key), before)   # counter untouched

    # ---- caching regressions ----
    def test_27_redis_roundtrip_preserves_rule_shape(self):
        configured = list(ns._configured_doctypes())
        self._require(configured, "no doctype has numbering rules")
        dt = configured[0]
        fresh = ns._build_numbering_rules(dt)
        ns.clear_numbering_rules_cache()
        frappe.local._numbering_rules_cache = {}
        ns._numbering_rules_for(dt)                          # populate redis
        frappe.local._numbering_rules_cache = {}
        from_redis = ns._numbering_rules_for(dt)             # redis hit
        self.assertEqual(from_redis, fresh)                 # identical shape/content
        for r in from_redis:
            for child in list(r.get("conditions", [])) + list(r.get("segments", [])):
                self.assertNotIn("parent", child)           # grouping key stripped

    def test_28_unconfigured_doctype_hits_no_db(self):
        ns._configured_doctypes()                           # warm the gate
        dt = "ToDo"
        self._require(dt not in ns._configured_doctypes(), "ToDo unexpectedly configured")
        frappe.local._numbering_rules_cache = {}
        self.assertEqual(self._count_db_queries(lambda: ns._numbering_rules_for(dt)), 0)

    def test_29_new_rule_visible_after_invalidation(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "UT" + frappe.generate_hash(length=6)
        self.assertNotIn(tag, (ns._docno_scope(self._pe()) or {}).get("key", ""))
        self._temp_rule(
            extra_segments=[
                {"segment_type": "Company Abbr"},
                {"segment_type": "Static Text", "static_value": tag},
                {"segment_type": "Fetch from Link", "field": "custom_p_type", "fetch_field": "data_hrcj"},
            ],
            conditions=[{"field": "custom_p_type", "value": PE_TYPE}],
        )
        scope = ns._docno_scope(self._pe())
        self.assertIsNotNone(scope)
        self.assertIn(tag, scope["key"])                    # cache invalidated on insert

    # ---- invariants / property / stress ----
    def test_30_sequential_draws_unique_and_gapless(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "SEQ" + frappe.generate_hash(length=6)
        self._temp_rule(
            extra_segments=[
                {"segment_type": "Company Abbr"},
                {"segment_type": "Static Text", "static_value": tag},
                {"segment_type": "Fetch from Link", "field": "custom_p_type", "fetch_field": "data_hrcj"},
            ],
            conditions=[{"field": "custom_p_type", "value": PE_TYPE}],
        )
        nums = [self._draw_pe(None) for _ in range(200)]
        self.assertEqual(nums, list(range(1, 201)))         # strictly 1..200, no gaps/dupes

    def test_31_high_concurrency_no_collision(self):
        tag = "HC" + frappe.generate_hash(length=8)
        n = 12
        by = self._run_concurrent([(i, tag) for i in range(n)])
        nums = by.get(tag, [])
        self.assertTrue(all(isinstance(x, int) for x in nums), msg=str(nums))
        self.assertEqual(sorted(nums), list(range(1, n + 1)))

    def test_32_auto_skips_past_a_manual_number(self):
        self._require(len(self.accounts) >= 2, "needs two accounts")
        big = 700000 + int(frappe.generate_hash(length=6), 16) % 90000
        self.addCleanup(self._cleanup_by_docno, big)
        m = self._je(custom_document_no=big, custom_document_no_manual=1)
        self._balance(m).insert(ignore_permissions=True)
        a = self._je()
        # peek reflects what auto WOULD assign, without consuming the counter
        self.assertGreater(ns.peek_next_document_no(a), big)  # floor jumped past the manual value

    def test_33_fiscal_years_are_separate_series(self):
        fys = frappe.get_all(
            "Fiscal Year", fields=["name", "year_start_date"],
            order_by="year_start_date desc", limit=2,
        )
        self._require(len(fys) >= 2, "needs two fiscal years")
        d1 = self._je(posting_date=fys[0].year_start_date)
        d2 = self._je(posting_date=fys[1].year_start_date)
        s1, s2 = ns._docno_scope(d1), ns._docno_scope(d2)
        self.assertIsNotNone(s1)
        self.assertIsNotNone(s2)
        self.assertNotEqual(s1["key"], s2["key"])
        self.assertNotEqual(ns._docno_series_key(d1, s1), ns._docno_series_key(d2, s2))

    def test_34_same_scope_different_doctype_isolated(self):
        scope = {"key": "SAME|CODE|82-83", "pattern": "%", "field": "custom_name"}
        k_je = ns._docno_series_key(self._je(), scope)
        k_pe = ns._docno_series_key(self._pe(), scope)
        self.assertNotEqual(k_je, k_pe)                     # doctype is part of the series key
        self.assertTrue(k_je.startswith("docno:Journal Entry|"))
        self.assertTrue(k_pe.startswith("docno:Payment Entry|"))

    def test_35_all_configured_doctypes_have_the_field(self):
        # The four AUTO_NUMBER_CONFIG doctypes must carry custom_document_no,
        # else apply_document_no silently no-ops for them.
        for dt in ns.AUTO_NUMBER_CONFIG:
            if not frappe.db.exists("DocType", dt):
                continue
            self.assertTrue(
                frappe.get_meta(dt).has_field("custom_document_no"),
                msg=f"{dt} is auto-numbered but has no custom_document_no field",
            )

    # ============================================================
    #  GENERALIZED RULE: configurable eligibility + condition operators
    # ============================================================
    #  A Payment Entry type NOT in the hardcoded AUTO_NUMBER_CONFIG, used to
    #  prove a rule can turn numbering ON beyond the shipped defaults.
    OFF_TYPE = "Vendor Payment"      # exists as a Payment - Receipt Type, not auto-numbered
    OFF_TYPE_2 = "Vendor Receipt"

    def _pe_off(self, ptype=None):
        return self._pe(custom_p_type=ptype or self.OFF_TYPE)

    # segments shared by these rule tests (Company Abbr + unique tag + code)
    def _tag_segments(self, tag):
        return [
            {"segment_type": "Company Abbr"},
            {"segment_type": "Static Text", "static_value": tag},
            {"segment_type": "Fetch from Link", "field": "custom_p_type", "fetch_field": "data_hrcj"},
        ]

    def test_36_docno_condition_turns_numbering_on_beyond_hardcoded_list(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        # baseline: a non-configured type is NOT eligible without a rule
        self.assertIsNone(ns._docno_scope(self._pe_off()))
        tag = "AF" + frappe.generate_hash(length=6)
        self._temp_rule(
            auto_document_no=1,
            extra_segments=self._tag_segments(tag),
            conditions=[],                               # voucher: applies to all PE
            document_no_conditions=[{"field": "custom_p_type", "operator": "Equals", "value": self.OFF_TYPE}],
        )
        scope = ns._docno_scope(self._pe_off())
        self.assertIsNotNone(scope)                      # eligible via the Document No. condition
        self.assertIn(tag, scope["key"])
        self.assertEqual(ns.peek_next_document_no(self._pe_off()), 1)

    def test_37_auto_flag_off_does_not_number(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "AF" + frappe.generate_hash(length=6)
        self._temp_rule(
            auto_document_no=0,                          # rule matches (name) but doesn't auto-number
            extra_segments=self._tag_segments(tag),
            conditions=[],
            document_no_conditions=[{"field": "custom_p_type", "operator": "Equals", "value": self.OFF_TYPE}],
        )
        self.assertIsNone(ns._docno_scope(self._pe_off()))  # flag off -> not eligible

    def test_38_docno_in_operator_matches_a_list(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "IN" + frappe.generate_hash(length=6)
        self._temp_rule(
            auto_document_no=1,
            extra_segments=self._tag_segments(tag),
            conditions=[],
            document_no_conditions=[{"field": "custom_p_type", "operator": "In",
                                     "value": f"{self.OFF_TYPE}, {self.OFF_TYPE_2}"}],
        )
        self.assertIn(tag, (ns._docno_scope(self._pe_off(self.OFF_TYPE)) or {}).get("key", ""))
        self.assertIn(tag, (ns._docno_scope(self._pe_off(self.OFF_TYPE_2)) or {}).get("key", ""))
        self.assertIsNone(ns._docno_scope(self._pe_off("Customers/Suppliers Receipt")))

    def test_39_docno_blank_operator_behaves_as_equals(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "EQ" + frappe.generate_hash(length=6)
        self._temp_rule(
            auto_document_no=1,
            extra_segments=self._tag_segments(tag),
            conditions=[],
            document_no_conditions=[{"field": "custom_p_type", "value": self.OFF_TYPE}],  # no operator -> Equals
        )
        self.assertIn(tag, (ns._docno_scope(self._pe_off(self.OFF_TYPE)) or {}).get("key", ""))
        self.assertIsNone(ns._docno_scope(self._pe_off(self.OFF_TYPE_2)))

    def test_40_voucher_and_docno_conditions_are_independent(self):
        # Voucher conditions gate the NAME; Document No. conditions gate the NUMBER.
        # Here the rule applies to ALL Payment Entries (empty voucher conditions)
        # but only auto-numbers OFF_TYPE — a different type is named but not numbered.
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "SEP" + frappe.generate_hash(length=6)
        self._temp_rule(
            auto_document_no=1,
            extra_segments=self._tag_segments(tag),
            conditions=[],
            document_no_conditions=[{"field": "custom_p_type", "operator": "Equals", "value": self.OFF_TYPE}],
        )
        # numbered (docno condition matches)
        self.assertIsNotNone(ns._docno_scope(self._pe_off(self.OFF_TYPE)))
        # NOT numbered via the rule (docno condition fails) and OFF_TYPE_2 isn't a
        # hardcoded auto type either -> no auto number, even though the rule still
        # builds this doc's name.
        self.assertIsNone(ns._docno_scope(self._pe_off(self.OFF_TYPE_2)))
