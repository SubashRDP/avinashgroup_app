// Company-specific print templates (Company Print Template doctype: one
// record per Document Type, one child row per company).
//
// Rules map (Document Type, Company) -> Print Format — plus an optional
// Return Print Format used when the document has is_return set — and are
// fetched once per desk session from
// company_print_template.get_print_templates (redis-cached server-side,
// invalidated when a rule changes; the endpoint flattens the child rows so
// this file never sees the parent/child shape). Two behaviours:
//
//   1. Print view default: set_default_print_format is patched so a document
//      whose company has a rule opens the Print view with that format
//      pre-selected (instead of the doctype-wide default, and instead of the
//      sticky last-used format — company must win when switching between
//      documents of different companies).
//
//   2. Print Immediately on Submit: for doctypes with such a rule, submitting
//      from the desk opens the print in a new tab at once. Formats whose
//      pdf_generator is "chrome" (the mm-exact NGI overlays) open through
//      download_pdf — same route ngi_print.js uses for the Print button —
//      while everything else opens /printview?trigger_print=1, which pops the
//      browser print dialog directly. Both routes count as an actual print
//      for the IRD copy counter (print_count.py).
//
// Submit detection needs TWO hooks because of save_and_submit.py: a Sales
// Invoice desk Save is escalated to Submit server-side, so the client never
// runs savesubmit and "on_submit" never fires — the doc simply comes back
// from a plain Save with docstatus 1. before_save records that the doc was a
// draft; after_save treats draft -> submitted as the submit signal. Ordinary
// doctypes fire "on_submit" normally. A per-doc set de-dupes if both fire.
// Documents submitted by a Workflow approval action reload server-side and
// trigger neither event — workflow-approved doctypes don't auto-print.

(function () {
	let rules = null; // {doctype: {company: rule}}
	const auto_printed = new Set();

	function get_rule(doctype, doc) {
		if (!rules || !doc) return null;
		const company = doc.company || doc.custom_company;
		return (rules[doctype] && rules[doctype][company]) || null;
	}

	// Returns {format, generator} — the return-specific format when the doc
	// is a return (credit/debit note) and one is configured, else the normal.
	function pick_format(rule, doc) {
		if (cint(doc.is_return) && rule.return_print_format) {
			return { format: rule.return_print_format, generator: rule.return_pdf_generator };
		}
		return { format: rule.print_format, generator: rule.pdf_generator };
	}

	// ------------------------------------------------------------------
	// 1. Print view: default the format to the company's template
	// ------------------------------------------------------------------

	function patch(cls) {
		if (!cls || cls.prototype._company_print_patched) return cls;
		const orig = cls.prototype.set_default_print_format;
		cls.prototype.set_default_print_format = function () {
			const rule = this.frm && get_rule(this.frm.doctype, this.frm.doc);
			if (rule) {
				const sel = pick_format(rule, this.frm.doc);
				if (frappe.meta.get_print_formats(this.frm.doctype).includes(sel.format)) {
					this.print_format_selector.empty();
					this.print_format_selector.val(sel.format);
					return;
				}
			}
			return orig.apply(this, arguments);
		};
		cls.prototype._company_print_patched = true;
		return cls;
	}

	// print/print.js loads lazily and assigns frappe.ui.form.PrintView then.
	// ngi_print.js already guards the property with its own get/set pair —
	// chain through the existing descriptor (so its printit patch still
	// applies) instead of replacing it. patch() is idempotent either way.
	const prev = Object.getOwnPropertyDescriptor(frappe.ui.form, "PrintView");
	let PV = patch(frappe.ui.form.PrintView);
	Object.defineProperty(frappe.ui.form, "PrintView", {
		get() {
			return prev && prev.get ? patch(prev.get()) : PV;
		},
		set(cls) {
			if (prev && prev.set) {
				prev.set(cls);
				PV = patch(prev.get());
			} else {
				PV = patch(cls);
			}
		},
		configurable: true,
	});

	// ------------------------------------------------------------------
	// 2. Print immediately on submit
	// ------------------------------------------------------------------

	function auto_print(frm) {
		const rule = get_rule(frm.doctype, frm.doc);
		if (!rule || !cint(rule.print_on_submit)) return;

		const key = frm.doctype + ":" + frm.doc.name;
		if (auto_printed.has(key)) return;
		auto_printed.add(key);

		const sel = pick_format(rule, frm.doc);
		let url;
		if (sel.generator === "chrome") {
			url =
				"/api/method/frappe.utils.print_format.download_pdf?" +
				new URLSearchParams({
					doctype: frm.doctype,
					name: frm.doc.name,
					format: sel.format,
					no_letterhead: "0",
				});
		} else {
			url =
				"/printview?" +
				new URLSearchParams({
					doctype: frm.doctype,
					name: frm.doc.name,
					format: sel.format,
					no_letterhead: "0",
					trigger_print: "1",
				});
		}
		url = frappe.urllib.get_full_url(url);

		const w = window.open(url);
		if (!w) {
			// Popup blocked (window.open ran outside the click's user
			// activation): hand the user a link instead of losing the print.
			frappe.msgprint({
				title: __("Print ready"),
				indicator: "blue",
				message: __("The browser blocked the print window. {0}", [
					`<a href="${url}" target="_blank" rel="noopener">${__("Open print")}</a>`,
				]),
			});
		}
	}

	function register_auto_print(doctypes) {
		doctypes.forEach(function (dt) {
			frappe.ui.form.on(dt, {
				before_save(frm) {
					frm.__cpt_was_draft = frm.doc.docstatus === 0;
				},
				after_save(frm) {
					if (frm.__cpt_was_draft && frm.doc.docstatus === 1) {
						auto_print(frm); // Save escalated to Submit server-side
					}
					frm.__cpt_was_draft = false;
				},
				on_submit(frm) {
					auto_print(frm);
				},
			});
		});
	}

	// ------------------------------------------------------------------
	// Load rules once the desk session is up
	// ------------------------------------------------------------------

	$(document).on("app_ready", function () {
		frappe
			.xcall(
				"avinashgroup_app.avinash_group_app.doctype.company_print_template.company_print_template.get_print_templates"
			)
			.then(function (list) {
				rules = {};
				const submit_doctypes = new Set();
				(list || []).forEach(function (r) {
					rules[r.document_type] = rules[r.document_type] || {};
					rules[r.document_type][r.company] = r;
					if (cint(r.print_on_submit)) {
						submit_doctypes.add(r.document_type);
					}
				});
				register_auto_print([...submit_doctypes]);
			})
			.catch(function () {
				// Config fetch failing must never break the desk; printing
				// simply falls back to stock behaviour.
			});
	});
})();
