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


def _lenient_warehouse_check(doc, validate):
	"""Drafts may be saved without a warehouse (it gets filled from the source
	document or by the user later), but submission must enforce it — otherwise
	stock documents submit with no warehouse and no Stock Ledger Entry."""
	if doc.docstatus.is_draft():
		try:
			validate()
		except frappe.ValidationError:
			pass
	else:
		validate()


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
		_lenient_warehouse_check(self, super().validate_warehouse)


class DeliveryNote(ERPNextDeliveryNote):
	def set_missing_values(self, for_validate=False):
		super().set_missing_values(for_validate)
		if not for_validate:
			_restore_warehouse(self, "so_detail", "Sales Order Item")

	def validate_warehouse(self):
		_lenient_warehouse_check(self, super().validate_warehouse)


class CustomSalesInvoice(ERPNextSalesInvoice):
	def before_submit(self):
		# Frappe never runs before_save on a submit pass (they are mutually
		# exclusive branches of run_before_save_methods), so core's paid-amount
		# logic does not see edits made in the same action that submits. Re-run
		# it here — both methods recompute from the payments child table, so
		# this is a no-op when nothing changed — and refresh the audit modifier
		# stamp so the submitting user is recorded even when they didn't author
		# the draft.
		#
		# NOTE: this is no longer a compensation for the desk save-and-submit.
		# That path saves a draft first and then submits (save_and_submit.py),
		# so core's before_save DOES run on desk-created invoices.
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
		_lenient_warehouse_check(self, super().validate_warehouse)

	def validate_zero_qty_for_return_invoices_with_stock(self):
		"""Let the zero-qty setting reach stock-affecting returns too.

		Core skips validate_qty_is_not_zero entirely for returns (is_return is
		checked before the call in accounts_controller.validate), so a credit
		note has always accepted qty=0 — except when update_stock is on, where
		this separate method throws instead. Unlike validate_qty_is_not_zero it
		reads no flag, so "Allow Sales Invoice with Zero Quantity" could not
		reach it. Honour the same flag here.

		No stock consequence: selling_controller.update_stock_ledger skips rows
		where flt(d.qty) is falsy, so a zero-qty row makes no Stock Ledger Entry
		whether or not update_stock is set — it carries neither movement nor
		value. This only removes the block, it does not change what is posted.

		The flag is set on before_validate by
		salesinvoice_taxes.allow_zero_qty_rows, which runs before validate().
		"""
		if self.flags.allow_zero_qty:
			return

		super().validate_zero_qty_for_return_invoices_with_stock()


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
		_lenient_warehouse_check(self, super().validate_warehouse)


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
		_lenient_warehouse_check(self, lambda: super(PurchaseInvoice, self).validate_warehouse(for_validate=for_validate))


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
