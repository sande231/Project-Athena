// common.js: helpers shared by every Athena page.
// Load it at the END of each page's <body>, before the page's own script:
//   <script src="common.js"></script>
//   <script> ...page code... </script>

// ---- Settings -------------------------------------------------------------

// Endpoints the backend has not built yet. While an entry is true, the page uses
// sample data from static/mock/ (or a stand-in) instead of the real API.
// When the backend ships an endpoint, change its entry to false. Nothing else changes.
const MOCK = {
  drift: true,    // GET  /api/drift
  models: true,   // GET  /api/models, POST /api/models/{id}/review|deploy|rollback
  auth: true,     // POST /api/auth/login
  stores: true,   // POST /api/stores
  upload: true,   // POST /api/transactions/upload (mock sends rows one by one to /api/transactions)
};

// Address of the Grafana dashboard. Leave empty until DevOps gives you one.
const GRAFANA_URL = "";

// ---- Formatting -----------------------------------------------------------

// Makes text safe to put inside HTML. Use it on anything that came from an order,
// from Claude, or from a user: email domains, reasons, names, file contents.
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

const money = v => v == null || isNaN(v) ? "" :
  "$" + Number(v).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});

const clock = iso => iso ? new Date(iso).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"}) : "";

const dateTime = iso => iso ? new Date(iso).toLocaleString([], {
  month: "short", day: "numeric", hour: "numeric", minute: "2-digit"}) : "";

const pct = v => v == null ? null : (v * 100).toFixed(1) + "%";

// Decisions always show a word as well as a colour.
const DECISION_WORDS = {approve: "Approved", review: "Needs review", block: "Blocked"};
const decisionTag = d => `<span class="tag ${esc(d)}">${esc(DECISION_WORDS[d] || d)}</span>`;

const SEVERITY_WORDS = {info: "Info", warning: "Warning", critical: "Critical"};

// ---- Browser storage (login token) ----------------------------------------
// Wrapped in try/catch because some browsers block storage (private mode).

const store = {
  get(key) { try { return JSON.parse(localStorage.getItem(key)); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ } },
  remove(key) { try { localStorage.removeItem(key); } catch { /* ignore */ } },
};

const currentUser = () => store.get("athena_user");

function logOut() {
  store.remove("athena_token");
  store.remove("athena_user");
  location.href = "index.html";
}

// ---- Talking to the API ----------------------------------------------------

// api("/api/alerts")                                  -> GET, returns the JSON
// api("/api/transactions/5/label", {method: "PATCH", json: {is_fraud: true}})
// api("/api/transactions/upload", {method: "POST", body: formData})   (file upload)
async function api(path, options = {}) {
  const headers = {};
  let body = options.body;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }
  const token = store.get("athena_token");
  if (token) headers["Authorization"] = "Bearer " + token;

  const response = await fetch(path, {method: options.method || "GET", headers, body});
  let data = null;
  try { data = await response.json(); } catch { /* empty or non-JSON answer */ }
  if (!response.ok) {
    throw new Error((data && data.error) || `The server answered ${response.status}`);
  }
  return data;
}

// For GET endpoints that may still be mocked: getData("drift", "/api/drift")
async function getData(mockKey, realPath) {
  if (MOCK[mockKey]) {
    const r = await fetch(`mock/${mockKey}.json`);
    return r.json();
  }
  return api(realPath);
}

// ---- Page furniture --------------------------------------------------------

const NAV_LINKS = [
  ["owner.html", "Owner View"],
  ["review.html", "Review"],
  ["alerts.html", "Alerts"],
  ["engineer.html", "Engineer"],
  ["drift.html", "Drift"],
  ["models.html", "Models"],
  ["connect.html", "Connect store"],
  ["store.html", "Demo store"],
];

// Fills <nav id="nav"></nav> and adds the "can't reach Athena" banner.
function setupPage() {
  const page = location.pathname.split("/").pop() || "index.html";
  const user = currentUser();
  const links = NAV_LINKS.map(([href, text]) =>
    `<a href="${href}"${href === page ? ' class="active"' : ""}>${text}</a>`).join("");
  const account = user
    ? `<span class="who">${esc(user.email)}</span><a href="#" id="logout">Log out</a>`
    : `<a href="login.html">Log in</a>`;
  const nav = document.getElementById("nav");
  if (nav) {
    nav.innerHTML = `<a class="brand" href="index.html">Athena</a><div class="links">${links}</div>` +
      `<div class="account">${account}</div>`;
    const out = document.getElementById("logout");
    if (out) out.addEventListener("click", e => { e.preventDefault(); logOut(); });
  }

  const banner = document.createElement("div");
  banner.id = "offline";
  banner.className = "offline";
  banner.hidden = true;
  banner.textContent = "Can't reach Athena right now. Retrying automatically…";
  document.body.prepend(banner);
}

function showOffline(isOffline) {
  const banner = document.getElementById("offline");
  if (banner) banner.hidden = !isOffline;
}

// Runs fn now and then every `ms` milliseconds. If fn fails (server down),
// shows the banner and keeps trying; when it works again the banner goes away.
function poll(fn, ms) {
  const run = async () => {
    try { await fn(); showOffline(false); }
    catch (err) { console.warn(err); showOffline(true); }
    setTimeout(run, ms);
  };
  run();
}

// Short message under a button, e.g. flash("deploy-msg", "Deployed.")
function flash(id, text, isError = false) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = isError ? "msg error" : "msg";
}

// common.js is loaded at the end of <body>, so the page's elements already exist.
setupPage();
