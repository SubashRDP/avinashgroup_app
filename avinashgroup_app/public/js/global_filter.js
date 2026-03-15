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

    // ================= GROUP FILTERS =================

    // Customer Group Filter
    frappe.ui.form.on('Customer', {
        setup: function(frm) {
            filterCustomerGroup(frm);
        },
        custom_company: function(frm) {
            frm.refresh_field('customer_group');
        }
    });

    // Supplier Group Filter
    frappe.ui.form.on('Supplier', {
        setup: function(frm) {
            filterSupplierGroup(frm);
        },
        custom_company: function(frm) {
            frm.refresh_field('supplier_group');
        }
    });

    // Item Group Filter
    frappe.ui.form.on('Item', {
        setup: function(frm) {
            filterItemGroup(frm);
        },
        refresh: function(frm) {
            filterItemGroup(frm);
        },
        custom_company: function(frm) {
            frm.refresh_field('item_group');
        }
    });

});


// ===== CUSTOMER GROUP FILTER =====
function filterCustomerGroup(frm) {
    frm.set_query('customer_group', function() {
        if (frm.doc.custom_company) {
            return {
                filters: {
                    custom_company: frm.doc.custom_company
                }
            };
        }
        return {};
    });
}

// ===== SUPPLIER GROUP FILTER =====
function filterSupplierGroup(frm) {
    frm.set_query('supplier_group', function() {
        if (frm.doc.custom_company) {
            return {
                filters: {
                    custom_company: frm.doc.custom_company
                }
            };
        }
        return {};
    });
}

// ===== ITEM GROUP FILTER =====
function filterItemGroup(frm) {
    frm.set_query('item_group', function() {
        if (frm.doc.custom_company) {
            return {
                filters: {
                    custom_company: frm.doc.custom_company
                }
            };
        }
        return {};
    });
}


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
    if (frm.fields_dict.employee) {
        frm.set_query('employee', function() {
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
    
    // Validate and clear items in batch
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
                        
                        r.message.forEach(function(item) {
                            if (item.custom_company && item.custom_company !== company) {
                                mismatchedItems.push(item.name);
                            }
                        });
                        
                        if (mismatchedItems.length > 0) {
                            let removedCount = 0;
                            let itemsToRemove = [];
                            
                            frm.doc.items.forEach(function(row) {
                                if (mismatchedItems.includes(row.item_code)) {
                                    itemsToRemove.push(row);
                                    removedCount++;
                                }
                            });
                            
                            itemsToRemove.forEach(function(row) {
                                frappe.model.clear_doc(row.doctype, row.name);
                            });
                            
                            frm.doc.items = frm.doc.items.filter(function(row) {
                                return !mismatchedItems.includes(row.item_code);
                            });
                            
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