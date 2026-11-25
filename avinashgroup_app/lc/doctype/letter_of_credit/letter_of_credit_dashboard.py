"""Connections on the Letter of Credit form: the entries and documents that carry its link."""

from frappe import _


def get_data():
	return {
		"fieldname": "letter_of_credit",
		"transactions": [
			{"label": _("Accounting"), "items": ["Journal Entry"]},
			{"label": _("Goods"), "items": ["Stock Entry", "Asset"]},
		],
	}
