import frappe

GAS_PURCHASE_TYPE = "Gas Purchase Invoice"

# Transportation Details fields copied into remarks, in the order they appear on
# the form. IOC Challan Date and Store Receipt Date are deliberately left out, and
# so is Voucher Receipt No. because that field is hidden on the form.
TRANSPORT_FIELDS = [
	("custom_pdo_no", "PDO No"),
	("custom_refinery", "Refinery"),
	("custom_vehicle_no", "Vehicle No"),
	("custom_ioc_challan_no", "IOC Challan No"),
	("custom_ico_challan_miti", "IOC Challan Miti"),
	("custom_store_receipt_no", "Store Receipt No"),
	("custom_store_receipt_miti", "Store Receipt Miti"),
	("custom_name_of_transportor", "Name of Transportor"),
]


def set_transport_remarks(doc, method=None):
	"""Rebuild the Transportation Details line at the top of remarks.

	The line reads "PDO No: 991, Refinery: Barauni, ...". It is rebuilt on every
	save so it always matches the current field values. Lines the user typed
	themselves are kept below it.
	"""
	kept_lines = _strip_transport_line(doc.remarks)

	if doc.custom_purchase_type != GAS_PURCHASE_TYPE:
		doc.remarks = "\n".join(kept_lines)
		return

	parts = []
	for fieldname, label in TRANSPORT_FIELDS:
		value = doc.get(fieldname)
		if value:
			parts.append(f"{label}: {value}")

	if not parts:
		doc.remarks = "\n".join(kept_lines)
		return

	# ERPNext fills this in when remarks is empty; it adds nothing here.
	kept_lines = [line for line in kept_lines if line.strip() != "No Remarks"]

	doc.remarks = "\n".join([", ".join(parts)] + kept_lines)


def _strip_transport_line(remarks):
	"""Drop the line this function generated on an earlier save.

	That line always starts with one of the transport labels, since the fields
	are emitted in a fixed order and empty ones are skipped.
	"""
	if not remarks:
		return []

	prefixes = tuple(f"{label}: " for _, label in TRANSPORT_FIELDS)
	kept = [line for line in remarks.splitlines() if not line.startswith(prefixes)]

	# Leading blank lines left behind by the removed line
	while kept and not kept[0].strip():
		kept.pop(0)

	return kept
