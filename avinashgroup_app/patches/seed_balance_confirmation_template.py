# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe

TEMPLATE_NAME = "Balance Confirmation Letter"

INTRO = """
<p style="text-align:right">Date: {{ today }}</p>
<p>To,<br><b>{{ data.party_name }}</b></p>
<p><b>Sub: Transaction &amp; Accounts Balance Confirmation</b></p>
<p>Dear Sir/Ma'am,</p>
<p>With reference to the above subject, as part of our annual audit procedure, we are
sending you the following information regarding sales, purchase and balance of accounts
for the period {{ data.from_date }} to {{ data.to_date }} for your confirmation.</p>
"""

FIELD_TABLE = [
	{"label": "Opening Balance", "value_expr": "fmt(data.opening_balance)"},
	{"label": "Sales / Purchase (Excl. VAT)", "value_expr": "fmt(data.period_debit)"},
	{"label": "VAT Amount", "value_expr": "fmt(data.vat_amount)"},
	{"label": "Closing Balance at Fiscal Year-End", "value_expr": "fmt(data.closing_balance)"},
]

CONFIRM = """
<p style="margin-top:14px">Please add your confirmation or send us the received copy with
sign &amp; official stamp within 7 days of its receipt. Failing to which the details
provided by us will be treated as final confirmation by you.</p>
<p>Thank you for your cooperation.</p>
"""

SIGNATURE = """
<table style="width:100%;margin-top:30px"><tr>
<td style="width:50%">______________________<br>Account Department<br>For {{ company }}</td>
<td style="width:50%;text-align:right">______________________<br>Confirmed by</td>
</tr></table>
"""


def execute():
	"""Seed a ready-to-use Balance Confirmation Letter template (idempotent)."""
	if frappe.db.exists("Document Template", TEMPLATE_NAME):
		return

	company = frappe.defaults.get_global_default("company") or frappe.db.get_value(
		"Company", {}, "name"
	)
	if not company:
		return

	doc = frappe.new_doc("Document Template")
	doc.template_name = TEMPLATE_NAME
	doc.target_doctype = "Customer"
	doc.data_provider = "Party Balance Confirmation"
	doc.party_type = "Customer"
	doc.append("companies", {"company": company})
	doc.print_orientation = "Portrait"
	doc.default_recipient_field = "email_id"
	doc.email_subject = "Balance Confirmation - {{ company }}"
	doc.is_active = 1

	doc.append("sections", {"section_title": "Letter Head", "section_type": "Letter Head", "is_mandatory": 1})
	doc.append("sections", {"section_title": "Introduction", "section_type": "Rich Text", "content": INTRO})
	doc.append(
		"sections",
		{"section_title": "Balance Summary", "section_type": "Field Table", "config_json": frappe.as_json(FIELD_TABLE)},
	)
	doc.append("sections", {"section_title": "Confirmation", "section_type": "Rich Text", "content": CONFIRM})
	doc.append("sections", {"section_title": "Signatures", "section_type": "Signature Block", "content": SIGNATURE, "is_mandatory": 1})

	doc.insert(ignore_permissions=True)
	frappe.db.commit()
