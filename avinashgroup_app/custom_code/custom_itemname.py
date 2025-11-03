from erpnext.stock.doctype.item.item import Item
import frappe
from frappe import _

class CustomItem(Item):
    def autoname(self):
        if not self.custom_abbr:
            frappe.throw(_("Custom Abbreviation is mandatory"))
        self.name = f"{self.custom_abbr}.{self.item_code}"
