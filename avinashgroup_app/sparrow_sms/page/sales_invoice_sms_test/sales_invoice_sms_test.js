// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.pages["sales-invoice-sms-test"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Sales Invoice SMS Test"),
		single_column: true,
	});

	new SalesInvoiceSMSTest(page);
};

const API =
	"avinashgroup_app.sparrow_sms.page.sales_invoice_sms_test.sales_invoice_sms_test_api";

class SalesInvoiceSMSTest {
	constructor(page) {
		this.page = page;
		this.rows = [];
		this.make_filters();
		this.make_body();
	}

	make_filters() {
		this.company = this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			change: () => this.load(),
		});

		this.customer_group = this.page.add_field({
			fieldname: "customer_group",
			label: __("Customer Group"),
			fieldtype: "Link",
			options: "Customer Group",
			change: () => this.load(),
		});

		this.only_with_mobile = this.page.add_field({
			fieldname: "only_with_mobile",
			label: __("Only With Phone Number"),
			fieldtype: "Check",
			change: () => this.load(),
		});

		this.page.set_primary_action(__("Reload"), () => this.load());
	}

	make_body() {
		this.$body = $(`
			<div class="si-sms-test-page">
				<style>
					.si-sms-test-page .table { margin-top: 10px; }
					.si-sms-test-page td { vertical-align: middle; }
					.si-sms-test-page input.cell { width: 100%; border: 1px solid var(--border-color);
						border-radius: 4px; padding: 4px 6px; background: var(--control-bg); }
					.si-sms-test-page .status-sent { color: var(--green-600); font-weight: 600; }
					.si-sms-test-page .status-failed { color: var(--red-600); font-weight: 600; }
					.si-sms-test-page .muted { color: var(--text-muted); }
				</style>
				<div class="result"></div>
			</div>
		`).appendTo(this.page.main);

		this.$result = this.$body.find(".result");
		this.$result.html(`<p class="muted">${__("Pick a company to load customers.")}</p>`);
	}

	load() {
		const company = this.company.get_value();
		if (!company) {
			return;
		}

		frappe.call({
			method: `${API}.get_customers`,
			args: {
				company: company,
				customer_group: this.customer_group.get_value(),
				only_with_mobile: this.only_with_mobile.get_value() ? 1 : 0,
			},
			freeze: true,
			freeze_message: __("Loading customers..."),
			callback: (r) => {
				this.rows = r.message || [];
				this.render();
			},
		});
	}

	render() {
		if (!this.rows.length) {
			this.$result.html(`<p class="muted">${__("No customers found.")}</p>`);
			return;
		}

		const header = `
			<thead><tr>
				<th style="width:16%">${__("Company")}</th>
				<th style="width:20%">${__("Customer")}</th>
				<th style="width:16%">${__("Phone Number")}</th>
				<th style="width:34%">${__("Message")}</th>
				<th style="width:14%"></th>
			</tr></thead>`;

		const body = this.rows
			.map(
				(row, i) => `
			<tr data-idx="${i}">
				<td class="muted">${frappe.utils.escape_html(row.company)}</td>
				<td>${frappe.utils.escape_html(row.customer_name)}
					<div class="muted small">${frappe.utils.escape_html(row.customer)}</div></td>
				<td><input class="cell mobile" value="${frappe.utils.escape_html(row.mobile_no)}"></td>
				<td><input class="cell message" value="${frappe.utils.escape_html(row.message)}"></td>
				<td class="action">
					<button class="btn btn-xs btn-primary send">${__("Send")}</button>
				</td>
			</tr>`
			)
			.join("");

		this.$result.html(`
			<table class="table table-bordered">${header}<tbody>${body}</tbody></table>
		`);

		this.$result.find("button.send").on("click", (e) => this.send($(e.currentTarget)));
	}

	send($btn) {
		const $tr = $btn.closest("tr");
		const row = this.rows[$tr.data("idx")];
		const mobile_no = $tr.find("input.mobile").val();
		const message = $tr.find("input.message").val();

		frappe.confirm(
			__("Send to {0} at <b>{1}</b>?", [
				frappe.utils.escape_html(row.customer_name),
				frappe.utils.escape_html(mobile_no || "—"),
			]),
			() => {
				$btn.prop("disabled", true).text(__("Sending..."));
				frappe.call({
					method: `${API}.send_one`,
					args: {
						customer: row.customer,
						mobile_no: mobile_no,
						message: message,
						company: row.company,
					},
					callback: (r) => {
						const ok = r.message && r.message.ok;
						$tr.find("td.action").html(
							ok
								? `<span class="status-sent">${__("Sent")}</span>`
								: `<span class="status-failed">${__("Failed")}</span>`
						);
						frappe.show_alert({
							message: ok
								? __("Sent to {0}", [r.message.receiver])
								: __("Failed — see Sparrow SMS Log"),
							indicator: ok ? "green" : "red",
						});
					},
					error: () => {
						$btn.prop("disabled", false).text(__("Send"));
					},
				});
			},
			() => {
				$btn.prop("disabled", false).text(__("Send"));
			}
		);
	}
}
