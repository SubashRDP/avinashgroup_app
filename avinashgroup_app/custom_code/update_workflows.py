import frappe
from avinashgroup_app.custom_code.dynamic_approval import setup_workflow

def run():
    settings = frappe.get_all("Dynamic Approval Setting", pluck="name")
    if not settings:
        print("No Dynamic Approval Settings found.")
        return
    for name in settings:
        print(f"Updating workflow for {name}...")
        setup_workflow(name)
    print("All configured workflows updated with latest fields.")
