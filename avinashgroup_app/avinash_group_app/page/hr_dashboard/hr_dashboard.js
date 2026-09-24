// Full-width HR Dashboard with the menu down the left side. The dashboard
// itself lives in public/js/hr_dashboard.js, shared with the HR Home workspace.

frappe.pages["hr-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("HR Dashboard"), single_column: true });
	frappe.require(["/assets/avinashgroup_app/js/hr_dashboard.js", "/assets/avinashgroup_app/css/hr_dashboard.css"], () => {
		wrapper.hr_dashboard = avinash_hr_dashboard.mount(page.main[0], { menu: "side" });
	});
};

frappe.pages["hr-dashboard"].on_page_show = function (wrapper) {
	wrapper.hr_dashboard && wrapper.hr_dashboard.refresh();
};
