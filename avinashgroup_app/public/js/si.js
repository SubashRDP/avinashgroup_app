frappe.ui.form.on('Sales Invoice', {
    customer: function(frm) {
        if (frm.doc.customer) {
            check_credit_on_customer_change(frm);
        }
    },
    
    onload: function(frm) {
        if (frm.doc.customer && frm.doc.__islocal) {
            check_credit_on_customer_change(frm);
        }
    },
    
    before_save: function(frm) {
        if (frm.doc.customer) {
            return check_credit_on_save(frm);
        }
    }
});

function check_credit_on_customer_change(frm) {
    // Only check days and bill count on customer change
    frappe.call({
        method: 'avinashgroup_app.custom_code.SalesInvoice.salesinvoice_customer.check_customer_credit_limit_on_load',
        args: {
            customer: frm.doc.customer
        },
        freeze: true,
        freeze_message: __('Checking customer credit...'),
        callback: function(r) {
            if (r.message && r.message.status === 'success') {
                const data = r.message;
                
                if (data.warnings && data.warnings.length > 0) {
                    show_warning_dialog(frm, data, 'customer_change');
                } else {
                    frappe.show_alert({
                        message: __('Customer {0}: Days and Bill Count checks passed', [frm.doc.customer]),
                        indicator: 'green'
                    }, 3);
                }
                
                // Show info about amount
                if (data.info_message) {
                    frappe.show_alert({
                        message: data.info_message,
                        indicator: 'blue'
                    }, 5);
                }
            }
        }
    });
}

function check_credit_on_save(frm) {
    // Check ALL conditions including amount on save
    return new Promise((resolve, reject) => {
        frappe.call({
            method: 'avinashgroup_app.custom_code.SalesInvoice.salesinvoice_customer.check_customer_credit_limit_on_save',
            args: {
                customer: frm.doc.customer,
                current_invoice_amount: frm.doc.grand_total,
                current_invoice_name: frm.doc.name
            },
            freeze: true,
            freeze_message: __('Validating credit limit with invoice amount...'),
            callback: function(r) {
                if (r.message && r.message.status === 'success') {
                    const data = r.message;
                    
                    if (data.is_blocked) {
                        show_warning_dialog(frm, data, 'save');
                        reject();  // Stop save
                    } else {
                        frappe.show_alert({
                            message: __('All credit checks passed'),
                            indicator: 'green'
                        }, 3);
                        resolve();  // Allow save
                    }
                } else {
                    resolve();  // Allow save if check fails
                }
            },
            error: function() {
                resolve();  // Allow save on error
            }
        });
    });
}

function show_warning_dialog(frm, data, trigger_type) {
    let warning_html = '';
    const is_save = trigger_type === 'save';
    
    // Build warnings HTML
    data.warnings.forEach(warning => {
        let detail_html = '';
        
        if (warning.type === 'amount' && warning.breakdown) {
            const b = warning.breakdown;
            detail_html = `
                <div style="margin-top: 10px; padding: 10px; background: #fff; border: 1px solid #ddd;">
                    <table style="width: 100%;">
                        <tr>
                            <td><strong>Existing Outstanding:</strong></td>
                            <td style="text-align: right;">${format_currency(b.existing_outstanding)}</td>
                        </tr>
                        <tr style="border-bottom: 2px solid #333;">
                            <td><strong>Current Invoice:</strong></td>
                            <td style="text-align: right;">${format_currency(b.current_invoice)}</td>
                        </tr>
                        <tr style="font-weight: bold;">
                            <td>Total Outstanding:</td>
                            <td style="text-align: right;">${format_currency(b.total)}</td>
                        </tr>
                        <tr>
                            <td>Credit Limit:</td>
                            <td style="text-align: right;">${format_currency(b.limit)}</td>
                        </tr>
                        <tr style="color: #d32f2f; font-weight: bold;">
                            <td>Exceeded By:</td>
                            <td style="text-align: right;">${format_currency(b.exceeded_by)}</td>
                        </tr>
                    </table>
                </div>
            `;
        }
        
        warning_html += `
            <div style="margin-bottom: 20px; padding: 15px; border-left: 4px solid #d32f2f; background: #ffebee;">
                <div style="color: #d32f2f; font-weight: bold; font-size: 14px;">
                    ⚠️ ${warning.title}
                </div>
                <div style="margin-top: 8px; color: #333;">
                    ${warning.message}
                </div>
                ${detail_html}
            </div>
        `;
    });
    
    // Add overdue invoices table
    if (data.overdue_invoices && data.overdue_invoices.length > 0) {
        warning_html += `
            <div style="margin-top: 20px;">
                <strong>Overdue Invoices:</strong>
                <div style="max-height: 200px; overflow-y: auto; border: 1px solid #ddd; margin-top: 10px;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead style="background: #f5f5f5; position: sticky; top: 0;">
                            <tr>
                                <th style="padding: 8px; text-align: left;">Invoice</th>
                                <th style="padding: 8px; text-align: left;">Date</th>
                                <th style="padding: 8px; text-align: right;">Outstanding</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.overdue_invoices.map(inv => `
                                <tr style="border-bottom: 1px solid #eee;">
                                    <td style="padding: 8px;">
                                        <a href="/app/sales-invoice/${inv.name}" target="_blank">${inv.name}</a>
                                    </td>
                                    <td style="padding: 8px;">${frappe.datetime.str_to_user(inv.posting_date)}</td>
                                    <td style="padding: 8px; text-align: right;">
                                        ${format_currency(inv.outstanding_amount)}
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }
    
    // Add summary
    warning_html += `
        <div style="margin-top: 20px; padding: 15px; background: #f5f5f5; border-radius: 4px;">
            <strong>Summary:</strong>
            <table style="width: 100%; margin-top: 10px;">
                <tr>
                    <td><strong>Credit Days:</strong></td>
                    <td>${data.limits.days} days</td>
                    <td><strong>Credit Limit:</strong></td>
                    <td>${format_currency(data.limits.amount_limit)}</td>
                </tr>
                <tr>
                    <td><strong>Bill Count Limit:</strong></td>
                    <td>${data.limits.bill_count_limit}</td>
                    ${is_save ? `
                        <td><strong>Total Outstanding:</strong></td>
                        <td style="color: #d32f2f; font-weight: bold;">
                            ${format_currency(data.current.total_outstanding_with_current)}
                        </td>
                    ` : `
                        <td><strong>Current Outstanding:</strong></td>
                        <td>${format_currency(data.current.total_outstanding)}</td>
                    `}
                </tr>
                <tr>
                    <td><strong>Unpaid Bills:</strong></td>
                    <td style="color: ${data.current.unpaid_count > data.limits.bill_count_limit ? '#d32f2f' : '#333'};">
                        ${data.current.unpaid_count}
                    </td>
                    <td><strong>Overdue Amount:</strong></td>
                    <td style="color: ${data.current.overdue_amount > 0 ? '#d32f2f' : '#333'};">
                        ${format_currency(data.current.overdue_amount)}
                    </td>
                </tr>
            </table>
        </div>
    `;
    
    const dialog = new frappe.ui.Dialog({
        title: `<span style="color: #d32f2f;">⚠️ Credit Limit ${is_save ? 'Validation' : 'Alert'}: ${data.customer}</span>`,
        size: 'large',
        fields: [{
            fieldtype: 'HTML',
            options: warning_html
        }],
        primary_action_label: data.is_blocked ? __('View Customer') : __('Proceed'),
        primary_action: function() {
            if (data.is_blocked) {
                frappe.set_route('Form', 'Customer', data.customer);
            }
            dialog.hide();
        },
        secondary_action_label: __('Cancel'),
        secondary_action: function() {
            dialog.hide();
        }
    });
    
    dialog.show();
}