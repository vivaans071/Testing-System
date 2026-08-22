/* ===========================================================================
   Testing sample inventory  —  Department > Campaign > Lot > Mini

   Loaded by index.html and driven by PAGE === "testing". Deliberately reuses
   the app's existing helpers (api, showModal, escapeHtml, DEPARTMENTS,
   MY_DEPARTMENT_ID) and CSS classes rather than introducing new ones.
   =========================================================================== */

let TESTING = { tree: [], criteria: [], states: [] };
let TEST_COLLAPSED = new Set();   // keys of collapsed groups
let TESTING_LOADED = false;
let TEST_SEARCH = "";        // filters on lot ID and mini ID
// Selecting a lot implies its minis — that's the whole point of the hierarchy,
// so the two sets are kept in step rather than tracked independently.
let TSEL_LOTS = new Set();
let TSEL_MINIS = new Set();

/* A cell is simply checked or not — click to toggle. */
const TEST_STATE_META = {
  "":     { label: "\u2013", cls: "never", title: "Not done \u2014 click to check" },
  "done": { label: "\u2713", cls: "ok",    title: "Done \u2014 click to uncheck" },
};
function nextTestState(cur) { return (cur === "done") ? "" : "done"; }




/* ------------------------------------------------- per-mini test pills */
function miniStatePill(miniPk, key, state) {
  const meta = TEST_STATE_META[state || ""] || TEST_STATE_META[""];
  return `<span class="pill test-pill ${meta.cls}" title="${meta.title}"
    onclick="cycleMiniTest(${miniPk}, '${key}', '${state || ""}')">${meta.label}</span>`;
}
async function cycleMiniTest(miniPk, key, cur) {
  const next = nextTestState(cur);
  try {
    await api(`/testing/minis/${miniPk}/tests`, { method: "PUT", body: { key, state: next } });
    TESTING.tree.forEach(g => g.campaigns.forEach(c => c.lots.forEach(l =>
      l.minis.forEach(m => { if (m.id === miniPk) {
        m.tests = m.tests || {};
        if (next) m.tests[key] = next; else delete m.tests[key];
      } }))));
    paintTesting();
  } catch (e) { alert(e.message); }
}

// The lot row summarises its minis: all done, some done, or none.
function lotRollupPill(lot, key) {
  const minis = lot.minis || [];
  if (!minis.length) return `<span class="help">\u2013</span>`;
  const done = minis.filter(m => (m.tests || {})[key] === "done").length;
  const cls = done === 0 ? "never" : (done === minis.length ? "ok" : "stale");
  const label = done === minis.length ? "\u2713" : `${done}/${minis.length}`;
  const title = done === minis.length ? "All minis done — click to clear all"
    : `${done} of ${minis.length} done — click to mark all done`;
  return `<span class="pill test-pill ${cls}" title="${title}"
    onclick="event.stopPropagation(); cycleLotAll(${lot.id}, '${key}', ${done === minis.length})">${label}</span>`;
}
async function cycleLotAll(lotPk, key, allDone) {
  const state = allDone ? "" : "done";
  try {
    await api(`/testing/lots/${lotPk}/tests-all`, { method: "PUT", body: { key, state } });
    const lot = findLot(lotPk);
    (lot ? lot.minis : []).forEach(m => {
      m.tests = m.tests || {};
      if (state) m.tests[key] = state; else delete m.tests[key];
    });
    paintTesting();
  } catch (e) { alert(e.message); }
}

/* ------------------------------------------------------------- lot detail */
// Actions live here rather than on every row — the grid was drowning in
// Edit/× buttons.
async function openLotDetail(lotPk) {
  const l = findLot(lotPk);
  if (!l) return;
  const row = (k, v) => `<div class="row2"><span>${k}</span><span>${escapeHtml(v || "\u2013")}</span></div>`;
  showModal(`
    <div class="overlay" onclick="if(event.target===this) closeModal()">
      <div class="modal" style="width:520px">
        <header><h3 class="mono">${escapeHtml(l.lot_id || "Lot")}</h3>
          <button class="x" onclick="closeModal()">&times;</button></header>
        <div class="body">
          <div class="item-details" style="display:block;margin-bottom:14px">
            ${row("Description", l.build)}
            ${row("Requestor", l.requestor)}
            ${row("Completed", l.completion_date)}
            ${row("Location", l.location)}
            ${row("Archive location", l.archive_location)}
            ${row("Comments", l.comments)}
            ${row("Minis", String((l.minis || []).length))}
            ${row("Custody", l.checked_out ? `Checked out to ${l.held_by}` : "Available")}
          </div>
          <div class="help">Test results are recorded on each mini — open a mini to see or change its own results.</div>
        </div>
        <footer>
          <button class="btn" onclick="closeModal()">Close</button>
          <button class="btn small" onclick="closeModal(); miniDialog(${l.id})">+ Mini</button>
          <button class="btn primary" onclick="closeModal(); lotDialog(${l.campaign_id}, ${l.id})">Edit</button>
          <button class="btn danger" onclick="closeModal(); deleteLot(${l.id})">Delete</button>
        </footer>
      </div>
    </div>`);
}

/* ------------------------------------------------------- selection + bulk */
function findLot(lotPk) {
  let out = null;
  TESTING.tree.forEach(g => g.campaigns.forEach(c => c.lots.forEach(l => {
    if (l.id === lotPk) out = l;
  })));
  return out;
}
function toggleLotSel(lotPk) {
  const lot = findLot(lotPk);
  if (TSEL_LOTS.has(lotPk)) {
    TSEL_LOTS.delete(lotPk);
    (lot ? lot.minis : []).forEach(m => TSEL_MINIS.delete(m.id));
  } else {
    TSEL_LOTS.add(lotPk);
    (lot ? lot.minis : []).forEach(m => TSEL_MINIS.add(m.id));  // lot implies its minis
  }
  paintTesting();
}
function toggleMiniSel(miniPk, lotPk) {
  if (TSEL_MINIS.has(miniPk)) {
    TSEL_MINIS.delete(miniPk);
    TSEL_LOTS.delete(lotPk);        // no longer the whole lot
  } else {
    TSEL_MINIS.add(miniPk);
    const lot = findLot(lotPk);
    if (lot && lot.minis.every(m => TSEL_MINIS.has(m.id))) TSEL_LOTS.add(lotPk);
  }
  paintTesting();
}
function clearTestSel() { TSEL_LOTS.clear(); TSEL_MINIS.clear(); paintTesting(); }

function testBulkBar() {
  const n = TSEL_LOTS.size + TSEL_MINIS.size;
  if (!n) return "";
  return `
    <div class="bulkbar active" style="margin-bottom:12px">
      <b>${TSEL_LOTS.size}</b> lot${TSEL_LOTS.size === 1 ? "" : "s"} &middot;
      <b>${TSEL_MINIS.size}</b> mini${TSEL_MINIS.size === 1 ? "" : "s"} selected
      <span style="flex:1"></span>
      <button class="btn small" onclick="testBulkEditDialog()">Edit</button>
      <button class="sel-x" onclick="clearTestSel()" title="Clear selection">&times;</button>
    </div>`;
}

// Same tick-to-change pattern as the asset dashboard: untouched fields are
// left alone, so you can set a location across 40 lots without wiping notes.
const TEST_BULK_FIELDS = [
  ["location", "Location"], ["requestor", "Requestor"],
  ["build", "Description"], ["comments", "Comments"],
  ["archive_location", "Archive location"], ["completion_date", "Completion date"],
];
function testBulkEditDialog() {
  const n = TSEL_LOTS.size + TSEL_MINIS.size;
  showModal(`
    <div class="overlay" onclick="if(event.target===this) closeModal()">
      <div class="modal" style="width:520px">
        <header><h3>Edit ${n} selected</h3><button class="x" onclick="closeModal()">&times;</button></header>
        <div class="body">
          <div class="help" style="margin-bottom:12px">Tick a field to change it on everything selected.
            Anything left unticked stays as it is. Setting a location on a lot also updates its minis.</div>
          ${TEST_BULK_FIELDS.map(([k, label]) => `
            <div class="bulk-edit-row">
              <label class="row" style="gap:8px;align-items:center;min-width:150px">
                <input type="checkbox" id="tbe_on_${k}" onchange="tbeToggle('${k}')" />
                <span>${label}</span></label>
              <div style="flex:1"><input id="tbe_${k}" disabled
                ${k === "completion_date" ? 'placeholder="yyyy-mm-dd"' : ""} autocomplete="off" /></div>
            </div>`).join("")}
          <div class="help" style="margin-top:10px">Only Location and Comments apply to minis;
            the rest are lot-level fields.</div>
          <div id="tbe_err" class="help" style="color:var(--red);margin-top:8px"></div>
        </div>
        <footer>
          <button class="btn" onclick="closeModal()">Cancel</button>
          <button class="btn primary" onclick="testBulkEditSave()">Apply to ${n}</button>
        </footer>
      </div>
    </div>`);
}
function tbeToggle(k) {
  const el = document.getElementById("tbe_" + k);
  el.disabled = !document.getElementById("tbe_on_" + k).checked;
  if (!el.disabled) el.focus();
}
async function testBulkEditSave() {
  const fields = {};
  TEST_BULK_FIELDS.forEach(([k]) => {
    if (document.getElementById("tbe_on_" + k).checked)
      fields[k] = document.getElementById("tbe_" + k).value;
  });
  if (!Object.keys(fields).length) {
    document.getElementById("tbe_err").textContent = "Tick at least one field."; return;
  }
  try {
    const r = await api("/testing/bulk-edit", { method: "POST", body: {
      lot_ids: [...TSEL_LOTS], mini_ids: [...TSEL_MINIS], fields } });
    closeModal();
    TSEL_LOTS.clear(); TSEL_MINIS.clear();
    await renderTestingSamples();
    alert(`Updated ${r.lots} lot${r.lots === 1 ? "" : "s"} and ${r.minis} mini${r.minis === 1 ? "" : "s"}.`);
  } catch (e) { document.getElementById("tbe_err").textContent = e.message; }
}

/* ------------------------------------------------------------ mini detail */
async function openMiniDetail(miniPk) {
  let d;
  try { d = await api(`/testing/minis/${miniPk}`); }
  catch (e) { alert(e.message); return; }
  const row = (k, v) => `<div class="row2"><span>${k}</span><span>${escapeHtml(v || "\u2013")}</span></div>`;
  showModal(`
    <div class="overlay" onclick="if(event.target===this) closeModal()">
      <div class="modal" style="width:520px">
        <header><h3>${escapeHtml(d.mini_id || "Mini")}</h3>
          <button class="x" onclick="closeModal()">&times;</button></header>
        <div class="body">
          <div class="item-details" style="display:block;margin-bottom:14px">
            ${row("Department", d.department)}
            ${row("Test / campaign", d.campaign ? d.campaign.name : null)}
            ${row("Lot", d.lot ? d.lot.lot_id : null)}
            ${row("Location", d.location)}
            ${row("Note", d.note)}
          </div>
          ${d.lot ? `
          <div class="help" style="font-weight:600;margin-bottom:6px">From its lot</div>
          <div class="item-details" style="display:block;margin-bottom:14px">
            ${row("Description", d.lot.build)}
            ${row("Requestor", d.lot.requestor)}
            ${row("Completed", d.lot.completion_date)}
            ${row("Archive location", d.lot.archive_location)}
            ${row("Comments", d.lot.comments)}
            ${row("Custody", d.lot.checked_out ? `Checked out to ${d.lot.held_by}` : "Available")}
          </div>` : ""}
          <div class="help" style="font-weight:600;margin-bottom:6px">Test results (recorded on the lot)</div>
          ${d.criteria.length ? `<div class="row" style="gap:6px;flex-wrap:wrap">
            ${d.criteria.map(c => `<span class="pill ${c.state === "done" ? "ok" : "never"}">
              ${escapeHtml(c.label)} ${c.state === "done" ? "\u2713" : "\u2013"}</span>`).join("")}
          </div>` : `<div class="help">No test columns yet \u2014 add one with "+ Field".</div>`}
        </div>
        <footer>
          <button class="btn" onclick="closeModal()">Close</button>
          <button class="btn primary" onclick="closeModal(); miniDialog(${d.lot ? d.lot.id : "null"}, ${d.id})">Edit</button>
          <button class="btn danger" onclick="closeModal(); deleteMini(${d.id})">Delete</button>
        </footer>
      </div>
    </div>`);
}

// Clicking a scan result opens the mini when one was scanned, otherwise the lot.
async function openScanHit(lotPk, miniPk) {
  if (miniPk) return openMiniDetail(miniPk);
  try {
    const t = await api("/testing/tree");
    TESTING = t;
    let lot = null;
    t.tree.forEach(g => g.campaigns.forEach(c => c.lots.forEach(l => {
      if (l.id === lotPk) lot = l;
    })));
    if (lot && lot.minis.length) return openMiniDetail(lot.minis[0].id);
    if (lot) lotDialog(lot.campaign_id, lot.id);
  } catch (e) { alert(e.message); }
}

/* ------------------------------------------------------------------ search */
// Filters the tree down to lots whose lot ID matches, or that contain a
// matching mini. A matching lot keeps all its minis so you can see the whole
// group; a lot matched only via a mini shows just the minis that matched.
function filterTestingTree(tree, q) {
  const term = (q || "").trim().toLowerCase();
  if (!term) return tree;
  const out = [];
  (tree || []).forEach(g => {
    const camps = [];
    (g.campaigns || []).forEach(c => {
      const lots = [];
      (c.lots || []).forEach(l => {
        const lotHit = (l.lot_id || "").toLowerCase().includes(term);
        const hitMinis = (l.minis || []).filter(m =>
          (m.mini_id || "").toLowerCase().includes(term));
        if (lotHit) lots.push(l);
        else if (hitMinis.length) lots.push(Object.assign({}, l, { minis: hitMinis }));
      });
      if (lots.length) camps.push(Object.assign({}, c, { lots }));
    });
    if (camps.length) out.push(Object.assign({}, g, { campaigns: camps }));
  });
  return out;
}

let TEST_SEARCH_TIMER = null;
function onTestSearch(v) {
  TEST_SEARCH = v;
  clearTimeout(TEST_SEARCH_TIMER);
  // Filtering is client-side, so this only debounces the repaint.
  TEST_SEARCH_TIMER = setTimeout(() => {
    const caret = (document.getElementById("testSearch") || {}).selectionStart;
    paintTesting();
    const box = document.getElementById("testSearch");
    if (box) { box.focus(); if (caret != null) box.setSelectionRange(caret, caret); }
  }, 120);
}

/* ------------------------------------------------------- scan / check out */
// Inline "+ Field" in the header — quicker than opening the manager just to
// add a column, which is the common case.
async function quickAddCriterion() {
  const label = prompt("New test column name (e.g. RnD Burn-In):");
  if (!label || !label.trim()) return;
  try {
    await api("/testing/criteria", { method: "POST", body: { label: label.trim() } });
    await renderTestingSamples();
  } catch (e) { alert(e.message); }
}

let TEST_SCAN_MODE = "checkout";
let TEST_SCAN_NAME = "";        // sticky between scans, on purpose
let TEST_SCAN_FEED = [];

function goTestingScan() { PAGE = "testingscan"; renderTestingScan(); }

async function renderTestingScan() {
  const modes = [["lookup", "Look up"], ["checkout", "Check out to\u2026"], ["return", "Return"]];
  const app = document.getElementById("app");
  app.innerHTML = `
    <div class="topbar">
      <div class="brand-header">
        <img src="/static/frore-logo.png" class="frore-logo" alt="Frore logo" />
        <div class="brand-copy">
          <div class="brand-title">Frore Systems</div>
          <div class="brand-subtitle">Inventory Management Dashboard</div>
        </div>
      </div>
      <span class="topbar-user">${escapeHtml(ME.full_name || "Guest")}</span>
      <button class="nav-pill" onclick="goTesting()"><i class="ti ti-arrow-left"></i> Back to testing</button>
    </div>
    <div class="wrap">
      <h2 style="margin:0 0 4px;font-family:var(--display);font-size:20px">Scan test samples</h2>
      <div class="help" style="margin-bottom:14px">Scan a lot or a mini &mdash; a mini resolves to its lot.</div>
      <div class="row" style="gap:6px;margin-bottom:12px">
        ${modes.map(([k, label]) => `
          <button class="btn scan-mode${TEST_SCAN_MODE === k ? " primary" : ""}"
                  onclick="setTestScanMode('${k}')">${label}</button>`).join("")}
      </div>
      <div id="testScanNameWrap" style="${TEST_SCAN_MODE === "checkout" ? "" : "display:none"}">
        <div class="row" style="gap:8px;align-items:center;background:var(--amber-bg);
             border:1px solid #f0c060;border-radius:8px;padding:10px 12px;margin-bottom:6px">
          <span class="help" style="white-space:nowrap">Lending everything scanned to:</span>
          <input id="testScanName" placeholder="Type a name\u2026" autocomplete="off"
                 value="${escapeHtml(TEST_SCAN_NAME)}" oninput="TEST_SCAN_NAME = this.value"
                 style="flex:1;padding:7px 10px;border:1px solid #dde2e7;border-radius:6px" />
        </div>
        <div class="help" style="text-align:center;margin-bottom:12px">
          The name stays put between scans &mdash; type it once, then keep scanning.</div>
      </div>
      <input id="testScanInput" placeholder="Scan or type a code\u2026" autocomplete="off"
             onkeydown="if(event.key==='Enter'){event.preventDefault();submitTestScan(this.value);this.value='';}"
             style="width:100%;padding:18px;font-size:19px;font-family:var(--mono);
                    border:2px solid var(--accent);border-radius:10px;text-align:center;box-sizing:border-box" />
      <div id="testScanFeed" style="margin-top:16px"></div>
    </div>`;
  paintTestScanFeed();
  const el = document.getElementById(
    TEST_SCAN_MODE === "checkout" && !TEST_SCAN_NAME ? "testScanName" : "testScanInput");
  if (el) el.focus();
}
function setTestScanMode(m) { TEST_SCAN_MODE = m; renderTestingScan(); }

async function submitTestScan(code) {
  code = (code || "").trim();
  if (!code) return;
  if (TEST_SCAN_MODE === "checkout" && !TEST_SCAN_NAME.trim()) {
    TEST_SCAN_FEED.unshift({ ok: false, msg: "Enter a name first, then scan." });
    paintTestScanFeed();
    const n = document.getElementById("testScanName"); if (n) n.focus();
    return;
  }
  try {
    const r = await api("/testing/scan", { method: "POST", body: {
      code, mode: TEST_SCAN_MODE, held_by: TEST_SCAN_NAME } });
    TEST_SCAN_FEED.unshift({ ok: true, lot: r.lot.lot_id, lotPk: r.lot.id,
      matched: r.matched, matchedId: r.matched_id, miniPk: r.mini_id || null,
      msg: r.message, ts: new Date() });
  } catch (e) {
    TEST_SCAN_FEED.unshift({ ok: false, code, msg: e.message || "Not found" });
  }
  paintTestScanFeed();
  const box = document.getElementById("testScanInput"); if (box) box.focus();
}

function paintTestScanFeed() {
  const el = document.getElementById("testScanFeed");
  if (!el) return;
  if (!TEST_SCAN_FEED.length) {
    el.innerHTML = `<div class="help" style="text-align:center">Scans appear here.</div>`;
    return;
  }
  el.innerHTML = TEST_SCAN_FEED.slice(0, 40).map(s => s.ok
    ? `<div class="scan-hit clickable" onclick="openScanHit(${s.lotPk}, ${s.miniPk || "null"})"
           title="Open details"><span class="dot"></span>
         <span class="name"><b class="mono">${escapeHtml(s.lot)}</b>
         ${s.matched === "mini" ? `<span class="help"> via mini ${escapeHtml(s.matchedId)}</span>` : ""}
         <span class="help"> &mdash; ${escapeHtml(s.msg)}</span></span>
         <span class="time">${s.ts.toLocaleTimeString()}</span></div>`
    : `<div class="scan-hit" style="border-left:3px solid var(--red)">
         <span class="name" style="color:var(--red)">${escapeHtml(s.msg)}</span></div>`).join("");
}

/* ------------------------------------------------------------ load + render */
async function renderTestingSamples() {
  const app = document.getElementById("app");
  app.innerHTML = `
    <div class="topbar">
      <div class="brand-header">
        <img src="/static/frore-logo.png" class="frore-logo" alt="Frore logo" />
        <div class="brand-copy">
          <div class="brand-title">Frore Systems</div>
          <div class="brand-subtitle">Inventory Management Dashboard</div>
        </div>
      </div>
      <span class="topbar-user">${escapeHtml(ME.full_name || "Guest")}</span>
      <button class="nav-pill" onclick="renderTestingSamples()"><i class="ti ti-refresh"></i> Refresh</button>
      <button class="nav-pill" onclick="goDashboard()"><i class="ti ti-arrow-left"></i> Done</button>
    </div>
    <div class="wrap">
      <div class="row" style="margin-bottom:14px;align-items:center">
        <h2 style="margin:0;font-family:var(--display);font-size:20px">Testing Inventory</h2>
        <span class="help" style="margin-left:10px">Department &rsaquo; Test &rsaquo; Lot &rsaquo; Mini</span>
        <span style="flex:1"></span>
        <button class="btn small" onclick="goTestingScan()">Scan</button>
        <button class="btn small" onclick="testImportDialog()">Import from Excel</button>
        <button class="btn primary small" onclick="campaignDialog()">+ New test</button>
      </div>
      <div class="row" style="margin-bottom:12px">
        <input id="testSearch" placeholder="Search lot or mini ID&hellip;" autocomplete="off"
               value="${escapeHtml(TEST_SEARCH)}" oninput="onTestSearch(this.value)"
               style="flex:1;max-width:420px;padding:8px 10px;border:1px solid #dde2e7;border-radius:6px" />
        <span id="testSearchInfo" class="help" style="align-self:center"></span>
      </div>
      <div id="testingBody"><div class="empty">Loading&hellip;</div></div>
    </div>`;
  try {
    TESTING = await api("/testing/tree");
    if (!TESTING_LOADED) { applyTestingFolding(); TESTING_LOADED = true; }
    paintTesting();
  } catch (e) {
    document.getElementById("testingBody").innerHTML =
      `<div class="empty" style="color:var(--red)">Couldn't load testing data. ${escapeHtml(e.message || "")}</div>`;
  }
}

/* Mirrors the dashboard: your own department opens, everything else folds. */
function applyTestingFolding() {
  TEST_COLLAPSED.clear();
  const mine = (typeof MY_DEPARTMENT_ID !== "undefined") ? MY_DEPARTMENT_ID : null;
  if (mine == null) return;
  TESTING.tree.forEach(g => {
    if (g.department_id !== mine) TEST_COLLAPSED.add("d" + g.department_id);
  });
}

function toggleTestGroup(key) {
  if (TEST_COLLAPSED.has(key)) TEST_COLLAPSED.delete(key); else TEST_COLLAPSED.add(key);
  paintTesting();
}

function testStatePill(lotPk, key, state) {
  const meta = TEST_STATE_META[state || ""] || TEST_STATE_META[""];
  return `<span class="pill test-pill ${meta.cls}"
    title="${meta.title} — click to change"
    onclick="cycleTest(${lotPk}, '${key}', '${state || ""}')">${meta.label}</span>`;
}

function paintTesting() {
  const box = document.getElementById("testingBody");
  if (!box) return;
  const crits = TESTING.criteria || [];

  if (!TESTING.tree.length) {
    box.innerHTML = `<div class="card"><div class="empty">
      No tests yet. Click <b>+ New test</b> to create your first campaign.</div></div>`;
    return;
  }

  const colCount = 5 + crits.length;
  const tree = filterTestingTree(TESTING.tree, TEST_SEARCH);
  const info = document.getElementById("testSearchInfo");
  if (info) {
    const n = tree.reduce((a, g) => a + g.campaigns.reduce((b, c) => b + c.lots.length, 0), 0);
    info.textContent = TEST_SEARCH ? `${n} lot${n === 1 ? "" : "s"} match` : "";
  }
  if (TEST_SEARCH && !tree.length) {
    box.innerHTML = `<div class="empty">Nothing matches &ldquo;${escapeHtml(TEST_SEARCH)}&rdquo;.</div>`;
    return;
  }
  box.innerHTML = testBulkBar() + tree.map(g => {
    const dKey = "d" + g.department_id;
    const dOpen = !TEST_COLLAPSED.has(dKey);
    const lotTotal = g.campaigns.reduce((n, c) => n + c.lots.length, 0);
    return `
      <div class="card" style="margin-bottom:14px;padding:0;overflow:hidden">
        <div class="group-head" style="cursor:pointer;padding:11px 14px"
             onclick="toggleTestGroup('${dKey}')">
          <span class="group-caret${dOpen ? "" : " collapsed"}">&#9662;</span>
          <span class="group-name">${escapeHtml(g.department)}</span>
          <span class="help">(${g.campaigns.length} test${g.campaigns.length === 1 ? "" : "s"},
            ${lotTotal} lot${lotTotal === 1 ? "" : "s"})</span>
        </div>
        ${!dOpen ? "" : g.campaigns.map(c => {
          const cKey = "c" + c.id;
          const cOpen = !TEST_COLLAPSED.has(cKey);
          return `
          <div style="border-top:1px solid var(--line-soft)">
            <div class="row" style="padding:9px 14px 9px 30px;align-items:center;background:#fbfcfe">
              <span class="group-caret${cOpen ? "" : " collapsed"}" style="cursor:pointer"
                    onclick="toggleTestGroup('${cKey}')">&#9662;</span>
              <b style="cursor:pointer" onclick="toggleTestGroup('${cKey}')">${escapeHtml(c.name)}</b>
              ${c.description ? `<span class="help">&middot; ${escapeHtml(c.description)}</span>` : ""}
              <span style="flex:1"></span>
              <button class="btn small" onclick="lotDialog(${c.id})">+ Lot</button>
              <button class="btn small" onclick="campaignDialog(${c.id})">Edit</button>
              <button class="btn small danger" onclick="deleteCampaign(${c.id})">Delete</button>
            </div>
            ${!cOpen ? "" : `
            <div class="tablewrap"><table>
              <thead><tr>
                <th class="sel-col"></th>
                <th style="min-width:170px">Lot / Mini</th>
                <th style="min-width:105px">Completed</th>
                <th style="min-width:95px">Requestor</th>
                <th style="min-width:130px">Location</th>
                ${crits.map(cr => `<th style="text-align:center">${escapeHtml(cr.label)}</th>`).join("")}
                <th style="text-align:center;min-width:78px">
                  <button class="btn small" title="Add a test column"
                          onclick="quickAddCriterion()">+ Field</button></th>
                <th></th>
              </tr></thead>
              <tbody>
                ${c.lots.length ? c.lots.map(l => lotRows(l, crits)).join("")
                  : `<tr><td colspan="${colCount}" class="empty">No lots in this test yet.</td></tr>`}
              </tbody>
            </table></div>`}
          </div>`;
        }).join("")}
      </div>`;
  }).join("");
}

function lotRows(l, crits) {
  const lKey = "l" + l.id;
  const open = !TEST_COLLAPSED.has(lKey);
  const head = `
    <tr class="test-lot-row clickable" onclick="openLotDetail(${l.id})">
      <td class="sel-col" onclick="event.stopPropagation()">
        <input type="checkbox" ${TSEL_LOTS.has(l.id) ? "checked" : ""}
               onchange="toggleLotSel(${l.id})" /></td>
      <td>
        ${l.minis.length ? `<span class="group-caret${open ? "" : " collapsed"}"
            style="cursor:pointer;margin-right:4px" onclick="toggleTestGroup('${lKey}')">&#9662;</span>`
          : `<span style="display:inline-block;width:14px"></span>`}
        <b class="mono">${escapeHtml(l.lot_id)}</b>
        ${l.minis.length ? `<span class="help"> (${l.minis.length})</span>` : ""}
        ${l.build ? `<div class="help" style="margin-left:18px">${escapeHtml(l.build)}</div>` : ""}
        ${l.comments ? `<div class="help" style="margin-left:18px;color:var(--amber)">${escapeHtml(l.comments)}</div>` : ""}
        ${l.checked_out ? `<div style="margin-left:18px;margin-top:3px">
          <span class="pill custody">out \u2192 ${escapeHtml(l.held_by || "?")}</span></div>` : ""}
      </td>
      <td class="mono">${l.completion_date ? new Date(l.completion_date + "T00:00:00").toLocaleDateString() : "\u2013"}</td>
      <td>${escapeHtml(l.requestor || "\u2013")}</td>
      <td>${escapeHtml(l.location || "\u2013")}
        ${l.archive_location ? `<div class="help">${escapeHtml(l.archive_location)}</div>` : ""}</td>
      ${crits.map(cr => `<td style="text-align:center">${lotRollupPill(l, cr.key)}</td>`).join("")}
      <td></td>
      <td></td>
    </tr>`;
  if (!open) return head;
  const kids = l.minis.map(m => `
    <tr class="test-mini-row clickable" onclick="openMiniDetail(${m.id})">
      <td class="sel-col" onclick="event.stopPropagation()">
        <input type="checkbox" ${TSEL_MINIS.has(m.id) ? "checked" : ""}
               onchange="toggleMiniSel(${m.id}, ${l.id})" /></td>
      <td style="padding-left:34px">
        <span class="mono" style="font-size:12.5px">${escapeHtml(m.mini_id || "")}</span>
        ${m.note ? `<span class="help"> &middot; ${escapeHtml(m.note)}</span>` : ""}
      </td>
      <td></td><td></td>
      <td>${m.location ? escapeHtml(m.location) : `<span class="help">\u2013</span>`}</td>
      ${(TESTING.criteria || []).map(cr => `<td style="text-align:center" onclick="event.stopPropagation()">
        ${miniStatePill(m.id, cr.key, (m.tests || {})[cr.key])}</td>`).join("")}
      <td></td>
      <td></td>
    </tr>`).join("");
  return head + kids;
}

/* --------------------------------------------------------- cycle a status */
async function cycleTest(lotPk, key, cur) {
  const next = nextTestState(cur);
  try {
    await api(`/testing/lots/${lotPk}/tests`, { method: "PUT", body: { key, state: next } });
    // patch in place so the whole tree doesn't re-fetch on every click
    TESTING.tree.forEach(g => g.campaigns.forEach(c => c.lots.forEach(l => {
      if (l.id === lotPk) {
        l.tests = l.tests || {};
        if (next) l.tests[key] = next; else delete l.tests[key];
      }
    })));
    paintTesting();
  } catch (e) { alert(e.message); }
}

/* --------------------------------------------------------------- campaigns */
function campaignDialog(id) {
  let c = null;
  TESTING.tree.forEach(g => g.campaigns.forEach(x => { if (x.id === id) c = x; }));
  const deptOpts = (typeof DEPARTMENTS !== "undefined" ? DEPARTMENTS : []).map(d =>
    `<option value="${d.id}" ${c && c.department_id === d.id ? "selected" : ""}>${escapeHtml(d.name)}</option>`).join("");
  showModal(`
    <div class="overlay" onclick="if(event.target===this) closeModal()">
      <div class="modal" style="width:460px">
        <header><h3>${c ? "Edit test" : "New test"}</h3><button class="x" onclick="closeModal()">&times;</button></header>
        <div class="body">
          <label class="f"><span>Test name *</span>
            <input id="tc_name" value="${c ? escapeHtml(c.name) : ""}"
                   placeholder="e.g. Gen3 Soft BCH Comparison" autocomplete="off" /></label>
          <label class="f" style="margin-top:10px"><span>Department</span>
            <select id="tc_dept"><option value="">\u2014 none \u2014</option>${deptOpts}</select></label>
          <label class="f" style="margin-top:10px"><span>Description</span>
            <input id="tc_desc" value="${c && c.description ? escapeHtml(c.description) : ""}"
                   placeholder="optional" autocomplete="off" /></label>
          <div id="tc_err" class="help" style="color:var(--red);margin-top:8px"></div>
        </div>
        <footer>
          <button class="btn" onclick="closeModal()">Cancel</button>
          <button class="btn primary" onclick="saveCampaign(${c ? c.id : "null"})">Save</button>
        </footer>
      </div>
    </div>`);
}
async function saveCampaign(id) {
  const body = {
    name: document.getElementById("tc_name").value,
    department_id: document.getElementById("tc_dept").value || null,
    description: document.getElementById("tc_desc").value,
  };
  try {
    if (id) await api(`/testing/campaigns/${id}`, { method: "PUT", body });
    else await api("/testing/campaigns", { method: "POST", body });
    closeModal(); await renderTestingSamples();
  } catch (e) { document.getElementById("tc_err").textContent = e.message; }
}
async function deleteCampaign(id) {
  if (!confirm("Delete this test and every lot and mini inside it?\n\nThis cannot be undone.")) return;
  try { await api(`/testing/campaigns/${id}`, { method: "DELETE" }); await renderTestingSamples(); }
  catch (e) { alert(e.message); }
}

/* -------------------------------------------------------------------- lots */
function lotDialog(campaignId, lotPk) {
  let l = null;
  TESTING.tree.forEach(g => g.campaigns.forEach(c => c.lots.forEach(x => { if (x.id === lotPk) l = x; })));
  showModal(`
    <div class="overlay" onclick="if(event.target===this) closeModal()">
      <div class="modal" style="width:520px">
        <header><h3>${l ? "Edit lot" : "New lot"}</h3><button class="x" onclick="closeModal()">&times;</button></header>
        <div class="body">
          <label class="f"><span>Lot ID *</span>
            <input id="tl_lot" value="${l ? escapeHtml(l.lot_id) : ""}"
                   placeholder="e.g. B2551-01 or L2605015E" autocomplete="off" /></label>
          <label class="f" style="margin-top:10px"><span>Build / description</span>
            <input id="tl_build" value="${l && l.build ? escapeHtml(l.build) : ""}"
                   placeholder="e.g. Gen3 BL 1F07M_1F12" autocomplete="off" /></label>
          <div class="row" style="gap:10px;margin-top:10px">
            <label class="f" style="flex:1"><span>Requestor</span>
              <input id="tl_req" value="${l && l.requestor ? escapeHtml(l.requestor) : ""}" autocomplete="off" /></label>
            <label class="f" style="flex:1"><span>Completion date</span>
              <input id="tl_date" type="date" value="${l && l.completion_date ? l.completion_date : ""}" /></label>
          </div>
          <div class="row" style="gap:10px;margin-top:10px">
            <label class="f" style="flex:1"><span>Test location</span>
              <input id="tl_loc" value="${l && l.location ? escapeHtml(l.location) : ""}"
                     placeholder="e.g. RnD Single Tile Tester" autocomplete="off" /></label>
            <label class="f" style="flex:1"><span>Archive location</span>
              <input id="tl_arch" value="${l && l.archive_location ? escapeHtml(l.archive_location) : ""}"
                     placeholder="e.g. Acoustic Lab" autocomplete="off" /></label>
          </div>
          <label class="f" style="margin-top:10px"><span>Comments</span>
            <input id="tl_com" value="${l && l.comments ? escapeHtml(l.comments) : ""}"
                   placeholder="e.g. HDT skipped, not signed off" autocomplete="off" /></label>
          <div id="tl_err" class="help" style="color:var(--red);margin-top:8px"></div>
        </div>
        <footer>
          <button class="btn" onclick="closeModal()">Cancel</button>
          <button class="btn primary" onclick="saveLot(${campaignId}, ${lotPk || "null"})">Save</button>
        </footer>
      </div>
    </div>`);
}
async function saveLot(campaignId, lotPk) {
  const body = {
    campaign_id: campaignId,
    lot_id: document.getElementById("tl_lot").value,
    build: document.getElementById("tl_build").value,
    requestor: document.getElementById("tl_req").value,
    completion_date: document.getElementById("tl_date").value || null,
    location: document.getElementById("tl_loc").value,
    archive_location: document.getElementById("tl_arch").value,
    comments: document.getElementById("tl_com").value,
  };
  try {
    if (lotPk) await api(`/testing/lots/${lotPk}`, { method: "PUT", body });
    else await api("/testing/lots", { method: "POST", body });
    closeModal(); await renderTestingSamples();
  } catch (e) { document.getElementById("tl_err").textContent = e.message; }
}
async function deleteLot(lotPk) {
  if (!confirm("Delete this lot and all its minis?")) return;
  try { await api(`/testing/lots/${lotPk}`, { method: "DELETE" }); await renderTestingSamples(); }
  catch (e) { alert(e.message); }
}

/* ------------------------------------------------------------------- minis */
function miniDialog(lotPk, miniPk) {
  let m = null;
  TESTING.tree.forEach(g => g.campaigns.forEach(c => c.lots.forEach(l =>
    l.minis.forEach(x => { if (x.id === miniPk) m = x; }))));
  showModal(`
    <div class="overlay" onclick="if(event.target===this) closeModal()">
      <div class="modal" style="width:440px">
        <header><h3>${m ? "Edit mini" : "Add mini"}</h3><button class="x" onclick="closeModal()">&times;</button></header>
        <div class="body">
          <label class="f"><span>Mini ID *</span>
            <input id="tm_id" value="${m ? escapeHtml(m.mini_id || "") : ""}"
                   placeholder="e.g. AET253900031-006-04" autocomplete="off" /></label>
          <label class="f" style="margin-top:10px"><span>Location</span>
            <input id="tm_loc" value="${m && m.location ? escapeHtml(m.location) : ""}"
                   placeholder="e.g. Acoustic Lab \u2014 Shelf 3" autocomplete="off" /></label>
          <label class="f" style="margin-top:10px"><span>Note</span>
            <input id="tm_note" value="${m && m.note ? escapeHtml(m.note) : ""}"
                   placeholder="e.g. Taken for Dust Test" autocomplete="off" /></label>
          <div class="help" style="margin-top:8px">Test results are recorded on the lot, not per mini.</div>
          <div id="tm_err" class="help" style="color:var(--red);margin-top:8px"></div>
        </div>
        <footer>
          <button class="btn" onclick="closeModal()">Cancel</button>
          <button class="btn primary" onclick="saveMini(${lotPk}, ${miniPk || "null"})">Save</button>
        </footer>
      </div>
    </div>`);
}
async function saveMini(lotPk, miniPk) {
  const body = { lot_id: lotPk, mini_id: document.getElementById("tm_id").value,
                 location: document.getElementById("tm_loc").value,
                 note: document.getElementById("tm_note").value };
  try {
    if (miniPk) await api(`/testing/minis/${miniPk}`, { method: "PUT", body });
    else await api("/testing/minis", { method: "POST", body });
    closeModal(); await renderTestingSamples();
  } catch (e) { document.getElementById("tm_err").textContent = e.message; }
}
async function deleteMini(miniPk) {
  if (!confirm("Remove this mini?")) return;
  try { await api(`/testing/minis/${miniPk}`, { method: "DELETE" }); await renderTestingSamples(); }
  catch (e) { alert(e.message); }
}

/* ------------------------------------------------- criteria (the columns) */
async function openCriteriaManager() {
  let rows = [];
  try { rows = await api("/testing/criteria"); } catch (e) { alert(e.message); return; }
  showModal(`
    <div class="overlay" onclick="if(event.target===this) closeModal()">
      <div class="modal" style="width:520px">
        <header><h3>Test columns</h3><button class="x" onclick="closeModal()">&times;</button></header>
        <div class="body">
          <div class="help" style="margin-bottom:10px">Each row here is a column in the testing grid.
            Removing one hides it but keeps any results already recorded, so adding it back restores them.</div>
          <table><thead><tr><th>Column</th><th>Key</th><th></th></tr></thead>
            <tbody>${rows.map(r => `<tr style="${r.active ? "" : "opacity:.45"}">
              <td><input value="${escapeHtml(r.label)}" style="width:100%"
                         onchange="saveCriterion(${r.id}, this.value)" /></td>
              <td class="mono help">${escapeHtml(r.key)}</td>
              <td style="white-space:nowrap">${r.active
                ? `<button class="btn small danger" onclick="removeCriterion(${r.id})">Remove</button>`
                : `<button class="btn small" onclick="restoreCriterion(${r.id})">Restore</button>`}</td>
            </tr>`).join("")}</tbody></table>
          <div class="row" style="margin-top:12px">
            <input id="tcr_new" placeholder="New column name, e.g. RnD Burn-In" style="flex:1"
                   autocomplete="off" onkeydown="if(event.key==='Enter')addCriterion()" />
            <button class="btn primary" onclick="addCriterion()">Add</button>
          </div>
          <div id="tcr_err" class="help" style="color:var(--red);margin-top:8px"></div>
        </div>
        <footer><button class="btn" onclick="closeModal()">Close</button></footer>
      </div>
    </div>`);
}
async function addCriterion() {
  const label = document.getElementById("tcr_new").value.trim();
  if (!label) return;
  try { await api("/testing/criteria", { method: "POST", body: { label } });
    await openCriteriaManager(); await refreshTestingTree(); }
  catch (e) { document.getElementById("tcr_err").textContent = e.message; }
}
async function saveCriterion(id, label) {
  try { await api(`/testing/criteria/${id}`, { method: "PUT", body: { label } });
    await refreshTestingTree(); }
  catch (e) { alert(e.message); }
}
async function removeCriterion(id) {
  if (!confirm("Remove this column from the grid?\n\nResults already recorded are kept and will reappear if you add it back.")) return;
  try { await api(`/testing/criteria/${id}`, { method: "DELETE" });
    await openCriteriaManager(); await refreshTestingTree(); }
  catch (e) { alert(e.message); }
}
async function restoreCriterion(id) {
  try { await api(`/testing/criteria/${id}`, { method: "PUT", body: { active: true } });
    await openCriteriaManager(); await refreshTestingTree(); }
  catch (e) { alert(e.message); }
}
async function refreshTestingTree() {
  try { TESTING = await api("/testing/tree"); paintTesting(); } catch (e) { /* modal stays open */ }
}

/* -------------------------------------------------- excel import wizard */
let TIMP = { file: null, sheet: "", headerRow: 1, columns: [], fields: [] };

function testImportDialog() {
  const camps = [];
  TESTING.tree.forEach(g => g.campaigns.forEach(c =>
    camps.push({ id: c.id, label: `${g.department || "(no department)"} — ${c.name}` })));
  showModal(`
    <div class="overlay" onclick="if(event.target===this) closeModal()">
      <div class="modal" style="width:520px">
        <header><h3>Import from Excel</h3><button class="x" onclick="closeModal()">&times;</button></header>
        <div class="body">
          <div class="help" style="margin-bottom:12px">Everything in the file imports into one test
            campaign, which already carries its department.</div>
          <label class="f"><span>Import into *</span>
            <select id="ti_camp">
              ${camps.length ? camps.map(c => `<option value="${c.id}">${escapeHtml(c.label)}</option>`).join("")
                             : `<option value="">— create a test first —</option>`}
            </select></label>
          <label class="f" style="margin-top:10px"><span>Excel file *</span>
            <input id="ti_file" type="file" accept=".xlsx,.xlsm" /></label>
          <label class="f" style="margin-top:10px"><span>Header row</span>
            <input id="ti_hdr" type="number" value="1" min="1" style="width:90px" /></label>
          <div id="ti_err" class="help" style="color:var(--red);margin-top:8px"></div>
        </div>
        <footer>
          <button class="btn" onclick="closeModal()">Cancel</button>
          <button class="btn primary" onclick="testImportLoad()">Load file</button>
        </footer>
      </div>
    </div>`);
}

async function testImportLoad() {
  const err = document.getElementById("ti_err"); err.textContent = "";
  const f = document.getElementById("ti_file").files[0];
  const camp = document.getElementById("ti_camp").value;
  if (!camp) { err.textContent = "Create a test campaign first."; return; }
  if (!f) { err.textContent = "Pick an .xlsx file."; return; }
  TIMP.file = f;
  TIMP.campaign = camp;
  TIMP.headerRow = Number(document.getElementById("ti_hdr").value) || 1;
  const fd = new FormData();
  fd.append("file", f); fd.append("header_row", TIMP.headerRow); fd.append("sheet", "");
  try {
    const r = await apiForm("/testing/import/inspect", fd);
    TIMP.columns = r.columns; TIMP.sheet = r.sheet; TIMP.sheets = r.sheets || [r.sheet];
    TIMP.fields = [{ label: "", column: "" }];
    testImportMapDialog();
  } catch (e) { err.textContent = e.message; }
}

// Field #1..#N are the manually chosen test columns — the whole point is that
// the app can't guess which spreadsheet columns are tests.
function testImportMapDialog() {
  const opt = sel => `<option value="">— none —</option>` +
    TIMP.columns.map(c => `<option value="${escapeHtml(c)}" ${c === sel ? "selected" : ""}>${escapeHtml(c)}</option>`).join("");
  const guess = (...names) => TIMP.columns.find(c =>
    names.some(n => c.toLowerCase().replace(/[^a-z]/g, "") === n)) || "";
  const rows = [
    ["lot_id", "Lot ID *", guess("lotid")],
    ["mini_id", "Mini ID", guess("miniids", "miniid")],
    ["build", "Description", guess("description", "build")],
    ["completion_date", "Completion date", guess("completiondate")],
    ["requestor", "Requestor", guess("requestor")],
    ["location", "Location", guess("ftttestlocation", "location")],
    ["archive_location", "Archive location", guess("archivelocation")],
    ["comments", "Comments", guess("comments")],
  ];
  showModal(`
    <div class="overlay" onclick="if(event.target===this) closeModal()">
      <div class="modal" style="width:600px">
        <header><h3>Match the columns</h3><button class="x" onclick="closeModal()">&times;</button></header>
        <div class="body" style="max-height:460px;overflow-y:auto">
          <div class="help" style="margin-bottom:10px">Sheet: <b>${escapeHtml(TIMP.sheet)}</b></div>
          <table><tbody>
            ${rows.map(([k, label, g]) => `<tr>
              <td style="white-space:nowrap;padding-right:10px">${label}</td>
              <td><select id="tim_${k}" style="width:100%">${opt(g)}</select></td>
            </tr>`).join("")}
          </tbody></table>
          <div style="margin-top:16px;border-top:1px solid var(--line);padding-top:12px">
            <div class="row" style="align-items:center;margin-bottom:6px">
              <b style="font-size:13px">Test columns</b>
              <span class="help" style="margin-left:8px">Name each one and point it at a column</span>
              <span style="flex:1"></span>
              <button class="btn small" onclick="timAddField()">+ Field</button>
            </div>
            <div id="tim_fields"></div>
          </div>
          <div id="tim_err" class="help" style="color:var(--red);margin-top:8px"></div>
        </div>
        <footer>
          <button class="btn" onclick="testImportDialog()">&larr; Back</button>
          <button class="btn primary" onclick="testImportCommit()">Import</button>
        </footer>
      </div>
    </div>`);
  timPaintFields();
}

function timPaintFields() {
  const el = document.getElementById("tim_fields");
  if (!el) return;
  el.innerHTML = TIMP.fields.map((f, i) => `
    <div class="row" style="gap:8px;margin-bottom:6px;align-items:center">
      <span class="help" style="min-width:56px">Field #${i + 1}</span>
      <input value="${escapeHtml(f.label)}" placeholder="Name, e.g. RnD FTT"
             oninput="TIMP.fields[${i}].label = this.value" style="flex:1" />
      <select onchange="TIMP.fields[${i}].column = this.value" style="flex:1">
        <option value="">— column —</option>
        ${TIMP.columns.map(c => `<option value="${escapeHtml(c)}" ${c === f.column ? "selected" : ""}>${escapeHtml(c)}</option>`).join("")}
      </select>
      <button class="btn small danger" onclick="timRemoveField(${i})">&times;</button>
    </div>`).join("");
}
function timAddField() { TIMP.fields.push({ label: "", column: "" }); timPaintFields(); }
function timRemoveField(i) { TIMP.fields.splice(i, 1); timPaintFields(); }

async function testImportCommit() {
  const err = document.getElementById("tim_err"); err.textContent = "";
  const mapping = {};
  ["lot_id", "mini_id", "build", "completion_date", "requestor",
   "location", "archive_location", "comments"].forEach(k => {
    const v = document.getElementById("tim_" + k).value;
    if (v) mapping[k] = v;
  });
  if (!mapping.lot_id) { err.textContent = "Lot ID must be mapped."; return; }
  const fields = TIMP.fields.filter(f => f.label.trim() && f.column);
  const fd = new FormData();
  fd.append("file", TIMP.file);
  fd.append("header_row", TIMP.headerRow);
  fd.append("sheet", TIMP.sheet);
  fd.append("mapping", JSON.stringify(mapping));
  fd.append("test_fields", JSON.stringify(fields));
  fd.append("campaign_id", TIMP.campaign);
  try {
    const r = await apiForm("/testing/import/commit", fd);
    closeModal();
    await renderTestingSamples();
    alert(`Imported into ${r.campaign}:\n${r.lots_created} lots, ${r.minis_created} minis.\n` +
          `${r.rows_skipped} rows skipped (banners/blank).`);
  } catch (e) { err.textContent = e.message; }
}
