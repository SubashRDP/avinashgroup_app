/**
 * Global Fiscal Year Cache with Smart Scheduling
 *
 * Features:
 * - Fetches fiscal year once per day (caches result)
 * - Schedules refresh at midnight (smart timing, not polling)
 * - Also checks when user returns to browser tab
 * - Zero overhead when cache is valid
 */

window.FiscalYearCache = {
	cache: null,
	cacheDate: null,
	timeoutId: null,

	/**
	 * Get default fiscal year, cached per day
	 * @returns {Promise<string>} Fiscal year name (e.g. "82/83")
	 */
	async getDefaultFiscalYear() {
		const today = new Date().toDateString();

		// Return cached value if still same day
		if (this.cache && this.cacheDate === today) {
			console.log("📦 Using cached fiscal year:", this.cache);
			return this.cache;
		}

		console.log("🔄 Fetching fiscal year from backend...");
		try {
			const result = await frappe.call({
				method: "avinashgroup_app.utils.fiscal_year_utils.get_default_fiscal_year",
				async: true,
			});

			if (result.message) {
				this.cache = result.message;
				this.cacheDate = today;
				console.log("✅ Cached fiscal year:", this.cache, "Date:", today);
				return this.cache;
			}
		} catch (error) {
			console.error("❌ Failed to fetch fiscal year:", error);
			return null;
		}
	},

	/**
	 * Schedule cache refresh at midnight (next day)
	 * Runs once per day at exact midnight
	 */
	scheduleNextCheck() {
		const now = new Date();
		const midnight = new Date(now);
		midnight.setHours(24, 0, 0, 0); // Next midnight

		const msUntilMidnight = midnight - now;
		const hoursUntil = (msUntilMidnight / (1000 * 60 * 60)).toFixed(2);

		console.log(`⏰ Scheduled cache refresh at midnight (in ${hoursUntil} hours)`);

		// Clear previous timeout if exists
		if (this.timeoutId) clearTimeout(this.timeoutId);

		this.timeoutId = setTimeout(() => {
			console.log("🌙 Midnight reached - clearing cache for new day");
			this.clearCache();
			this.getDefaultFiscalYear();
			this.scheduleNextCheck(); // Reschedule for next day
		}, msUntilMidnight);
	},

	/**
	 * Check cache when user returns to browser tab
	 * Useful if user leaves browser open past midnight
	 */
	checkOnPageFocus() {
		document.addEventListener("visibilitychange", () => {
			if (!document.hidden) { // Page became visible
				const today = new Date().toDateString();
				if (this.cacheDate && this.cacheDate !== today) {
					console.log(`👁️ Page visible - detected new day! Refreshing cache... (${this.cacheDate} → ${today})`);
					this.clearCache();
					this.getDefaultFiscalYear();
					this.scheduleNextCheck();
				}
			}
		});
	},

	/**
	 * Initialize cache and scheduling
	 */
	start() {
		console.log("▶️ Starting Fiscal Year Cache (Option 3: Smart + Visibility)");
		this.getDefaultFiscalYear();
		this.scheduleNextCheck();
		this.checkOnPageFocus();
		console.log("✅ Fiscal Year Cache initialized");
	},

	/**
	 * Clear cache manually (useful for testing)
	 */
	clearCache() {
		this.cache = null;
		this.cacheDate = null;
		console.log("🗑️ Fiscal year cache cleared");
	},

	/**
	 * Stop scheduler (rarely needed)
	 */
	stop() {
		if (this.timeoutId) {
			clearTimeout(this.timeoutId);
			this.timeoutId = null;
		}
		console.log("⏹️ Fiscal year cache scheduler stopped");
	},
};

// Auto-start when Frappe is ready.
// `frappe.ready` only exists on website/portal pages, not in Desk, so guard
// for it and fall back to jQuery's document-ready (available in both contexts).
(function () {
	const init = () => {
		if (typeof window.FiscalYearCache !== "undefined") {
			window.FiscalYearCache.start();
		}
	};

	if (typeof frappe !== "undefined" && typeof frappe.ready === "function") {
		frappe.ready(init);
	} else {
		$(document).ready(init);
	}
})();
