// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.pages["print-count-import"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Print Count Import"),
		single_column: true,
	});

	new PrintCountImport(page);
};

const API =
	"avinashgroup_app.avinash_group_app.page.print_count_import.print_count_import_api";

class PrintCountImport {
	constructor(page) {
		this.page = page;
		this.running = false;
		this.make_body();
		this.make_form();
		this.listen();
		this.load_summary();

		this.page.set_primary_action(__("Dry Run"), () => this.start(0));
		this.page.set_secondary_action(__("Import"), () => this.confirm_import());
	}

	make_body() {
		this.page.main.html(`
			<div class="print-count-import">
				<p class="text-muted" style="margin-bottom: 15px;">
					${__(
						"Loads a Sale Invoice Register export (.xls) from the old billing software into Sales Invoice Print Count. Invoices are matched on the branch-wise number stored against each Sales Invoice."
					)}
				</p>
				<div class="form-area"></div>
				<div class="summary-area" style="margin-top: 15px;"></div>
				<div class="result-area" style="margin-top: 20px;"></div>
			</div>
		`);
		this.$form = this.page.main.find(".form-area");
		this.$summary = this.page.main.find(".summary-area");
		this.$result = this.page.main.find(".result-area");
	}

	make_form() {
		this.form = new frappe.ui.FieldGroup({
			parent: this.$form,
			body: this.$form,
			fields: [
				{
					fieldname: "file_url",
					label: __("Register File (.xls)"),
					fieldtype: "Attach",
					reqd: 1,
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "mode",
					label: __("If a count already exists"),
					fieldtype: "Select",
					default: "max",
					options: [
						{ value: "max", label: __("Raise it to this file's total (safe to re-run)") },
						{ value: "add", label: __("Add this file's sheets to it") },
					],
					description: __(
						"Use Raise unless you know this file covers prints the existing count does not already include. Add counts twice if the same file is imported twice."
					),
				},
				{ fieldtype: "Section Break" },
				{
					fieldname: "only_prefix",
					label: __("Only invoice numbers starting with"),
					fieldtype: "Data",
					description: __("Leave blank to import every invoice in the file."),
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "drop_batch_events",
					label: __("Ignore batch print events"),
					fieldtype: "Check",
					description: __(
						"A batch event is one timestamp shared by many invoices - a single bulk reprint. Off by default, so those sheets are counted."
					),
				},
			],
		});
		this.form.make();
	}

	listen() {
		frappe.realtime.on("print_count_import", (payload) => {
			this.running = false;
			this.page.clear_indicator();
			payload.ok ? this.render(payload.result) : this.render_error(payload.error);
			this.load_summary();
		});
	}

	load_summary() {
		frappe.call({ method: `${API}.summary` }).then((r) => {
			if (!r || !r.message) return;
			const m = r.message;
			this.$summary.html(`
				<div class="text-muted">
					${__("Currently stored")}:
					<b>${format_number(m.counters, null, 0)}</b> ${__("counters")},
					<b>${format_number(m.sheets, null, 0)}</b> ${__("sheets")}
				</div>
			`);
		});
	}

	values() {
		const v = this.form.get_values();
		if (!v) return null;
		if (!v.file_url) {
			frappe.msgprint(__("Attach the register file first."));
			return null;
		}
		return v;
	}

	confirm_import() {
		const v = this.values();
		if (!v) return;

		const warning =
			v.mode === "add"
				? __(
						"Mode is <b>Add</b>. If this file was already imported, importing it again counts those sheets twice."
				  )
				: __("Mode is <b>Raise</b>, so importing the same file again changes nothing.");

		frappe.confirm(
			`${__("Write these print counts to the database?")}<br><br>${warning}<br><br>${__(
				"Run a Dry Run first if you have not already."
			)}`,
			() => this.start(1)
		);
	}

	start(commit) {
		if (this.running) {
			frappe.msgprint(__("An import is already running. Wait for it to finish."));
			return;
		}
		const v = this.values();
		if (!v) return;

		this.running = true;
		this.$result.html(
			`<div class="text-muted">${__("Working on it - large files take a few minutes.")}</div>`
		);
		this.page.set_indicator(commit ? __("Importing") : __("Dry run"), "orange");

		frappe
			.call({
				method: `${API}.start`,
				args: {
					file_url: v.file_url,
					mode: v.mode || "max",
					only_prefix: v.only_prefix || null,
					drop_batch_events: v.drop_batch_events ? 1 : 0,
					commit: commit,
				},
			})
			.catch(() => {
				this.running = false;
				this.page.clear_indicator();
				this.$result.empty();
			});
	}

	render(r) {
		const dry = r.dry_run;
		const inserted = dry ? r.would_insert : r.inserted;
		const updated = dry ? r.would_update : r.updated;

		const rows = [
			[__("File"), r.file],
			[__("Mode"), r.mode === "max" ? __("Raise to file total") : __("Add to existing")],
			[__("Invoices in file"), format_number(r.excel_invoices, null, 0)],
			[dry ? __("Would create") : __("Created"), format_number(inserted, null, 0)],
			[dry ? __("Would change") : __("Changed"), format_number(updated, null, 0)],
			[__("Sheets written"), format_number(r.total_sheets, null, 0)],
			[__("Not matched to an invoice"), format_number(r.unmatched, null, 0)],
		];

		if (r.only_prefix) {
			rows.push([__("Skipped by prefix"), format_number(r.skipped_by_prefix, null, 0)]);
		}
		if (r.batch_events) {
			rows.push([
				__("Batch print events"),
				`${format_number(r.batch_events, null, 0)} (${
					r.batch_events_dropped ? __("ignored") : __("counted")
				}) - ${(r.batch_timestamps || []).join(", ")}`,
			]);
		}

		const body = rows
			.map(
				([k, v]) =>
					`<tr><td style="width: 45%;" class="text-muted">${k}</td><td><b>${
						frappe.utils.escape_html(String(v == null ? "" : v))
					}</b></td></tr>`
			)
			.join("");

		let notes = "";
		if (r.unmatched) {
			notes += `<div class="alert alert-warning" style="margin-top: 12px;">
				${__("These invoice numbers from the file have no matching Sales Invoice:")}
				<br><code>${frappe.utils.escape_html(
					(r.unmatched_invoices || []).join(", ")
				)}</code>
			</div>`;
		}
		notes += `<div class="alert ${dry ? "alert-info" : "alert-success"}" style="margin-top: 12px;">
			${
				dry
					? __("Nothing was written. Check the numbers, then press Import.")
					: __("Import finished and saved.")
			}
		</div>`;

		this.$result.html(
			`<h5>${dry ? __("Dry run result") : __("Import result")}</h5>
			 <table class="table table-bordered" style="max-width: 720px;"><tbody>${body}</tbody></table>
			 ${notes}`
		);
	}

	render_error(traceback) {
		this.$result.html(
			`<div class="alert alert-danger">${__("The import failed and nothing was saved.")}</div>
			 <pre style="white-space: pre-wrap; font-size: 11px;">${frappe.utils.escape_html(
					traceback || ""
				)}</pre>`
		);
	}
}
