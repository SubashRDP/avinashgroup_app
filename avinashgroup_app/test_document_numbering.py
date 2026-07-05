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
        cls.company = frappe.db.get_value("Company", {"abbr": ["is", "set"]}, "name")
        cls.abbr = frappe.get_cached_value("Company", cls.company, "abbr") if cls.company else None
        fy = frappe.get_all(
            "Fiscal Year", fields=["name", "year_start_date"],
            order_by="year_start_date desc", limit=1,
        )
        cls.fy = fy[0].name if fy else None
        cls.pdate = fy[0].year_start_date if fy else None
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

    def _temp_rule(self, *, extra_segments, conditions, doctype="Payment Entry",
                   target="custom_name", separator="-"):
        segments = list(extra_segments) + [
            {"segment_type": "Document Field", "field": "custom_document_no", "number_length": 6},
            {"segment_type": "Fiscal Year"},
        ]
        rule = frappe.get_doc({
            "doctype": "Numbering Configuration", "document_type": doctype,
            "enabled": 1, "target_field": target, "separator": separator,
            "conditions": conditions, "segments": segments,
        }).insert(ignore_permissions=True)
        ns.clear_numbering_rules_cache()
        self.addCleanup(self._drop_rule, rule.name)
        return rule

    def _drop_rule(self, name):
        if frappe.db.exists("Numbering Configuration", name):
            frappe.delete_doc("Numbering Configuration", name, force=1, ignore_permissions=True)
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
        big = 900001
        a = self._je(custom_document_no=big, custom_document_no_manual=1)
        self._balance(a).insert(ignore_permissions=True)
        b = self._je(custom_document_no=big, custom_document_no_manual=1)
        self._balance(b)
        with self.assertRaises(frappe.ValidationError) as cm:
            b.insert(ignore_permissions=True)
        self.assertIn("Next available number", str(cm.exception))

    def test_16_delete_reverts_last_number(self):
        self._require(len(self.accounts) >= 2, "needs two accounts")
        d = self._je()
        self._balance(d).insert(ignore_permissions=True)
        scope = ns._docno_scope(d)
        key = ns._docno_series_key(d, scope)
        before = ns._series_current(key)
        self.assertEqual(before, d.custom_document_no)  # counter holds our number
        d.delete()
        self.assertEqual(ns._series_current(key), before - 1)  # freed for reuse

    def test_17_end_to_end_je_insert(self):
        self._require(len(self.accounts) >= 2, "needs two accounts")
        d = self._je()
        self._balance(d).insert(ignore_permissions=True)
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
