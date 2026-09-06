"""Whether the site being served right now is one of ours.

The before_request/before_job patches mutate modules in sys.modules, and the
gunicorn and RQ workers share those modules across every site on the bench.
Hooks are scoped per site; the modules they patch are not. So the first request
for a site that has this app installed leaves the patch in place for every
later request that worker serves -- including sites where this app was never
installed and whose database has none of its doctypes, which is how the
General Ledger override ended up querying a missing Numbering Configuration
table on himalpowerdemo.

Patch time cannot tell the difference. Call time can, so every wrapper asks
here first and hands back to the function it replaced when the answer is no.
"""

import frappe

APP = "avinashgroup_app"


def app_installed() -> bool:
	"""True when the current site has this app installed."""
	try:
		return APP in frappe.get_installed_apps()
	except Exception:
		# No site bound, or installed-apps unreadable: treat as not ours rather
		# than running site-specific code against a site we cannot identify.
		return False
