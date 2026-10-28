"""LC Shipment — one drawing under the LC: its documents, acceptance, settlement and customs proof.

Written only by lc/lifecycle.py (Add Shipment, Docs Received, Accept, Settle, Customs Proof)."""

from frappe.model.document import Document


class LCShipment(Document):
	pass
