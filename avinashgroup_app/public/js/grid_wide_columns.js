// Child tables cap out at ten columns in Frappe v15. This lifts the cap.
//
// The grid gives each row a budget of 11 "column units" (Bootstrap twelfths,
// less one for the row-index gutter). `Grid.setup_visible_columns` walks the
// configured columns adding up their widths and bails out of the loop with
// `return false` the moment the running total passes 11 -- so every column
// after that point is silently dropped, with no error and nothing in the
// console. With each column set to width 1 that lands you on exactly ten.
// The Configure Columns dialog enforces the same ceiling up front, throwing
// "The total column width cannot be more than 10."
//
// Frappe v16 removed both. Past 10 units it tags the grid container
// `.column-limit-reached`, which swaps the percentage-based Bootstrap widths
// for fixed pixel ones and lets the container scroll sideways instead of
// wrapping. This file is that change, backported; grid_wide_columns.css
// carries the styling half.
//
// It is a prototype patch rather than an edit to apps/frappe so that
// `bench update` cannot quietly revert it. Grid and GridRow are ES module
// classes with no handle on `frappe.ui.form`, so both prototypes are reached
// through the first live instance instead: ControlTable.make() builds a Grid,
// and Grid.make_head() builds the header GridRow that owns the dialog.

(() => {
	const WIDE_CLASS = "column-limit-reached";
	const PATCH_FLAG = "_agx_wide_columns_patched";
	const DROPDOWN_CLASS = "agx-grid-dropdown";

	// ------------------------------------------------------------------
	// GridRow.prototype -- drop the Configure Columns ceiling
	// ------------------------------------------------------------------

	// Lift a Link cell's autocomplete list out of the scrolling container.
	//
	// A scroll container clips BOTH axes -- `overflow-x: auto` forces the
	// other axis to clip too -- and the grid container is only about one row
	// tall, so a list opening inside a cell is cut to nothing. The list is
	// re-parented once, onto the grid wrapper; its position is recomputed on
	// every focus so it still lands under the right cell after the grid has
	// been scrolled sideways.
	//
	// The list keeps a `.awesomplete` parent at its new home, so awesomplete's
	// own `.awesomplete > [role="listbox"]` styling still applies.
	function bind_dropdown_escape($col, grid_row) {
		$col.on("focusin", function () {
			const grid = grid_row.grid;
			const $wrapper = grid && grid.wrapper;
			// A grid inside the old budget clips nothing -- leave it alone.
			if (!$wrapper || !$wrapper.children(".form-grid-container").hasClass(WIDE_CLASS)) {
				return;
			}

			const cell = this;
			// the control, and with it the awesomplete, is built lazily when
			// the row goes editable -- give it a tick to exist
			frappe.utils.sleep(150).then(() => {
				let $host = $col.data("agx_dropdown_host");

				if (!$host || !$host.parent().length) {
					const $list = $col.find(".awesomplete > ul").first();
					if (!$list.length) return;
					$host = $(`<div class="awesomplete ${DROPDOWN_CLASS}"></div>`).appendTo(
						$wrapper
					);
					$host.append($list);
					$col.data("agx_dropdown_host", $host);
				}

				const c = cell.getBoundingClientRect();
				const w = $wrapper[0].getBoundingClientRect();
				$host.css({
					top: Math.round(c.bottom - w.top) + "px",
					left: Math.round(c.left - w.left) + "px",
					width: Math.round(c.width) + "px",
				});
			});
		});
	}

	function patch_grid_row(proto) {
		if (!proto || proto[PATCH_FLAG]) return;

		// Called from the dialog's Update action. Nothing downstream needs a
		// ceiling now that the grid scrolls, and `update_column_width` still
		// rejects a zero width, so this can just stand down.
		proto.validate_columns_width = function () {};

		// Only Link and Dynamic Link open a list that the scroll container
		// would clip; Select uses a native <select>, which the browser renders
		// outside the page box.
		const orig_make_column = proto.make_column;
		proto.make_column = function (df) {
			const $col = orig_make_column.apply(this, arguments);
			if ($col && df && (df.fieldtype === "Link" || df.fieldtype === "Dynamic Link")) {
				bind_dropdown_escape($col, this);
			}
			return $col;
		};

		proto[PATCH_FLAG] = true;
	}

	// ------------------------------------------------------------------
	// Grid.prototype -- stop truncating, and flag the wide grids
	// ------------------------------------------------------------------

	function patch_grid(proto) {
		if (!proto || proto[PATCH_FLAG]) return;

		// Toggle the wide-grid class from the widths the grid just resolved.
		// The container is a direct child of the grid wrapper, so `children`
		// (not `find`) keeps a table-in-a-grid-form from being flagged by its
		// parent's column count.
		proto.apply_wide_columns_class = function () {
			const container = this.wrapper && this.wrapper.children(".form-grid-container");
			if (!container || !container.length) return;

			// Width of the data columns only -- the row-index and checkbox
			// gutters are not part of the budget. Note this is NOT the
			// `total_colsize` of setup_visible_columns, which seeds itself at
			// 1: a stock grid summing to exactly 10 fits, and must not be
			// flagged.
			const total = (this.visible_columns || []).reduce(
				(sum, col) => sum + cint(col[1]),
				0
			);
			container.toggleClass(WIDE_CLASS, total > 10);
		};

		// v15's setup_visible_columns verbatim, with two changes: the
		// `if (total_colsize > 11) return false;` truncation is gone, and the
		// class toggle runs on both exits. `df` is declared properly here --
		// core leaks it to the global scope.
		proto.setup_visible_columns = function () {
			if (this.visible_columns && this.visible_columns.length > 0) {
				this.apply_wide_columns_class();
				return;
			}

			this.user_defined_columns = [];
			this.setup_user_defined_columns();
			var total_colsize = 1,
				fields =
					this.user_defined_columns && this.user_defined_columns.length > 0
						? this.user_defined_columns
						: this.editable_fields || this.docfields;

			this.visible_columns = [];

			for (var ci in fields) {
				var _df = fields[ci];

				// get docfield if from fieldname
				let df =
					this.user_defined_columns && this.user_defined_columns.length > 0
						? _df
						: this.fields_map[_df.fieldname];

				if (
					df &&
					!df.hidden &&
					(this.editable_fields || df.in_list_view) &&
					((this.frm && this.frm.get_perm(df.permlevel, "read")) || !this.frm) &&
					!frappe.model.layout_fields.includes(df.fieldtype)
				) {
					if (df.columns) {
						df.colsize = df.columns;
					} else {
						this.update_default_colsize(df);
					}

					// attach formatter on refresh
					if (
						df.fieldtype == "Link" &&
						!df.formatter &&
						df.parent &&
						frappe.meta.docfield_map[df.parent]
					) {
						const docfield = frappe.meta.docfield_map[df.parent][df.fieldname];
						if (docfield && docfield.formatter) {
							df.formatter = docfield.formatter;
						}
					}

					total_colsize += df.colsize;
					this.visible_columns.push([df, df.colsize]);
				}
			}

			// redistribute if total-col size is less than 12
			var passes = 0;
			while (total_colsize < 11 && passes < 12) {
				for (var i in this.visible_columns) {
					var df = this.visible_columns[i][0];
					var colsize = this.visible_columns[i][1];
					if (
						colsize > 1 &&
						colsize < 11 &&
						frappe.model.is_non_std_field(df.fieldname)
					) {
						if (
							passes < 3 &&
							["Int", "Currency", "Float", "Check", "Percent"].indexOf(
								df.fieldtype
							) !== -1
						) {
							// don't increase col size of these fields in first 3 passes
							continue;
						}

						this.visible_columns[i][1] += 1;
						total_colsize++;
					}

					if (total_colsize > 10) break;
				}
				passes++;
			}

			this.apply_wide_columns_class();
		};

		// reset_grid rebuilds every column, so any dropdown lifted out of the
		// container belongs to a cell that is about to be discarded. Drop them
		// with it, otherwise they accumulate on the wrapper.
		const orig_reset_grid = proto.reset_grid;
		proto.reset_grid = function () {
			this.wrapper && this.wrapper.children("." + DROPDOWN_CLASS).remove();
			return orig_reset_grid.apply(this, arguments);
		};

		// The header row is the only GridRow that owns the Configure Columns
		// dialog, and it is built here -- first pass through gives us the
		// GridRow prototype. It lands well before the dialog can be opened.
		const orig_make_head = proto.make_head;
		proto.make_head = function () {
			const out = orig_make_head.apply(this, arguments);
			if (this.header_row) {
				patch_grid_row(Object.getPrototypeOf(this.header_row));
			}
			return out;
		};

		proto[PATCH_FLAG] = true;
	}

	// ------------------------------------------------------------------
	// Entry point: every child table control builds a Grid in make()
	// ------------------------------------------------------------------

	const ControlTable = frappe.ui.form.ControlTable;
	if (ControlTable && !ControlTable.prototype[PATCH_FLAG]) {
		const orig_make = ControlTable.prototype.make;
		ControlTable.prototype.make = function () {
			const out = orig_make.apply(this, arguments);
			// The constructor only assigns state; the first render is still
			// ahead of us, so patching here is early enough for this grid.
			this.grid && patch_grid(Object.getPrototypeOf(this.grid));
			return out;
		};
		ControlTable.prototype[PATCH_FLAG] = true;
	}
})();
