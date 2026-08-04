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

# Global key recording which real rules a running test has disabled, so a
# killed run can be healed by the next one (see _heal_quarantine_leftovers).
QUARANTINE_MARKER = "numbering_test_quarantine"


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

        # A second company, for the per-company uniqueness scope. Only ever set
        # on unsaved docs, so it needs no accounts of its own.
        cls.company2 = next(
            (
                name
                for name in frappe.get_all(
                    "Company", filters={"abbr": ["is", "set"]}, order_by="name", pluck="name"
                )
                if name != cls.company
            ),
            None,
        )

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
        if cls.has_rules:
            cls._heal_quarantine_leftovers()
        # Company-scoped uniqueness only applies to targets WITHOUT a DB unique
        # index, and custom_name carries one on every audited doctype
        # (add_unique_custom_name_index). Create a plain non-unique Data field to
        # act as the target for those tests, and remove it afterwards.
        cls.scoped_target = "custom_test_voucher_no"
        cls._created_target_field = None
        if not frappe.get_meta("Journal Entry").has_field(cls.scoped_target):
            cf = frappe.get_doc({
                "doctype": "Custom Field", "dt": "Journal Entry",
                "fieldname": cls.scoped_target, "label": "Test Voucher No",
                "fieldtype": "Data",
            }).insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.clear_cache(doctype="Journal Entry")
            cls._created_target_field = cf.name
            cls.addClassCleanup(cls._drop_created_target_field)

        # The branch-grouping tests need a real custom_branch column on Payment
        # Entry (group-by scope and field locks read doc.meta). Not every site
        # deploys it — create it for the run and remove it afterwards.
        cls._created_branch_field = None
        if not frappe.get_meta("Payment Entry").has_field("custom_branch"):
            cf = frappe.get_doc({
                "doctype": "Custom Field", "dt": "Payment Entry",
                "fieldname": "custom_branch", "label": "Branch",
                "fieldtype": "Link", "options": "Branch",
            }).insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.clear_cache(doctype="Payment Entry")
            cls._created_branch_field = cf.name
            cls.addClassCleanup(cls._drop_created_branch_field)

    @classmethod
    def _drop_created_target_field(cls):
        if cls._created_target_field and frappe.db.exists("Custom Field", cls._created_target_field):
            frappe.delete_doc("Custom Field", cls._created_target_field,
                              force=1, ignore_permissions=True)
            frappe.db.commit()
            frappe.clear_cache(doctype="Journal Entry")

    @classmethod
    def _drop_created_branch_field(cls):
        if cls._created_branch_field and frappe.db.exists("Custom Field", cls._created_branch_field):
            frappe.delete_doc("Custom Field", cls._created_branch_field,
                              force=1, ignore_permissions=True)
            frappe.db.commit()
            frappe.clear_cache(doctype="Payment Entry")

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
        # Some tests set a Branch's abbreviation; snapshot and restore it so the
        # suite never changes real branch data.
        self._branch_abbr_snapshot = {
            b: frappe.db.get_value("Branch", b, "custom_abbr") for b in self.branches
        }
        self.addCleanup(self._restore_branch_abbrs)
        # Site-configured Numbering Configuration rules are AUTHORITATIVE (an
        # Auto-fill rule's conditions can turn numbering OFF), so whatever an
        # admin configured on this site would change test outcomes. Quarantine:
        # disable every enabled rule for the duration of the test — _temp_rule
        # creates exactly the rules a test wants — and restore them afterwards.
        # Crash safety: the cleanup is registered BEFORE the mutation, and the
        # disabled list is persisted as a global so a killed run (SIGKILL /
        # power loss) is healed by the next run's setUpClass instead of
        # leaving the site's numbering silently off.
        self._live_rules = (
            frappe.get_all("Numbering Configuration", filters={"enabled": 1}, pluck="name")
            if self.has_rules else []
        )
        self.addCleanup(self._restore_live_rules)
        if self._live_rules:
            frappe.db.set_global(QUARANTINE_MARKER, json.dumps(self._live_rules))
            frappe.db.sql(
                "UPDATE `tabNumbering Configuration` SET enabled=0 WHERE name IN %s",
                (tuple(self._live_rules),),
            )
            frappe.db.commit()
            ns.clear_numbering_rules_cache()

    def _restore_live_rules(self):
        if getattr(self, "_live_rules", None):
            frappe.db.sql(
                "UPDATE `tabNumbering Configuration` SET enabled=1 WHERE name IN %s",
                (tuple(self._live_rules),),
            )
            frappe.db.set_global(QUARANTINE_MARKER, None)
            frappe.db.commit()
            ns.clear_numbering_rules_cache()

    @staticmethod
    def _heal_quarantine_leftovers():
        """A previous test run killed mid-quarantine left real rules disabled:
        re-enable whatever the persisted marker recorded."""
        leftover = frappe.db.get_global(QUARANTINE_MARKER)
        if not leftover:
            return
        names = [n for n in json.loads(leftover) if frappe.db.exists("Numbering Configuration", n)]
        if names:
            frappe.db.sql(
                "UPDATE `tabNumbering Configuration` SET enabled=1 WHERE name IN %s",
                (tuple(names),),
            )
        frappe.db.set_global(QUARANTINE_MARKER, None)
        frappe.db.commit()
        ns.clear_numbering_rules_cache()

    def _restore_branch_abbrs(self):
        for b, abbr in self._branch_abbr_snapshot.items():
            if frappe.db.get_value("Branch", b, "custom_abbr") != abbr:
                frappe.db.set_value("Branch", b, "custom_abbr", abbr)
        frappe.db.commit()

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
                   document_no_conditions=None, document_no_field=None,
                   duplicate_action=None, normal_docno_mode=None, return_docno_mode=None,
                   docno_group_by=None, raw_segments=False,
                   legacy_upto=None, legacy_source_field=None):
        segments = list(extra_segments)
        if not raw_segments:
            segments += [
                # the name's number slot references the SAME field the number is
                # written into, so the voucher name always contains the number
                {"segment_type": "Document Field", "field": document_no_field or "custom_document_no", "number_length": 6},
                {"segment_type": "Fiscal Year"},
            ]
        rule = frappe.get_doc({
            "doctype": "Numbering Configuration", "document_type": doctype,
            "enabled": 1, "target_field": target, "separator": separator,
            "auto_document_no": auto_document_no,
            "normal_docno_mode": normal_docno_mode or "Auto",
            "return_docno_mode": return_docno_mode or "Auto",
            "document_no_field": document_no_field or "custom_document_no",
            "duplicate_action": duplicate_action or "Throw Error",
            "legacy_upto": legacy_upto,
            "legacy_source_field": legacy_source_field,
            "conditions": conditions,
            "document_no_conditions": document_no_conditions or [],
            "docno_group_by": [
                # accepts "fieldname" or {"field": ..., "lock_after_numbering": ...}
                (f if isinstance(f, dict) else {"field": f})
                for f in (docno_group_by or [])
            ],
            "segments": segments,
        }).insert(ignore_permissions=True)
        # Frappe auto-fills `company` from user defaults during insert, which
        # would silently scope this GLOBAL test rule to the site's default
        # company (and away from the test docs' company). Clear it in the DB —
        # setting it before insert doesn't survive the default-filling.
        if rule.company:
            frappe.db.set_value("Numbering Configuration", rule.name, "company", None)
            rule.company = None
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
        self.assertLessEqual({"key", "pattern", "field", "number_field"}, set(scope))
        self.assertEqual(scope["number_field"], "custom_document_no")   # default
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
        # DESK form save: a new doc carrying a value with the manual flag unset
        # is a stale preview / copied value -> redrawn with the authoritative
        # draw. (Outside the desk — import/API/script — the value is kept;
        # see test_56.)
        d = self._je(custom_document_no=321, custom_document_no_manual=0)
        frappe.form_dict["cmd"] = "frappe.desk.form.save.savedocs"
        try:
            ns.apply_document_no(d)
        finally:
            frappe.form_dict.pop("cmd", None)
        self.assertIsNotNone(d.custom_document_no)
        self.assertNotEqual(d.custom_document_no, 321)

    def test_09_ineligible_type_not_numbered_but_value_preserved(self):
        # An ineligible type gets no auto number. And a value that was set
        # programmatically (no desk request) is PRESERVED — blanking only happens
        # in the desk to clear a stale client preview, never on import/API.
        d = self._je(custom_p_type=JE_TYPE_OFF,
                     custom_document_no=7, custom_document_no_manual=0)
        self.assertIsNone(ns._docno_scope(d))     # not eligible
        ns.apply_document_no(d)
        self.assertEqual(d.custom_document_no, 7)  # non-UI value kept (no data loss)

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

    def test_41_document_no_field_is_configurable(self):
        # The auto number can be written into a field other than custom_document_no.
        self._require(self.has_rules, "Numbering Configuration not installed")
        alt = "custom_document_word"   # a real (non-default) field on Payment Entry
        self._require(frappe.get_meta("Payment Entry").has_field(alt), "needs an alternate field")
        tag = "FLD" + frappe.generate_hash(length=6)
        self._temp_rule(
            auto_document_no=1,
            document_no_field=alt,
            extra_segments=self._tag_segments(tag),
            conditions=[],
            document_no_conditions=[{"field": "custom_p_type", "value": self.OFF_TYPE}],
        )
        d = self._pe_off(self.OFF_TYPE)
        scope = ns._docno_scope(d)
        self.assertIsNotNone(scope)
        self.assertEqual(scope["number_field"], alt)     # scope points at the configured field
        ns.apply_document_no(d)
        self.assertTrue(frappe.utils.cint(d.get(alt)) > 0)   # number written to the alt field
        self.assertFalse(d.get("custom_document_no"))        # NOT the default field

    # ============================================================
    #  RANDOMISED FUZZ — many situations, core invariants each time
    # ============================================================
    def test_50_fuzz_random_situations(self):
        """Deterministic-seed randomised coverage across branch/no-branch, each
        operator, default vs custom number field, eligible vs not, auto vs
        manual — asserting the invariants (gapless sequence, non-reserving peek,
        manual kept, ineligible not numbered) on every iteration."""
        import random
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.branches) >= 1, "needs a branch")
        random.seed(20260706)
        branch = self.branches[0]
        frappe.db.set_value("Branch", branch, "custom_abbr", "fz")   # restored by cleanup
        has_word = frappe.get_meta("Payment Entry").has_field("custom_document_word")

        for i in range(50):
            tag = "FZ%02d%s" % (i, frappe.generate_hash(length=4))
            use_branch = random.random() < 0.5
            field = "custom_document_word" if (has_word and random.random() < 0.35) else "custom_document_no"
            op = random.choice(["Equals", "In", "Is Set"])
            if op == "In":
                dcond = [{"field": "custom_p_type", "operator": "In",
                          "value": f"{self.OFF_TYPE} , {self.OFF_TYPE_2}"}]   # spaces on purpose
                ptype = random.choice([self.OFF_TYPE, self.OFF_TYPE_2]); bad = "Customers/Suppliers Receipt"
            elif op == "Is Set":
                dcond = [{"field": "custom_p_type", "operator": "Is Set", "value": ""}]
                ptype = self.OFF_TYPE; bad = ""     # empty type -> Is Set fails
            else:
                dcond = [{"field": "custom_p_type", "operator": "Equals", "value": self.OFF_TYPE}]
                ptype = self.OFF_TYPE; bad = self.OFF_TYPE_2

            segs = [{"segment_type": "Company Abbr"}, {"segment_type": "Static Text", "static_value": tag}]
            if use_branch:
                segs.append({"segment_type": "Branch Abbr"})
            segs.append({"segment_type": "Fetch from Link", "field": "custom_p_type", "fetch_field": "data_hrcj"})
            rule = self._temp_rule(auto_document_no=1, document_no_field=field,
                                   extra_segments=segs, conditions=[], document_no_conditions=dcond)
            ctx = f"iter {i} op={op} field={field} branch={use_branch}"
            try:
                def mk(pt):
                    d = self._pe()
                    d.custom_p_type = pt      # set directly ("" stays empty)
                    if use_branch:
                        d.custom_branch = branch
                    return d

                # (1) eligible: n fresh draws -> gapless 1..n in the configured field
                n = random.randint(2, 4)
                nums = [self._draw_into(mk(ptype), field) for _ in range(n)]
                self.assertEqual(nums, list(range(1, n + 1)), msg=f"{ctx}: {nums}")
                # (2) peek is non-reserving and predicts the next number
                self.assertEqual(ns.peek_next_document_no(mk(ptype)), n + 1, msg=ctx)
                # (3) a manually-set number is kept
                dm = mk(ptype); dm.set(field, 987654)
                if frappe.get_meta("Payment Entry").has_field(field + "_manual"):
                    dm.set(field + "_manual", 1)
                ns.apply_document_no(dm)
                self.assertEqual(frappe.utils.cint(dm.get(field)), 987654, msg=f"manual not kept {ctx}")
                # (4) a doc that fails the Document No. condition is not numbered
                self.assertIsNone(ns._docno_scope(mk(bad)), msg=f"ineligible got scope {ctx}")
            finally:
                self._drop_rule(rule.name)   # keep exactly one rule live at a time

    def _draw_into(self, doc, field):
        ns.apply_document_no(doc)
        return frappe.utils.cint(doc.get(field))

    # ============================================================
    #  CORE DOCTYPE — rule-driven numbering on a core Frappe doctype
    # ============================================================
    def test_51_core_doctype_todo(self):
        """Prove the generalized numbering works on a CORE doctype (ToDo) — not
        just the ERPNext transaction doctypes. Adds temp fields, a rule, inserts
        ToDos, checks the number + name, then removes everything."""
        self._require(self.has_rules, "Numbering Configuration not installed")
        from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
        dt = "ToDo"
        create_custom_fields({dt: [
            {"fieldname": "custom_document_no", "label": "Doc No", "fieldtype": "Int", "insert_after": "description"},
            {"fieldname": "custom_voucher_no", "label": "Voucher No", "fieldtype": "Data", "insert_after": "custom_document_no"},
        ]}, ignore_validate=True)
        self.addCleanup(self._drop_todo_fields)
        frappe.clear_cache(doctype=dt)

        tag = "TD" + frappe.generate_hash(length=5)
        self._temp_rule(
            doctype=dt, target="custom_voucher_no", auto_document_no=1,
            document_no_field="custom_document_no",
            extra_segments=[{"segment_type": "Static Text", "static_value": tag}],
            conditions=[], document_no_conditions=[],
        )
        made = []
        self.addCleanup(lambda: [self._force_delete(dt, n) for n in made])

        def mk():
            d = frappe.new_doc(dt)
            d.description = "numbering demo " + frappe.generate_hash(length=4)
            d.insert(ignore_permissions=True)
            made.append(d.name)
            return d

        a, b = mk(), mk()
        self.assertEqual(a.custom_document_no, 1)                 # core doctype auto-numbered
        self.assertEqual(b.custom_document_no, 2)
        self.assertTrue(a.custom_voucher_no.startswith(tag + "-"))   # name built from the rule
        self.assertIn("000001", a.custom_voucher_no)             # padded number inside the name

    def _drop_todo_fields(self):
        for fn in ("custom_document_no", "custom_voucher_no"):
            name = frappe.db.get_value("Custom Field", {"dt": "ToDo", "fieldname": fn})
            if name:
                frappe.delete_doc("Custom Field", name, force=1, ignore_permissions=True)
        frappe.db.commit()
        frappe.clear_cache(doctype="ToDo")

    def test_52_is_set_treats_zero_as_unset(self):
        # Regression: an unchecked Check / Int 0 is "not set" for the Is Set /
        # Is Not Set operators (only "", "0", "0.0" and None count as unset).
        cm = ns._condition_matches
        d = frappe._dict({"flag0": 0, "flag1": 1, "empty": "", "txt": "x", "zerostr": "0"})
        self.assertFalse(cm(d, {"field": "flag0", "operator": "Is Set", "value": ""}))
        self.assertTrue(cm(d, {"field": "flag0", "operator": "Is Not Set", "value": ""}))
        self.assertFalse(cm(d, {"field": "zerostr", "operator": "Is Set", "value": ""}))
        self.assertFalse(cm(d, {"field": "missing", "operator": "Is Set", "value": ""}))
        self.assertTrue(cm(d, {"field": "flag1", "operator": "Is Set", "value": ""}))
        self.assertTrue(cm(d, {"field": "txt", "operator": "Is Set", "value": ""}))
        self.assertFalse(cm(d, {"field": "empty", "operator": "Is Set", "value": ""}))

    def test_53_manual_number_bumps_counter(self):
        # A manually-entered number raises the scope counter, so the next auto
        # draw continues PAST it (concurrency hardening for manual-vs-auto).
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "MB" + frappe.generate_hash(length=6)
        self._temp_rule(
            auto_document_no=1, extra_segments=self._tag_segments(tag),
            conditions=[], document_no_conditions=[{"field": "custom_p_type", "value": self.OFF_TYPE}],
        )
        d1 = self._pe_off(); ns.apply_document_no(d1)
        self.assertEqual(d1.custom_document_no, 1)
        dm = self._pe_off(); dm.custom_document_no = 500; dm.custom_document_no_manual = 1
        ns.apply_document_no(dm)
        self.assertEqual(dm.custom_document_no, 500)          # manual kept
        d2 = self._pe_off(); ns.apply_document_no(d2)
        self.assertEqual(d2.custom_document_no, 501)          # auto skipped past the manual number

    def test_54_duplicate_action_uses_next_available(self):
        # Rule policy 'Use Next Available Number': a manually-typed number that
        # is already used is bumped to the next free one (instead of the save
        # being rejected), and ownership returns to auto (manual flag cleared).
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "DA" + frappe.generate_hash(length=6)
        self._temp_rule(
            doctype="Journal Entry", auto_document_no=1,
            extra_segments=self._tag_segments(tag), conditions=[],
            document_no_conditions=[{"field": "custom_p_type", "value": JE_TYPE}],
            duplicate_action="Use Next Available Number",
        )
        d1 = self._insert_je()                                # takes number 1
        self.assertEqual(frappe.utils.cint(d1.custom_document_no), 1)

        dm = self._je(); dm.custom_document_no = 1; dm.custom_document_no_manual = 1
        ns.apply_document_no(dm)
        self.assertEqual(frappe.utils.cint(dm.custom_document_no), 2)   # bumped, not kept
        self.assertEqual(frappe.utils.cint(dm.custom_document_no_manual), 0)  # back to auto

        # default policy keeps the duplicate (validators reject it at save)
        dt = self._je(); dt.custom_document_no = 1; dt.custom_document_no_manual = 1
        rule = ns._match_numbering_rule(dt)
        self.assertEqual(ns._duplicate_action({}), "Throw Error")       # default
        self.assertEqual(ns._duplicate_action(rule), "Use Next Available Number")

    def test_55_check_document_no_availability(self):
        # The typing-time availability check: reports who holds a taken number
        # and the next free one; a free number reports available.
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "AV" + frappe.generate_hash(length=6)
        self._temp_rule(
            doctype="Journal Entry", auto_document_no=1,
            extra_segments=self._tag_segments(tag), conditions=[],
            document_no_conditions=[{"field": "custom_p_type", "value": JE_TYPE}],
        )
        d1 = self._insert_je()
        payload = {"doctype": "Journal Entry", "company": self.company,
                   "posting_date": self.pdate, "voucher_type": "Journal Entry",
                   "custom_p_type": JE_TYPE,
                   "custom_document_no": frappe.utils.cint(d1.custom_document_no)}
        res = ns.check_document_no_availability(doc=payload)
        self.assertTrue(res and res["taken"])
        self.assertEqual(res["used_by"], d1.name)
        self.assertEqual(res["next"], frappe.utils.cint(d1.custom_document_no) + 1)

        payload["custom_document_no"] = 424242
        res = ns.check_document_no_availability(doc=payload)
        self.assertFalse(res["taken"])
        self.assertIsNone(res["used_by"])

    def test_56_import_keeps_and_continues_file_numbers(self):
        # Data Import contract: a row WITHOUT a number is auto-numbered, a row
        # WITH a number keeps it (legacy data), the sequence continues past
        # imported numbers, and a duplicate row fails visibly (never silently
        # renumbered).
        frappe.flags.in_import = True
        self.addCleanup(setattr, frappe.flags, "in_import", False)

        blank = self._je()
        ns.apply_document_no(blank)
        self.assertEqual(blank.custom_document_no, 1)              # auto

        legacy = self._je(custom_document_no=500)                  # flag NOT set,
        ns.apply_document_no(legacy)                               # like an import row
        self.assertEqual(legacy.custom_document_no, 500)           # kept
        self.assertEqual(frappe.utils.cint(legacy.custom_document_no_manual), 1)  # marked manual

        nxt = self._je()
        ns.apply_document_no(nxt)
        self.assertEqual(nxt.custom_document_no, 501)              # continues past 500

    def test_57_draft_scope_change_redraws_number(self):
        # A saved DRAFT edited onto a different series must not keep the old
        # series' number: the old one is given back (if last) and a fresh one
        # is drawn from the new series. Manual numbers are never touched.
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.branches) >= 2, "needs two branches")
        b1, b2 = self.branches
        frappe.db.set_value("Branch", b1, "custom_abbr", "t1")
        frappe.db.set_value("Branch", b2, "custom_abbr", "t2")
        tag = "SC" + frappe.generate_hash(length=6)
        self._temp_rule(
            auto_document_no=1,
            extra_segments=self._tag_segments(tag) + [{"segment_type": "Branch Abbr"}],
            conditions=[{"field": "custom_p_type", "value": PE_TYPE}],
        )
        d = self._pe(custom_branch=b1)
        ns.apply_document_no(d)
        self.assertEqual(d.custom_document_no, 1)
        old_scope = ns._docno_scope(d)

        # simulate the SAVED draft being edited: branch b1 -> b2
        before = self._pe(custom_branch=b1, custom_document_no=d.custom_document_no)
        d.name = "SIM-DRAFT-0001"; d.set("__islocal", 0)   # looks saved now
        d.custom_branch = b2
        d.flags.pop("_docno_assigned", None)
        d._doc_before_save = before
        ns._redraw_docno_if_scope_changed(d)
        self.assertEqual(d.custom_document_no, 1)   # b2's own series starts at 1
        self.assertNotEqual(ns._docno_scope(d)["key"], old_scope["key"])
        # the b1 number was reverted (it was the last drawn)
        self.assertEqual(ns._series_current(ns._docno_series_key(before, old_scope)), 0)

        # manual numbers are never redrawn
        m = self._pe(custom_branch=b1, custom_document_no=42, custom_document_no_manual=1)
        mb = self._pe(custom_branch=b1, custom_document_no=42, custom_document_no_manual=1)
        m.name = "SIM-DRAFT-0002"; m.set("__islocal", 0)
        m.custom_branch = b2
        m._doc_before_save = mb
        ns._redraw_docno_if_scope_changed(m)
        self.assertEqual(m.custom_document_no, 42)

    # ================================================================
    #  SPECIFICATION MATRIX — one comprehensive, deterministic spec per
    #  doctype: every operator x scope x field x mode x match/no-match,
    #  each asserting the same invariants. The matrix IS the logic.
    # ================================================================
    def _spec_doc(self, cfg, ptype, use_branch):
        d = frappe.new_doc(cfg["doctype"])
        d.company = self.company
        d.posting_date = self.pdate
        if cfg["doctype"] == "Journal Entry":
            d.voucher_type = "Journal Entry"
        elif cfg["doctype"] == "Payment Entry":
            d.payment_type = "Receive"
        d.custom_p_type = ptype
        if use_branch and cfg.get("branch"):
            d.custom_branch = cfg["branch"]
        return d

    def _run_spec_matrix(self, cfg):
        """Generic driver. For every (operator x scope x field), build the rule,
        then assert the invariants for a MATCHING doc (numbered) and a
        NON-MATCHING doc (not numbered). `cfg` is the per-doctype spec."""
        off, off2, bad = cfg["off"], cfg["off2"], cfg["bad"]
        # operator -> (matching value, non-matching value)
        ops = {
            "Equals":     (off,  off2),
            "Not Equals": (off2, off),
            "In":         (off,  bad),
            "Not In":     (bad,  off),
            "Is Set":     (off,  ""),
            "Is Not Set": ("",   off),
        }
        branch_choices = [False, True] if cfg.get("branch") else [False]
        fields = ["custom_document_no"]
        if frappe.get_meta(cfg["doctype"]).has_field("custom_document_word"):
            fields.append("custom_document_word")

        checked = 0
        for op, (match_val, nomatch_val) in ops.items():
            for use_branch in branch_choices:
                for field in fields:
                    tag = "MX" + frappe.generate_hash(length=6)
                    if op in ("Is Set", "Is Not Set"):
                        val = ""
                    elif op in ("In", "Not In"):
                        val = f"{off} , {off2}"
                    else:
                        val = off
                    segs = [{"segment_type": "Company Abbr"},
                            {"segment_type": "Static Text", "static_value": tag}]
                    if use_branch:
                        segs.append({"segment_type": "Branch Abbr"})
                    segs.append({"segment_type": "Fetch from Link",
                                 "field": "custom_p_type", "fetch_field": cfg["code_fetch"]})
                    rule = self._temp_rule(
                        doctype=cfg["doctype"], auto_document_no=1, document_no_field=field,
                        extra_segments=segs, conditions=[],
                        document_no_conditions=[{"field": "custom_p_type", "operator": op, "value": val}],
                    )
                    ctx = f"{cfg['doctype']} op={op} branch={use_branch} field={field}"
                    try:
                        # POSITIVE: matching doc -> eligible
                        d1 = self._spec_doc(cfg, match_val, use_branch)
                        ns.apply_document_no(d1)
                        self.assertEqual(frappe.utils.cint(d1.get(field)), 1, msg=f"{ctx}: not 1")
                        ns.set_custom_branch_name(d1)               # build the name
                        self.assertIn(tag, d1.get(cfg["target"]), msg=f"{ctx} name={d1.get(cfg['target'])}")
                        self.assertIn("000001", d1.get(cfg["target"]), msg=f"{ctx} name={d1.get(cfg['target'])}")
                        # gapless sequence + non-reserving peek
                        seq = [1] + [self._draw_into(self._spec_doc(cfg, match_val, use_branch), field) for _ in range(2)]
                        self.assertEqual(seq, [1, 2, 3], msg=f"{ctx}: {seq}")
                        self.assertEqual(ns.peek_next_document_no(self._spec_doc(cfg, match_val, use_branch)), 4, msg=ctx)
                        # manual kept
                        dm = self._spec_doc(cfg, match_val, use_branch)
                        dm.set(field, 9999)
                        if frappe.get_meta(cfg["doctype"]).has_field(field + "_manual"):
                            dm.set(field + "_manual", 1)
                        ns.apply_document_no(dm)
                        self.assertEqual(frappe.utils.cint(dm.get(field)), 9999, msg=f"{ctx}: manual lost")
                        # NEGATIVE: non-matching doc (and not a fallback type) -> not numbered
                        self.assertIsNone(ns._docno_scope(self._spec_doc(cfg, nomatch_val, use_branch)),
                                          msg=f"{ctx}: nomatch {nomatch_val!r} eligible")
                        checked += 1
                    finally:
                        self._drop_rule(rule.name)
        return checked

    def test_60_spec_matrix_payment_entry(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.branches) >= 1, "needs a branch")
        branch = self.branches[0]
        frappe.db.set_value("Branch", branch, "custom_abbr", "sp")
        n = self._run_spec_matrix({
            "doctype": "Payment Entry", "target": "custom_name", "code_fetch": "data_hrcj",
            "off": "Vendor Payment", "off2": "Vendor Receipt", "bad": "Customers/Suppliers Receipt",
            "branch": branch,
        })
        self.assertGreaterEqual(n, 20)   # 6 ops x 2 branch x 2 fields

    def test_61_spec_matrix_journal_entry(self):
        self._require(self.has_rules, "Numbering Configuration not installed")
        # Journal Entry has no branch field — the driver skips that dimension.
        for t in ("Cash Entry", "Opening Entry", "Contract Form"):
            if not frappe.db.exists("JV Type", t):
                self.skipTest(f"JV Type {t} missing")
        n = self._run_spec_matrix({
            "doctype": "Journal Entry", "target": "custom_name", "code_fetch": "jv_type_code",
            "off": "Cash Entry", "off2": "Opening Entry", "bad": "Contract Form",
            "branch": None,
        })
        self.assertGreaterEqual(n, 6)    # 6 ops x 1 x fields

    def test_62_amendment_pins_original_number(self):
        # An amendment's Document No. is ALWAYS the number stored on the
        # original: a typed-over value, a stale preview or an API payload
        # cannot move it (the form additionally shows the field read-only).
        orig = self._insert_je()
        n = frappe.utils.cint(orig.custom_document_no)
        self.assertGreater(n, 0)

        # typed-over manual value -> pinned back; flag follows the original (auto)
        d = self._je(amended_from=orig.name,
                     custom_document_no=999999, custom_document_no_manual=1)
        ns.apply_document_no(d)
        self.assertEqual(frappe.utils.cint(d.custom_document_no), n)
        self.assertEqual(frappe.utils.cint(d.custom_document_no_manual), 0)

        # blank payload (a copy path that stripped the field) -> still pinned
        d2 = self._je(amended_from=orig.name)
        ns.apply_document_no(d2)
        self.assertEqual(frappe.utils.cint(d2.custom_document_no), n)

        # pinned on EVERY save, not just the first: a later edit that slipped
        # a different number in (docstatus 0 draft re-save) is reset too
        d2.flags.pop("_docno_assigned", None)
        d2.custom_document_no = 424242
        ns.apply_document_no(d2)
        self.assertEqual(frappe.utils.cint(d2.custom_document_no), n)

    # ============================================================
    #  STABILITY: server is the single source of truth for the number
    # ============================================================
    def test_63_status_endpoint_reflects_server_decision(self):
        # The form now asks the server for the field's state instead of guessing.
        # An auto-numbered draft reports auto=True with the peeked next number;
        # a draft no rule numbers reports auto=False (field becomes manual/required).
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "ST" + frappe.generate_hash(length=6)
        self._temp_rule(
            auto_document_no=1, extra_segments=self._tag_segments(tag),
            conditions=[], document_no_conditions=[{"field": "custom_p_type", "value": self.OFF_TYPE}],
        )
        auto = ns.get_document_no_status(doc=json.dumps({
            "doctype": "Payment Entry", "company": self.company,
            "posting_date": str(self.pdate), "payment_type": "Receive",
            "custom_p_type": self.OFF_TYPE,
        }))
        self.assertTrue(auto["auto"])
        self.assertEqual(auto["next"], ns.peek_next_document_no(self._pe_off(self.OFF_TYPE)))
        self.assertFalse(auto["ambiguous"])

        manual = ns.get_document_no_status(doc=json.dumps({
            "doctype": "Payment Entry", "company": self.company,
            "posting_date": str(self.pdate), "payment_type": "Receive",
            "custom_p_type": self.OFF_TYPE_2,   # not numbered by the rule or fallback
        }))
        self.assertFalse(manual["auto"])
        self.assertIsNone(manual["next"])

    def test_64_saved_number_is_server_draw_not_client_value(self):
        # Stability guarantee: whatever number the form displayed as a preview,
        # the SAVED number is the server's authoritative draw. A stale non-manual
        # value on a fresh DESK-FORM draft is overwritten, never trusted.
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "SV" + frappe.generate_hash(length=6)
        self._temp_rule(
            auto_document_no=1, extra_segments=self._tag_segments(tag),
            conditions=[], document_no_conditions=[{"field": "custom_p_type", "value": self.OFF_TYPE}],
        )
        d1 = self._pe_off(); ns.apply_document_no(d1)
        self.assertEqual(d1.custom_document_no, 1)
        # Simulate a desk form save: a bogus preview (999) with the manual flag
        # unset is OUR preview -> the server ignores it and draws the real next.
        orig_fd = getattr(frappe.local, "form_dict", None)
        frappe.local.form_dict = frappe._dict({"cmd": "frappe.desk.form.save.savedocs"})
        self.addCleanup(setattr, frappe.local, "form_dict", orig_fd)
        d2 = self._pe_off()
        d2.custom_document_no = 999
        if frappe.get_meta("Payment Entry").has_field("custom_document_no_manual"):
            d2.custom_document_no_manual = 0
        ns.apply_document_no(d2)
        self.assertEqual(d2.custom_document_no, 2)   # server draw, not the 999 preview

    def test_65_equally_specific_rules_flagged_ambiguous(self):
        # Two enabled rules with the SAME scope both match a doc: the winner is
        # still deterministic, but the overlap is reported so an admin can fix it.
        self._require(self.has_rules, "Numbering Configuration not installed")
        vcond = [{"field": "custom_p_type", "value": self.OFF_TYPE}]   # voucher condition -> both match, tie
        self._temp_rule(auto_document_no=1, conditions=vcond, document_no_conditions=[],
                        extra_segments=self._tag_segments("AM1" + frappe.generate_hash(length=4)))
        self._temp_rule(auto_document_no=1, conditions=vcond, document_no_conditions=[],
                        extra_segments=self._tag_segments("AM2" + frappe.generate_hash(length=4)))
        d = self._pe_off(self.OFF_TYPE)
        tied = ns._ambiguous_numbering_rules(d)
        self.assertGreaterEqual(len(tied), 2)             # overlap detected
        self.assertIsNotNone(ns._match_numbering_rule(d)) # still resolves to one

    def test_66_return_auto_normal_manual_same_doctype(self):
        # The docs recipe (docs/numbering_configuration.md §4): ONE rule on a
        # doctype holding both normal and return documents (is_return), with
        # Document No. condition `is_return Equals 1` -> returns are
        # auto-numbered, normal documents stay manual (field required on the
        # form). Uses Purchase Invoice, whose returns live in the same doctype.
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "RA" + frappe.generate_hash(length=6)
        self._temp_rule(
            doctype="Purchase Invoice", auto_document_no=1,
            extra_segments=[{"segment_type": "Company Abbr"},
                            {"segment_type": "Static Text", "static_value": tag}],
            conditions=[],                                            # names every PI
            document_no_conditions=[{"field": "is_return", "operator": "Equals", "value": "1"}],
        )

        def pi(is_return):
            d = frappe.new_doc("Purchase Invoice")
            d.company = self.company
            d.posting_date = self.pdate
            d.is_return = is_return
            return d

        # RETURN -> auto: eligible, status says auto, draws a gapless sequence
        self.assertIsNotNone(ns._docno_scope(pi(1)))
        st = ns.get_document_no_status(doc=json.dumps({
            "doctype": "Purchase Invoice", "company": self.company,
            "posting_date": str(self.pdate), "is_return": 1}))
        self.assertTrue(st["auto"])
        nums = [self._draw_into(pi(1), "custom_document_no") for _ in range(2)]
        self.assertEqual(nums, [1, 2])

        # NORMAL -> manual: the auto-fill rule is authoritative and its
        # Document No. condition fails, so the doc is NOT auto-numbered
        # (the form then shows the field as required manual entry).
        self.assertIsNone(ns._docno_scope(pi(0)))
        st = ns.get_document_no_status(doc=json.dumps({
            "doctype": "Purchase Invoice", "company": self.company,
            "posting_date": str(self.pdate), "is_return": 0}))
        self.assertFalse(st["auto"])

    def test_67_normal_return_mode_switches(self):
        # The simple UI for the same split: ONE rule matching every document,
        # with the "Normal Documents" / "Return Documents" Auto/Manual selects
        # instead of hand-typed conditions. normal=Manual + return=Auto ->
        # returns auto-numbered, normal manual. Blank modes behave as Auto.
        self._require(self.has_rules, "Numbering Configuration not installed")
        tag = "MD" + frappe.generate_hash(length=6)
        self._temp_rule(
            doctype="Purchase Invoice", auto_document_no=1,
            normal_docno_mode="Manual", return_docno_mode="Auto",
            extra_segments=[{"segment_type": "Company Abbr"},
                            {"segment_type": "Static Text", "static_value": tag}],
            conditions=[], document_no_conditions=[],
        )

        def pi(is_return):
            d = frappe.new_doc("Purchase Invoice")
            d.company = self.company
            d.posting_date = self.pdate
            d.is_return = is_return
            return d

        # return -> Auto mode -> numbered
        self.assertIsNotNone(ns._docno_scope(pi(1)))
        self.assertEqual(self._draw_into(pi(1), "custom_document_no"), 1)
        # normal -> Manual mode -> not auto-numbered (authoritative)
        self.assertIsNone(ns._docno_scope(pi(0)))
        st = ns.get_document_no_status(doc=json.dumps({
            "doctype": "Purchase Invoice", "company": self.company,
            "posting_date": str(self.pdate), "is_return": 0}))
        self.assertFalse(st["auto"])
        # a doctype WITHOUT is_return uses the Normal mode: Manual blocks it too
        rule = {"auto_document_no": 1, "normal_docno_mode": "Manual",
                "return_docno_mode": "Auto", "document_no_conditions": []}
        self.assertFalse(ns._docno_eligible(self._pe_off(), rule))
        # blank modes (pre-existing rules) keep numbering everything
        rule_blank = {"auto_document_no": 1, "document_no_conditions": []}
        self.assertTrue(ns._docno_eligible(self._pe_off(), rule_blank))

    def test_68_group_by_fields_partition_the_series(self):
        # "Group Document No. By": the admin picks the fields whose value
        # combinations each count on their OWN sequence — here company + branch
        # + custom_p_type + fiscal year on Payment Entry. Branches and types
        # must number independently; same group must be gapless; manual numbers
        # bump only their own group's counter.
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.branches) >= 2, "needs two branches")
        b1, b2 = self.branches
        tag = "GB" + frappe.generate_hash(length=6)
        self._temp_rule(
            auto_document_no=1,
            extra_segments=self._tag_segments(tag),
            conditions=[], document_no_conditions=[],
            docno_group_by=["company", "custom_branch", "custom_p_type",
                            "custom_fiscal_year"],
        )

        def pe(branch, ptype=None):
            return self._pe(custom_branch=branch, custom_p_type=ptype or self.OFF_TYPE)

        scope = ns._docno_scope(pe(b1))
        self.assertIsNotNone(scope)
        self.assertTrue(scope["key"].startswith("gb|"))      # group-by scope in use
        self.assertIn("custom_branch=" + b1, scope["group"])
        self.assertIn("fy=", scope["group"])                 # fiscal year resolved

        # groups count sequentially and INDEPENDENTLY — measured from each
        # group's own starting point, because the group-by scope deliberately
        # continues whatever real data the live site already holds
        b1_start = ns.peek_next_document_no(pe(b1))
        b2_start = ns.peek_next_document_no(pe(b2))
        t2_start = ns.peek_next_document_no(pe(b1, self.OFF_TYPE_2))
        self.assertEqual(self._draw_into(pe(b1), "custom_document_no"), b1_start)
        self.assertEqual(self._draw_into(pe(b1), "custom_document_no"), b1_start + 1)
        # b1's draws advanced ONLY b1's group
        self.assertEqual(self._draw_into(pe(b2), "custom_document_no"), b2_start)
        self.assertEqual(self._draw_into(pe(b1, self.OFF_TYPE_2), "custom_document_no"), t2_start)

        # manual number bumps ONLY its own group: next b1 draw skips past it,
        # b2 keeps counting where it was
        manual = ns.peek_next_document_no(pe(b1)) + 1000
        dm = pe(b1); dm.custom_document_no = manual; dm.custom_document_no_manual = 1
        ns.apply_document_no(dm)
        self.assertEqual(dm.custom_document_no, manual)
        self.assertEqual(ns.peek_next_document_no(pe(b1)), manual + 1)
        self.assertEqual(ns.peek_next_document_no(pe(b2)), b2_start + 1)

    def test_69_voucher_counter_never_reissues_stored_numbers(self):
        # The voucher-name Number draw must jump past numbers already STORED
        # in the target column even when the tabSeries counter lags them
        # (hand-edited value, restored backup). A lagging counter used to make
        # every subsequent save collide: "Number ... is already used by ...".
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.accounts) >= 2, "needs two accounts")
        tag = "VC" + frappe.generate_hash(length=6)
        # raw_segments: no Document Field docno slot — the name exercises ONLY
        # the voucher Number segment under test (custom_document_no is still
        # filled by the fallback, satisfying the field's mandatory flag).
        self._temp_rule(
            doctype="Journal Entry",
            raw_segments=True,
            extra_segments=[
                {"segment_type": "Static Text", "static_value": tag},
                {"segment_type": "Number", "number_length": 6},
                {"segment_type": "Fiscal Year"},
            ],
            conditions=[{"field": "custom_p_type", "value": JE_TYPE}],
        )
        key = f"{tag}-{self.fy}-"
        self.addCleanup(self._drop_series, key)

        a = self._insert_je()
        self.assertEqual(a.custom_name, f"{tag}-000001-{self.fy}")
        self.assertEqual(ns._series_current(key), 1)

        # counter lags the data (reset to 0): the draw must self-heal to 2
        frappe.db.sql("UPDATE `tabSeries` SET `current`=0 WHERE `name`=%s", key)
        b = self._insert_je()
        self.assertEqual(b.custom_name, f"{tag}-000002-{self.fy}")

        # a hand-edited HIGHER stored number becomes the floor of the series
        frappe.db.set_value("Journal Entry", b.name, "custom_name",
                            f"{tag}-000009-{self.fy}")
        frappe.db.sql("UPDATE `tabSeries` SET `current`=0 WHERE `name`=%s", key)
        c = self._insert_je()
        self.assertEqual(c.custom_name, f"{tag}-000010-{self.fy}")

    def test_70_stored_number_is_immutable_from_outside(self):
        # A STORED voucher number must not change once assigned: an edit
        # arriving from a client/API/script save is discarded in favor of the
        # stored value. Only frappe.flags.allow_number_overwrite (a deliberate
        # server-side correction) may replace it.
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.accounts) >= 2, "needs two accounts")
        tag = "IM" + frappe.generate_hash(length=6)
        self._temp_rule(
            doctype="Journal Entry",
            raw_segments=True,
            extra_segments=[
                {"segment_type": "Static Text", "static_value": tag},
                {"segment_type": "Number", "number_length": 6},
            ],
            conditions=[{"field": "custom_p_type", "value": JE_TYPE}],
        )
        self.addCleanup(self._drop_series, f"{tag}-")

        a = self._insert_je()
        assigned = a.custom_name
        self.assertTrue(assigned.startswith(tag))

        # an outside edit (form/REST/script) is silently reverted on save
        a.custom_name = f"{tag}-999999"
        a.user_remark = "edited"
        a.save(ignore_permissions=True)
        self.assertEqual(a.custom_name, assigned)
        self.assertEqual(
            frappe.db.get_value("Journal Entry", a.name, "custom_name"), assigned)

        # a deliberate correction can opt in via the flag
        frappe.flags.allow_number_overwrite = True
        try:
            a.custom_name = f"{tag}-999999"
            a.save(ignore_permissions=True)
        finally:
            frappe.flags.allow_number_overwrite = False
        self.assertEqual(a.custom_name, f"{tag}-999999")

    def test_71_locked_group_field_rejects_change(self):
        # "Group Document No. By -> Lock After Numbering": once a Document No.
        # is assigned, a locked group field may no longer change — the save is
        # rejected instead of silently renumbering into the new group.
        # Unlocked fields keep the default draft renumbering (test_57).
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.branches) >= 2, "needs two branches")
        b1, b2 = self.branches
        tag = "LK" + frappe.generate_hash(length=6)
        self._temp_rule(
            auto_document_no=1,
            extra_segments=self._tag_segments(tag),
            conditions=[], document_no_conditions=[],
            docno_group_by=[
                {"field": "company"},
                {"field": "custom_branch", "lock_after_numbering": 1},
                {"field": "custom_fiscal_year", "lock_after_numbering": 1},
            ],
        )

        d = self._pe(custom_branch=b1)
        ns.apply_document_no(d)
        self.assertTrue(d.custom_document_no)

        def simulate_saved_edit(**changes):
            before = self._pe(custom_branch=b1, custom_document_no=d.custom_document_no)
            cur = self._pe(custom_branch=b1, custom_document_no=d.custom_document_no)
            cur.name = "SIM-LOCK-0001"; cur.set("__islocal", 0)
            for k, v in changes.items():
                setattr(cur, k, v)
            cur._doc_before_save = before
            return cur

        # locked branch changed -> rejected
        with self.assertRaises(frappe.ValidationError):
            ns._enforce_locked_group_fields(simulate_saved_edit(custom_branch=b2))

        # locked fiscal year: posting date moved into ANOTHER fiscal year -> rejected
        other_fy = frappe.get_all("Fiscal Year", filters={"name": ["!=", self.fy]},
                                  fields=["name", "year_start_date"], limit=1)
        if other_fy:
            with self.assertRaises(frappe.ValidationError):
                ns._enforce_locked_group_fields(
                    simulate_saved_edit(posting_date=other_fy[0].year_start_date))

        # nothing changed -> passes
        ns._enforce_locked_group_fields(simulate_saved_edit())

        # company is in the grouping but NOT locked -> the lock lets it through
        # (the scope-change redraw handles the renumbering)
        other_company = frappe.get_all(
            "Company", filters={"name": ["!=", self.company]}, pluck="name", limit=1)
        if other_company:
            ns._enforce_locked_group_fields(simulate_saved_edit(company=other_company[0]))

        # the status endpoint reports the locked REAL columns for the form
        # (custom_fiscal_year excluded: within-FY date edits stay allowed)
        st = ns.get_document_no_status(self._pe(custom_branch=b1).as_dict())
        self.assertEqual(st.get("locked_fields"), ["custom_branch"])

        # rule-level "Lock All Group Fields After Numbering": every group row
        # is locked without ticking them one by one — company now throws too
        rule = ns._match_numbering_rule(self._pe(custom_branch=b1))
        rule_all = dict(rule, lock_group_fields=1)
        self.assertEqual(
            ns._locked_group_fields(rule_all),
            ["company", "custom_branch", "custom_fiscal_year"])

    def test_72_stale_manual_leftover_redrawn_on_desk_save(self):
        # A FLAGGED manual value on a NEW desk-form save of an AUTO-mode doc is
        # a leftover — typed during a Manual-mode stint before the type/scope
        # flipped the doc to Auto, or carried in by Duplicate (the form hides
        # the field in auto mode, so it cannot have been typed HERE). The auto
        # draw wins and the flag is cleared.
        self._require(
            frappe.get_meta("Journal Entry").has_field("custom_document_no_manual"),
            "needs the manual flag field")
        orig_fd = getattr(frappe.local, "form_dict", None)
        frappe.local.form_dict = frappe._dict({"cmd": "frappe.desk.form.save.savedocs"})
        self.addCleanup(setattr, frappe.local, "form_dict", orig_fd)

        d = self._je(custom_document_no=999999, custom_document_no_manual=1)
        ns.apply_document_no(d)
        self.assertNotEqual(frappe.utils.cint(d.custom_document_no), 999999)  # redrawn
        self.assertGreater(frappe.utils.cint(d.custom_document_no), 0)
        self.assertEqual(frappe.utils.cint(d.custom_document_no_manual), 0)   # back to auto

        # An INELIGIBLE (manual-mode) doc keeps its flagged value on the same
        # desk save — the discard applies only where auto would number the doc.
        m = self._je(custom_p_type=JE_TYPE_OFF,
                     custom_document_no=999999, custom_document_no_manual=1)
        ns.apply_document_no(m)
        self.assertEqual(frappe.utils.cint(m.custom_document_no), 999999)

        # Outside the desk (import/REST/script) a flagged value is intentional
        # data and stays verbatim even on an auto-mode doc (see test_06/56).
        frappe.local.form_dict = frappe._dict({})
        s = self._je(custom_document_no=999999, custom_document_no_manual=1)
        ns.apply_document_no(s)
        self.assertEqual(frappe.utils.cint(s.custom_document_no), 999999)

    def test_73_manual_mode_duplicate_is_rejected(self):
        # A Manual-mode doc has no auto scope, but a typed number must STILL be
        # unique within its would-be series: a duplicate (typed again, or
        # carried in by a copy path) is rejected, and the typing-time
        # availability check reports it. Both were silent before
        # ignore_eligibility — the checks bailed on the missing auto scope.
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.accounts) >= 2, "needs two accounts")
        tag = "MM" + frappe.generate_hash(length=6)
        self._temp_rule(
            doctype="Journal Entry", auto_document_no=1,
            normal_docno_mode="Manual",                      # nothing auto-numbered
            extra_segments=self._tag_segments(tag),
            conditions=[], document_no_conditions=[],
        )
        big = 800000 + int(frappe.generate_hash(length=6), 16) % 90000
        a = self._je(custom_document_no=big, custom_document_no_manual=1)
        self.assertIsNone(ns._docno_scope(a))                # manual mode: no auto scope
        self._balance(a).insert(ignore_permissions=True)
        self.addCleanup(self._force_delete, "Journal Entry", a.name)
        self.assertEqual(frappe.utils.cint(a.custom_document_no), big)   # kept

        # typing-time check sees the taken number despite manual mode
        res = ns.check_document_no_availability(doc={
            "doctype": "Journal Entry", "company": self.company,
            "posting_date": str(self.pdate), "voucher_type": "Journal Entry",
            "custom_p_type": JE_TYPE, "custom_document_no": big})
        self.assertTrue(res and res["taken"])
        self.assertEqual(res["used_by"], a.name)

        # save-time: the duplicate is rejected, not silently kept
        b = self._je(custom_document_no=big, custom_document_no_manual=1)
        self._balance(b)
        with self.assertRaises(frappe.ValidationError) as cm:
            b.insert(ignore_permissions=True)
        self.assertIn("already used", str(cm.exception))

    # ------------------------------------------- 74-76  per-company uniqueness
    def _legacy_passthrough_rule(self, target):
        """A rule shaped like the live Sales Invoice one: inside its legacy window
        the number is COPIED from the target field itself (the "keep the imported
        number" config), so no counter is involved."""
        return self._temp_rule(
            doctype="Journal Entry", target=target, raw_segments=True,
            legacy_upto=frappe.utils.add_years(self.pdate, 1),
            legacy_source_field=target,
            extra_segments=[
                {"segment_type": "Company Abbr"},
                {"segment_type": "Number", "number_length": 6},
                {"segment_type": "Fiscal Year"},
            ],
            conditions=[{"field": "custom_p_type", "value": JE_TYPE}],
        )

    def test_74_legacy_number_may_repeat_in_another_company(self):
        # The old ERPs numbered each company independently, so the SAME legacy
        # number can legitimately arrive for two companies (NGI's RTN/000001 and
        # NGK's RTN/000001 are different invoices). It must be kept verbatim for
        # both — not treated as a copied number and renumbered, which silently
        # discarded 417 imported NGK return numbers.
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.accounts) >= 2, "needs two accounts")
        self._require(bool(self.company2), "needs a second company")
        target = self.scoped_target
        self._legacy_passthrough_rule(target)
        value = "RTN/" + frappe.generate_hash(length=6)

        a = self._insert_je(**{target: value})
        self.assertEqual(a.get(target), value)                      # kept as given

        # same number, other company: kept, no throw, no renumber
        b = self._je(**{"company": self.company2, target: value})
        ns.set_custom_branch_name(b)
        self.assertEqual(b.get(target), value)

    def test_74b_legacy_number_may_repeat_in_another_fiscal_year(self):
        # The legacy counters restarted every year: NGK holds NGK/000001 in
        # 77/78 AND again in 79/80. Same company, same number, different year is
        # therefore NOT a duplicate — 362 rows of a pending import depend on it.
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.accounts) >= 2, "needs two accounts")
        prev = frappe.get_all(
            "Fiscal Year", filters={"year_end_date": ["<", self.pdate]},
            fields=["name", "year_start_date"], order_by="year_end_date desc", limit=1)
        self._require(bool(prev), "needs an earlier fiscal year")
        target = self.scoped_target
        self._legacy_passthrough_rule(target)
        value = "RTN/" + frappe.generate_hash(length=6)

        a = self._insert_je(**{target: value})                      # current year
        self.assertEqual(a.get(target), value)

        # same company, same number, EARLIER fiscal year: kept
        b = self._je(**{"posting_date": prev[0].year_start_date, target: value})
        ns.set_custom_branch_name(b)
        self.assertEqual(b.get(target), value)

        # and the same year still collides
        c = self._je(**{target: value})
        with self.assertRaises(frappe.ValidationError):
            ns.set_custom_branch_name(c)

    def test_75_duplicate_in_same_company_throws(self):
        # Inside ONE company the number is still unique — and a duplicate is
        # REJECTED, never replaced by a generated number.
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.accounts) >= 2, "needs two accounts")
        target = self.scoped_target
        self._legacy_passthrough_rule(target)
        value = "RTN/" + frappe.generate_hash(length=6)

        a = self._insert_je(**{target: value})

        b = self._je(**{target: value})
        with self.assertRaises(frappe.ValidationError) as cm:
            ns.set_custom_branch_name(b)
        self.assertIn("already used", str(cm.exception))
        self.assertIn(a.name, str(cm.exception))
        self.assertEqual(b.get(target), value)     # NOT silently renumbered

    def test_76_globally_unique_target_stays_group_wide(self):
        # custom_name carries a DB UNIQUE index (add_unique_custom_name_index),
        # so the database enforces group-wide uniqueness whatever Python thinks.
        # The check must stay group-wide there — scoping it below the constraint
        # would only turn a readable error into an IntegrityError.
        self._require(self.has_rules, "Numbering Configuration not installed")
        self._require(len(self.accounts) >= 2, "needs two accounts")
        self._require(bool(self.company2), "needs a second company")
        self._require(
            bool(frappe.get_meta("Journal Entry").get_field("custom_name").get("unique")),
            "custom_name is not DB-unique on this site",
        )
        self._legacy_passthrough_rule("custom_name")
        value = "RTN/" + frappe.generate_hash(length=6)

        a = self._insert_je(custom_name=value)
        self.assertEqual(a.custom_name, value)

        b = self._je(company=self.company2, custom_name=value)
        with self.assertRaises(frappe.ValidationError) as cm:
            ns.set_custom_branch_name(b)
        self.assertIn("already used", str(cm.exception))
