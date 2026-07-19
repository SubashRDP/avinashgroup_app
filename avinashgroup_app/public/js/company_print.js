// Company-specific print templates (Company Print Template doctype: one
// record per Document Type, one child row per company).
//
// Rules map (Document Type, Company) -> Print Format — plus an optional
// Return Print Format used when the document has is_return set — and come
// from company_print_template.get_print_templates (redis-cached server-side,
// invalidated when a rule changes; the endpoint flattens the child rows so
// this file never sees the parent/child shape). Fetched at app_ready, then
// re-fetched whenever a Company Print Template is saved (realtime event
// published by the doctype) and on every Print view open — an edited rule
// must win in already-open desk sessions, not only after a reload. Three
// behaviours:
//
//   1. Direct print from the form: Form.print_doc (the Print menu item, the
//      toolbar printer icon, Ctrl+P) is patched so a saved document whose
//      company has a rule prints AT ONCE with that format — no Print view, no
//      "choose format" step. An alert offers a link to the Print view for the
//      rare case a different format is wanted. Dirty/new documents fall back
//      to the stock Print view (a direct print would render the saved version
//      and silently drop the user's unsaved edits).
//
//   2. Print view default: set_default_print_format is patched so a document
//      whose company has a rule opens the Print view with that format
//      pre-selected (instead of the doctype-wide default, and instead of the
//      sticky last-used format — company must win when switching between
//      documents of different companies). Reached via the alert link in (1),
//      or for doctypes/companies with no rule.
//
//   3. Print Immediately on Submit: for doctypes with such a rule, submitting
//      from the desk opens the print in a new tab at once.
//
// (1) and (3) share one routing rule: formats whose pdf_generator is "chrome"
// (the mm-exact NGI overlays) open through download_pdf — same route
// ngi_print.js uses for the Print view's Print button — while everything else
// opens /printview?trigger_print=1, which pops the browser print dialog
// directly. Both routes count as an actual print for the IRD copy counter
// (print_count.py).
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
	// Raw queue created on every office print machine by PrintBridgeSetup.exe:
	// Generic/Text Only driver, so RAW ESC/P bytes bypass the Epson driver that
	// swallows them. Kept as the client-side default; the agent reports its own
	// via /ping (avinash.print_bridge.default_printer).
	const DEFAULT_RAW_PRINTER = "LQ310-RAW";

	let rules = null; // {doctype: {company: rule}}
	let rules_request = null; // in-flight fetch, shared by concurrent callers
	const auto_printed = new Set();
	const registered_doctypes = new Set();

	function load_rules() {
		if (!rules_request) {
			rules_request = frappe
				.xcall(
					"avinashgroup_app.avinash_group_app.doctype.company_print_template.company_print_template.get_print_templates"
				)
				.then(function (list) {
					rules = {};
					(list || []).forEach(function (r) {
						rules[r.document_type] = rules[r.document_type] || {};
						rules[r.document_type][r.company] = r;
					});
					register_auto_print(Object.keys(rules));
				})
				.catch(function () {
					// Config fetch failing must never break the desk; keep the
					// last-known rules (stock behaviour when none loaded yet).
				})
				.then(function () {
					rules_request = null;
				});
		}
		return rules_request;
	}

	function get_rule(doctype, doc) {
		if (!rules || !doc) return null;
		const company = doc.company || doc.custom_company;
		return (rules[doctype] && rules[doctype][company]) || null;
	}

	// Returns {format, generator, raw} — the return-specific format when the
	// doc is a return (credit/debit note) and one is configured, else the normal.
	function pick_format(rule, doc) {
		if (cint(doc.is_return) && rule.return_print_format) {
			return {
				format: rule.return_print_format,
				generator: rule.return_pdf_generator,
				raw: cint(rule.return_raw_printing),
			};
		}
		return {
			format: rule.print_format,
			generator: rule.pdf_generator,
			raw: cint(rule.raw_printing),
		};
	}

	// Raw (ESC/P) formats must never go through /printview — the browser
	// print dialog renders HTML through the OS printer driver, which dumps
	// the text at the top of the form. Send the rendered raw commands to the
	// printer through the Print Bridge instead. Rendering server-side bumps the
	// IRD copy counter, same as the other routes. Uses the same localStorage
	// printer mapping as the Print view ("Printer Settings" there); without a
	// mapping the agent's default queue (LQ310-RAW) is used.
	function raw_print(doctype, name, sel) {
		frappe.call({
			method: "frappe.www.printview.get_rendered_raw_commands",
			args: { doc: doctype, name: name, print_format: sel.format },
			callback: function (r) {
				if (r.exc) return;
				let mapping = [];
				try {
					const map = JSON.parse(localStorage.print_format_printer_map)[doctype] || [];
					mapping = map.filter(function (m) {
						return m.print_format === sel.format;
					});
				} catch (e) {
					mapping = [];
				}
				// The Print Bridge is the ONLY raw transport now — QZ Tray is
				// gone. A machine without the agent is told to install it rather
				// than falling back to QZ's every-session prompt and instability.
				avinash.print_bridge.available().then(function (has_bridge) {
					if (has_bridge) {
						const printer = mapping.length === 1 ? mapping[0].printer : DEFAULT_RAW_PRINTER;
						avinash.print_bridge
							.print(printer, r.message.raw_commands)
							.then(function () {
								frappe.show_alert(
									{ message: __("Printing via {0}", [printer]), indicator: "green" },
									5
								);
							})
							.catch(function (err) {
								frappe.show_alert(
									{
										message: __("Print bridge: {0}", [err.message]),
										indicator: "red",
									},
									10
								);
							});
						return;
					}
					// No agent on this machine: tell the user to install it.
					// QZ Tray is gone (see print_bridge.js) — never launched here.
					avinash.print_bridge.show_not_installed();
				});
			},
		});
	}

	// Open the actual print output for (doctype, name) with the selected
	// format: chrome formats via download_pdf, the rest via the browser print
	// dialog. Both bump the IRD copy counter server-side.
	function open_print(doctype, name, sel) {
		if (sel.raw) {
			raw_print(doctype, name, sel);
			return;
		}
		let url;
		if (sel.generator === "chrome") {
			url =
				"/api/method/frappe.utils.print_format.download_pdf?" +
				new URLSearchParams({
					doctype: doctype,
					name: name,
					format: sel.format,
					no_letterhead: "0",
				});
		} else {
			url =
				"/printview?" +
				new URLSearchParams({
					doctype: doctype,
					name: name,
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

	// ------------------------------------------------------------------
	// 1. Direct print from the form — skip the "choose format" step
	// ------------------------------------------------------------------

	// Form.print_doc is the single entry point for the Print menu item, the
	// toolbar printer icon, and Ctrl+P. With a company rule the format choice
	// is already made — print straight away instead of routing to the Print
	// view. Everything else (no rule, unknown format, unsaved changes) falls
	// through to the stock behaviour.
	const FormCls = frappe.ui.form.Form;
	if (FormCls && !FormCls.prototype._company_print_doc_patched) {
		const orig_print_doc = FormCls.prototype.print_doc;
		FormCls.prototype.print_doc = function () {
			const frm = this;
			// A direct print renders the SAVED document; with unsaved edits the
			// stock Print view (which warns about them) is the honest path.
			if (frm.doc.__islocal || frm.is_dirty()) {
				return orig_print_doc.apply(this, arguments);
			}
			load_rules().then(function () {
				const rule = get_rule(frm.doctype, frm.doc);
				const sel = rule && pick_format(rule, frm.doc);
				if (!sel || !frappe.meta.get_print_formats(frm.doctype).includes(sel.format)) {
					return orig_print_doc.call(frm);
				}
				open_print(frm.doctype, frm.doc.name, sel);
				const print_view_url = frappe.urllib.get_full_url(
					"/app/print/" +
						encodeURIComponent(frm.doctype) +
						"/" +
						encodeURIComponent(frm.doc.name)
				);
				frappe.show_alert(
					{
						message: __("Printing {0} — {1}", [
							frappe.utils.escape_html(sel.format),
							`<a href="${print_view_url}">${__("choose another format")}</a>`,
						]),
						indicator: "blue",
					},
					7
				);
			});
		};
		FormCls.prototype._company_print_doc_patched = true;
	}

	// ------------------------------------------------------------------
	// 2. Print view: default the format to the company's template
	// ------------------------------------------------------------------

	function patch(cls) {
		if (!cls || cls.prototype._company_print_patched) return cls;
		const orig = cls.prototype.set_default_print_format;
		cls.prototype.set_default_print_format = function () {
			const args = arguments;
			// Re-fetch the rules first (cheap: redis-cached server-side) so a
			// template edited after this desk session loaded still wins here.
			// show() runs this through frappe.run_serially, which waits on the
			// returned promise before rendering the preview.
			return load_rules().then(() => {
				const rule = this.frm && get_rule(this.frm.doctype, this.frm.doc);
				if (rule) {
					const sel = pick_format(rule, this.frm.doc);
					if (frappe.meta.get_print_formats(this.frm.doctype).includes(sel.format)) {
						this.print_format_selector.empty();
						this.print_format_selector.val(sel.format);
						return;
					}
				}
				return orig.apply(this, args);
			});
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
	// 3. Print immediately on submit
	// ------------------------------------------------------------------

	function auto_print(frm) {
		const rule = get_rule(frm.doctype, frm.doc);
		if (!rule || !cint(rule.print_on_submit)) return;

		const key = frm.doctype + ":" + frm.doc.name;
		if (auto_printed.has(key)) return;
		auto_printed.add(key);

		open_print(frm.doctype, frm.doc.name, pick_format(rule, frm.doc));
	}

	// Handlers are registered for every doctype that has any rule — whether to
	// actually print is decided at fire time (auto_print re-reads the rule), so
	// toggling Print on Submit mid-session behaves once the rules re-fetch.
	function register_auto_print(doctypes) {
		doctypes.forEach(function (dt) {
			if (registered_doctypes.has(dt)) return;
			registered_doctypes.add(dt);
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
	// Load rules when the desk session is up; keep them fresh via realtime
	// ------------------------------------------------------------------

	$(document).on("app_ready", function () {
		load_rules();
		frappe.realtime.on("company_print_templates_updated", function () {
			load_rules();
		});
	});
})();
