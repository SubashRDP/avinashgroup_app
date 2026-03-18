$(document).on('app_ready', function() {
    // doctypes that have company field and need supplier/customer/item filtering
    const relevantDocTypes = [
        "Sales Invoice", 
        "Sales Order", 
        "Delivery Note",
        "Purchase Invoice", 
        "Purchase Order", 
        "Purchase Receipt",
        "Payment Entry",
        "Journal Entry",
        "Quotation",
        "Supplier Quotation",
        "Material Request",
        "Stock Entry",
       
    ];
    $.each(relevantDocTypes, function(i, doctype) {
        frappe.ui.form.on(doctype, {
            company: function(frm) {
                setupCompanyBasedFilters(frm);
                
                // Clear supplier/customer if they don't match new company
                validateAndClearFields(frm);
            },  
            party_type: function(frm) {
                setupCompanyBasedFilters(frm);
                validateAndClearFields(frm);
            },
            supplier: function(frm){
                  validateAndClearFields(frm);
            },
            customer: function(frm){
                    validateAndClearFields(frm);
                },
            employee: function(frm){
                    validateAndClearFields(frm);
                }
        });
    });
});

function setupCompanyBasedFilters(frm) {
    if (!frm.fields_dict.company) {
        return;
    }
    let company = frm.doc.company;    
    if (frm.fields_dict.supplier) {
        frm.set_query('supplier', function() {
            if (company) {
                return {
                    filters: {
                        'custom_company': company,
                        'disabled': 0 
                    }
                };
            }
            return {
                filters: {
                    'disabled': 0
                }
            };
        });
    }
    if (frm.fields_dict.customer) {
        frm.set_query('customer', function() {
            if (company) {
                return {
                    filters: {
                        'custom_company': company,
                        'disabled': 0  // Only show active customers
                    }
                };
            }
            return {
                filters: {
                    'disabled': 0
                }
            };
        });
    }
    if (frm.fields_dict.employee) {
        frm.set_query('employee', function() {
            if (company) {
                return {
                    filters: {
                        'custom_company': company,
                        'disabled': 0  // Only show active customers
                    }
                };
            }
            return {
                filters: {
                    'disabled': 0
                }
            };
        });
    }

    if (frm.doctype === "Payment Entry" && frm.fields_dict.party) {
        frm.set_query('party', function() {
            const party_type = frm.doc.party_type;
            if (!company || !party_type) {
                return {};
            }
            return {
                query: "avinashgroup_app.custom_code.globalfilter.globalfilter.search_party",
                filters: {
                    party_type: party_type,
                    company: company
                }
            };
        });
    }
    
    if (frm.fields_dict.custom_suppliers) {
        frm.set_query('custom_suppliers', function() {
            if (company) {
                return {
                    filters: {
                        'custom_company': company,
                        'disabled': 0
                    }
                };
            }
            return {};
        });
    }

    if (frm.fields_dict.customer_name) {
        frm.set_query('customer_name', function() {
            if (company) {
                return {
                    filters: {
                        'custom_company': company,
                        'disabled': 0
                    }
                };
            }
            return {};
        });
    }
    setupItemCodeFilter(frm, company);
}
function setupItemCodeFilter(frm, company) {
    if(frm.fields_dict.items) {
        frm.set_query('item_code', 'items', function() {
            if (company) {
                return {
                    filters: {
                        'custom_company': company,
                        'disabled': 0
                    }
                };
            }
            return {
                filters: {
                    'disabled': 0
                }
            };
        });
    }
}
function validateAndClearFields(frm) {
    let company = frm.doc.company;
    
    if (!company) {
        return;
    }
    
    if (frm.doc.supplier) {
        frappe.db.get_value('Supplier', frm.doc.supplier, 'custom_company', function(r) {
            if (r && r.custom_company && r.custom_company !== company) {
                frappe.msgprint({
                    title: __('Company Mismatch'),
                    message: __('Supplier {0} does not belong to company {1}. Clearing supplier field.', 
                        [frm.doc.supplier, company]),
                    indicator: 'orange'
                });
                frm.set_value('supplier', '');
            }
        });
    }
    
    // Validate and clear customer
    if (frm.doc.customer) {
        frappe.db.get_value('Customer', frm.doc.customer, 'custom_company', function(r) {
            if (r && r.custom_company && r.custom_company !== company) {
                frappe.msgprint({
                    title: __('Company Mismatch'),
                    message: __('Customer {0} does not belong to company {1}. Clearing customer field.', 
                        [frm.doc.customer, company]),
                    indicator: 'orange'
                });
                frm.set_value('customer', '');
            }
        });
    }
     if (frm.doc.employee) {
        frappe.db.get_value('Employee', frm.doc.employee, 'custom_company', function(r) {
            if (r && r.custom_company && r.custom_company !== company) {
                frappe.msgprint({
                    title: __('Company Mismatch'),
                    message: __('Employee {0} does not belong to company {1}. Clearing employee field.', 
                        [frm.doc.employee, company]),
                    indicator: 'orange'
                });
                frm.set_value('employee', '');
            }
        });
    }

    // Validate and clear Payment Entry party
    if (frm.doctype === "Payment Entry" && frm.doc.party && frm.doc.party_type) {
        const party_type = frm.doc.party_type;
        const company_field = getCompanyFieldForParty(party_type);
        if (company_field) {
            frappe.db.get_value(party_type, frm.doc.party, company_field, function(r) {
                if (r && r[company_field] && r[company_field] !== company) {
                    frappe.msgprint({
                        title: __('Company Mismatch'),
                        message: __('{0} {1} does not belong to company {2}. Clearing party field.', 
                            [party_type, frm.doc.party, company]),
                        indicator: 'orange'
                    });
                    frm.set_value('party', '');
                }
            });
        }
    }
    
    //Validate and clear items in batch
    if (frm.doc.items && frm.doc.items.length > 0) {
        let itemCodes = frm.doc.items
            .filter(item => item.item_code)
            .map(item => item.item_code);
        
        if (itemCodes.length > 0) {
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Item',
                    filters: {
                        name: ['in', itemCodes]
                    },
                    fields: ['name', 'custom_company']
                },
                callback: function(r) {
                    if (r && r.message && r.message.length > 0) {
                        let mismatchedItems = [];
                        
                        // Check each item's custom_company
                        r.message.forEach(function(item) {
                            // Item doesn't match if custom_company exists and is different
                            if (item.custom_company && item.custom_company !== company) {
                                mismatchedItems.push(item.name);
                            }
                        });
                        
                        if (mismatchedItems.length > 0) {
                            // Remove entire rows for mismatched items
                            let removedCount = 0;
                            let itemsToRemove = [];
                            
                            // Collect rows to remove
                            frm.doc.items.forEach(function(row) {
                                if (mismatchedItems.includes(row.item_code)) {
                                    itemsToRemove.push(row);
                                    removedCount++;
                                }
                            });
                            
                            // Remove the rows
                            itemsToRemove.forEach(function(row) {
                                frappe.model.clear_doc(row.doctype, row.name);
                            });
                            
                            // Update the items array
                            frm.doc.items = frm.doc.items.filter(function(row) {
                                return !mismatchedItems.includes(row.item_code);
                            });
                            
                            // Show message and refresh
                            if (removedCount > 0) {
                                frappe.msgprint({
                                    title: __('Company Mismatch'),
                                    message: __('Removed {0} item row(s) that do not belong to company {1}', 
                                        [removedCount, company]),
                                    indicator: 'orange'
                                });
                                frm.refresh_field('items');
                                frm.dirty();
                            }
                        }
                    }
                }
            });
        }
    }
}

function doctypeHasField(doctype, fieldname) {
    const meta = frappe.get_meta(doctype);
    return meta && meta.fields && meta.fields.some(f => f.fieldname === fieldname);
}

function getCompanyFieldForParty(doctype) {
    if (partyTypeCompanyFieldOverride[doctype]) {
        return partyTypeCompanyFieldOverride[doctype];
    }
    if (doctypeHasField(doctype, 'custom_company')) {
        return 'custom_company';
    }
    if (doctypeHasField(doctype, 'company')) {
        return 'company';
    }
    return null;
}

const partyTypeCompanyFieldOverride = {
    "Customer": "custom_company",
    "Supplier": "custom_company",
    "Employee": "company",
    "Shareholder": "company"
};
