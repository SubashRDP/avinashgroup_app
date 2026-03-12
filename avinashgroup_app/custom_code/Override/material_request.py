import frappe
from erpnext.stock.doctype.material_request.material_request import MaterialRequest as ERPNextMaterialRequest


class MaterialRequest(ERPNextMaterialRequest):
    def validate_workflow(self):
        workflow = self.meta.get_workflow()
        if isinstance(workflow, str):
            workflow = frappe.get_cached_doc("Workflow", workflow)
        if workflow and workflow.name == "Material Request One-Line Approver":
            if frappe.session.user == "Administrator":
                return
        super().validate_workflow()
