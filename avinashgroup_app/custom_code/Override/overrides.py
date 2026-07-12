import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice as ERPNextSalesInvoice
from erpnext.stock.doctype.delivery_note.delivery_note import DeliveryNote as ERPNextDeliveryNote
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice as ERPNextPurchaseInvoice
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt as ERPNextPurchaseReceipt
from erpnext.buying.doctype.request_for_quotation.request_for_quotation import RequestforQuotation as ERPNextRequestforQuotation
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder as ERPNextSalesOrder
from erpnext.buying.doctype.supplier_quotation.supplier_quotation import SupplierQuotation as ERPNextSupplierQuotation
from erpnext.stock.doctype.material_request.material_request import MaterialRequest as ERPNextMaterialRequest
from erpnext.buying.doctype.purchase_order.purchase_order import PurchaseOrder as ERPNextPurchaseOrder


def _restore_warehouse(doc, link_field, source_doctype):
	"""Restore warehouse from source document item.
	Only runs during document creation (for_validate=False) so that
	user-edited warehouses on subsequent saves are never overwritten."""
	for item in doc.get("items"):
		source_name = item.get(link_field)
		if source_name:
			source_warehouse = frappe.db.get_value(source_doctype, source_name, "warehouse")
			item.warehouse = source_warehouse or ""


# ─── Selling Hierarchy ────────────────────────────────────────────────────────

class SalesOrder(ERPNextSalesOrder):
	def set_missing_values(self, for_validate=False):
		super().set_missing_values(for_validate)
		if not for_validate:
			_restore_warehouse(self, "quotation_item", "Quotation Item")

	def validate_warehouse(self):
		try:
			super().validate_warehouse()
		except Exception:
			pass


class DeliveryNote(ERPNextDeliveryNote):
	def set_missing_values(self, for_validate=False):
		super().set_missing_values(for_validate)
		if not for_validate:
			_restore_warehouse(self, "so_detail", "Sales Order Item")

	def validate_warehouse(self):
		try:
			super().validate_warehouse()
		except Exception:
			pass


class CustomSalesInvoice(ERPNextSalesInvoice):
	def before_submit(self):
		# The desk's atomic save-and-submit (save_and_submit.py) makes Frappe run
		# before_submit INSTEAD of before_save, so core before_save logic would be
		# silently skipped on desk-created invoices. Re-run it here — both methods
		# recompute from the payments child table, so a second run on the normal
		# two-step path is a no-op — and refresh the audit modifier stamp so the
		# submitting user is recorded even when they didn't author the draft.
		self.set_account_for_mode_of_payment()
		self.set_paid_amount()
		from avinashgroup_app.utils.audit_file_manager import set_audit_fields
		set_audit_fields(self)
		super().before_submit()

	def set_missing_values(self, for_validate=False):
		super().set_missing_values(for_validate)
		if not for_validate:
			for item in self.get("items"):
				if item.get("dn_detail"):
					source_warehouse = frappe.db.get_value("Delivery Note Item", item.dn_detail, "warehouse")
					item.warehouse = source_warehouse or ""
				elif item.get("so_detail"):
					source_warehouse = frappe.db.get_value("Sales Order Item", item.so_detail, "warehouse")
					item.warehouse = source_warehouse or ""

	def validate_warehouse(self):
		try:
			super().validate_warehouse()
		except Exception:
			pass


# ─── Buying Hierarchy ─────────────────────────────────────────────────────────

class RequestforQuotation(ERPNextRequestforQuotation):
	def set_missing_values(self, for_validate=False):
		super().set_missing_values(for_validate)
		if not for_validate:
			_restore_warehouse(self, "material_request_item", "Material Request Item")

	def validate(self):
		try:
			super().validate()
		except frappe.ValidationError as e:
			if "Warehouse is mandatory for stock Item" in str(e):
				pass
			else:
				raise


class SupplierQuotation(ERPNextSupplierQuotation):
	def set_missing_values(self, for_validate=False):
		super().set_missing_values(for_validate)
		if not for_validate:
			_restore_warehouse(self, "request_for_quotation_item", "Request for Quotation Item")

	def validate(self):
		try:
			super().validate()
		except frappe.ValidationError as e:
			if "Warehouse is mandatory for stock Item" in str(e):
				pass
			else:
				raise


class PurchaseOrder(ERPNextPurchaseOrder):
	def set_missing_values(self, for_validate=False):
		super().set_missing_values(for_validate)
		if not for_validate:
			_restore_warehouse(self, "supplier_quotation_item", "Supplier Quotation Item")

	def validate_workflow(self):
		workflow = self.meta.get_workflow()
		if workflow and isinstance(workflow, str):
			workflow = frappe.get_cached_doc("Workflow", workflow)
		if workflow and workflow.name == "Purchase Order Workflow":
			if frappe.session.user == "Administrator":
				return
		super().validate_workflow()

	def validate(self):
		try:
			super().validate()
		except frappe.ValidationError as e:
			if "Warehouse is mandatory for stock Item" in str(e):
				pass
			else:
				raise


class PurchaseReceipt(ERPNextPurchaseReceipt):
	def set_missing_values(self, for_validate=False):
		super().set_missing_values(for_validate)
		if not for_validate:
			_restore_warehouse(self, "purchase_order_item", "Purchase Order Item")

	def validate_warehouse(self):
		try:
			super().validate_warehouse()
		except Exception:
			pass


class PurchaseInvoice(ERPNextPurchaseInvoice):
	def set_missing_values(self, for_validate=False):
		super().set_missing_values(for_validate)
		if not for_validate:
			for item in self.get("items"):
				if item.get("pr_detail"):
					source_warehouse = frappe.db.get_value("Purchase Receipt Item", item.pr_detail, "warehouse")
					item.warehouse = source_warehouse or ""
				elif item.get("po_detail"):
					source_warehouse = frappe.db.get_value("Purchase Order Item", item.po_detail, "warehouse")
					item.warehouse = source_warehouse or ""

	def validate_warehouse(self, for_validate=True):
		try:
			super().validate_warehouse(for_validate=for_validate)
		except Exception:
			pass


# ─── Other Overrides ──────────────────────────────────────────────────────────

class MaterialRequest(ERPNextMaterialRequest):
	def validate_workflow(self):
		workflow = self.meta.get_workflow()
		if workflow and isinstance(workflow, str):
			workflow = frappe.get_cached_doc("Workflow", workflow)
		if workflow and workflow.name == "Material Request One-Line Approver":
			if frappe.session.user == "Administrator":
				return
		super().validate_workflow()

	def validate(self):
		try:
			super().validate()
		except frappe.ValidationError as e:
			if "Warehouse is mandatory for stock Item" in str(e):
				pass
			else:
				raise
