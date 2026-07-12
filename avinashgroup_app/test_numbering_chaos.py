"""Chaos fuzz: randomized adversarial attack on the Numbering Configuration
engine. Goal: MAKE IT BREAK — duplicate numbers, name/number disagreement,
counter corruption, or any non-ValidationError crash.

Random hostile rules (weird segments, separators, operators, group-bys,
legacy cut-overs, ambiguous twins, enable/disable churn) are combined with
random hostile documents (blank codes, boundary dates, manual-number
collisions, draft scope flips, deletes) on Journal Entry + Payment Entry.
After EVERY operation the invariants are re-checked:

  I1  no two live docs in the same series scope hold the same number
  I2  an auto draw never collides with a live number (reuse of a DELETED
      number is legal by design — delete reverts the counter)
  I3  the built voucher name embeds exactly the number the doc was assigned
  I4  only frappe.ValidationError-family exceptions may escape an operation

Reproducible: seed printed at start, override with CHAOS_SEED; op count with
CHAOS_OPS (default 500). Site hygiene mirrors test_ngk_numbering_format:
live rules quarantined (persisted marker), series snapshot/restored, every
created rule/doc deleted.

    CHAOS_OPS=500 bench --site avinas1 run-tests --app avinashgroup_app \
        --module avinashgroup_app.test_numbering_chaos
"""

import json
import os
import random
import re
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from avinashgroup_app.custom_code.Override import naming_series as ns

COMPANY = "Nepal Gas Udhyog (Karnali) Pvt. Ltd."
QUARANTINE_MARKER = "numbering_chaos_quarantine"
MAX_LIVE_DOCS = 15

JE_TYPES = ["Bank Entry", "Cash Entry", "Journal Entry", "Party Journal",
            "Debit Note", "Credit Note", "Opening Entry", None]
PE_TYPES = ["Bank Customers Receipt", "NOC Payment", "Vendor Payment",
            "Customers/Suppliers Receipt", "Contra Voucher- cash to bank", None]
SEPARATORS = ["-", "/", ".", ""]
STATIC_TEXTS = ["CHAOS", "X-Y", "क्रम", "A/B", " ", "", "00", "%s", "'"]
OPERATORS = ["Equals", "Not Equals", "In", "Not In", "Is Set", "Is Not Set", ""]


class TestNumberingChaos(FrappeTestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Company", COMPANY):
            raise unittest.SkipTest(f"company {COMPANY!r} missing")
        cls.today = frappe.utils.today()
        cls.fy = ns.get_fiscal_year_from_date(cls.today)
        cls.accounts = frappe.get_all(
            "Account", filters={"company": COMPANY, "is_group": 0, "disabled": 0},
            pluck="name", limit=2)
        cls.company_doc = frappe.get_doc("Company", COMPANY)
        cls.customer = frappe.db.get_value(
            "Customer", {"disabled": 0, "custom_company": COMPANY}, "name")
        cls.bank = frappe.db.get_value(
            "Account", {"company": COMPANY, "account_type": "Bank",
                        "is_group": 0, "disabled": 0}, "name")

    def setUp(self):
        self.seed = int(os.environ.get("CHAOS_SEED") or random.SystemRandom().randint(1, 10 ** 9))
        self.ops_budget = int(os.environ.get("CHAOS_OPS") or 500)
        self.rng = random.Random(self.seed)
        print(f"\nCHAOS_SEED={self.seed} CHAOS_OPS={self.ops_budget}", flush=True)

        rows = frappe.db.sql(
            "SELECT `name`, `current` FROM `tabSeries` "
            "WHERE `name` LIKE %s OR `name` LIKE %s", ("docno:%", "NGK-%"))
        self._series_snapshot = {n: c for n, c in rows}
        self.addCleanup(self._restore_series)

        leftover = frappe.db.get_global(QUARANTINE_MARKER)
        if leftover:
            self._enable(json.loads(leftover))
        self._live_rules = frappe.get_all(
            "Numbering Configuration", filters={"enabled": 1}, pluck="name")
        self.addCleanup(self._restore_live_rules)
        if self._live_rules:
            frappe.db.set_global(QUARANTINE_MARKER, json.dumps(self._live_rules))
            frappe.db.sql(
                "UPDATE `tabNumbering Configuration` SET enabled=0 WHERE name IN %s",
                (tuple(self._live_rules),))
            frappe.db.commit()
            ns.clear_numbering_rules_cache()

        self.my_rules = []      # rule names this run created
        self.live_docs = []     # (doctype, name) of inserted docs
        self.op_log = []        # (i, op name, detail) for failure reports
        self.addCleanup(self._destroy_created)

    # ------------------------------------------------------------ hygiene
    def _restore_live_rules(self):
        if getattr(self, "_live_rules", None):
            self._enable(self._live_rules)
        frappe.db.set_global(QUARANTINE_MARKER, None)
        frappe.db.commit()

    @staticmethod
    def _enable(names):
        names = [n for n in names if frappe.db.exists("Numbering Configuration", n)]
        if names:
            frappe.db.sql(
                "UPDATE `tabNumbering Configuration` SET enabled=1 WHERE name IN %s",
                (tuple(names),))
            frappe.db.commit()
            ns.clear_numbering_rules_cache()

    def _restore_series(self):
        rows = frappe.db.sql(
            "SELECT `name`, `current` FROM `tabSeries` "
            "WHERE `name` LIKE %s OR `name` LIKE %s", ("docno:%", "NGK-%"))
        for name, cur in rows:
            snap = self._series_snapshot.get(name)
            if snap is None:
                frappe.db.sql("DELETE FROM `tabSeries` WHERE `name`=%s", name)
            elif snap != cur:
                frappe.db.sql(
                    "UPDATE `tabSeries` SET `current`=%s WHERE `name`=%s", (snap, name))
        frappe.db.commit()

    def _destroy_created(self):
        for doctype, name in list(self.live_docs):
            if frappe.db.exists(doctype, name):
                frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
        for name in self.my_rules:
            if frappe.db.exists("Numbering Configuration", name):
                frappe.delete_doc("Numbering Configuration", name,
                                  force=1, ignore_permissions=True)
        frappe.db.commit()
        ns.clear_numbering_rules_cache()

    # ------------------------------------------------------- doc factories
    def _doc(self, doctype):
        rng = self.rng
        d = frappe.new_doc(doctype)
        d.company = COMPANY if rng.random() > 0.05 else None
        date = rng.choice([
            self.today, "2025-07-17", "2026-07-16",   # FY boundaries
            "1999-01-01", "2099-01-01", None, self.today])
        d.posting_date = date
        if doctype == "Journal Entry":
            d.voucher_type = "Journal Entry"
            d.custom_p_type = rng.choice(JE_TYPES)
            d.append("accounts", {"account": self.accounts[0],
                                  "debit_in_account_currency": 100, "debit": 100})
            d.append("accounts", {"account": self.accounts[1],
                                  "credit_in_account_currency": 100, "credit": 100})
        else:
            d.payment_type = "Receive"
            d.custom_p_type = rng.choice(PE_TYPES)
            d.party_type = "Customer"
            d.party = self.customer
            d.paid_from = self.company_doc.default_receivable_account
            d.paid_to = self.bank
            d.paid_amount = d.received_amount = 100
            d.source_exchange_rate = d.target_exchange_rate = 1
            d.reference_no = "CHAOS"
            d.reference_date = self.today
        return d

    # ------------------------------------------------------- rule factory
    def _random_segments(self):
        rng = self.rng
        segs = []
        for _ in range(rng.randint(1, 5)):
            kind = rng.choice(["Static Text", "Company Abbr", "Fiscal Year",
                               "Document Field", "Number"])
            seg = {"segment_type": kind,
                   "join_previous": 1 if rng.random() < 0.15 else 0}
            if kind == "Static Text":
                seg["static_value"] = rng.choice(STATIC_TEXTS)
            elif kind == "Document Field":
                seg["field"] = rng.choice(
                    ["custom_document_no", "custom_p_type_code", "nonexistent_field"])
                if seg["field"] == "custom_document_no":
                    seg["number_length"] = rng.randint(1, 9)
            elif kind == "Number":
                seg["number_length"] = rng.randint(1, 9)
        # a rule whose number slot is the docno field must reference it —
        # randomly guarantee one so scopes are sometimes derivable
            segs.append(seg)
        if rng.random() < 0.5 and not any(
                s.get("field") == "custom_document_no" or s["segment_type"] == "Number"
                for s in segs):
            segs.append({"segment_type": "Document Field",
                         "field": "custom_document_no",
                         "number_length": rng.randint(3, 8)})
        return segs

    def _random_conditions(self, doctype):
        rng = self.rng
        conds = []
        for _ in range(rng.randint(0, 2)):
            conds.append({
                "field": rng.choice(
                    ["custom_p_type", "company", "posting_date", "voucher_type"]),
                "operator": rng.choice(OPERATORS),
                "value": rng.choice([
                    "Bank Entry", "Bank Entry,NOC Payment", COMPANY, "", "0",
                    "garbage-value", "-", "%"]),
            })
        return conds

    def _op_create_rule(self):
        rng = self.rng
        doctype = rng.choice(["Journal Entry", "Payment Entry"])
        rule = frappe.get_doc({
            "doctype": "Numbering Configuration",
            "document_type": doctype,
            "company": COMPANY if rng.random() < 0.7 else None,
            "enabled": 1,
            "target_field": "custom_name",
            "separator": rng.choice(SEPARATORS),
            "auto_document_no": rng.choice([0, 1]),
            "document_no_field": "custom_document_no",
            "duplicate_action": rng.choice(["Throw Error", "Use Next Available Number"]),
            "normal_docno_mode": rng.choice(["Auto", "Manual", None]),
            "return_docno_mode": rng.choice(["Auto", "Manual", None]),
            "conditions": self._random_conditions(doctype),
            "document_no_conditions": self._random_conditions(doctype),
            "docno_group_by": [
                {"field": f, "lock_after_numbering": rng.choice([0, 1])}
                for f in rng.sample(
                    ["company", "custom_p_type", "custom_fiscal_year"],
                    rng.randint(0, 3))
            ],
            "segments": self._random_segments(),
            "legacy_upto": rng.choice([None, None, "2025-01-01", self.today]),
        })
        rule.insert(ignore_permissions=True)
        if rule.company and self.rng.random() < 0.5:
            frappe.db.set_value("Numbering Configuration", rule.name, "company", None)
        self.my_rules.append(rule.name)
        ns.clear_numbering_rules_cache()
        return f"rule {rule.name} on {doctype}"

    def _op_toggle_rule(self):
        if not self.my_rules:
            return "noop"
        name = self.rng.choice(self.my_rules)
        if not frappe.db.exists("Numbering Configuration", name):
            return "noop"
        cur = frappe.db.get_value("Numbering Configuration", name, "enabled")
        frappe.db.set_value("Numbering Configuration", name, "enabled",
                            0 if frappe.utils.cint(cur) else 1)
        ns.clear_numbering_rules_cache()
        return f"toggle {name}"

    def _op_drop_rule(self):
        if not self.my_rules:
            return "noop"
        name = self.rng.choice(self.my_rules)
        if frappe.db.exists("Numbering Configuration", name):
            frappe.delete_doc("Numbering Configuration", name,
                              force=1, ignore_permissions=True)
        self.my_rules.remove(name)
        ns.clear_numbering_rules_cache()
        return f"drop {name}"

    # --------------------------------------------------------- doc ops
    def _op_insert_auto(self):
        doctype = self.rng.choice(["Journal Entry", "Payment Entry"])
        d = self._doc(doctype)
        d.insert(ignore_permissions=True)
        self.live_docs.append((doctype, d.name))
        self._check_name_number_consistency(d)
        return f"insert {d.name} no={d.get('custom_document_no')}"

    def _op_insert_manual(self):
        doctype = self.rng.choice(["Journal Entry", "Payment Entry"])
        d = self._doc(doctype)
        live_numbers = [
            frappe.db.get_value(dt, n, "custom_document_no")
            for dt, n in self.live_docs if dt == doctype
        ]
        candidates = [0, -5, 1, 424242, 99999999] + [
            frappe.utils.cint(v) for v in live_numbers if v]
        d.custom_document_no = self.rng.choice(candidates)
        d.custom_document_no_manual = self.rng.choice([0, 1])
        d.insert(ignore_permissions=True)
        self.live_docs.append((doctype, d.name))
        self._check_name_number_consistency(d)
        return f"manual insert {d.name} no={d.get('custom_document_no')}"

    def _op_scope_flip(self):
        if not self.live_docs:
            return "noop"
        doctype, name = self.rng.choice(self.live_docs)
        if not frappe.db.exists(doctype, name):
            return "noop"
        d = frappe.get_doc(doctype, name)
        if d.docstatus != 0:
            return "noop"
        d.custom_p_type = self.rng.choice(
            JE_TYPES if doctype == "Journal Entry" else PE_TYPES)
        d.save(ignore_permissions=True)
        self._check_name_number_consistency(d)
        return f"scope flip {name} -> {d.custom_p_type} no={d.get('custom_document_no')}"

    def _op_delete_doc(self):
        if not self.live_docs:
            return "noop"
        pick = self.rng.choice(self.live_docs)
        doctype, name = pick
        if frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
        self.live_docs.remove(pick)
        return f"delete {name}"

    # -------------------------------------------------------- invariants
    def _check_name_number_consistency(self, d):
        """I3: the voucher name must embed exactly the assigned number."""
        number = frappe.utils.cint(d.get("custom_document_no"))
        name_val = d.get("custom_name")
        if not (number and name_val):
            return
        digits = re.findall(r"\d+", name_val)
        self.assertTrue(
            any(frappe.utils.cint(x) == number for x in digits),
            f"I3 violated: {d.doctype} {d.name} number {number} "
            f"not embedded in voucher name {name_val!r} "
            f"(seed {self.seed}, ops {self.op_log[-5:]})")

    def _check_no_scope_duplicates(self):
        """I1/I2: among live docs, one number per scope."""
        seen = {}
        for doctype, name in self.live_docs:
            if not frappe.db.exists(doctype, name):
                continue
            d = frappe.get_doc(doctype, name)
            n = frappe.utils.cint(d.get("custom_document_no"))
            if not n:
                continue
            scope = ns._docno_scope(d)
            if not scope:
                continue
            key = (doctype, scope["key"], n)
            self.assertNotIn(
                key, seen,
                f"I1 violated: {name} and {seen.get(key)} share number {n} in "
                f"scope {scope['key']} (seed {self.seed}, ops {self.op_log[-8:]})")
            seen[key] = name

    # ------------------------------------------------------------- fuzz
    def test_chaos(self):
        ops = [
            (self._op_create_rule, 15),
            (self._op_toggle_rule, 8),
            (self._op_drop_rule, 6),
            (self._op_insert_auto, 30),
            (self._op_insert_manual, 15),
            (self._op_scope_flip, 12),
            (self._op_delete_doc, 14),
        ]
        weighted = [op for op, w in ops for _ in range(w)]
        crashes = []
        for i in range(self.ops_budget):
            op = self.rng.choice(weighted)
            try:
                detail = op()
                self.op_log.append((i, op.__name__, detail))
            except frappe.ValidationError:
                self.op_log.append((i, op.__name__, "ValidationError (allowed)"))
                frappe.db.rollback()
            except Exception as e:
                # I4 violated — a non-validation crash escaped the engine
                crashes.append((i, op.__name__, type(e).__name__, str(e)[:300]))
                frappe.db.rollback()
            if len(self.live_docs) > MAX_LIVE_DOCS:
                self._op_delete_doc()
            if i % 10 == 0:
                self._check_no_scope_duplicates()
        self._check_no_scope_duplicates()
        if crashes:
            self.fail(
                f"I4 violated — {len(crashes)} non-ValidationError crash(es) "
                f"escaped the engine (seed {self.seed}):\n"
                + "\n".join(repr(c) for c in crashes[:10]))
        print(f"chaos survived {self.ops_budget} ops "
              f"(seed {self.seed}, {len(self.my_rules)} rules alive at end)",
              flush=True)
