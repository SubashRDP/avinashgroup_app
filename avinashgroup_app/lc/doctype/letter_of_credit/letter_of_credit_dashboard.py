"""Connections on the Letter of Credit form: the entries and vouchers that carry its link."""

from frappe import _


def get_data():
	return {
		"fieldname": "letter_of_credit",
		"transactions": [
			{"label": _("Accounting"), "items": ["Journal Entry"]},
			{"label": _("Landed Cost"), "items": ["Landed Cost Voucher"]},
		],
	}
