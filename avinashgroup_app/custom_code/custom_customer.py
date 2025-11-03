from erpnext.selling.doctype.customer.customer import Customer

class CustomCustomer(Customer):
    def autoname(self):
        self.name = f"{self.custom_abbr}.{self.customer_name}" 
