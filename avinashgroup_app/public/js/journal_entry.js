// Cache to store account sub-ledger categories
let account_subtype_cache = {};

frappe.ui.form.on('Journal Entry', {
    refresh: function(frm) {
        // Clear cache on form refresh
        account_subtype_cache = {};
        
        // Pre-fetch all unique accounts in one batch call
        prefetch_account_subtypes(frm);
    },
    
    accounts_add: function(frm, cdt, cdn) {
        // When a new row is added, set initial empty filter
        let grid_row = frm.fields_dict['accounts'].grid.grid_rows_by_docname[cdn];
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

frappe.ui.form.on('Journal Entry Account', {
    account: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        
        // Clear the custom_subtype field when account changes
        frappe.model.set_value(cdt, cdn, 'custom_subtype', '');
        
        if (row.account) {
            // Use cached data or fetch if not available
            get_account_subtypes(row.account).then(sub_ledger_categories => {
                apply_subtype_filter(frm, cdn, sub_ledger_categories);
            });
        } else {
            // If no account selected, reset the filter
            apply_subtype_filter(frm, cdn, []);
        }
    }
});

// Pre-fetch all account subtypes in a single batch call
function prefetch_account_subtypes(frm) {
    if (!frm.doc.accounts || frm.doc.accounts.length === 0) {
        return;
    }
    
    // Get unique account names
    let unique_accounts = [...new Set(
        frm.doc.accounts
            .map(row => row.account)
            .filter(account => account)
    )];
    
    if (unique_accounts.length === 0) {
        return;
    }
    // Batch fetch all accounts at once using frappe.call
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Account',
            filters: {
                'name': ['in', unique_accounts]
            },
            fields: ['name', 'custom_sub_type_list']
        },
        callback: function(r) {
            if (r.message) {
                // For each account, fetch the child table data
                let promises = r.message.map(account => {
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
                Promise.all(promises).then(() => {
                    frm.doc.accounts.forEach(row => {
                        if (row.account && account_subtype_cache[row.account]) {
                            apply_subtype_filter(frm, row.name, account_subtype_cache[row.account]);
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
    let grid_row = frm.fields_dict['accounts'].grid.grid_rows_by_docname[row_name];
    
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