// Full-width CEO Dashboard. The dashboard itself is public/js/ceo_dashboard.js
// (+ css/ceo_dashboard.css); data comes from avinashgroup_app.ceo_dashboard.data.
//
// The two files are loaded here with a plain <script>/<link> and our own ?v=,
// not frappe.require: /assets is cached for a year and frappe.require only
// busts that cache on `bench build`, and it cannot take a path that already
// has a query string (AssetManager.extn reads the extension after the "?").
// Bump CEO_DASHBOARD_ASSET_VERSION and the "modified" stamp in
// ceo_dashboard.json whenever either file changes; the stamp is what makes
// browsers drop their cached copy of this loader.

var CEO_DASHBOARD_ASSET_VERSION = 136; // var: the page script may be evaluated twice

function ceo_dashboard_load_assets() {
	const base = "/assets/avinashgroup_app";
	const v = `?v=${CEO_DASHBOARD_ASSET_VERSION}`;
	if (!document.querySelector(`link[data-ceo-css="${CEO_DASHBOARD_ASSET_VERSION}"]`)) {
		const link = document.createElement("link");
		link.rel = "stylesheet";
		link.href = `${base}/css/ceo_dashboard.css${v}`;
		link.dataset.ceoCss = CEO_DASHBOARD_ASSET_VERSION;
		document.head.appendChild(link);
	}
	if (window.avinash_ceo_dashboard) return Promise.resolve();
	return new Promise((resolve, reject) => {
		const s = document.createElement("script");
		s.src = `${base}/js/ceo_dashboard.js${v}`;
		s.onload = resolve;
		s.onerror = () => reject(new Error("Could not load ceo_dashboard.js"));
		document.head.appendChild(s);
	});
}

frappe.pages["ceo-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("CEO Dashboard"), single_column: true });
	ceo_dashboard_load_assets()
		.then(() => {
			wrapper.ceo_dashboard = avinash_ceo_dashboard.mount(page.main[0], page);
		})
		.catch((e) => frappe.msgprint(e.message));
};
