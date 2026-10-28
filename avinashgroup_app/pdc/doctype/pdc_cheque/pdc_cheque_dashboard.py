from frappe import _


def get_data():
	"""Connections on a PDC Cheque: every entry it posted, and the Payment Entries tied to it."""
	return {
		"fieldname": "pdc_cheque",
		"non_standard_fieldnames": {"Payment Entry": "pdc_cheque"},
		"transactions": [
			{"label": _("Accounting"), "items": ["Journal Entry", "Payment Entry"]},
		],
	}
