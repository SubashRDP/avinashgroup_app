// Live document-number preview for doctypes with Numbering Configuration rules.
//
// While the user fills a draft, any change to a field the rules depend on
// (type, company, dates, document no, word, ...) asks the server what number
// the engine WOULD assign (counter peeked, never consumed) and shows it as a
// small alert — so the voucher number is visible before the document is saved.

(function () {
	const DEBOUNCE_MS = 500;
	let timer = null;

	function show_preview(frm) {
		// drafts only — submitted/cancelled documents never renumber
		if (frm.doc.docstatus !== 0) return;

		frappe.call({
			method: "avinashgroup_app.custom_code.Override.naming_series.preview_document_number",
			args: { doc: frm.doc },
			callback(r) {
				const res = r.message;
				if (!res || !res.number) return;
				// skip when the doc already carries this exact number
				if ((frm.doc[res.target_field] || "") === res.number) return;
				if (frm._numbering_preview_last === res.number) return;
				frm._numbering_preview_last = res.number;
				frappe.show_alert(
					{
						message: __("{0} will be: <b>{1}</b>", [
							__(res.label),
							frappe.utils.escape_html(res.number),
						]),
						indicator: "blue",
					},
					6
				);
			},
		});
	}

	function schedule_preview(frm) {
		clearTimeout(timer);
		timer = setTimeout(() => show_preview(frm), DEBOUNCE_MS);
	}

	frappe.call({
		method: "avinashgroup_app.custom_code.Override.naming_series.get_numbering_preview_config",
		callback(r) {
			const config = r.message || {};
			Object.keys(config).forEach((doctype) => {
				const handlers = {
					onload_post_render(frm) {
						if (frm.is_new()) schedule_preview(frm);
					},
				};
				config[doctype].forEach((field) => {
					handlers[field] = schedule_preview;
				});
				frappe.ui.form.on(doctype, handlers);
			});
		},
	});
})();
