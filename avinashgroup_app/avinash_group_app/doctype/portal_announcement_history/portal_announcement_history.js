// Copyright (c) 2026, Avinash Group and contributors
// For license information, please see license.txt

// Draws the Preview field the same way the popup lays out an announcement:
// title, then image, then the body — Custom HTML replaces the Message when filled.
// It renders inside an iframe so <style> tags in the Custom HTML cannot restyle the desk.
frappe.ui.form.on("Portal Announcement History", {
	refresh(frm) {
		const doc = frm.doc;
		const has_custom = !!(doc.custom_html || "").trim();
		const body = has_custom ? doc.custom_html : doc.message || "";
		const image = doc.image ? `<img src="${encodeURI(doc.image)}" alt="">` : "";

		const page = `<!doctype html><html><head><base target="_blank">
			<style>
				body { margin: 0; padding: 16px; font-family: system-ui, sans-serif; color: #1f2937; }
				h3 { margin: 0 0 12px; font-size: 18px; }
				img { display: block; max-width: 100%; height: auto; margin-bottom: 12px; border-radius: 6px; }
			</style></head>
			<body><h3>${frappe.utils.escape_html(doc.title || "")}</h3>${image}<div>${body}</div></body></html>`;

		const $wrapper = frm.get_field("preview").$wrapper;
		$wrapper.empty();

		// allow-same-origin only, no allow-scripts: the frame's height can be read
		// from here, but nothing inside it can run.
		const iframe = $(
			'<iframe sandbox="allow-same-origin allow-popups" ' +
				'style="width:100%;max-width:560px;border:1px solid var(--border-color);border-radius:10px;background:#fff;"></iframe>'
		).appendTo($wrapper)[0];

		iframe.onload = () => {
			const height = iframe.contentDocument ? iframe.contentDocument.documentElement.scrollHeight : 400;
			iframe.style.height = height + "px";
		};
		iframe.srcdoc = page;
	},
});
