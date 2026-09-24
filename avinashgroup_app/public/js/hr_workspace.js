// The HR dashboard at the top of the stock HR workspace (/app/hr).
//
// The HR workspace belongs to HRMS (hrms/hr/workspace/hr/hr.json). Editing it
// in the desk would be undone by the next HRMS update — and in developer mode
// saving it writes straight into apps/hrms. So the dashboard is not a block in
// that workspace: it is placed above the workspace's editor after each render,
// where the editor never sees it and "Edit → Save" can never store it.
//
// Also hides HRMS's "Let's Set Up the Human Resource Module" onboarding on the
// HR page only — the setup it walks through is done, and the dashboard's
// "Employee data missing" list is the real checklist here.
// The dashboard itself: public/js/hr_dashboard.js.

(function () {
	const WORKSPACE = "HR";
	const ROLES = ["HR Manager", "HR User", "System Manager"];
	const ASSETS = ["/assets/avinashgroup_app/js/hr_dashboard.js", "/assets/avinashgroup_app/css/hr_dashboard.css"];

	function patch() {
		const Workspace = frappe.views && frappe.views.Workspace;
		if (!Workspace || Workspace.prototype.__hr_dashboard_patched) return;
		const show_page = Workspace.prototype.show_page;
		Workspace.prototype.show_page = async function (page) {
			const result = await show_page.apply(this, arguments);
			place(this, page);
			return result;
		};
		Workspace.prototype.__hr_dashboard_patched = true;
	}

	function place(workspace, page) {
		const on_hr = page && page.name === WORKSPACE && ROLES.some((r) => frappe.user.has_role(r));
		let $box = workspace.body.children(".hr-workspace-dashboard");
		workspace.body.toggleClass("hr-workspace-has-dashboard", !!on_hr);
		if (!on_hr) return $box.hide();

		if (!$box.length) {
			$box = $('<div class="hr-workspace-dashboard"></div>').prependTo(workspace.body);
			frappe.require(ASSETS, () => {
				workspace.hr_dashboard = avinash_hr_dashboard.mount($box[0], { menu: "top" });
			});
		} else if (workspace.hr_dashboard) {
			workspace.hr_dashboard.refresh(); // back on HR: fresh numbers
		}
		$box.show();
	}

	$(document).ready(patch);
	patch();
})();
