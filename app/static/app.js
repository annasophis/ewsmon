const REFRESH_MS = 10_000;

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

  const slowClass = (Number(lastMs) >= 1500) ? "slow" : "";
  const canView = id !== undefined && id !== null && String(id).length > 0;

  return `
    <tr>
      <td>${escapeHtml(name)}</td>
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

function computeTopStats(items){
  const svcCount = items.length;
  const upCount = items.filter(x => !!pick(x, ["is_up","ok","up"])).length;
  const downCount = svcCount - upCount;

  let slowest = null;
  for (const it of items){
    const ms = Number(pick(it, ["last_ms","duration_ms","ms"]));
    if (!Number.isNaN(ms)){
      if (!slowest || ms > slowest.ms){
        slowest = { name: pick(it, ["name","service","service_name"]) ?? "—", ms };
      }
    }
  }

  return { svcCount, upCount, downCount, slowest };
}

async function fetchJson(url){
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return await r.json();
}

async function load(){
  const rowsEl = document.getElementById("rows");
  const lastUpdatedEl = document.getElementById("lastUpdated");
  const bannerEl = document.getElementById("banner");

  try{
    // Fetch summary + banner at same time
    const [data, notices] = await Promise.all([
      fetchJson("/api/summary"),
      fetchJson("/api/notices").catch(() => null)
    ]);

    // ---------- BANNER ----------
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
    // ---------- END BANNER ----------

    // existing summary logic
    const items = Array.isArray(data) ? data : (data.items ?? []);

    if (!items.length){
      rowsEl.innerHTML = `<tr><td colspan="10" class="muted">No data yet… (worker just started)</td></tr>`;
    } else {
      rowsEl.innerHTML = items.map(rowHtml).join("");
    }

    const { svcCount, upCount, downCount, slowest } = computeTopStats(items);
    document.getElementById("svcCount").textContent = String(svcCount);
    document.getElementById("upCount").textContent = String(upCount);
    document.getElementById("downCount").textContent = String(downCount);
    document.getElementById("slowest").textContent =
      slowest ? `${slowest.name} • ${slowest.ms.toFixed(0)} ms` : "—";

    lastUpdatedEl.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;

  } catch (e){
    rowsEl.innerHTML = `<tr><td colspan="10" class="muted">Error loading data: ${escapeHtml(String(e.message || e))}</td></tr>`;
    lastUpdatedEl.textContent = `Last updated: (error)`;
  }
}

document.getElementById("refreshBtn").addEventListener("click", load);
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