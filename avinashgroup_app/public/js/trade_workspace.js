// The Selling and Buying dashboards at the top of the stock Selling (/app/selling)
// and Buying (/app/buying) workspaces.
//
// Both workspaces belong to ERPNext (erpnext/selling/workspace, buying/workspace).
// Editing them in the desk would be undone by the next ERPNext update — and in
// developer mode saving writes straight into apps/erpnext. So the dashboard is
// not a block in the workspace: it is placed above the workspace's editor after
// each render, where "Edit → Save" can never store it. Same approach as
// hr_workspace.js; the two patches chain, each with its own flag.
// The dashboard itself: public/js/trade_dashboard.js (+ css/trade_dashboard.css),
// loaded only when one of these workspaces is opened.

(function () {
	// workspace name → dashboard mode, and the roles that see it. The server
	// checks the same roles (sales_purchase/dashboard.py MODES); this copy only
	// avoids loading the assets for someone who would be refused.
	const BOARDS = {
		Selling: { mode: "selling", roles: ["Sales User", "Sales Manager", "Accounts User", "Accounts Manager", "System Manager"] },
		Buying: { mode: "buying", roles: ["Purchase User", "Purchase Manager", "Accounts User", "Accounts Manager", "System Manager"] },
	};
	// No "?v=" here: frappe.require picks its loader from the file extension,
	// and a query string makes it read "js?v=1" and throw.
	const ASSETS = ["/assets/avinashgroup_app/js/trade_dashboard.js", "/assets/avinashgroup_app/css/trade_dashboard.css"];

	function patch() {
		const Workspace = frappe.views && frappe.views.Workspace;
		if (!Workspace || Workspace.prototype.__trade_dashboard_patched) return;
		const show_page = Workspace.prototype.show_page;
		Workspace.prototype.show_page = async function (page) {
			const result = await show_page.apply(this, arguments);
			place(this, page);
			return result;
		};
		Workspace.prototype.__trade_dashboard_patched = true;
	}

	function place(workspace, page) {
		const board = page && BOARDS[page.name];
		const allowed = board && board.roles.some((r) => frappe.user.has_role(r));
		workspace.trade_dashboards = workspace.trade_dashboards || {};

		// Hide every board that is not for this page.
		workspace.body.children(".trade-workspace-dashboard").each(function () {
			$(this).toggle(!!allowed && $(this).data("mode") === board.mode);
		});
		if (!allowed) return;

		let $box = workspace.body.children(`.trade-workspace-dashboard[data-mode="${board.mode}"]`);
		if (!$box.length) {
			$box = $(`<div class="trade-workspace-dashboard" data-mode="${board.mode}"></div>`).prependTo(workspace.body);
			frappe.require(ASSETS, () => {
				workspace.trade_dashboards[board.mode] = avinash_trade_dashboard.mount($box[0], { mode: board.mode });
			});
		} else if (workspace.trade_dashboards[board.mode]) {
			workspace.trade_dashboards[board.mode].refresh(); // back on the page: fresh numbers (cached ≤5 min)
		}
		$box.show();
	}

	$(document).ready(patch);
	patch();
})();
