// Default the list sidebar ("Filter By" panel) to hidden for every list view.
// This seeds frappe's own show_sidebar preference, so it stays fully
// toggleable: the header sidebar button shows/hides it on the current page,
// and "Toggle Sidebar" (Ctrl+K) in the list menu flips the saved preference
// back on permanently. Only seeds when unset, so a user's own choice is
// never overwritten.
if (localStorage.getItem("show_sidebar") === null) {
	localStorage.setItem("show_sidebar", "false");
}
