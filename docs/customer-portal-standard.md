# Customer Portal Standard

How every customer-facing portal page is built, so a new page looks and behaves
like the rest. Written from the November 2026 portal redesign on `demo-nggroup`.
Who gets a login is covered in `customer-portal-access.md`.

## Pages

| Route | Source |
| --- | --- |
| `/me` | `www/me.html`, `www/me.py` |
| `/place_order` | `templates/pages/place_order.*` |
| `/orders` | `www/Sales Order.*`, `portal_orders.py`, `templates/includes/portal_order_row.html` |
| `/invoices` | `www/Sales Invoice.*`, `portal_invoices.py`, `templates/includes/portal_invoice_row.html` |
| `/orders/<name>`, `/invoices/<name>` | `www/order.*`, `portal_document.py`, `templates/includes/portal_document.html` |
| `/customer_statement` | `templates/pages/customer_statement.*` |
| `/product_wise_invoice_details` | `templates/pages/product_wise_invoice_details.*` |
| `/sales_order_analysis` | `templates/pages/sales_order_analysis.*` |
| `/portal_announcement_history` and detail | `www/portal_announcement_history*` |

`www/Sales Order.html` and `www/Sales Invoice.html` work because ERPNext routes
`/orders` and `/invoices` to endpoints with those names. Our templates take over
without patching ERPNext. `www/order.*` handles the shared transaction detail
endpoint, so it also runs for purchase documents: anything other than Sales Order
and Sales Invoice must keep rendering the stock content.

## Menu

One menu, in `portal_nav.py`, `templates/includes/portal_nav.html`,
`public/css/portal_nav.css` and `public/js/portal_nav.js`, attached through the
`update_website_context` hook.

- **Never copy menu markup into a page.** To add an entry, add it to
  `STANDARD_MENU` and enable the route in Portal Settings. The menu still reads
  Portal Settings, so role filtering is unchanged.
- It only renders on `no_cache` pages for logged-in users with the Customer role.
  A new page without `no_cache = 1` gets no menu.
- Desktop: fixed left rail with a panel-icon collapse control, remembered in
  `localStorage` (`ag_portal_nav`). Phone: the same entries in the ☰ menu.

## Design

| Token | Value |
| --- | --- |
| Page background | `#EDF0F7` |
| Surface / field | `#FFFFFF` / `#F5F7FC` |
| Navy 900 / 700 / 500 | `#141F4A` / `#233A86` / `#435CA8` |
| Red 600 / 700 | `#D6202A` / `#AE1720` |
| Lines | `#D8DFEE`, soft `#E9EDF6` |
| Muted text | `#56628C` |
| Text / headings / figures | Barlow / Barlow Semi Condensed / IBM Plex Mono |

Page shape: up to 1460px wide, title close under the navbar, one filter card,
summary cards, navy sticky table header, right-aligned mono numbers, status
badges, and separate loading, empty and error states. Tables become cards on a
phone. Keyboard focus is always visible. Styles stay page-local, under a page
prefix (`.ol-`, `.cs-`, `.po-`).

## Rules that prevent real bugs

- **Use container queries for page layout.** The menu takes width that viewport
  media queries cannot see. Viewport breakpoints printed the Place Order summary
  over the form.
- **No page-level sideways scroll at 360px.** Check `scrollWidth` against
  `clientWidth`.
- **Show the posting date.** ERPNext's stock row shows `modified`, which made every
  invoice appear to be dated today.
- **User-specific pages need `no_cache = 1`.** Website HTML is cached by path and
  language, not by user.
- **Figures come from the server.** Redesigns must not recalculate in the browser.
  Compare displayed figures before and after.
- **Scope every whitelisted method to the session user's own customers,** on the
  server. Hiding a choice in the page is not a permission check.
- **Sort customers by name, then `name`.** Several records share "Demo Customer",
  so sorting by name alone can flip the default between page loads.
- **Portal `frappe.call` ignores `error`.** Do not rely on that callback to leave a
  loading state. Guard customer switches against stale responses.

## Going live

- `.html` templates show on the next load.
- `.py` and `hooks.py` changes need a worker reload, **then** a cache clear. In the
  other order, old workers can cache the stale hooks again:

  ```bash
  kill -HUP <gunicorn master pid>
  bench --site <site> clear-cache
  bench --site <site> clear-website-cache
  ```

- Plain files in `public/` need no build, but bump their `?v=` so browsers fetch
  the new copy.
- The app is shared by the bench: a portal change reaches every site with
  `avinashgroup_app` installed.

## Before calling a page done

Check as a single-customer and a multi-customer login, at 1440px with the menu open
and collapsed, and at 360px. Confirm figures are unchanged, another customer's
document is refused, and the console has no errors.
