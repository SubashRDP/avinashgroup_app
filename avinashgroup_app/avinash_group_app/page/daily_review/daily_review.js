// Daily Business Review: the six figures the management meeting goes through every
// morning, opened from the CEO Dashboard. The page itself is
// public/js/daily_review.js (+ css/daily_review.css); figures come from
// avinashgroup_app.ceo_dashboard.daily_review, which runs the existing reports.
//
// Loaded with our own ?v= for the same reason as the CEO Dashboard loader (see
// page/ceo_dashboard/ceo_dashboard.js): bump DAILY_REVIEW_ASSET_VERSION and
// the "modified" stamp in daily_review.json whenever either file changes.

var DAILY_REVIEW_ASSET_VERSION = 1; // var: the page script may be evaluated twice

function daily_review_load_assets() {
	const base = "/assets/avinashgroup_app";
	const v = `?v=${DAILY_REVIEW_ASSET_VERSION}`;
	if (!document.querySelector(`link[data-dr-css="${DAILY_REVIEW_ASSET_VERSION}"]`)) {
		const link = document.createElement("link");
		link.rel = "stylesheet";
		link.href = `${base}/css/daily_review.css${v}`;
		link.dataset.drCss = DAILY_REVIEW_ASSET_VERSION;
		document.head.appendChild(link);
	}
	if (window.avinash_daily_review) return Promise.resolve();
	return new Promise((resolve, reject) => {
		const s = document.createElement("script");
		s.src = `${base}/js/daily_review.js${v}`;
		s.onload = resolve;
		s.onerror = () => reject(new Error("Could not load daily_review.js"));
		document.head.appendChild(s);
	});
}

frappe.pages["daily-review"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Daily Business Review"), single_column: true });
	daily_review_load_assets()
		.then(() => {
			wrapper.daily_review = avinash_daily_review.mount(page.main[0], page);
		})
		.catch((e) => frappe.msgprint(e.message));
};

frappe.pages["daily-review"].on_page_show = function (wrapper) {
	if (wrapper.daily_review) wrapper.daily_review.show();
};
