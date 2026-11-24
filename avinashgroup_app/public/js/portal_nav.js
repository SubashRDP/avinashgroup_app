// Standard customer portal menu: the collapse control and the phone ☰ entries.
// The markup is server-rendered by portal_nav.py. This runs deferred, so before
// jQuery's ready handlers: portal_mobile_menu.js then sees the ☰ entries already
// here and doesn't add its own list.
(function () {
	const KEY = "ag_portal_nav";
	const nav = document.getElementById("ag-pn");
	if (!nav) return;

	const toggle = nav.querySelector(".ag-pn-toggle");

	function show(collapsed) {
		document.body.classList.toggle("ag-pn-collapsed", collapsed);
		toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
		toggle.setAttribute("aria-label", toggle.dataset[collapsed ? "expandLabel" : "collapseLabel"]);
		toggle.title = toggle.getAttribute("aria-label");
	}

	show(document.body.classList.contains("ag-pn-collapsed"));

	toggle.addEventListener("click", function () {
		const collapsed = !document.body.classList.contains("ag-pn-collapsed");
		show(collapsed);
		try {
			localStorage.setItem(KEY, collapsed ? "collapsed" : "open");
		} catch (e) {
			// storage blocked: the choice just lasts for this page
		}
	});

	const navbarList = document.querySelector("#navbarSupportedContent ul.ml-auto.navbar-nav");
	if (!navbarList) return;

	const block = document.createElement("div");
	block.className = "d-block d-lg-none ag-pn-mobile";
	block.appendChild(document.createElement("hr"));
	nav.querySelectorAll(".ag-pn-list a").forEach(function (link) {
		const li = document.createElement("li");
		li.className = "nav-item";
		const a = link.cloneNode(true);
		a.classList.add("nav-link");
		a.classList.add(link.classList.contains("active") ? "text-dark" : "text-muted");
		li.appendChild(a);
		block.appendChild(li);
	});
	block.appendChild(document.createElement("hr"));

	const login = navbarList.querySelector(":scope > #website-post-login");
	navbarList.insertBefore(block, login);
})();
