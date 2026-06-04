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
		this.state = { name: null, meta: {} };
		this.controls = {};
		this.custom_inputs = [];

		const ro = frappe.route_options || {};
		this.load_name = ro.generated_document || null;
		frappe.route_options = null;

		this.make_layout();
		this.make_selector();
		this.make_actions();
		if (this.load_name) this.load_existing(this.load_name);
	}

	make_layout() {
		this.body = $(`
			<div class="dg-wrap">
				<div class="dg-selector"></div>
				<div class="dg-toolbar" style="display:none">
					<button data-cmd="bold"><b>B</b></button>
					<button data-cmd="italic"><i>I</i></button>
					<button data-cmd="underline"><u>U</u></button>
					<button data-cmd="insertUnorderedList">• List</button>
					<button data-cmd="insertOrderedList">1. List</button>
					<button data-cmd="justifyLeft">⯇</button>
					<button data-cmd="justifyCenter">≡</button>
					<button data-cmd="justifyRight">⯈</button>
					<button data-img="1">🖼 ${__("Image")}</button>
				</div>
				<div class="dg-empty text-muted">${__("Pick a template and fill the inputs — the document builds automatically.")}</div>
				<div class="dg-page-wrap"><div class="dg-doc-edit" contenteditable="true"></div></div>
			</div>
		`).appendTo(this.page.main);

		this.$selector = this.body.find(".dg-selector");
		this.$toolbar = this.body.find(".dg-toolbar");
		this.$empty = this.body.find(".dg-empty");
		this.$editor = this.body.find(".dg-doc-edit");
		this.body.find(".dg-page-wrap").hide();

		this.$toolbar.find("button").on("mousedown", (e) => {
			e.preventDefault();
			if (e.currentTarget.dataset.img) return this.insert_image();
			document.execCommand("styleWithCSS", false, true);
			document.execCommand(e.currentTarget.dataset.cmd, false, null);
		});
	}

	make_selector() {
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

	// Rebuild the document from the current inputs. Debounced so rapid edits (typing,
	// clearing competitors, BS↔AD sync) collapse into a single regeneration.
	schedule_regen() {
		if (!this.controls.template?.get_value()) return;
		clearTimeout(this._regen_timer);
		this._regen_timer = setTimeout(() => {
			if (this.inputs_ready()) this.load_document();
		}, 400);
	}

	// Only auto-build once the company and every currently-mandatory input are filled,
	// so we don't generate an empty/zero document while the user is still picking inputs.
	// (reqd is dynamic — exclusivity drops it on a bundle once a competitor is chosen.)
	inputs_ready() {
		if (this.controls.company && !this.controls.company.get_value()) return false;
		return (this.custom_inputs || []).every((inp) => {
			const ctrl = this.controls[inp.fieldname];
			return !ctrl || !ctrl.df.reqd || !!ctrl.get_value();
		});
	}

	render_params() {
		const m = this.state.meta;
		const row = $('<div class="dg-selector-row"></div>').appendTo(this.$params);
		this.custom_inputs = []; // so company's initial set_value (below) is a safe no-op
		const companies = m.companies || [];
		if (companies.length) {
			this.controls.company = this.make_control(row, {
				fieldname: "company", label: __("Company"), fieldtype: "Select",
				options: companies.join("\n"), default: companies[0], reqd: 1,
				onchange: () => { this.on_company_change(); this.schedule_regen(); },
			});
			this.controls.company.set_value(companies[0]);
		} else {
			this.controls.company = this.make_control(row, {
				fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
				onchange: () => { this.on_company_change(); this.schedule_regen(); },
			});
		}
		this.custom_inputs = (m.inputs || []).filter((i) => i.fieldname !== "company");
		this.bs_partners = {};
		this.custom_inputs.forEach((inp) => {
			const group = (inp.exclusive_group || "").trim();
			const is_date = (inp.input_type || "Data") === "Date";
			// A Link whose target doctype has a company field is scoped to the chosen company.
			const company_field = inp.company_filter_field;
			const control = this.make_control(row, {
				fieldname: inp.fieldname,
				label: inp.label || inp.fieldname,
				fieldtype: inp.input_type || "Data",
				options: inp.options || undefined,
				reqd: inp.reqd ? 1 : 0,
				exclusive_group: group || undefined,
				get_query: company_field
					? () => {
							const company = this.controls.company?.get_value();
							return company ? { filters: { [company_field]: company } } : {};
					  }
					: undefined,
				onchange: () => {
					if (group) this.sync_exclusive_groups(inp.fieldname);
					if (is_date) this.sync_ad_to_bs(inp.fieldname);
					this.schedule_regen();
				},
			});
			this.controls[inp.fieldname] = control;
			// Every AD Date input gets a paired Nepali (BS) field that two-way syncs.
			if (is_date) this.make_bs_partner(row, inp, control);
		});
		this.sync_exclusive_groups();
	}

	// Changing the company invalidates any company-scoped Link selection, so clear them.
	on_company_change() {
		(this.custom_inputs || []).forEach((inp) => {
			if (inp.company_filter_field && this.controls[inp.fieldname]?.get_value()) {
				this.controls[inp.fieldname].set_value("");
			}
		});
	}

	// Build the BS partner field for an AD Date input and attach the Nepali calendar
	// popup (nepali.datepicker, loaded globally by rdp_common_app). The AD control stays
	// the source of truth for the payload — the BS field is purely a Nepali-facing mirror.
	make_bs_partner(parent, inp, ad_control) {
		const bs = this.make_control(parent, {
			fieldname: `${inp.fieldname}_bs`,
			label: `${inp.label || inp.fieldname} (BS)`,
			fieldtype: "Data",
		});
		this.bs_partners[inp.fieldname] = bs;

		// $input isn't ready until the control renders.
		setTimeout(() => {
			const $input = bs.$input;
			if (!$input || !$input.length || $input.data("ndpAttached")) return;
			$input.attr("placeholder", "YYYY-MM-DD (BS)");
			const on_pick = () => this.sync_bs_to_ad(inp.fieldname);
			try {
				if (typeof $input.nepaliDatePicker === "function") {
					$input.nepaliDatePicker({
						ndpYear: true,
						ndpMonth: true,
						dateFormat: "YYYY-MM-DD",
						closeOnDateSelect: true,
						onChange: on_pick,
					});
				} else if ($input[0] && typeof $input[0].NepaliDatePicker === "function") {
					$input[0].NepaliDatePicker({ dateFormat: "YYYY-MM-DD", onSelect: on_pick });
				} else {
					console.warn("nepali.datepicker not loaded — BS field accepts typed dates only.");
				}
				$input.data("ndpAttached", true);
			} catch (e) {
				console.error("Failed to attach Nepali date picker:", e);
			}
			// Also handle manual typing / the picker closing on blur.
			$input.on("change.ndp blur.ndp", on_pick);
			this.sync_ad_to_bs(inp.fieldname); // seed BS from any AD default
		}, 300);
	}

	// AD changed → mirror to BS. Guarded against the BS→AD echo by _date_syncing and
	// by only writing when the converted value actually differs.
	sync_ad_to_bs(fieldname) {
		if (this._date_syncing) return;
		const ad = this.controls[fieldname];
		const bs = this.bs_partners?.[fieldname];
		if (!ad || !bs) return;
		const ad_val = (ad.get_value() || "").trim();
		this._date_syncing = true;
		try {
			if (!ad_val) {
				if (bs.get_value()) bs.set_value("");
				return;
			}
			const bs_val = window.NepaliFunctions ? window.NepaliFunctions.AD2BS(ad_val, "YYYY-MM-DD") : "";
			if (bs_val && bs.get_value() !== bs_val) bs.set_value(bs_val);
		} catch (e) {
			// leave BS untouched on a bad/partial AD value
		} finally {
			this._date_syncing = false;
		}
	}

	// BS picked/typed → convert to AD and drive the AD control (the payload source).
	sync_bs_to_ad(fieldname) {
		if (this._date_syncing) return;
		const ad = this.controls[fieldname];
		const bs = this.bs_partners?.[fieldname];
		if (!ad || !bs) return;
		const bs_val = ((bs.get_value() || bs.$input?.val()) || "").trim();
		this._date_syncing = true;
		try {
			if (!bs_val) {
				if (ad.get_value()) ad.set_value("");
				return;
			}
			const ad_val = window.NepaliFunctions ? window.NepaliFunctions.BS2AD(bs_val, "YYYY-MM-DD") : "";
			if (ad_val && ad.get_value() !== ad_val) ad.set_value(ad_val);
		} catch (e) {
			frappe.show_alert({ message: __("Invalid Nepali date: {0}", [bs_val]), indicator: "red" });
		} finally {
			this._date_syncing = false;
		}
		// Run exclusivity off the freshly-set AD value.
		if (ad.df.exclusive_group) this.sync_exclusive_groups(fieldname);
	}

	// Map of exclusive SET -> { group name -> [controls] }. An exclusive_group is a bundle
	// of inputs filled together; bundles compete ONLY within the same exclusive_set, so a
	// template can carry several independent either/or choices. Blank exclusive_set = the
	// default shared set "".
	exclusive_sets() {
		const sets = {};
		this.custom_inputs.forEach((inp) => {
			const g = (inp.exclusive_group || "").trim();
			const ctrl = this.controls[inp.fieldname];
			if (!g || !ctrl) return;
			const s = (inp.exclusive_set || "").trim(); // "" = default shared set
			const set_map = (sets[s] = sets[s] || {});
			(set_map[g] = set_map[g] || []).push(ctrl);
		});
		return sets;
	}

	_set_of_group(group) {
		const inp = this.custom_inputs.find((i) => (i.exclusive_group || "").trim() === group);
		return inp ? (inp.exclusive_set || "").trim() : "";
	}

	_orig_reqd(fieldname) {
		const inp = this.custom_inputs.find((i) => i.fieldname === fieldname);
		return inp && inp.reqd ? 1 : 0;
	}

	// Enforce mutual exclusivity PER SET (without disabling): filling an input clears the
	// competing bundles in the SAME set only — bundles in other sets are untouched. Then
	// re-sync the mandatory indicator so the chosen bundle's competitors drop their reqd.
	sync_exclusive_groups(changed) {
		if (this._syncing) return;
		const sets = this.exclusive_sets();

		if (changed) {
			const changed_ctrl = this.controls[changed];
			const changed_group = (changed_ctrl?.df.exclusive_group || "").trim();
			// Only clear competitors when the just-touched field actually holds a value.
			if (changed_group && changed_ctrl?.get_value()) {
				const groups_in_set = sets[this._set_of_group(changed_group)] || {};
				this._syncing = true;
				try {
					Object.keys(groups_in_set).forEach((g) => {
						if (g === changed_group) return;
						groups_in_set[g].forEach((c) => {
							if (c.get_value()) c.set_value(""); // clears the BS partner too via onchange
							const bs = this.bs_partners?.[c.df.fieldname];
							if (bs && bs.get_value()) bs.set_value("");
						});
					});
				} finally {
					this._syncing = false;
				}
			}
		}

		this.refresh_exclusive_mandatory(sets);
	}

	// Within each set: a bundle that holds a value is the "chosen" one, so its competitors
	// drop their mandatory marker; until something is picked, every bundle keeps its
	// configured reqd so the user is prompted to fill one. reqd is only a visual cue here
	// (nothing server-side enforces it), so this just keeps the indicator honest.
	refresh_exclusive_mandatory(sets) {
		sets = sets || this.exclusive_sets();
		Object.keys(sets).forEach((set_name) => {
			const groups = sets[set_name];
			const group_names = Object.keys(groups);
			if (group_names.length < 2) {
				// Lone bundle — no competition; keep its configured reqd.
				group_names.forEach((g) => this._apply_group_reqd(groups[g], true));
				return;
			}
			const active = group_names.find((g) => groups[g].some((c) => c.get_value()));
			group_names.forEach((g) => this._apply_group_reqd(groups[g], !active || g === active));
		});
	}

	_apply_group_reqd(controls, keep_reqd) {
		controls.forEach((c) => {
			const want = keep_reqd ? this._orig_reqd(c.df.fieldname) : 0;
			if ((c.df.reqd ? 1 : 0) !== want) {
				c.df.reqd = want;
				c.refresh();
			}
		});
	}

	build_payload() {
		const payload = { company: this.controls.company?.get_value() };
		this.custom_inputs.forEach((inp) => {
			payload[inp.fieldname] = this.controls[inp.fieldname]?.get_value();
		});
		return payload;
	}

	async load_document() {
		const template = this.controls.template.get_value();
		if (!template) {
			frappe.msgprint(__("Please select a template."));
			return false;
		}
		frappe.dom.freeze(__("Generating..."));
		try {
			const r = await frappe.call({
				method: `${API}.instantiate_document`,
				args: { template, payload: JSON.stringify(this.build_payload()) },
			});
			this.state = Object.assign(this.state, { name: null }, r.message);
			this.show_document(r.message.body_html);
			return true;
		} finally {
			frappe.dom.unfreeze();
		}
	}

	async load_existing(name) {
		const r = await frappe.call({ method: `${API}.get_generated_document`, args: { name } });
		this.state = Object.assign(this.state, r.message);
		if (this.controls.template) this.controls.template.set_value(this.state.template);
		this.show_document(r.message.body_html);
	}

	show_document(html) {
		this.$empty.hide();
		this.body.find(".dg-page-wrap").show();
		this.$toolbar.css("display", "flex");
		this.$editor.html(html || "");
	}

	insert_image() {
		const inp = document.createElement("input");
		inp.type = "file";
		inp.accept = "image/*";
		inp.onchange = () => {
			const f = inp.files[0];
			if (!f) return;
			const reader = new FileReader();
			reader.onload = () => {
				this.$editor.focus();
				document.execCommand("insertHTML", false, `<img src="${reader.result}" style="max-width:100%">`);
			};
			reader.readAsDataURL(f);
		};
		inp.click();
	}

	make_actions() {
		// No standalone Save — every Print/Email saves the current document first, so a
		// printed/emailed copy is always persisted as a Generated Document.
		// Print on pre-printed letterhead paper: reserves the header/footer space but
		// does not draw them.
		this.page.add_action_item(__("Print (letterhead paper)"), () => this.output("Print", 0));
		// Print a full digital copy with the header/footer drawn.
		this.page.add_action_item(__("Print (with letterhead)"), () => this.output("Print", 1));
		this.page.add_action_item(__("Email"), () => this.output("Email"));
	}

	body_html() {
		return this.$editor.html();
	}

	async save() {
		if (!this.state.template) return frappe.msgprint(__("Load a template first."));
		const r = await frappe.call({
			method: `${API}.save_generated_document`,
			args: {
				data: JSON.stringify({
					name: this.state.name,
					template: this.state.template,
					target_doctype: this.state.target_doctype,
					company: this.state.company,
					reference_name: this.state.reference_name,
					print_orientation: this.state.print_orientation,
					payload: this.state.payload,
					title: this.state.title,
					recipients: this.state.recipients,
					body_html: this.body_html(),
					header_html: this.state.header_html,
					footer_html: this.state.footer_html,
					header_height: this.state.header_height,
					footer_height: this.state.footer_height,
				}),
			},
		});
		this.state.name = r.message.name;
		frappe.show_alert({ message: __("Saved {0}", [r.message.name]), indicator: "green" });
		return r.message.name;
	}

	async output(action, withHeader = 0) {
		// The document already reflects the current inputs (it auto-regenerates on change),
		// so just save the latest editor content before producing the output.
		let name;
		frappe.dom.freeze(__("Saving..."));
		try {
			name = await this.save();
		} finally {
			frappe.dom.unfreeze();
		}
		if (!name) return;
		if (action === "Print") await this.download_pdf(name, withHeader);
		if (action === "Email") this.prompt_email(name);
	}

	// Open the PDF in a new tab via a blob URL (Chrome's normal PDF viewer).
	// This is a "view", not a download, so it never triggers Chrome's scary
	// "insecure download" banner on http sites. The user saves/prints from the viewer.
	async download_pdf(name, withHeader = 0) {
		// Open the tab synchronously to keep the user-gesture (avoids popup blocking).
		const tab = window.open("", "_blank");
		frappe.dom.freeze(__("Preparing PDF..."));
		try {
			const url = `/api/method/${API}.download_document_pdf?generated_document=${encodeURIComponent(
				name
			)}&with_header=${withHeader ? 1 : 0}`;
			const resp = await fetch(url, { credentials: "same-origin" });
			if (!resp.ok) {
				if (tab) tab.close();
				frappe.msgprint(__("Could not generate the PDF."));
				return;
			}
			const blobUrl = URL.createObjectURL(await resp.blob());
			if (tab) {
				tab.location.href = blobUrl;
			} else {
				// Popup blocked — fall back to a blob download (no insecure-http warning).
				const a = document.createElement("a");
				a.href = blobUrl;
				a.download = `${this.state.title || "document"}.pdf`;
				document.body.appendChild(a);
				a.click();
				a.remove();
			}
			setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
		} finally {
			frappe.dom.unfreeze();
		}
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
