$(document).on('app_ready', function() {
    // Doctypes that use company-based party/item filters
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
        "Stock Reconciliation"
    ];

    $.each(relevantDocTypes, function(i, doctype) {
        frappe.ui.form.on(doctype, {
            company: function(frm) {
                setupCompanyBasedFilters(frm);
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

    // Customer: group + defaults filtered by custom_company
    frappe.ui.form.on('Customer', {
        setup: function(frm) {
            filterCustomerGroup(frm);
            filterCustomerDefaultBankAccount(frm);
            filterCustomerDefaultPriceList(frm);
        },
        refresh: function(frm) {
            filterCustomerDefaultBankAccount(frm);
            filterCustomerDefaultPriceList(frm);
        },
        custom_company: function(frm) {
            frm.refresh_field('customer_group');
            frm.refresh_field('default_bank_account');
            frm.refresh_field('default_company_bank_account');
            frm.refresh_field('default_price_list');
        }
    });

    // Supplier: group + defaults filtered by custom_company
    frappe.ui.form.on('Supplier', {
        setup: function(frm) {
            filterSupplierGroup(frm);
            filterSupplierDefaultBankAccount(frm);
            filterSupplierDefaultPriceList(frm);
        },
        refresh: function(frm) {
            filterSupplierDefaultBankAccount(frm);
            filterSupplierDefaultPriceList(frm);
        },
        custom_company: function(frm) {
            frm.refresh_field('supplier_group');
            frm.refresh_field('default_bank_account');
            frm.refresh_field('default_company_bank_account');
            frm.refresh_field('default_price_list');
        }
    });

    // Item: groups + child tables filtered by custom_company
    frappe.ui.form.on('Item', {
        setup: function(frm) {
            filterItemGroup(frm);
            filterItemAssetCategory(frm);
            setupItemPartyFilters(frm);
            setupItemTaxTemplateFilters(frm);
        },
        refresh: function(frm) {
            filterItemGroup(frm);
            filterItemAssetCategory(frm);
            setupItemPartyFilters(frm);
            setupItemTaxTemplateFilters(frm);
        },
        item_defaults_add: function(frm, cdt, cdn) {
            setChildRowCompanyFromParent(frm, cdt, cdn, 'custom_company');
        },
        custom_company: function(frm) {
            frm.refresh_field('item_group');
            frm.refresh_field('asset_category');
            setupItemPartyFilters(frm);
            setupItemTaxTemplateFilters(frm);
        }
    });

    // Child row validation for Item child tables
    setupItemCompanyValidation();

    // Child row validation for Supplier child tables
    setupSupplierCompanyValidation();

});


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

function applyCompanyFilterToLinkFields(frm, fieldnames, company_fieldname, target_company_fieldname) {
    fieldnames.forEach(function(fieldname) {
        if (!frm.fields_dict[fieldname]) {
            return;
        }
        frm.set_query(fieldname, function() {
            const company_value = frm.doc[company_fieldname];
            if (company_value) {
                return {
                    filters: {
                        [target_company_fieldname]: company_value
                    }
                };
            }
            return {};
        });
    });
}

function setChildRowCompanyFromParent(frm, cdt, cdn, parent_company_fieldname) {
    if (!frm || !frm.doc) {
        return;
    }
    const parent_company = frm.doc[parent_company_fieldname];
    if (!parent_company) {
        return;
    }
    frappe.model.set_value(cdt, cdn, 'company', parent_company);
}

function filterCustomerDefaultBankAccount(frm) {
    applyCompanyFilterToLinkFields(
        frm,
        ['default_bank_account', 'default_company_bank_account'],
        'custom_company',
        'company'
    );
}

function filterCustomerDefaultPriceList(frm) {
    if (!frm.fields_dict.default_price_list) {
        return;
    }
    frm.set_query('default_price_list', function() {
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

function filterSupplierDefaultBankAccount(frm) {
    applyCompanyFilterToLinkFields(
        frm,
        ['default_bank_account', 'default_company_bank_account'],
        'custom_company',
        'company'
    );
}

function filterSupplierDefaultPriceList(frm) {
    if (!frm.fields_dict.default_price_list) {
        return;
    }
    frm.set_query('default_price_list', function() {
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

function filterItemAssetCategory(frm) {
    if (!frm.fields_dict.asset_category) {
        return;
    }
    frm.set_query('asset_category', function() {
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

// Main party/item filters on sales/purchase doctypes
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
    setupSupplierFilter(frm, company);
    setupJournalEntryAccountFilters(frm, company);
}


// Items child table filter by company
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


// RFQ supplier child table filter by company
function setupSupplierFilter(frm, company) {
    // RFQ supplier rows
    if(frm.doctype === 'Request for Quotation' && frm.fields_dict.suppliers) {
        frm.set_query('supplier', 'suppliers', function() {
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

function setupJournalEntryAccountFilters(frm, company) {
    if (frm.doctype !== "Journal Entry" || !frm.fields_dict.accounts) {
        return;
    }

    // Party filter based on party type + company (same logic as Payment Entry)
    frm.set_query('party', 'accounts', function(doc, cdt, cdn) {
        const row = locals[cdt][cdn];
        const party_type = row ? row.party_type : null;
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

    // Vehicle (custom_subtype) company-wise filter
    frm.set_query('custom_subtype', 'accounts', function() {
        if (!company) {
            return {};
        }
        return {
            filters: {
                custom_company: company
            }
        };
    });

    // Bank Account company-wise filter
    frm.set_query('bank_account', 'accounts', function() {
        if (!company) {
            return {};
        }
        return {
            filters: {
                company: company
            }
        };
    });

    // Project company-wise filter
    frm.set_query('project', 'accounts', function() {
        if (!company) {
            return {};
        }
        return {
            filters: {
                company: company
            }
        };
    });
}


// Clear mismatched party/item rows when company changes
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
                    message: __('Supplier {0} does not belong to company {1}.', 
                        [frm.doc.supplier, company]),
                    indicator: 'orange'
                });
                frm.set_value('supplier', '');
            }
        });
    }
    
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


// Validate Item child tables on selection/paste
function setupItemCompanyValidation() {
    const ITEM_CHILD_DOCTYPES = [
        "Sales Invoice Item",
        "Purchase Order Item",
        "Purchase Invoice Item",
        "Sales Order Item",
        "Delivery Note Item",
        "Purchase Receipt Item",
        "Material Request Item",
        "Supplier Quotation Item",
        "Quotation Item",
        "Stock Entry Detail",
        "Production Plan Item",
        "Job Card Item",
        "Purchase Request Item",
        "Request for Quotation Item",
        "Stock Reconciliation Item",
    ];

    ITEM_CHILD_DOCTYPES.forEach(function(child_doctype) {
        frappe.ui.form.on(child_doctype, {
            item_code: function(frm, cdt, cdn) {
                validateItemCompanyMatch(frm, cdt, cdn);
            }
        });
    });
}


function validateItemCompanyMatch(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row || !row.item_code) {
        return;
    }

    const parent_company = frm.doc.custom_company || frm.doc.company;

    if (!parent_company) {
        return;
    }

    frappe.db.get_value('Item', row.item_code, 'custom_company', function(r) {
        if (!r) {
            return;
        }

        const item_company = r.custom_company;

        if (item_company && item_company.toLowerCase() !== parent_company.toLowerCase()) {
            const selected_item = row.item_code;

            frappe.model.set_value(cdt, cdn, 'item_code', '');

            frappe.msgprint({
                title: __('Company Mismatch'),
                message: __('Item {0} does not belong to company {1}.', [
                    selected_item,
                    parent_company
                ]),
                indicator: 'red'
            });
        }
    });
}


// Validate supplier child tables on selection/paste
function setupSupplierCompanyValidation() {
    const SUPPLIER_CHILD_DOCTYPES = [
        "Request for Quotation Supplier"
    ];

    SUPPLIER_CHILD_DOCTYPES.forEach(function(child_doctype) {
        frappe.ui.form.on(child_doctype, {
            supplier: function(frm, cdt, cdn) {
                validateSupplierCompanyMatch(frm, cdt, cdn);
            }
        });
    });
}


function validateSupplierCompanyMatch(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row || !row.supplier) {
        return;
    }

    const parent_company = frm.doc.custom_company || frm.doc.company;

    if (!parent_company) {
        return;
    }

    frappe.db.get_value('Supplier', row.supplier, 'custom_company', function(r) {
        if (!r) {
            return;
        }

        const supplier_company = r.custom_company;

        if (supplier_company && supplier_company.toLowerCase() !== parent_company.toLowerCase()) {
            const selected_supplier = row.supplier;

            frappe.model.set_value(cdt, cdn, 'supplier', '');

            frappe.msgprint({
                title: __('Company Mismatch'),
                message: __('Supplier {0} does not belong to company {1}. ', [
                    selected_supplier,
                    parent_company
                ]),
                indicator: 'red'
            });
        }
    });
}


// Item child tables: supplier/customer filters
function setupItemPartyFilters(frm) {
    if (!frm || !frm.doc) {
        return;
    }
    const parent_company = frm.doc.custom_company;
    if (frm.fields_dict.supplier_items) {
        frm.set_query('supplier', 'supplier_items', function() {
            if (parent_company) {
                return {
                    filters: {
                        custom_company: parent_company,
                        disabled: 0
                    }
                };
            }
            return {
                filters: {
                    disabled: 0
                }
            };
        });
    }
    if (frm.fields_dict.customer_items) {
        frm.set_query('customer_name', 'customer_items', function() {
            if (parent_company) {
                return {
                    filters: {
                        custom_company: parent_company,
                        disabled: 0
                    }
                };
            }
            return {
                filters: {
                    disabled: 0
                }
            };
        });
    }
}

// Item taxes child table: item_tax_template filter
function setupItemTaxTemplateFilters(frm) {
    if (!frm || !frm.doc) {
        return;
    }
    const parent_company = frm.doc.custom_company;
    if (frm.fields_dict.taxes) {
        frm.set_query('item_tax_template', 'taxes', function() {
            if (parent_company) {
                return {
                    filters: {
                        company: parent_company,
                        disabled: 0
                    }
                };
            }
            return {
                filters: {
                    disabled: 0
                }
            };
        });
    }
}
