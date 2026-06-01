// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

/**
 * DocumentCanvas — a reusable stacked-block document editor.
 *
 * Blocks flow top-to-bottom on an A4-width sheet. You drag a block's handle to
 * REORDER it (no free positioning / no overlaps), set each block's width% and
 * alignment, edit text inline (floating rich-text toolbar), add images, duplicate
 * and copy/paste. The layout maps 1:1 to the generated PDF.
 *
 * Usage:
 *   const canvas = new DocumentCanvas({ $mount, sections, onChange });
 *   canvas.set_sections([...]); const out = canvas.get_sections();
 *   canvas.add_section(); canvas.add_image(); canvas.destroy();
 */
window.DocumentCanvas = class DocumentCanvas {
	constructor(opts) {
		this.$mount = opts.$mount;
		this.sections = opts.sections || [];
		this.onChange = opts.onChange || function () {};
		this.selected = null;
		this.clipboard = null;
		this.PAGE_WIDTH = 794;
		this.COMPUTED = ["Field Table", "Data Table", "Spacer", "Image"];
		this.render();
		this.make_toolbar();
		this.bind_keyboard();
	}

	render() {
		this.$mount.empty();
		this.wrap = $(`
			<div class="dg-canvas-area">
				<div class="dg-canvas">
					<div class="dg-page" style="width:${this.PAGE_WIDTH}px"></div>
				</div>
			</div>
		`).appendTo(this.$mount);
		this.$page = this.wrap.find(".dg-page");
		this.$page.on("mousedown", (e) => {
			if (e.target === this.$page[0]) this.select(null);
		});
		this.render_blocks();
	}

	set_sections(arr) {
		this.sections = arr || [];
		this.render_blocks();
	}

	render_blocks() {
		this.$page.empty();
		this.selected = null;
		this.hide_toolbar();
		this.sections.forEach((s) => this.add_block(s));
		this.init_sortable();
	}

	_changed() {
		this.onChange();
	}

	add_block(section) {
		if (!section._id) section._id = "dgb-" + Math.random().toString(36).slice(2, 9);
		const $b = $(`
			<div class="dg-block" data-id="${section._id}">
				<div class="dg-block-bar">
					<span class="dg-move" title="${__("Long-press anywhere on the block to drag; hold Ctrl/Alt to drop a copy")}">⋮⋮</span>
					<span class="dg-block-label"></span>
					<span class="dg-grow"></span>
					<select class="dg-width" title="${__("Width %")}">
						<option value="25">25%</option>
						<option value="50">50%</option>
						<option value="75">75%</option>
						<option value="100">100%</option>
					</select>
					<span class="dg-align">
						<button data-al="Left" title="${__("Left")}">⯇</button>
						<button data-al="Center" title="${__("Center")}">≡</button>
						<button data-al="Right" title="${__("Right")}">⯈</button>
					</span>
					<button class="btn btn-xs dg-block-dup" title="${__("Duplicate")}">⧉</button>
					<button class="btn btn-xs dg-block-del" title="${__("Remove")}">✕</button>
				</div>
				<div class="dg-block-body">
					<div class="dg-block-content" contenteditable="true"></div>
				</div>
			</div>
		`);
		$b.find(".dg-block-label").text(section.section_title || section.section_type);
		$b.find(".dg-width").val(String(section.width_pct || "100"));

		const editable = !this.COMPUTED.includes(section.section_type);
		const $content = $b.find(".dg-block-content");
		$content.attr("contenteditable", editable ? "true" : "false");
		$content.html(section.display_content != null ? section.display_content : section.content || "");
		if (section.is_locked) $b.find(".dg-block-del").prop("disabled", true);

		$b.data("section", section);
		section.$el = $b;
		this.apply_layout(section);

		$b.on("mousedown", () => this.select(section));

		if (editable) {
			$content.on("input", () => {
				section.content = $content.html();
				this._changed();
			});
			$content.on("focus", () => {
				this.select(section);
				this.show_toolbar(section);
			});
			$content.on("blur", () => (section.content = $content.html()));
		}
		if (section.section_type === "Image") {
			$content.on("dblclick", () =>
				this.pick_image((dataUrl) => {
					section.content = `<img src="${dataUrl}" style="max-width:100%">`;
					$content.html(section.content);
					this._changed();
				})
			);
		}

		$b.find(".dg-width").on("change", (e) => {
			section.width_pct = e.target.value;
			this.apply_layout(section);
			this._changed();
		});
		$b.find(".dg-align button").on("click", (e) => {
			e.stopPropagation();
			section.align = e.currentTarget.dataset.al;
			this.apply_layout(section);
			this._changed();
		});
		$b.find(".dg-block-del").on("click", (e) => {
			e.stopPropagation();
			this.delete_block(section);
		});
		$b.find(".dg-block-dup").on("click", (e) => {
			e.stopPropagation();
			this.duplicate_section(section);
		});

		this.$page.append($b);
	}

	apply_layout(section) {
		const w = parseInt(section.width_pct, 10) || 100;
		const align = section.align || "Left";
		const css = {
			width: w + "%",
			"text-align": align.toLowerCase(),
			"margin-left": align === "Right" || align === "Center" ? "auto" : "0",
			"margin-right": align === "Center" ? "auto" : "0",
		};
		section.$el.find(".dg-block-body").css(css);
		section.$el
			.find(".dg-align button")
			.removeClass("active")
			.filter(`[data-al="${align}"]`)
			.addClass("active");
	}

	init_sortable() {
		if (this.sortable) this.sortable.destroy();
		if (typeof Sortable === "undefined") return;
		this.sortable = new Sortable(this.$page[0], {
			// Long-press anywhere on a block starts the drag; a quick click edits text,
			// and click-drag (immediate move) still selects text — both cancel the drag.
			delay: 250,
			delayOnTouchOnly: false,
			animation: 150,
			// Keep the per-block controls clickable (don't start a drag from them).
			filter: ".dg-width, .dg-align, .dg-align button, .dg-block-dup, .dg-block-del, select, option",
			preventOnFilter: false,
			onStart: (evt) => {
				const oe = evt.originalEvent || {};
				this._copyDrag = !!(oe.ctrlKey || oe.metaKey || oe.altKey);
			},
			onEnd: (evt) => this.on_sort_end(evt),
		});
	}

	on_sort_end(evt) {
		// Ctrl/Alt-drag drops a COPY at the release position; the original stays.
		if (this._copyDrag) {
			this._copyDrag = false;
			const moved = this.sections[evt.oldIndex];
			if (moved) {
				const clone = this.clone_section(moved);
				const arr = this.sections.slice();
				arr.splice(evt.newIndex, 0, clone);
				this.set_sections(arr);
				this._changed();
				return;
			}
		}
		this.reorder_from_dom();
	}

	reorder_from_dom() {
		const order = [];
		this.$page.find(".dg-block").each((_, el) => {
			const s = this.sections.find((x) => x._id === $(el).data("id"));
			if (s) order.push(s);
		});
		this.sections = order;
		this._changed();
	}

	select(section) {
		this.$page.find(".dg-block").removeClass("selected");
		this.selected = section;
		if (section && section.$el) section.$el.addClass("selected");
		else this.hide_toolbar();
	}

	delete_block(section) {
		if (section.is_locked) return;
		section.$el.remove();
		this.sections = this.sections.filter((s) => s !== section);
		this.hide_toolbar();
		this._changed();
	}

	clone_section(section) {
		return {
			section_title: section.section_title,
			section_type: section.section_type,
			content: section.$el ? section.$el.find(".dg-block-content").html() : section.content,
			config_json: section.config_json,
			enabled: 1,
			is_locked: 0,
			align: section.align || "Left",
			width_pct: section.width_pct || "100",
		};
	}

	add_section_obj(data) {
		const section = Object.assign({}, data);
		delete section._id;
		this.sections.push(section);
		this.add_block(section);
		this.select(section);
		this._changed();
		return section;
	}

	duplicate_section(section) {
		this.add_section_obj(this.clone_section(section));
	}

	add_section() {
		this.add_section_obj({
			section_title: __("New Section"),
			section_type: "Rich Text",
			content: "<p>" + __("New text") + "</p>",
			enabled: 1,
			is_locked: 0,
			align: "Left",
			width_pct: "100",
		});
	}

	pick_image(cb) {
		const inp = document.createElement("input");
		inp.type = "file";
		inp.accept = "image/*";
		inp.onchange = () => {
			const f = inp.files[0];
			if (!f) return;
			const reader = new FileReader();
			reader.onload = () => cb(reader.result);
			reader.readAsDataURL(f);
		};
		inp.click();
	}

	add_image() {
		this.pick_image((dataUrl) => {
			this.add_section_obj({
				section_title: __("Image"),
				section_type: "Image",
				content: `<img src="${dataUrl}" style="max-width:100%">`,
				enabled: 1,
				is_locked: 0,
				align: "Left",
				width_pct: "50",
			});
		});
	}

	make_toolbar() {
		this.$toolbar = $(`
			<div class="dg-fmt-toolbar" style="display:none">
				<button data-cmd="bold"><b>B</b></button>
				<button data-cmd="italic"><i>I</i></button>
				<button data-cmd="underline"><u>U</u></button>
				<button data-cmd="insertUnorderedList">• List</button>
				<button data-cmd="insertOrderedList">1. List</button>
				<button data-size="bigger">A+</button>
				<button data-size="smaller">A−</button>
				<button data-img="1" title="${__("Insert image")}">🖼</button>
			</div>
		`).appendTo(document.body);

		this.$toolbar.find("button").on("mousedown", (e) => {
			e.preventDefault();
			if (e.currentTarget.dataset.img) {
				const sec = this.selected;
				this.pick_image((dataUrl) => {
					if (!sec) return;
					const $c = sec.$el.find(".dg-block-content");
					$c.append(`<img src="${dataUrl}" style="max-width:100%">`);
					sec.content = $c.html();
					this._changed();
				});
				return;
			}
			const cmd = e.currentTarget.dataset.cmd;
			const size = e.currentTarget.dataset.size;
			document.execCommand("styleWithCSS", false, true);
			if (cmd) document.execCommand(cmd, false, null);
			if (size) document.execCommand("fontSize", false, size === "bigger" ? 5 : 2);
			if (this.selected) {
				this.selected.content = this.selected.$el.find(".dg-block-content").html();
				this._changed();
			}
		});
	}

	show_toolbar(section) {
		const r = section.$el.find(".dg-block-body")[0].getBoundingClientRect();
		this.$toolbar.css({
			display: "flex",
			top: window.scrollY + r.top - 44 + "px",
			left: window.scrollX + r.left + "px",
		});
	}

	hide_toolbar() {
		if (this.$toolbar) this.$toolbar.hide();
	}

	bind_keyboard() {
		this._keyHandler = (e) => {
			if (!this.$page || !document.body.contains(this.$page[0])) return;
			if (!(e.ctrlKey || e.metaKey)) return;
			const ae = document.activeElement;
			const editingText = ae && ae.classList && ae.classList.contains("dg-block-content");
			const k = e.key.toLowerCase();
			if (k === "d") {
				if (this.selected) {
					e.preventDefault();
					this.duplicate_section(this.selected);
				}
				return;
			}
			if (editingText) return;
			if (k === "c" && this.selected) {
				this.clipboard = this.clone_section(this.selected);
			} else if (k === "v" && this.clipboard) {
				e.preventDefault();
				this.add_section_obj(this.clipboard);
			}
		};
		document.addEventListener("keydown", this._keyHandler);
	}

	// Read current order/content/layout from the DOM into plain section dicts.
	get_sections() {
		const order = [];
		this.$page.find(".dg-block").each((i, el) => {
			const s = this.sections.find((x) => x._id === $(el).data("id"));
			if (!s) return;
			if (s.$el && !this.COMPUTED.includes(s.section_type)) {
				s.content = s.$el.find(".dg-block-content").html();
			}
			order.push({
				section_title: s.section_title,
				section_type: s.section_type,
				content: s.content,
				config_json: s.config_json,
				enabled: s.enabled,
				is_locked: s.is_locked,
				align: s.align || "Left",
				width_pct: s.width_pct || "100",
				idx: i + 1,
			});
		});
		return order;
	}

	destroy() {
		if (this.sortable) this.sortable.destroy();
		if (this.$toolbar) this.$toolbar.remove();
		if (this._keyHandler) document.removeEventListener("keydown", this._keyHandler);
		if (this.$mount) this.$mount.empty();
	}
};
