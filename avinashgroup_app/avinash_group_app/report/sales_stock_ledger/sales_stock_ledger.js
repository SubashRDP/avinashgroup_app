frappe.query_reports["Sales Stock Ledger"] = {

    filters: [
        {
            fieldname: "report_type",
            label: __("Report Type"),
            fieldtype: "Select",
            options: "Detail\nSummarized",
            default: "Detail",
            reqd: 1,
            on_change: function () {
                frappe.query_report.refresh();
            },
        },
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            on_change: function () {
                frappe.query_report.set_filter_value("branch", "");
                frappe.query_report.set_filter_value("warehouse", "");
                frappe.query_report.set_filter_value("price_list", "");
                frappe.query_report.set_filter_value("voucher_no", "");
                frappe.query_report.set_filter_value("item", "");
                frappe.query_report.set_filter_value("item_group", "");
                frappe.query_report.refresh();
            },
        },
        {
            fieldname: "branch",
            label: __("Branch"),
            fieldtype: "Link",
            options: "Branch",
            get_query: function () {
                const company = frappe.query_report.get_filter_value("company");
                return company
                    ? { filters: { custom_company: company } }
                    : {};
            },
        },
        // Nepali (Bikram Sambat) month selection is provided by the shared
        // "📅 Select Month" widget + the per-field BS date inputs that
        // rdp_common_app injects for every Date filter (its Nepali tab sets the
        // period to a whole BS month). The Detail view also shows a "Nepali
        // Date (BS)" column for each row.
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_end(),
            reqd: 1,
        },
        {
            fieldname: "warehouse",
            label: __("Warehouse"),
            fieldtype: "Link",
            options: "Warehouse",
            get_query: function () {
                const company = frappe.query_report.get_filter_value("company");
                return company
                    ? { filters: { company: company } }
                    : {};
            },
        },
        {
            fieldname: "item",
            label: __("Item"),
            fieldtype: "Link",
            options: "Item",
            get_query: function () {
                const company = frappe.query_report.get_filter_value("company");
                return company
                    ? { filters: [["Item Default", "company", "=", company]] }
                    : {};
            },
        },
        {
            fieldname: "item_group",
            label: __("Item Group"),
            fieldtype: "Link",
            options: "Item Group",
            get_query: function () {
                const company = frappe.query_report.get_filter_value("company");
                return company
                    ? { filters: { custom_company: company } }
                    : {};
            },
        },
        {
            fieldname: "price_list",
            label: __("Price List"),
            fieldtype: "Link",
            options: "Price List",
            get_query: function () {
                const company = frappe.query_report.get_filter_value("company");
                return company
                    ? { filters: { custom_company: company } }
                    : {};
            },
        },
        {
            fieldname: "uom",
            label: __("UOM"),
            fieldtype: "Link",
            options: "UOM",
        },
        {
            fieldname: "voucher_no",
            label: __("Voucher No"),
            fieldtype: "Link",
            options: "Sales Invoice",
            get_query: function () {
                const company = frappe.query_report.get_filter_value("company");
                return company
                    ? { filters: { company: company, docstatus: 1 } }
                    : { filters: { docstatus: 1 } };
            },
        },
        {
            fieldname: "voucher_type",
            label: __("Voucher Type"),
            fieldtype: "Select",
            options: "\nSales Invoice\nSales Return",
        },
        {
            fieldname: "fit_columns",
            label: __("Fit Columns"),
            fieldtype: "Check",
            default: 1,
            on_change: function () {
                frappe.query_report.refresh();
            },
        },
        {
            fieldname: "sales_return_merge",
            label: __("Sales / Return Merge"),
            fieldtype: "Check",
            default: 0,
        },
    ],

    get_datatable_options(options) {
        // "Fit Columns" → frappe-datatable's native fluid layout, which stretches
        // every column to fill the table width (and re-balances on window resize),
        // keeping header and body in sync. Unchecked → fixed widths from the .py
        // column defs, with horizontal scroll when they exceed the viewport.
        const fit = frappe.query_report.get_filter_value("fit_columns");
        return Object.assign(options, { layout: fit ? "fluid" : "fixed" });
    },

    after_datatable_render: function (dt) {
        this._initDragScroll(dt);
        this._tagRows(dt);
    },

    // Add CSS hooks to rows so total / return rows and zebra striping render.
    _tagRows: function (dt) {
        const scrollable = dt && dt.bodyScrollable;
        if (!scrollable) return;
        const data = (dt.datamanager && dt.datamanager.data) || [];
        const rows = scrollable.querySelectorAll(".dt-row");
        rows.forEach((rowEl, i) => {
            const d = data[i] || {};
            rowEl.classList.remove(
                "ssl-total-row", "ssl-return-row", "ssl-row-even"
            );
            if (d.bold) {
                rowEl.classList.add("ssl-total-row");
            } else {
                if (d.voucher_type === "Sales Return") {
                    rowEl.classList.add("ssl-return-row");
                }
                if (i % 2 === 1) rowEl.classList.add("ssl-row-even");
            }
        });
    },

    _initDragScroll: function (dt) {
        const scrollable = dt.bodyScrollable;
        if (!scrollable || scrollable._dragScrollBound) return;
        scrollable._dragScrollBound = true;

        let isDragging = false;
        let startX, startY, scrollLeft, scrollTop;

        scrollable.addEventListener("mousedown", (e) => {
            // only trigger on left click, not on links/buttons
            if (e.button !== 0) return;
            if (e.target.closest("a, button, input, select")) return;
            isDragging  = true;
            startX      = e.pageX - scrollable.offsetLeft;
            startY      = e.pageY - scrollable.offsetTop;
            scrollLeft  = scrollable.scrollLeft;
            scrollTop   = scrollable.scrollTop;
            scrollable.style.cursor = "grabbing";
            scrollable.style.userSelect = "none";
            e.preventDefault();
        });

        document.addEventListener("mousemove", (e) => {
            if (!isDragging) return;
            const dx = e.pageX - scrollable.offsetLeft - startX;
            const dy = e.pageY - scrollable.offsetTop  - startY;
            scrollable.scrollLeft = scrollLeft - dx;
            scrollable.scrollTop  = scrollTop  - dy;
        });

        document.addEventListener("mouseup", () => {
            if (!isDragging) return;
            isDragging = false;
            scrollable.style.cursor    = "grab";
            scrollable.style.userSelect = "";
        });

        // default cursor
        scrollable.style.cursor = "grab";
    },

    formatter: function (value, row, column, data, default_formatter) {
        let formatted = default_formatter(value, row, column, data);

        if (data) {
            // Color-code the voucher type as a pill badge (skip the total row).
            if (column.fieldname === "voucher_type" && !data.bold && value) {
                if (value === "Sales Return") {
                    formatted = `<span class="ssl-badge ssl-badge--return">${value}</span>`;
                } else if (value === "Sales Invoice") {
                    formatted = `<span class="ssl-badge ssl-badge--invoice">${value}</span>`;
                }
            }

            // Emphasise the Nepali (BS) date.
            if (column.fieldname === "nepali_date" && value) {
                formatted = `<span class="ssl-nepali-date">${value}</span>`;
            }

            if (data.bold) {
                formatted = `<strong>${formatted}</strong>`;
            }
        }

        // Some fonts lack the ₨ (U+20A8) glyph and render it as an empty box in
        // front of currency values; show the universally-available "Rs" instead.
        if (formatted && formatted.indexOf("₨") !== -1) {
            formatted = formatted.split("₨").join("Rs");
        }

        return formatted;
    },

    onload: function () {
        // Always re-inject so CSS updates apply on SPA navigation (a stale style
        // tag from a previous visit would otherwise mask changes).
        const existing = document.getElementById("ssl-report-style");
        if (existing) existing.remove();

        const style = document.createElement("style");
        style.id = "ssl-report-style";
        style.textContent = `
            .query-report-wrapper .datatable {
                width: 100% !important;
            }
            /* Row numbering column (fix 2-digit numbers getting ellipsized) */
            .query-report-wrapper .dt-row-header {
                min-width: 52px !important;
                width: 52px !important;
            }
            .query-report-wrapper .dt-row-header .dt-cell__content {
                overflow: visible !important;
                text-overflow: unset !important;
                text-align: center;
                width: 100%;
            }
            .query-report-wrapper .dt-scrollable {
                overflow-x: auto !important;
                -webkit-overflow-scrolling: touch;
            }
            .query-report-wrapper .dt-cell {
                display: flex;
                align-items: center;
                padding: 8px !important;
                box-sizing: border-box;
            }
            .query-report-wrapper .dt-cell__content {
                /* Fill the cell so right-aligned currency values (rendered as an
                   inner <div style="text-align:right">) span the full width and
                   aren't clipped to a sliver by flex shrinking. */
                flex: 1 1 auto;
                min-width: 0;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                line-height: 1.4;
            }
            /* The empty inline-edit overlay is unused in a read-only report and
               can steal width inside the flex cell. */
            .query-report-wrapper .dt-cell__edit {
                display: none !important;
            }
            .query-report-wrapper .dt-cell__header {
                font-weight: 600;
                white-space: normal;
                word-break: break-word;
            }
            .query-report-wrapper .dt-row {
                height: auto;
                min-height: 30px;
            }
            /* Header band */
            .query-report-wrapper .dt-header .dt-cell--header {
                background: #f4f5f6;
                border-bottom: 2px solid #d1d8dd;
            }
            .query-report-wrapper .dt-header .dt-cell__content--header {
                color: #1f272e;
                font-weight: 600;
            }
            /* Zebra striping for readability */
            .query-report-wrapper .dt-row.ssl-row-even .dt-cell {
                background: #fbfcfd;
            }
            .query-report-wrapper .dt-row:hover .dt-cell {
                background: #f0f7ff !important;
            }
            /* Total row highlight (rows we tag with .ssl-total-row) */
            .query-report-wrapper .dt-row.ssl-total-row .dt-cell {
                background: #eef4ff !important;
                border-top: 2px solid #b3c8ff;
            }
            /* Sales Return rows tinted */
            .query-report-wrapper .dt-row.ssl-return-row .dt-cell {
                background: #fff6f6;
            }
            /* Nepali date cell */
            .ssl-nepali-date {
                color: #b5430f;
                font-weight: 600;
                font-variant-numeric: tabular-nums;
            }
            .ssl-badge {
                display: inline-block;
                padding: 1px 7px;
                border-radius: 10px;
                font-size: 11px;
                font-weight: 600;
                line-height: 1.5;
            }
            .ssl-badge--invoice { background: #e6f4ea; color: #137333; }
            .ssl-badge--return  { background: #fce8e6; color: #c5221f; }
        `;
        document.head.appendChild(style);
    },
};
