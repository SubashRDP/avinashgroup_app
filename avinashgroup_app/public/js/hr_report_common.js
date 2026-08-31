/**
 * Shared cell renderers for the HR/payroll reports.
 *
 * The employee cell exists because a Link column to Employee renders
 * "NGI-EMP-00015: Baburam Mahato" on one line: at any sane column width the
 * name is clipped, and reports that also carry a Name column print the same
 * name twice side by side. Stacking name over ID inside one clickable cell
 * fits, reads, and frees a column.
 *
 * Lives here rather than in a report's own JS so Monthly Attendance BS,
 * Yearly Leave Details BS and Work On Holiday BS share one implementation and
 * one stylesheet. Loaded from hooks.py app_include_js.
 */
window.NepalHR = window.NepalHR || {};

(function (NepalHR) {
	const STYLE_ID = "nepal-hr-report-cells";

	function injectStyles() {
		if (document.getElementById(STYLE_ID)) return;
		$(`<style id="${STYLE_ID}">
			/* .dt-cell__content is built for one line — white-space: nowrap,
			   overflow: hidden and 8px padding — which clips the second line
			   away entirely. Relax it for this cell only. */
			.dt-cell:not(.dt-cell--header) .dt-cell__content:has(.nepal-emp-cell) {
				padding: 0;
				white-space: normal;
			}
			.nepal-emp-cell {
				display: flex;
				flex-direction: column;
				justify-content: center;
				gap: 1px;
				height: 100%;
				width: 100%;
				padding: 3px 10px;
				text-decoration: none;
				color: inherit;
				line-height: 1.2;
			}
			.nepal-emp-cell:hover { background: #F5F2EE; }
			.nepal-emp-cell:focus-visible {
				outline: 2px solid var(--primary, #2490EF);
				outline-offset: -2px;
			}
			.nepal-emp-name {
				font-weight: 500;
				color: #2F3437;
				white-space: nowrap;
				overflow: hidden;
				text-overflow: ellipsis;
			}
			.nepal-emp-id {
				font-size: 11px;
				color: var(--text-light, #8D8D8D);
				font-variant-numeric: tabular-nums;
				white-space: nowrap;
				overflow: hidden;
				text-overflow: ellipsis;
			}
			.nepal-emp-cell:hover .nepal-emp-name { color: var(--primary, #2490EF); }
		</style>`).appendTo("head");
	}

	/**
	 * Name over ID in one cell, the whole cell a link to the Employee doc.
	 * The anchor fills the cell so the dead space between the two lines is
	 * clickable too — a 15px target inside a 42px row is fiddly to hit.
	 *
	 * Returns null when there is no employee on the row, so the caller can
	 * fall through to the default formatter (total rows, group headers).
	 */
	NepalHR.employeeCell = function (data) {
		if (!data || !data.employee) return null;
		injectStyles();
		const name = frappe.utils.escape_html(data.employee_name || "");
		const id = frappe.utils.escape_html(data.employee);
		return `
			<a class="nepal-emp-cell" href="/app/employee/${encodeURIComponent(data.employee)}"
			   title="${name} — ${id}">
				<span class="nepal-emp-name">${name || id}</span>
				<span class="nepal-emp-id">${id}</span>
			</a>`;
	};
})(window.NepalHR);
