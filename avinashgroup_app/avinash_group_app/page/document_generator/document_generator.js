// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.pages["document-generator"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Document Generator"),
		single_column: true,
	});
	wrapper.document_generator = new DocumentGenerator(page);
};

const API = "avinashgroup_app.custom_code.document_generator.api";

class DocumentGenerator {
	constructor(page) {
		this.page = page;
		this.state = { working_sections: [], name: null, meta: {} };
		this.controls = {};

		const ro = frappe.route_options || {};
		this.design = !!ro.design_template; // template layout designer mode
		this.design_template = ro.design_template || null;
		this.load_name = ro.generated_document || null;
		frappe.route_options = null;

		this.make_layout();
		this.make_selector();
		this.make_actions();
		this.boot();
	}

	async boot() {
		if (this.design) return this.load_design(this.design_template);
		if (this.load_name) return this.load_existing(this.load_name);
	}

	async load_existing(name) {
		const r = await frappe.call({ method: `${API}.get_generated_document`, args: { name } });
		this.state = Object.assign(this.state, r.message);
		if (this.controls.template) this.controls.template.set_value(this.state.template);
		this.render_canvas();
	}

	async load_design(template) {
		const r = await frappe.call({ method: `${API}.get_template_for_design`, args: { template } });
		this.state.working_sections = r.message.sections || [];
		this.page.set_title(__("Design Layout: {0}", [r.message.template_name]));
		this.render_canvas();
	}

	// ── Layout ────────────────────────────────────────────────────────────────
	make_layout() {
		this.body = $(`
			<div class="dg-wrap">
				<div class="dg-selector"></div>
				<div class="dg-empty text-muted">${__("Select a template and load to begin.")}</div>
				<div class="dg-canvas-host"></div>
			</div>
		`).appendTo(this.page.main);

		this.$selector = this.body.find(".dg-selector");
		this.$empty = this.body.find(".dg-empty");
		this.canvas = new DocumentCanvas({
			$mount: this.body.find(".dg-canvas-host"),
			sections: [],
			onChange: () => {},
		});
	}

	// ── Selector ────────────────────────────────────────────────────────────────
	make_selector() {
		if (this.design) {
			this.$selector.html(
				`<div class="text-muted">${__("Arranging the template's default layout. Drag, resize and edit the boxes, then Save Layout.")}</div>`
			);
			return;
		}
		const row = $('<div class="dg-selector-row"></div>').appendTo(this.$selector);
		this.controls.template = this.make_control(row, {
			fieldname: "template",
			label: __("Template"),
			fieldtype: "Link",
			options: "Document Template",
			get_query: () => ({ filters: { is_active: 1 } }),
			onchange: () => this.on_template_change(),
		});
		this.$params = $('<div class="dg-params"></div>').appendTo(this.$selector);
		$(`<button class="btn btn-primary btn-sm dg-load">${__("Load")}</button>`)
			.appendTo(this.$selector)
			.on("click", () => this.load_document());
	}

	make_control(parent, df) {
		const control = frappe.ui.form.make_control({
			df: Object.assign({ placeholder: df.label }, df),
			parent: $('<div class="dg-field"></div>').appendTo(parent)[0],
			render_input: true,
		});
		control.refresh();
		return control;
	}

	async on_template_change() {
		const template = this.controls.template.get_value();
		this.$params.empty();
		if (!template) return;
		const r = await frappe.call({ method: `${API}.get_template_meta`, args: { template } });
		this.state.meta = r.message || {};
		this.render_params();
	}

	render_params() {
		const m = this.state.meta;
		const row = $('<div class="dg-selector-row"></div>').appendTo(this.$params);
		const companies = m.companies || [];
		if (companies.length) {
			this.controls.company = this.make_control(row, {
				fieldname: "company", label: __("Company"), fieldtype: "Select",
				options: companies.join("\n"), default: companies[0], reqd: 1,
			});
			this.controls.company.set_value(companies[0]);
		} else {
			this.controls.company = this.make_control(row, {
				fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
			});
		}
		if (m.data_provider === "Party Balance Confirmation") {
			this.controls.party = this.make_control(row, {
				fieldname: "party", label: m.party_type || __("Party"), fieldtype: "Link",
				options: m.party_type, reqd: 1,
			});
			this.controls.from_date = this.make_control(row, {
				fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1,
			});
			this.controls.to_date = this.make_control(row, {
				fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1,
			});
		} else if (m.data_provider === "Custom Data Sources") {
			this.custom_inputs = (m.inputs || []).filter((i) => i.fieldname !== "company");
			this.custom_inputs.forEach((inp) => {
				this.controls[inp.fieldname] = this.make_control(row, {
					fieldname: inp.fieldname,
					label: inp.label || inp.fieldname,
					fieldtype: inp.input_type || "Data",
					options: inp.options || undefined,
					reqd: inp.reqd ? 1 : 0,
				});
			});
		} else {
			this.controls.record = this.make_control(row, {
				fieldname: "record_name", label: m.target_doctype || __("Record"),
				fieldtype: "Link", options: m.target_doctype, reqd: 1,
			});
		}
	}

	build_payload() {
		const m = this.state.meta;
		const company = this.controls.company?.get_value();
		if (m.data_provider === "Party Balance Confirmation") {
			return {
				company,
				party: this.controls.party?.get_value(),
				from_date: this.controls.from_date?.get_value(),
				to_date: this.controls.to_date?.get_value(),
			};
		}
		if (m.data_provider === "Custom Data Sources") {
			const payload = { company };
			(this.custom_inputs || []).forEach((inp) => {
				payload[inp.fieldname] = this.controls[inp.fieldname]?.get_value();
			});
			return payload;
		}
		return { company, record_name: this.controls.record?.get_value() };
	}

	async load_document() {
		const template = this.controls.template.get_value();
		if (!template) return frappe.msgprint(__("Please select a template."));
		frappe.dom.freeze(__("Generating..."));
		try {
			const r = await frappe.call({
				method: `${API}.instantiate_document`,
				args: { template, payload: JSON.stringify(this.build_payload()) },
			});
			this.state = Object.assign(this.state, { name: null }, r.message);
			this.render_canvas();
		} finally {
			frappe.dom.unfreeze();
		}
	}

	render_canvas() {
		this.$empty.toggle(!this.state.working_sections.length);
		this.canvas.set_sections(this.state.working_sections);
	}

	// ── Actions ─────────────────────────────────────────────────────────────────
	make_actions() {
		if (this.design) {
			this.page.set_primary_action(__("Save Layout"), () => this.save());
			this.page.add_action_item(__("Add Section"), () => this.canvas.add_section());
			this.page.add_action_item(__("Add Image"), () => this.canvas.add_image());
			this.page.add_action_item(__("Back to Template"), () =>
				frappe.set_route("Form", "Document Template", this.design_template)
			);
			return;
		}
		this.page.set_primary_action(__("Save"), () => this.save());
		this.page.add_action_item(__("Add Section"), () => this.canvas.add_section());
		this.page.add_action_item(__("Add Image"), () => this.canvas.add_image());
		this.page.add_action_item(__("Print (PDF)"), () => this.output("Print"));
		this.page.add_action_item(__("Email"), () => this.output("Email"));
		this.page.add_action_item(__("Email + Print"), () => this.output("Both"));
	}

	payload_for_save() {
		return {
			name: this.state.name,
			template: this.state.template,
			target_doctype: this.state.target_doctype,
			company: this.state.company,
			reference_name: this.state.reference_name,
			party: this.state.party,
			data_provider: this.state.data_provider,
			print_orientation: this.state.print_orientation,
			payload: this.state.payload,
			title: this.state.title,
			recipients: this.state.recipients,
			working_sections: this.canvas.get_sections(),
		};
	}

	async save() {
		const sections = this.canvas.get_sections();
		if (!sections.length) return frappe.msgprint(__("Nothing to save."));

		if (this.design) {
			await frappe.call({
				method: `${API}.save_template_layout`,
				args: { template: this.design_template, sections: JSON.stringify(sections) },
			});
			frappe.show_alert({ message: __("Template layout saved"), indicator: "green" });
			return;
		}

		const r = await frappe.call({
			method: `${API}.save_generated_document`,
			args: { data: JSON.stringify(this.payload_for_save()) },
		});
		this.state.name = r.message.name;
		frappe.show_alert({ message: __("Saved {0}", [r.message.name]), indicator: "green" });
		return r.message.name;
	}

	async output(action) {
		const name = this.state.name || (await this.save());
		if (!name) return;
		if (action === "Print" || action === "Both")
			window.open(`/api/method/${API}.download_document_pdf?generated_document=${encodeURIComponent(name)}`);
		if (action === "Email" || action === "Both") this.prompt_email(name);
	}

	prompt_email(name) {
		frappe.prompt(
			[{ fieldname: "recipients", label: __("Recipients (comma separated, blank = auto)"), fieldtype: "Small Text" }],
			(values) => {
				frappe.call({
					method: `${API}.send_document_email`,
					args: { generated_document: name, recipients: values.recipients || "", action: "Email" },
					freeze: true,
					freeze_message: __("Sending..."),
					callback: (r) => {
						if (r.message)
							frappe.show_alert({ message: __("Queued to {0}", [r.message.recipients]), indicator: "green" });
					},
				});
			},
			__("Send Email"),
			__("Send")
		);
	}
}
