frappe.ui.form.on('Purchase Invoice', {
    refresh: function(frm) {
        account_subtype_cache = {};
        update_fiscal_year(frm);
        prefetch_account_subtypes(frm);
    },
    
    posting_date: function(frm) {
        update_fiscal_year(frm);
    },
    
    items_add: function(frm, cdt, cdn) {
        // Set initial empty filter
        let grid_row = frm.fields_dict['items'].grid.grid_rows_by_docname[cdn];
        if (grid_row) {
            grid_row.get_field('custom_subtype').get_query = function() {
                return {
                    filters: {
                        'name': ['in', ['__no_match__']]
                    }
                };
            };
        }
    }
});

frappe.ui.form.on('Purchase Invoice Item', {
    item_code: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        
        // Clear the custom_subtype field when item_code changes
        frappe.model.set_value(cdt, cdn, 'custom_subtype', '');
        
        if (row.item_code) {
            // Fetch Item doc and get expense_account from item_defaults
            get_expense_account_from_item(row.item_code).then(expense_account => {
                if (expense_account) {
                    // Use cached data or fetch if not available
                    get_account_subtypes(expense_account).then(sub_ledger_categories => {
                        apply_subtype_filter(frm, cdn, sub_ledger_categories);
                    });
                } else {
                    // If no expense_account found, reset the filter
                    apply_subtype_filter(frm, cdn, []);
                }
            });
        } else {
            // If no item_code selected, reset the filter
            apply_subtype_filter(frm, cdn, []);
        }
    }
});

// Get expense account from Item's item_defaults child table
function get_expense_account_from_item(item_code) {
    return new Promise((resolve, reject) => {
        frappe.db.get_doc('Item', item_code)
            .then(item_doc => {
                let expense_account = null;
                
                if (item_doc.item_defaults && item_doc.item_defaults.length > 0) {
                    // Get the first item_default entry's expense_account
                    for (let default_entry of item_doc.item_defaults) {
                        if (default_entry.expense_account) {
                            expense_account = default_entry.expense_account;
                            break;
                        }
                    }
                }
                
                resolve(expense_account);
            })
            .catch(err => {
                console.error('Error fetching item details:', err);
                reject(err);
            });
    });
}

// Pre-fetch all account subtypes in a single batch call
function prefetch_account_subtypes(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        return;
    }
    
    let unique_items = [...new Set(
        frm.doc.items
            .map(row => row.item_code)
            .filter(item => item)
    )];
    
    if (unique_items.length === 0) {
        return;
    }
    
    // Batch fetch all items at once
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Item',
            filters: {
                'name': ['in', unique_items]
            },
            fields: ['name']
        },
        callback: function(r) {
            if (r.message) {
                let item_promises = r.message.map(item => {
                    return frappe.db.get_doc('Item', item.name)
                        .then(item_doc => {
                            let expense_account = null;
                            if (item_doc.item_defaults && item_doc.item_defaults.length > 0) {
                                for (let default_entry of item_doc.item_defaults) {
                                    if (default_entry.expense_account) {
                                        expense_account = default_entry.expense_account;
                                        break;
                                    }
                                }
                            }
                            return expense_account;
                        });
                });
                
                Promise.all(item_promises).then(expense_accounts => {
                    let unique_accounts = [...new Set(expense_accounts.filter(acc => acc))];
                    
                    if (unique_accounts.length === 0) {
                        return;
                    }
                    
                    frappe.call({
                        method: 'frappe.client.get_list',
                        args: {
                            doctype: 'Account',
                            filters: {
                                'name': ['in', unique_accounts]
                            },
                            fields: ['name', 'custom_sub_type_list']
                        },
                        callback: function(r2) {
                            if (r2.message) {
                                let account_promises = r2.message.map(account => {
                                    return frappe.db.get_doc('Account', account.name)
                                        .then(account_doc => {
                                            if (account_doc.custom_sub_type_list && account_doc.custom_sub_type_list.length > 0) {
                                                account_subtype_cache[account.name] = account_doc.custom_sub_type_list.map(
                                                    item => item.sub_type_list
                                                );
                                            } else {
                                                account_subtype_cache[account.name] = [];
                                            }
                                        });
                                });
                                
                                // Once all accounts are cached, apply filters
                                Promise.all(account_promises).then(() => {
                                    frm.doc.items.forEach(row => {
                                        if (row.item_code) {
                                            get_expense_account_from_item(row.item_code).then(expense_account => {
                                                if (expense_account && account_subtype_cache[expense_account]) {
                                                    apply_subtype_filter(frm, row.name, account_subtype_cache[expense_account]);
                                                }
                                            });
                                        }
                                    });
                                });
                            }
                        }
                    });
                });
            }
        }
    });
}

// Get account subtypes with caching
function get_account_subtypes(account) {
    return new Promise((resolve, reject) => {
        // Check cache first
        if (account_subtype_cache[account] !== undefined) {
            resolve(account_subtype_cache[account]);
            return;
        }
        
        // Fetch from database if not in cache
        frappe.db.get_doc('Account', account)
            .then(account_doc => {
                let sub_ledger_categories = [];
                
                if (account_doc.custom_sub_type_list && account_doc.custom_sub_type_list.length > 0) {
                    sub_ledger_categories = account_doc.custom_sub_type_list.map(
                        item => item.sub_type_list
                    );
                }
                
                // Store in cache
                account_subtype_cache[account] = sub_ledger_categories;
                resolve(sub_ledger_categories);
            })
            .catch(err => {
                console.error('Error fetching account details:', err);
                reject(err);
            });
    });
}

// Apply filter to a specific row
function apply_subtype_filter(frm, row_name, sub_ledger_categories) {
    let grid_row = frm.fields_dict['items'].grid.grid_rows_by_docname[row_name];
    
    if (grid_row) {
        grid_row.get_field('custom_subtype').get_query = function() {
            if (sub_ledger_categories.length > 0) {
                return {
                    filters: {
                        'name': ['in', sub_ledger_categories]
                    }
                };
            } else {
                return {
                    filters: {
                        'name': ['in', ['__no_match__']]
                    }
                };
            }
        };
        
        grid_row.refresh_field('custom_subtype');
    }
}

function update_fiscal_year(frm) {
    if (frm.doc.posting_date) {
        console.log("Posting date!");
        frappe.call({
            method: 'frappe.client.get_value',
            args: {
                doctype: "Fiscal Year",
                filters: {
                    year_start_date: ["<=", frm.doc.posting_date],
                    year_end_date: [">=", frm.doc.posting_date]
                },
                fieldname: "name"
            },
            callback: function(r) {
                if (r.message) {
                    frm.set_value("custom_fiscal_year", r.message.name);
                } else {
                    frm.set_value("custom_fiscal_year", "Not Found");
                }
            }
        });
    }
}

