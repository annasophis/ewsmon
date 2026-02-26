const REFRESH_MS = 10_000;
const STORAGE_KEY_FILTER = "ewsmon_env_filter";
const STORAGE_KEY_INCIDENT_TIMELINE_OPEN = "ewsmon_incident_timeline_open";
const STORAGE_KEY_INCIDENT_HISTORY_OPEN = "ewsmon_incident_history_open";
const STORAGE_KEY_THEME = "ewsmon_theme";
const INCIDENT_MSG_TRUNCATE = 120;

function getStoredTheme() {
  try {
    const v = localStorage.getItem(STORAGE_KEY_THEME);
    if (v === "dark" || v === "light") return v;
  } catch (_) {}
  return "light";
}

function setStoredTheme(theme) {
  try {
    localStorage.setItem(STORAGE_KEY_THEME, theme);
  } catch (_) {}
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
}

function initThemeToggle() {
  var themeToggle = document.getElementById("themeToggle");
  if (!themeToggle) return;
  themeToggle.addEventListener("click", function () {
    var next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    setStoredTheme(next);
    applyTheme(next);
    themeToggle.setAttribute("aria-label", next === "dark" ? "Switch to dark mode" : "Switch to light mode");
  });
  var current = getStoredTheme();
  themeToggle.setAttribute("aria-label", current === "dark" ? "Switch to light mode" : "Switch to dark mode");
}

/** Infer environment: "uat" if name contains "(UAT)" or url contains "certwebservices", else "prod" */
function inferEnv(item) {
  const name = (pick(item, ["name", "service_name"]) ?? "").toString();
  const url = (pick(item, ["url"]) ?? "").toString();
  if (/\(UAT\)/i.test(name) || /certwebservices/i.test(url)) return "uat";
  return "prod";
}

function filterByEnv(items, env) {
  if (!env || env === "all") return items;
  return items.filter((it) => inferEnv(it) === env);
}

function getStoredFilter() {
  try {
    const v = localStorage.getItem(STORAGE_KEY_FILTER);
    if (v === "prod" || v === "uat" || v === "all") return v;
  } catch (_) {}
  return "all";
}

function setStoredFilter(env) {
  try {
    localStorage.setItem(STORAGE_KEY_FILTER, env);
  } catch (_) {}
}

function fmtMs(v){
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  return n.toFixed(2);
}

function fmtPct(v){
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  return (n * 100).toFixed(2) + "%";
}

function fmtTime(iso){
  if (!iso) return "—";
  try{
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString();
  }catch{
    return String(iso);
  }
}

function pick(obj, keys){
  for (const k of keys){
    if (obj && obj[k] !== undefined) return obj[k];
  }
  return undefined;
}

function statusBadge(isUp){
  const up = !!isUp;
  const cls = up ? "badge up" : "badge down";
  const label = up ? "UP" : "DOWN";
  return `<span class="${cls}"><span class="bDot"></span>${label}</span>`;
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/** Strip "Purolator " prefix for display on dashboard */
function displayName(name) {
  if (name == null || name === "") return "—";
  const s = String(name).trim();
  return s.replace(/^Purolator\s+/i, "").trim() || s;
}

function rowHtml(item){
  // Be defensive: your API might name things slightly differently.
  const id = pick(item, ["id", "target_id", "targetId", "service_id"]);
  const name = pick(item, ["name", "service", "service_name"]) ?? "—";
  const isUp = pick(item, ["is_up", "ok", "up", "status_up"]) ?? false;
  const lastChecked = pick(item, ["last_checked", "last_ts", "ts", "last_time"]);
  const http = pick(item, ["http_status", "status_code", "last_status"]);
  const lastMs = pick(item, ["last_ms", "duration_ms", "ms"]);
  const avgDay = pick(item, ["avg_today_ms", "avg_1d_ms", "avg_day_ms", "avg_ms_today", "daily_avg_ms", "avg_ms"]);
  const avg7d = pick(item, ["avg_7d_ms", "avg_week_ms", "avg_7_days_ms"]);
  const upDay = pick(item, ["uptime_today", "uptime_1d", "uptime_1d_pct"]);
  const up7d = pick(item, ["uptime_7d", "uptime_week", "uptime_7d_pct"]);

  const slowClass = (Number(lastMs) >= DEGRADED_MS) ? "slow" : "";
  const canView = id !== undefined && id !== null && String(id).length > 0;
  const display = displayName(name);

  return `
    <tr>
      <td class="service-name">
        ${canView
          ? `<button type="button" class="link-like js-open-chart" data-target-id="${escapeHtml(String(id))}" data-target-name="${escapeHtml(String(name))}">${escapeHtml(display)}</button>`
          : escapeHtml(display)
        }
      </td>
      <td>${statusBadge(isUp)}</td>
      <td class="muted">${escapeHtml(fmtTime(lastChecked))}</td>
      <td class="num ${slowClass}">${escapeHtml(fmtMs(lastMs))}</td>
      <td class="num">${escapeHtml(http ?? "—")}</td>
      <td class="num">${escapeHtml(fmtMs(avgDay))}</td>
      <td class="num">${escapeHtml(fmtMs(avg7d))}</td>
      <td class="num">${escapeHtml(fmtPct(upDay))}</td>
      <td class="num">${escapeHtml(fmtPct(up7d))}</td>

      <!-- ✅ Notes column -->
      <td>
        ${
          canView
            ? `<button
                 class="btn btn-secondary btn-sm js-view-notes"
                 data-target-id="${escapeHtml(String(id))}"
                 data-target-name="${escapeHtml(String(name))}"
                 type="button"
               >View</button>`
            : `<span class="muted">—</span>`
        }
      </td>
    </tr>
  `;
}

const DEGRADED_MS = 1500; // same as backend: response >= this (ms) = degraded when up

function computeTopStats(items){
  const svcCount = items.length;
  const upCount = items.filter(x => !!pick(x, ["is_up","ok","up"])).length;
  const downCount = svcCount - upCount;
  const degradedCount = items.filter(it => {
    const up = !!pick(it, ["is_up","ok","up"]);
    const ms = Number(pick(it, ["last_ms","duration_ms","ms"]));
    return up && !Number.isNaN(ms) && ms >= DEGRADED_MS;
  }).length;

  return { svcCount, upCount, downCount, degradedCount };
}

async function fetchJson(url){
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return await r.json();
}

let lastFetchedItems = [];
let sortColumn = "status";
let sortDir = "asc"; // for status: asc = DOWN first, then Degraded, then UP

/** Status rank for sorting: DOWN=0, Degraded=1, UP=2 */
function getStatusRank(item) {
  const isUp = !!pick(item, ["is_up", "ok", "up", "status_up"]);
  const lastMs = Number(pick(item, ["last_ms", "duration_ms", "ms"]));
  const degraded = isUp && !Number.isNaN(lastMs) && lastMs >= DEGRADED_MS;
  if (!isUp) return 0;
  return degraded ? 1 : 2;
}

function sortItems(items, column, dir) {
  const mult = dir === "asc" ? 1 : -1;
  return [...items].sort((a, b) => {
    let cmp = 0;
    switch (column) {
      case "service": {
        const na = (pick(a, ["name", "service_name"]) ?? "").toString();
        const nb = (pick(b, ["name", "service_name"]) ?? "").toString();
        cmp = na.localeCompare(nb, undefined, { sensitivity: "base" });
        break;
      }
      case "status":
        cmp = getStatusRank(a) - getStatusRank(b);
        break;
      case "lastChecked": {
        const ta = new Date(pick(a, ["last_checked", "last_ts", "ts"]) || 0).getTime();
        const tb = new Date(pick(b, ["last_checked", "last_ts", "ts"]) || 0).getTime();
        cmp = ta - tb;
        break;
      }
      case "lastMs": {
        const va = Number(pick(a, ["last_ms", "duration_ms", "ms"])) || 0;
        const vb = Number(pick(b, ["last_ms", "duration_ms", "ms"])) || 0;
        cmp = va - vb;
        break;
      }
      case "http": {
        const va = Number(pick(a, ["http_status", "status_code", "last_status"])) || 0;
        const vb = Number(pick(b, ["http_status", "status_code", "last_status"])) || 0;
        cmp = va - vb;
        break;
      }
      case "avgToday": {
        const va = Number(pick(a, ["avg_today_ms", "avg_1d_ms", "avg_day_ms", "daily_avg_ms", "avg_ms"])) || 0;
        const vb = Number(pick(b, ["avg_today_ms", "avg_1d_ms", "avg_day_ms", "daily_avg_ms", "avg_ms"])) || 0;
        cmp = va - vb;
        break;
      }
      case "avg7d": {
        const va = Number(pick(a, ["avg_7d_ms", "avg_week_ms", "avg_7_days_ms"])) || 0;
        const vb = Number(pick(b, ["avg_7d_ms", "avg_week_ms", "avg_7_days_ms"])) || 0;
        cmp = va - vb;
        break;
      }
      case "uptimeToday":
      case "uptime7d": {
        const key = column === "uptimeToday" ? "uptime_today" : "uptime_7d";
        const va = Number(pick(a, [key, "uptime_1d", "uptime_1d_pct", "uptime_week", "uptime_7d_pct"])) || 0;
        const vb = Number(pick(b, [key, "uptime_1d", "uptime_1d_pct", "uptime_week", "uptime_7d_pct"])) || 0;
        cmp = va - vb;
        break;
      }
      default:
        cmp = 0;
    }
    return mult * (cmp || 0);
  });
}

function updateSortHeaders() {
  document.querySelectorAll(".table thead th.sortable").forEach((th) => {
    const col = th.getAttribute("data-sort");
    const arrow = th.querySelector(".sort-arrow");
    const isActive = col === sortColumn;
    th.classList.toggle("sort-active", isActive);
    th.setAttribute("aria-sort", isActive ? (sortDir === "asc" ? "ascending" : "descending") : "none");
    if (arrow) arrow.textContent = isActive ? (sortDir === "asc" ? "↑" : "↓") : "";
  });
}

function applyFilter() {
  const rowsEl = document.getElementById("rows");
  const filter = getStoredFilter();
  const filtered = filterByEnv(lastFetchedItems, filter);
  const sorted = sortItems(filtered, sortColumn, sortDir);

  rowsEl.style.opacity = "0.6";

  function commit() {
    if (!sorted.length) {
      rowsEl.innerHTML = `<tr><td colspan="10" class="muted">No ${filter === "all" ? "data" : filter.toUpperCase() + " endpoints"} to show.</td></tr>`;
    } else {
      rowsEl.innerHTML = sorted.map(rowHtml).join("");
    }
    rowsEl.style.opacity = "1";
  }

  const t = parseFloat(getComputedStyle(rowsEl).transitionDuration) * 1000 || 200;
  setTimeout(commit, Math.min(t, 120));

  updateSortHeaders();

  const { svcCount, upCount, downCount, degradedCount } = computeTopStats(filtered);
  document.getElementById("svcCount").textContent = String(svcCount);
  document.getElementById("upCount").textContent = String(upCount);
  document.getElementById("downCount").textContent = String(downCount);
  document.getElementById("degradedCount").textContent = String(degradedCount);
  document.getElementById("degradedCount").className = "cardValue degraded";

  document.querySelectorAll(".segmented .segment").forEach((btn) => {
    const isActive = btn.getAttribute("data-filter") === filter;
    btn.classList.toggle("segment--active", isActive);
    btn.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

async function load(){
  const rowsEl = document.getElementById("rows");
  const lastUpdatedEl = document.getElementById("lastUpdated");
  const bannerEl = document.getElementById("banner");

  try{
    const [data, notices] = await Promise.all([
      fetchJson("/api/summary"),
      fetchJson("/api/notices").catch(() => null)
    ]);

    if (bannerEl){
      const b = notices?.banner;
      if (b && b.enabled){
        bannerEl.style.display = "block";
        bannerEl.className = `banner ${b.type || "info"}`;
        bannerEl.textContent = b.message || "";
      } else {
        bannerEl.style.display = "none";
        bannerEl.textContent = "";
        bannerEl.className = "banner";
      }
    }

    lastFetchedItems = Array.isArray(data) ? data : (data.items ?? []);
    applyFilter();
    lastUpdatedEl.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;

    await loadIncidentActive();
    await loadIncidentHistory();
  } catch (e){
    rowsEl.innerHTML = `<tr><td colspan="10" class="muted">Error loading data: ${escapeHtml(String(e.message || e))}</td></tr>`;
    lastUpdatedEl.textContent = `Last updated: (error)`;
  }
}

initThemeToggle();
document.getElementById("refreshBtn").addEventListener("click", load);

// Segmented filter: persist selection and re-apply
document.querySelectorAll(".segmented .segment").forEach((btn) => {
  btn.addEventListener("click", () => {
    const filter = btn.getAttribute("data-filter");
    if (!filter) return;
    setStoredFilter(filter);
    applyFilter();
  });
});

// Restore segment active state from localStorage on first paint
(function setInitialSegment() {
  const filter = getStoredFilter();
  document.querySelectorAll(".segmented .segment").forEach((btn) => {
    const isActive = btn.getAttribute("data-filter") === filter;
    btn.classList.toggle("segment--active", isActive);
    btn.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
})();

// Table column sort: click header to toggle asc/desc
document.querySelectorAll(".table thead th.sortable").forEach((th) => {
  th.addEventListener("click", () => {
    const col = th.getAttribute("data-sort");
    if (!col) return;
    if (sortColumn === col) {
      sortDir = sortDir === "asc" ? "desc" : "asc";
    } else {
      sortColumn = col;
      sortDir = "asc";
    }
    applyFilter();
  });
});

// -------------------- Incident Updates --------------------
function getIncidentTimelineOpen(id) {
  try {
    const key = STORAGE_KEY_INCIDENT_TIMELINE_OPEN + "_" + id;
    return localStorage.getItem(key) === "true";
  } catch (_) {}
  return false;
}
function setIncidentTimelineOpen(id, open) {
  try {
    const key = STORAGE_KEY_INCIDENT_TIMELINE_OPEN + "_" + id;
    localStorage.setItem(key, open ? "true" : "false");
  } catch (_) {}
}
function getIncidentHistoryOpen() {
  try {
    return localStorage.getItem(STORAGE_KEY_INCIDENT_HISTORY_OPEN) === "true";
  } catch (_) {}
  return false;
}
function setIncidentHistoryOpen(open) {
  try {
    localStorage.setItem(STORAGE_KEY_INCIDENT_HISTORY_OPEN, open ? "true" : "false");
  } catch (_) {}
}

function renderIncidentTimelineItems(timeline) {
  if (!timeline || timeline.length === 0) return "<li class=\"muted\">No updates yet.</li>";
  return timeline.map((it) => {
    const ts = escapeHtml(fmtTime(it.created_at));
    const status = (it.status || "").toLowerCase();
    const msg = (it.message || "").trim();
    const truncated = msg.length > INCIDENT_MSG_TRUNCATE;
    const displayMsg = truncated ? msg.slice(0, INCIDENT_MSG_TRUNCATE) + "…" : msg;
    const msgClass = truncated ? "incident-msg truncated" : "incident-msg";
    const fullHtml = escapeHtml(msg).replace(/\n/g, "<br>");
    const dataFull = fullHtml.replace(/"/g, "&quot;");
    return `<li><span class="incident-ts">${ts}</span><span class="incident-pill ${escapeHtml(status)}">${escapeHtml(status)}</span><div class="${msgClass}" data-full="${dataFull}" title="${truncated ? "Click to expand" : ""}">${escapeHtml(displayMsg)}</div></li>`;
  }).join("");
}

function bindTruncatedMessages(container) {
  if (!container) return;
  container.querySelectorAll(".incident-msg.truncated").forEach((el) => {
    el.addEventListener("click", () => {
      const full = el.getAttribute("data-full");
      if (full) { el.innerHTML = full; el.classList.remove("truncated"); el.removeAttribute("data-full"); }
    });
  });
}

async function loadIncidentTimelineForId(incidentId, timelineEl) {
  if (!timelineEl) return;
  try {
    const data = await fetchJson("/api/incidents/" + encodeURIComponent(incidentId));
    const timeline = data.timeline || [];
    timelineEl.innerHTML = renderIncidentTimelineItems(timeline);
    bindTruncatedMessages(timelineEl);
  } catch (_) {
    timelineEl.innerHTML = "<li class=\"muted\">Could not load updates.</li>";
  }
}

async function loadIncidentActive() {
  const section = document.getElementById("incidentSection");
  const listEl = document.getElementById("incidentActiveList");
  if (!section || !listEl) return;
  try {
    const data = await fetchJson("/api/incidents/active");
    const items = data.items || [];
    if (items.length === 0) {
      section.style.display = "none";
      return;
    }
    section.style.display = "block";
    listEl.innerHTML = items.map((inc) => {
      const id = inc.id;
      const status = (inc.status || "investigating").toLowerCase();
      const isOpen = getIncidentTimelineOpen(id);
      const cardId = "incident-card-" + id;
      const timelineId = "incident-timeline-" + id;
      const toggleId = "incident-toggle-" + id;
      return `
        <div class="incident-card" id="${cardId}" data-incident-id="${escapeHtml(String(id))}">
          <div class="incident-banner card ${escapeHtml(status)}">
            <div class="incident-banner-inner">
              <div class="incident-status-label">${escapeHtml((inc.status || "").replace(/_/g, " "))}</div>
              <div class="incident-title">${escapeHtml(inc.title || "Incident")}</div>
              <div class="incident-message">${escapeHtml(inc.message || "")}</div>
              <div class="incident-updated muted">Last updated: ${escapeHtml(fmtTime(inc.updated_at || inc.created_at))}</div>
            </div>
          </div>
          <div class="incident-timeline-wrap">
            <button type="button" class="incident-toggle btn btn-secondary" id="${toggleId}" data-incident-id="${escapeHtml(String(id))}" aria-expanded="${isOpen ? "true" : "false"}">${isOpen ? "Hide updates" : "View updates"}</button>
            <div id="${timelineId}" class="incident-timeline ${isOpen ? "" : "hidden"}"></div>
          </div>
        </div>
      `;
    }).join("");

    items.forEach((inc) => {
      const id = inc.id;
      const toggle = document.getElementById("incident-toggle-" + id);
      const timelineEl = document.getElementById("incident-timeline-" + id);
      const isOpen = getIncidentTimelineOpen(id);
      if (toggle && timelineEl) {
        if (isOpen) loadIncidentTimelineForId(id, timelineEl);
        toggle.addEventListener("click", () => {
          const open = timelineEl.classList.toggle("hidden") === false;
          setIncidentTimelineOpen(id, open);
          toggle.textContent = open ? "Hide updates" : "View updates";
          toggle.setAttribute("aria-expanded", open ? "true" : "false");
          if (open) loadIncidentTimelineForId(id, timelineEl);
        });
      }
    });
  } catch (_) {
    section.style.display = "none";
  }
}

async function loadIncidentHistory() {
  const content = document.getElementById("incidentHistoryContent");
  const listEl = document.getElementById("incidentHistoryList");
  const toggleBtn = document.getElementById("incidentHistoryToggle");
  if (!content || !listEl || !toggleBtn) return;
  const isOpen = getIncidentHistoryOpen();
  content.classList.toggle("hidden", !isOpen);
  toggleBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
  toggleBtn.textContent = isOpen ? "Hide Incident History" : "Incident History";

  try {
    const data = await fetchJson("/api/incidents/history?limit=50");
    const items = data.items || [];
    if (items.length === 0) {
      listEl.innerHTML = "<p class=\"muted\">No resolved incidents.</p>";
      return;
    }
    function formatDuration(sec) {
      if (sec == null || sec < 0) return "—";
      if (sec < 60) return sec + "s";
      if (sec < 3600) return Math.floor(sec / 60) + "m";
      const h = Math.floor(sec / 3600);
      const m = Math.floor((sec % 3600) / 60);
      return m ? h + "h " + m + "m" : h + "h";
    }
    listEl.innerHTML = items.map((it) => {
      const id = it.id;
      const durationStr = formatDuration(it.duration_seconds);
      const expandedId = "incident-history-expanded-" + id;
      return `
        <div class="incident-history-item" data-incident-id="${escapeHtml(String(id))}">
          <div class="incident-history-row">
            <span class="incident-history-title">${escapeHtml(it.title || "Incident")}</span>
            <span class="incident-history-meta">${escapeHtml(it.affected_service || "—")} • ${escapeHtml(fmtTime(it.created_at))} • ${escapeHtml(durationStr)}</span>
            <button type="button" class="btn btn-secondary btn-sm js-view-incident-history" data-incident-id="${escapeHtml(String(id))}">View</button>
          </div>
          <div id="${expandedId}" class="incident-history-timeline hidden"></div>
        </div>
      `;
    }).join("");

    listEl.querySelectorAll(".js-view-incident-history").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-incident-id");
        const expandedEl = document.getElementById("incident-history-expanded-" + id);
        if (!expandedEl) return;
        const isExpanded = expandedEl.classList.toggle("hidden") === false;
        btn.textContent = isExpanded ? "Hide" : "View";
        if (isExpanded && expandedEl.children.length === 0) {
          expandedEl.innerHTML = "<ul class=\"incident-timeline\">Loading…</ul>";
          fetchJson("/api/incidents/" + encodeURIComponent(id)).then((data) => {
            const timeline = data.timeline || [];
            const ul = expandedEl.querySelector("ul");
            if (ul) {
              ul.innerHTML = renderIncidentTimelineItems(timeline);
              bindTruncatedMessages(ul);
            }
          }).catch(() => {
            const ul = expandedEl.querySelector("ul");
            if (ul) ul.innerHTML = "<li class=\"muted\">Could not load timeline.</li>";
          });
        }
      });
    });
  } catch (_) {
    listEl.innerHTML = "<p class=\"muted\">Could not load incident history.</p>";
  }
}

document.getElementById("incidentHistoryToggle")?.addEventListener("click", () => {
  const content = document.getElementById("incidentHistoryContent");
  const toggleBtn = document.getElementById("incidentHistoryToggle");
  if (!content || !toggleBtn) return;
  const isOpen = content.classList.toggle("hidden") === false;
  setIncidentHistoryOpen(isOpen);
  toggleBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
  toggleBtn.textContent = isOpen ? "Hide Incident History" : "Incident History";
  if (isOpen) loadIncidentHistory();
});

load();
setInterval(load, REFRESH_MS);

// -------------------- Notes Modal --------------------
(function () {
  const modal = document.getElementById("notesModal");
  if (!modal) return; // ✅ guard in case JS loads on a page without the modal

  const backdrop = document.getElementById("notesModalBackdrop");
  const closeBtn = document.getElementById("notesModalClose");
  const closeBtn2 = document.getElementById("notesModalClose2");
  const title = document.getElementById("notesModalTitle");
  const subtitle = document.getElementById("notesModalSubtitle");
  const state = document.getElementById("notesModalState");
  const list = document.getElementById("notesModalList");

  function openModal() {
    modal.classList.remove("hidden");
    backdrop.classList.remove("hidden");
    document.addEventListener("keydown", onEsc);
  }

  function closeModal() {
    modal.classList.add("hidden");
    backdrop.classList.add("hidden");
    document.removeEventListener("keydown", onEsc);
  }

  function onEsc(e) {
    if (e.key === "Escape") closeModal();
  }

  function setState(msg) {
    state.textContent = msg || "";
  }

  function clearList() {
    list.innerHTML = "";
  }

  function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  }

  function renderNotes(notes) {
    clearList();

    if (!notes || notes.length === 0) {
      setState("No notes yet for this API.");
      return;
    }

    setState("");

    // newest first (if backend already does it, this is harmless)
    const sorted = [...notes].sort((a, b) => {
      const da = new Date(a.created_at || a.createdAt || 0).getTime();
      const db = new Date(b.created_at || b.createdAt || 0).getTime();
      return db - da;
    });

    const html = sorted.map(n => {
      const created = n.created_at || n.createdAt;
      const author = n.created_by || n.createdBy || n.author || "";
      const body = n.note || n.body || n.text || "";

      return `
        <div class="note">
          <div class="note-meta">
            <span>${escapeHtml(formatDate(created))}</span>
            ${author ? `<span>•</span><span>${escapeHtml(author)}</span>` : ""}
          </div>
          <div class="note-body">${escapeHtml(body)}</div>
        </div>
      `;
    }).join("");

    list.innerHTML = html;
  }

  async function fetchNotes(targetId) {
    const res = await fetch(`/api/targets/${encodeURIComponent(targetId)}/notes`, {
      headers: { "Accept": "application/json" }
    });

    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`Failed to load notes (${res.status}). ${txt}`);
    }

    return await res.json();
  }

  async function showNotesForTarget(targetId, targetName) {
    title.textContent = "API Notes";
    subtitle.textContent = targetName ? `${targetName} (id: ${targetId})` : `Target id: ${targetId}`;
    setState("Loading notes…");
    clearList();
    openModal();

    try {
      const data = await fetchNotes(targetId);

      // supports either { notes: [...] } or just [...]
      const notes = Array.isArray(data) ? data : (data.notes || data.items || []);
      renderNotes(notes);
    } catch (err) {
      console.error(err);
      setState("Could not load notes. Check console / network tab.");
    }
  }

  // Close handlers
  backdrop.addEventListener("click", closeModal);
  closeBtn.addEventListener("click", closeModal);
  closeBtn2.addEventListener("click", closeModal);

  // View button handler (event delegation)
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".js-view-notes");
    if (!btn) return;

    const targetId = btn.getAttribute("data-target-id");
    const targetName = btn.getAttribute("data-target-name") || "";

    if (!targetId) return;
    showNotesForTarget(targetId, targetName);
  });
})();

// -------------------- Chart Modal (probe history) --------------------
(function () {
  const DEFAULT_RANGE = "1h";

  const modal = document.getElementById("chartModal");
  const backdrop = document.getElementById("chartModalBackdrop");
  const titleEl = document.getElementById("chartModalTitle");
  const subtitleEl = document.getElementById("chartModalSubtitle");
  const stateEl = document.getElementById("chartModalState");
  const summaryEl = document.getElementById("chartSummary");
  const canvas = document.getElementById("chartCanvas");
  const closeBtn = document.getElementById("chartModalClose");
  const closeBtn2 = document.getElementById("chartModalClose2");
  const rangeSegmented = document.querySelector(".chart-range-segmented");

  if (!modal || !canvas) return;

  let chartInstance = null;
  let currentTargetId = null;
  let currentTargetName = null;
  let currentRange = DEFAULT_RANGE;

  function openChartModal() {
    modal.classList.remove("hidden");
    backdrop.classList.remove("hidden");
    document.addEventListener("keydown", onEsc);
  }

  function closeChartModal() {
    modal.classList.add("hidden");
    backdrop.classList.add("hidden");
    document.removeEventListener("keydown", onEsc);
    if (chartInstance) {
      chartInstance.destroy();
      chartInstance = null;
    }
  }

  function onEsc(e) {
    if (e.key === "Escape") closeChartModal();
  }

  function getBucketLabel(bucketTimestamp) {
    if (!bucketTimestamp) return "";
    const d = new Date(bucketTimestamp);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function renderChart(buckets) {
    if (chartInstance) chartInstance.destroy();

    const labels = buckets.map((b) => getBucketLabel(b.timestamp));
    const avgMs = buckets.map((b) => (b.avg_duration_ms != null ? b.avg_duration_ms : null));

    const bucketLabel = currentRange === "1h" ? "5 min" : currentRange === "6h" ? "30 min" : currentRange === "24h" ? "1h" : "6h";
    const ctx = canvas.getContext("2d");
    chartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: `Avg response time (${bucketLabel} buckets)`,
          data: avgMs,
          borderColor: "rgb(124, 156, 255)",
          backgroundColor: "rgba(124, 156, 255, 0.1)",
          fill: true,
          tension: 0.2,
          spanGaps: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        aspectRatio: 2.2,
        plugins: {
          legend: { display: true },
        },
        scales: {
          x: {
            grid: { color: "rgba(255,255,255,0.06)" },
            ticks: { color: "#a9b2d6", maxTicksLimit: 12 },
          },
          y: {
            title: { display: true, text: "ms", color: "#a9b2d6" },
            grid: { color: "rgba(255,255,255,0.06)" },
            ticks: { color: "#a9b2d6" },
            beginAtZero: true,
          },
        },
      },
    });
  }

  function setSummaryFromApi(summary) {
    if (!summary || summary.total_probes === 0) {
      summaryEl.textContent = "No probe data in this range.";
      return;
    }
    const s = summary;
    const pct = s.total_probes ? ((s.success_count / s.total_probes) * 100).toFixed(1) : "0";
    const avgStr = s.avg_ms != null ? s.avg_ms.toFixed(0) : "—";
    const p95Str = s.p95_ms != null ? s.p95_ms.toFixed(0) : "";
    summaryEl.textContent = `Probes: ${s.total_probes} • Success: ${s.success_count}/${s.total_probes} (${pct}%) • Avg: ${avgStr} ms${p95Str ? " • P95: " + p95Str + " ms" : ""}`;
  }

  function updateRangeSegmentedUI(selectedRange) {
    if (!rangeSegmented) return;
    rangeSegmented.querySelectorAll(".segment").forEach((btn) => {
      const isActive = btn.getAttribute("data-range") === selectedRange;
      btn.classList.toggle("segment--active", isActive);
      btn.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  async function fetchAndRenderHistory(targetId, range) {
    if (!targetId) return;
    stateEl.textContent = "Loading…";
    try {
      const res = await fetch(`/api/targets/${encodeURIComponent(targetId)}/history?range=${encodeURIComponent(range)}`);
      if (!res.ok) throw new Error(`History ${res.status}`);
      const data = await res.json();
      const buckets = data.buckets || [];
      const summary = data.summary || {};
      stateEl.textContent = "";

      if (buckets.length) {
        renderChart(buckets);
      } else {
        stateEl.textContent = "No probe data yet for this endpoint.";
        if (chartInstance) {
          chartInstance.destroy();
          chartInstance = null;
        }
      }
      setSummaryFromApi(summary);
    } catch (err) {
      console.error(err);
      stateEl.textContent = "Could not load history. Check console.";
    }
  }

  async function showChartForTarget(targetId, targetName) {
    const display = displayName(targetName || "");
    titleEl.textContent = "Probe history";
    subtitleEl.textContent = display ? `${display} (id: ${targetId})` : `Target id: ${targetId}`;
    currentTargetId = targetId;
    currentTargetName = targetName;
    currentRange = DEFAULT_RANGE;
    updateRangeSegmentedUI(currentRange);
    summaryEl.textContent = "";
    if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
    openChartModal();

    await fetchAndRenderHistory(targetId, currentRange);
  }

  if (rangeSegmented) {
    rangeSegmented.addEventListener("click", (e) => {
      const btn = e.target.closest(".segment[data-range]");
      if (!btn || !currentTargetId) return;
      const range = btn.getAttribute("data-range");
      if (!range) return;
      currentRange = range;
      updateRangeSegmentedUI(currentRange);
      fetchAndRenderHistory(currentTargetId, currentRange);
    });
  }

  backdrop.addEventListener("click", closeChartModal);
  closeBtn.addEventListener("click", closeChartModal);
  closeBtn2.addEventListener("click", closeChartModal);

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".js-open-chart");
    if (!btn) return;
    e.preventDefault();
    const targetId = btn.getAttribute("data-target-id");
    const targetName = btn.getAttribute("data-target-name") || "";
    if (!targetId) return;
    showChartForTarget(targetId, targetName);
  });
})();