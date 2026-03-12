import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import PurchaseOrder as ERPNextPurchaseOrder


class PurchaseOrder(ERPNextPurchaseOrder):
    def validate_workflow(self):
        workflow = self.meta.get_workflow()
        if isinstance(workflow, str):
            workflow = frappe.get_cached_doc("Workflow", workflow)
        if workflow and workflow.name == "Purchase Order Workflow":
            if frappe.session.user == "Administrator":
                return
        super().validate_workflow()
