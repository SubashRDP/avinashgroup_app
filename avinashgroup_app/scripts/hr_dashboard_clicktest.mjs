// Click-through test for the HR dashboard (top of the HR workspace + /app/hr-dashboard).
//
// Drives a headless Chrome over the DevTools protocol: opens the menus, follows
// links, steps the BS month, switches company, clicks a KPI card and a
// data-gap row, hovers the chart, and reports PASS/FAIL per step.
//
//   google-chrome --headless=new --no-sandbox --remote-debugging-port=9333 \
//       --user-data-dir=/tmp/hrd-prof about:blank &
//   node scripts/hr_dashboard_clicktest.mjs <sid>
//
// <sid>: a desk session id for a user with HR Manager / HR User / System
// Manager (LoginManager().login_as(user) from a bench script prints one).
// Known noise: Monthly Attendance BS throws "Filter missing" twice on open,
// with or without the dashboard — that report's own behaviour.
const SID = process.argv[2];
const chrome = { kill() {} }; // started by the shell
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let targets;
for (let i = 0; i < 40 && !targets; i++) {
  await sleep(500);
  try { targets = await (await fetch("http://127.0.0.1:9333/json")).json(); } catch (e) {}
}
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = {};
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending[d.id]) { pending[d.id](d); delete pending[d.id]; } };
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => { const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }); return r.result?.result?.value ?? r.result?.exceptionDetails?.exception?.description; };
const until = async (expr, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await ev(expr)) return true; await sleep(250); } return false; };
const results = []; const check = (name, ok, extra = "") => { results.push(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`); };

await send("Page.enable"); await send("Runtime.enable");
const errors = [];
ws.addEventListener("message", (m) => { const d = JSON.parse(m.data); if (d.method === "Runtime.exceptionThrown") { const x=d.params.exceptionDetails; errors.push(JSON.stringify({t:x.text, d:(x.exception?.description||x.exception?.value||"").toString().slice(0,200), u:x.url, l:x.lineNumber, when: results.length})); } });

// ---------- workspace
await send("Page.navigate", { url: `http://localhost:8000/app/hr?sid=${SID}` });
const root = `document.querySelector('.hr-workspace-dashboard')`;
check("workspace: dashboard mounts on the HR page", await until(`${root}?.querySelector('.hrd-kpi-value')`));
check("workspace: top menu has 6 groups", (await ev(`${root}.querySelectorAll('.hrd-top-group').length`)) === 6);
await ev(`window.__marker = 42`);
await ev(`${root}.querySelectorAll('.hrd-top-btn')[4].click()`);
check("workspace: Payroll dropdown opens", await ev(`${root}.querySelectorAll('.hrd-top-group')[4].classList.contains('is-open')`));
await ev(`[...${root}.querySelectorAll('.hrd-top-group')[4].querySelectorAll('a')].find(a=>a.textContent.includes('Salary Slips')).click()`);
await until(`frappe.get_route_str() === 'List/Salary Slip/List'`, 8000);
check("workspace: menu link routes without reload", (await ev(`frappe.get_route_str()`)) === "List/Salary Slip/List" && (await ev(`window.__marker`)) === 42, await ev(`frappe.get_route_str()`));

await ev(`frappe.set_route('hr')`);
await until(`${root}?.querySelector('.hrd-kpi-value')`);
await ev(`(() => { const i=${root}.querySelector('.hrd-top-search input'); i.value='monthly att'; i.dispatchEvent(new Event('input',{bubbles:true})); })()`);
check("workspace: search shows results", (await ev(`${root}.querySelectorAll('.hrd-results a').length`)) >= 1, await ev(`${root}.querySelector('.hrd-results').textContent.trim()`));
await ev(`${root}.querySelector('.hrd-top-search input').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))`);
await until(`frappe.get_route_str().startsWith('query-report')`, 8000);
check("workspace: Enter opens first result", (await ev(`frappe.get_route_str()`)).startsWith("query-report/Monthly Attendance BS"), await ev(`frappe.get_route_str()`));

await ev(`frappe.set_route('hr')`);
await until(`${root}?.querySelector('.hrd-month-label strong')`);
await ev(`${root}.querySelector('.hrd-prev').click()`);
check("workspace: previous month", await until(`${root}.querySelector('.hrd-month-label strong')?.textContent === 'Shrawan 2083'`, 8000), await ev(`${root}.querySelector('.hrd-month-label strong').textContent`));
await ev(`${root}.querySelector('.hrd-next').click()`);
check("workspace: next month", await until(`${root}.querySelector('.hrd-month-label strong')?.textContent === 'Bhadra 2083'`, 8000));
await ev(`(() => { const s=${root}.querySelector('.hrd-company'); s.value='Nepal Gas Udhyog Pvt. Ltd.'; s.dispatchEvent(new Event('change',{bubbles:true})); })()`);
check("workspace: company filter → NGI headcount 107", await until(`${root}.querySelector('.hrd-kpi-value')?.textContent === '107'`, 8000), await ev(`${root}.querySelector('.hrd-kpi-value').textContent`));
await ev(`(() => { const s=${root}.querySelector('.hrd-company'); s.value=''; s.dispatchEvent(new Event('change',{bubbles:true})); })()`);
await until(`${root}.querySelector('.hrd-kpi-value')?.textContent === '292'`, 8000);

await ev(`${root}.querySelector('.hrd-kpi').click()`);
await until(`frappe.get_route_str().startsWith('List/Employee')`, 8000);
check("workspace: Employees card → Employee list", (await ev(`frappe.get_route_str()`)).startsWith("List/Employee"), await ev(`frappe.get_route_str()`));

await ev(`frappe.set_route('hr')`);
await until(`${root}?.querySelector('[data-gap]')`);
await ev(`${root}.querySelector('[data-gap]').click()`);
await until(`frappe.get_route_str() === 'List/Employee/Report'`, 8000);
await sleep(1500);
const filters = await ev(`JSON.stringify(cur_list && cur_list.filter_area ? cur_list.filter_area.get() : null)`);
check("workspace: device-ID gap → Employee report filtered", (filters || "").includes("attendance_device_id"), filters);

await ev(`frappe.set_route('hr')`);
await until(`${root}?.querySelector('.hrd-chart .day')`);
await ev(`${root}.querySelectorAll('.hrd-chart .day')[4].dispatchEvent(new MouseEvent('mouseover',{bubbles:true}))`);
check("workspace: chart tooltip on hover", await ev(`${root}.querySelector('.hrd-tip').classList.contains('is-shown')`), await ev(`${root}.querySelector('.hrd-tip').textContent.replace(/\\s+/g,' ').trim()`));

// ---------- page
await ev(`frappe.set_route('hr-dashboard')`);
check("page: dashboard mounts with side menu", await until(`document.querySelector('.hrd-menu-side .hrd-kpi-value')`));
const closedBefore = await ev(`!document.querySelectorAll('.hrd-menu-side .hrd-group')[1].classList.contains('is-open')`);
await ev(`document.querySelectorAll('.hrd-menu-side .hrd-group-head')[1].click()`);
check("page: side group expands", closedBefore && (await ev(`document.querySelectorAll('.hrd-menu-side .hrd-group')[1].classList.contains('is-open')`)));
await ev(`(() => { const i=document.querySelector('.hrd-menu-side .hrd-nav input'); i.value='dashain'; i.dispatchEvent(new Event('input',{bubbles:true})); })()`);
check("page: side search filters", (await ev(`[...document.querySelectorAll('.hrd-menu-side .hrd-group li')].filter(l=>l.style.display!=='none').map(l=>l.textContent.trim()).join('|')`)) === "Dashain Bonus", await ev(`[...document.querySelectorAll('.hrd-menu-side .hrd-group li')].filter(l=>l.style.display!=='none').map(l=>l.textContent.trim()).join('|')`));

// Monthly Attendance BS throws "Filter missing" on open by itself; ignore only that.
const real = errors.filter((e) => !e.includes("Filter missing"));
check("no uncaught JS errors (besides the report's own)", real.length === 0, real.join(" / "));
console.log(results.join("\n"));
ws.close(); chrome.kill();
process.exit(0);
