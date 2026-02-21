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

function rowHtml(item){
  // Be defensive: your API might name things slightly differently.
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

  return `
    <tr>
      <td>${name}</td>
      <td>${statusBadge(isUp)}</td>
      <td class="muted">${fmtTime(lastChecked)}</td>
      <td class="num ${slowClass}">${fmtMs(lastMs)}</td>
      <td class="num">${http ?? "—"}</td>
      <td class="num">${fmtMs(avgDay)}</td>
      <td class="num">${fmtMs(avg7d)}</td>
      <td class="num">${fmtPct(upDay)}</td>
      <td class="num">${fmtPct(up7d)}</td>
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

  try{
    // Prefer summary (it has all metrics). If you only have /api/status, swap to that.
    let data = await fetchJson("/api/summary");

    // If your /api/summary returns {items:[...]} instead of [...]
    const items = Array.isArray(data) ? data : (data.items ?? []);

    if (!items.length){
      rowsEl.innerHTML = `<tr><td colspan="9" class="muted">No data yet… (worker just started)</td></tr>`;
    } else {
      rowsEl.innerHTML = items.map(rowHtml).join("");
    }

    const { svcCount, upCount, downCount, slowest } = computeTopStats(items);
    document.getElementById("svcCount").textContent = String(svcCount);
    document.getElementById("upCount").textContent = String(upCount);
    document.getElementById("downCount").textContent = String(downCount);
    document.getElementById("slowest").textContent = slowest ? `${slowest.name} • ${slowest.ms.toFixed(0)} ms` : "—";

    lastUpdatedEl.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
  } catch (e){
    rowsEl.innerHTML = `<tr><td colspan="9" class="muted">Error loading data: ${String(e.message || e)}</td></tr>`;
    lastUpdatedEl.textContent = `Last updated: (error)`;
  }
}

document.getElementById("refreshBtn").addEventListener("click", load);
load();
setInterval(load, REFRESH_MS);