"""Regression: the NGK voucher numbering format sheet (FACT -> ERPNext mapping).

Locks in, for Nepal Gas Udhyog (Karnali) Pvt. Ltd. (abbr NGK), the numbering
behaviour documented in the migration format sheet:

  Transaction        Type master              Auto types                Manual types
  Purchase Receipt   Receipt type             PR                        PC
  Purchase Invoice   Purchase Type            RTN                       PBO FAP PB ICP NA CYL
  Payment Entry      Payment - Receipt Type   RC NOC T                  (blank) RF VP
  Journal Entry      JV Type                  BJV PJ DN CN              PTY CV JV CF CS
  Sales Invoice      (naming series)          SB / SRTN (returns)       -

  FACT voucher name (custom_name):  NGK-<code>-<6-digit no.>-<FY>
  ERPNext ID (doc.name):            NGK-<prefix>-<FY>-<5-digit seq>

Two tests:
  test_01_number_is_right_for_every_voucher_type
      Every type row: the code resolves, Auto/Manual matches the sheet, Auto
      rows draw exactly the peeked next number, and the FACT voucher name is
      formatted right.
  test_02_each_doctype_saves_one_correct_document
      One REAL document per transaction doctype is inserted; its saved
      ERPNext ID, FACT voucher name and document number must all be correct.
      Everything the test creates is deleted and every counter it moved is
      restored, so the suite is non-polluting and re-runnable.

Run with:
  bench --site avinas1 run-tests --app avinashgroup_app \
      --module avinashgroup_app.test_ngk_numbering_format
"""

import json
import re
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from avinashgroup_app.custom_code.Override import naming_series as ns

COMPANY = "Nepal Gas Udhyog (Karnali) Pvt. Ltd."
ABBR = "NGK"
QUARANTINE_MARKER = "ngk_format_test_quarantine"

# One row per voucher type in the format sheet:
# (doctype, type_field, type master record, FACT code, auto-numbered?)
SPEC = [
    ("Purchase Receipt", "custom_receipt_type", "Gas Purchase Receipt",         "PC",  False),
    ("Purchase Receipt", "custom_receipt_type", "Other Purchase Receipt",       "PR",  True),
    ("Purchase Invoice", "custom_purchase_type", "Purchase Other Service/Goods", "PBO", False),
    ("Purchase Invoice", "custom_purchase_type", "Fixed Assets Purchase",        "FAP", False),
    ("Purchase Invoice", "custom_purchase_type", "Gas Purchase Invoice",         "PB",  False),
    ("Purchase Invoice", "custom_purchase_type", "Service Charge ICP",           "ICP", False),
    ("Purchase Invoice", "custom_purchase_type", "Service Charge NA",            "NA",  False),
    ("Purchase Invoice", "custom_purchase_type", "Purchase Cylinder",            "CYL", False),
    ("Purchase Invoice", "custom_purchase_type", "Purchase Return",              "RTN", True),
    ("Payment Entry",    "custom_p_type", "Customers/Suppliers Receipt",  None,  False),
    ("Payment Entry",    "custom_p_type", "Bank Customers Receipt",       "RC",  True),
    ("Payment Entry",    "custom_p_type", "Cylinder Deposit Slip",        "RF",  False),
    ("Payment Entry",    "custom_p_type", "Vendor Payment",               "VP",  False),
    ("Payment Entry",    "custom_p_type", "NOC Payment",                  "NOC", True),
    ("Payment Entry",    "custom_p_type", "Contra Voucher- cash to bank", "T",   True),
    ("Journal Entry",    "custom_p_type", "Bank Entry",                   "BJV", True),
    ("Journal Entry",    "custom_p_type", "Cash Entry",                   "PTY", False),
    ("Journal Entry",    "custom_p_type", "Cash/ Bank or Contra Voucher", "CV",  False),
    ("Journal Entry",    "custom_p_type", "Journal Entry",                "JV",  False),
    ("Journal Entry",    "custom_p_type", "Contract Form",                "CF",  False),
    ("Journal Entry",    "custom_p_type", "Opening Entry",                "CS",  False),
    ("Journal Entry",    "custom_p_type", "Party Journal",                "PJ",  True),
    ("Journal Entry",    "custom_p_type", "Debit Note",                   "DN",  True),
    ("Journal Entry",    "custom_p_type", "Credit Note",                  "CN",  True),
]

# ERPNext ID prefixes per doctype (make_autoname drops the '.' in PAY.REC)
ID_PREFIX = {
    "Journal Entry": "JE",
    "Payment Entry": "PAYREC",
    "Purchase Invoice": "PI",
    "Purchase Receipt": "GRN",
    "Sales Invoice": "SB",
}


class TestNGKNumberingFormat(FrappeTestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Company", COMPANY):
            raise unittest.SkipTest(f"company {COMPANY!r} not on this site")
        cls.today = frappe.utils.today()
        cls.fy = ns.get_fiscal_year_from_date(cls.today)
        if not cls.fy:
            raise unittest.SkipTest("no fiscal year covers today")
        cls.company_doc = frappe.get_doc("Company", COMPANY)

    def setUp(self):
        # Counter hygiene: apply_document_no / autoname draws COMMIT (hooks
        # commit mid-save), so snapshot every counter this suite can move and
        # restore it afterwards — deleted docs free their names, so winding
        # the counters back cannot reissue a used number.
        rows = frappe.db.sql(
            "SELECT `name`, `current` FROM `tabSeries` "
            "WHERE `name` LIKE %s OR `name` LIKE %s",
            ("docno:%", ABBR + "-%"),
        )
        self._series_snapshot = {n: c for n, c in rows}
        self.addCleanup(self._restore_series)
        # Site-configured Numbering Configuration rules are authoritative and
        # would change outcomes — quarantine them for the duration (persisted
        # marker heals a killed run on the next pass).
        leftover = frappe.db.get_global(QUARANTINE_MARKER)
        if leftover:
            self._enable_rules([n for n in json.loads(leftover)
                                if frappe.db.exists("Numbering Configuration", n)])
        self._live_rules = frappe.get_all(
            "Numbering Configuration", filters={"enabled": 1}, pluck="name")
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
            self._enable_rules(self._live_rules)
        frappe.db.set_global(QUARANTINE_MARKER, None)
        frappe.db.commit()

    @staticmethod
    def _enable_rules(names):
        if names:
            frappe.db.sql(
                "UPDATE `tabNumbering Configuration` SET enabled=1 WHERE name IN %s",
                (tuple(names),),
            )
            frappe.db.commit()
            ns.clear_numbering_rules_cache()

    def _restore_series(self):
        rows = frappe.db.sql(
            "SELECT `name`, `current` FROM `tabSeries` "
            "WHERE `name` LIKE %s OR `name` LIKE %s",
            ("docno:%", ABBR + "-%"),
        )
        for name, cur in rows:
            snap = self._series_snapshot.get(name)
            if snap is None:
                frappe.db.sql("DELETE FROM `tabSeries` WHERE `name`=%s", name)
            elif snap != cur:
                frappe.db.sql("UPDATE `tabSeries` SET `current`=%s WHERE `name`=%s",
                              (snap, name))
        frappe.db.commit()

    # ------------------------------------------------------------- helpers
    def _doc(self, doctype, type_field, type_name):
        d = frappe.new_doc(doctype)
        d.company = COMPANY
        d.posting_date = self.today
        d.set(type_field, type_name)
        if doctype == "Journal Entry":
            d.voucher_type = "Journal Entry"
        elif doctype == "Payment Entry":
            d.payment_type = "Receive"
        return d

    def _fact_name(self, code, number):
        return f"{ABBR}-{code}-{str(number).zfill(6)}-{self.fy}"

    def _force_delete(self, doctype, name):
        if name and frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
        frappe.db.commit()

    def _insert(self, doc):
        doc.insert(ignore_permissions=True)
        self.addCleanup(self._force_delete, doc.doctype, doc.name)
        return doc

    def _account(self, **filters):
        filters.update({"company": COMPANY, "is_group": 0, "disabled": 0})
        name = frappe.db.get_value("Account", filters, "name")
        self.assertTrue(name, f"no account for {filters} on {COMPANY}")
        return name

    # ------------------------------------------------------ test 1: numbers
    def test_01_number_is_right_for_every_voucher_type(self):
        """Every voucher type in the sheet: code, Auto/Manual mode, drawn
        number and FACT voucher name are all right."""
        for doctype, type_field, type_name, code, auto in SPEC:
            with self.subTest(voucher=f"{doctype}/{type_name}"):
                self.assertTrue(
                    frappe.db.exists(frappe.get_meta(doctype).get_field(type_field).options,
                                     type_name),
                    f"type master {type_name!r} missing")
                d = self._doc(doctype, type_field, type_name)

                # the sheet's code column
                self.assertEqual(ns._resolve_p_type_code(d), code)
                # the sheet's Auto/Manual column
                self.assertEqual(bool(ns._docno_eligible(d, ns._match_numbering_rule(d))),
                                 auto)

                if auto:
                    expected = ns.peek_next_document_no(d)
                    self.assertIsNotNone(expected)
                    self.assertGreaterEqual(expected, 1)
                    ns.apply_document_no(d)
                    self.assertEqual(d.custom_document_no, expected,
                                     "assigned number must equal the peeked next number")
                    ns.set_custom_name_field(d)
                    self.assertEqual(d.custom_name, self._fact_name(code, expected))
                else:
                    ns.apply_document_no(d)
                    self.assertFalse(d.get("custom_document_no"),
                                     "manual types must not be auto-numbered")
                    if code:  # blank-code types carry no FACT voucher name spec
                        d.custom_document_no = 424242
                        d.custom_document_no_manual = 1
                        # the code lands on the doc via the field's fetch_from
                        # during a real save; set it the same way here
                        d.custom_p_type_code = ns._resolve_p_type_code(d)
                        ns.set_custom_name_field(d)
                        self.assertEqual(d.custom_name, self._fact_name(code, 424242))

    # ---------------------------------------------- test 2: one real doc each
    def test_02_each_doctype_saves_one_correct_document(self):
        """Insert one real document per transaction doctype and verify the
        saved ERPNext ID, FACT voucher name and document number."""
        made = {}

        # Journal Entry — Bank Entry (auto, BJV)
        accounts = frappe.get_all(
            "Account", filters={"company": COMPANY, "is_group": 0, "disabled": 0},
            pluck="name", limit=2)
        self.assertGreaterEqual(len(accounts), 2, "needs two NGK accounts")
        je = self._doc("Journal Entry", "custom_p_type", "Bank Entry")
        je.append("accounts", {"account": accounts[0],
                               "debit_in_account_currency": 100, "debit": 100})
        je.append("accounts", {"account": accounts[1],
                               "credit_in_account_currency": 100, "credit": 100})
        je_next = ns.peek_next_document_no(je)
        made["Journal Entry"] = (self._insert(je), "BJV", je_next)

        # Payment Entry — NOC Payment (auto, NOC)
        customer = frappe.db.get_value(
            "Customer", {"disabled": 0, "custom_company": COMPANY}, "name")
        self.assertTrue(customer, "needs a customer")
        receivable = (self.company_doc.default_receivable_account
                      or self._account(account_type="Receivable"))
        bank = self._account(account_type="Bank")
        pe = self._doc("Payment Entry", "custom_p_type", "NOC Payment")
        pe.update({
            "party_type": "Customer", "party": customer,
            "paid_from": receivable, "paid_to": bank,
            "paid_amount": 100, "received_amount": 100,
            "source_exchange_rate": 1, "target_exchange_rate": 1,
            "reference_no": "NGK-FMT-TEST", "reference_date": self.today,
        })
        pe_next = ns.peek_next_document_no(pe)
        made["Payment Entry"] = (self._insert(pe), "NOC", pe_next)

        # Purchase Invoice — Purchase Other Service/Goods (manual, PBO)
        supplier = frappe.db.get_value(
            "Supplier", {"disabled": 0, "custom_company": COMPANY}, "name")
        service_item = frappe.db.get_value(
            "Item", {"disabled": 0, "is_stock_item": 0, "has_variants": 0,
                     "custom_company": COMPANY}, "name")
        self.assertTrue(supplier and service_item, "needs a supplier and a service item")
        expense = (self.company_doc.default_expense_account
                   or self._account(root_type="Expense"))
        pi = self._doc("Purchase Invoice", "custom_purchase_type",
                       "Purchase Other Service/Goods")
        pi.update({"supplier": supplier, "due_date": self.today,
                   "credit_to": self.company_doc.default_payable_account
                                or self._account(account_type="Payable")})
        pi.append("items", {"item_code": service_item, "qty": 1, "rate": 100,
                            "expense_account": expense, "cost_center":
                            self.company_doc.cost_center})
        pi_manual = 424243
        pi.custom_document_no = pi_manual
        pi.custom_document_no_manual = 1
        made["Purchase Invoice"] = (self._insert(pi), "PBO", pi_manual)

        # Purchase Receipt — Other Purchase Receipt (auto, PR)
        stock_item = frappe.db.get_value(
            "Item", {"disabled": 0, "is_stock_item": 1, "has_variants": 0,
                     "has_batch_no": 0, "has_serial_no": 0,
                     "custom_company": COMPANY}, "name")
        warehouse = frappe.db.get_value(
            "Warehouse", {"company": COMPANY, "is_group": 0, "disabled": 0}, "name")
        self.assertTrue(stock_item and warehouse, "needs a stock item and NGK warehouse")
        pr = self._doc("Purchase Receipt", "custom_receipt_type",
                       "Other Purchase Receipt")
        pr.supplier = supplier
        pr.append("items", {"item_code": stock_item, "qty": 1, "rate": 100,
                            "warehouse": warehouse, "cost_center":
                            self.company_doc.cost_center})
        pr_next = ns.peek_next_document_no(pr)
        made["Purchase Receipt"] = (self._insert(pr), "PR", pr_next)

        # Sales Invoice — plain sale (naming-series SB; no custom_name field)
        price_list = frappe.db.get_value(
            "Price List", {"enabled": 1, "selling": 1, "custom_company": COMPANY},
            "name")
        si = frappe.new_doc("Sales Invoice")
        si.update({"company": COMPANY, "posting_date": self.today,
                   "set_posting_time": 1, "customer": customer,
                   "due_date": self.today,
                   "selling_price_list": price_list,
                   "debit_to": receivable})
        si.append("items", {"item_code": service_item, "qty": 1, "rate": 100,
                            "income_account": self.company_doc.default_income_account
                                              or self._account(root_type="Income"),
                            "cost_center": self.company_doc.cost_center})
        made["Sales Invoice"] = (self._insert(si), None, None)

        # ---- every doctype produced exactly one correct document ----
        for doctype, (doc, code, number) in made.items():
            with self.subTest(doctype=doctype):
                doc.reload()  # what the DB really holds, post-hooks
                self.assertEqual(doc.docstatus, 0)
                self.assertEqual(doc.company, COMPANY)
                # ERPNext ID: NGK-<prefix>-<FY>-<5 digits>
                fy = re.escape(self.fy)
                self.assertRegex(
                    doc.name, rf"^{ABBR}-{ID_PREFIX[doctype]}-{fy}-\d{{5}}$")
                if code:
                    # document number: exactly the peeked / typed number
                    # (cint: Purchase Receipt stores it in a Data column)
                    self.assertEqual(frappe.utils.cint(doc.custom_document_no), number)
                    # FACT voucher name: NGK-<code>-<6-digit no.>-<FY>
                    self.assertEqual(doc.custom_name, self._fact_name(code, number))
