// Small vanilla-JS front end for the report agent. All data comes from /api.

const $ = (id) => document.getElementById(id);
const state = { clients: [], clientId: null, report: null };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));
const fmt = (n) => Number(n).toLocaleString("en-US");
const pretty = (s) => ({ tiktok: "TikTok", instagram: "Instagram", facebook: "Facebook" }[s]
  || String(s).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()));

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body ? { "Content-Type": "application/json" } : {},
    ...opts,
  });
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = data?.detail;
    const msg = typeof detail === "string" ? detail
      : detail?.errors ? `${detail.message}:\n${detail.errors.join("\n")}`
      : Array.isArray(detail) ? detail.map((d) => d.msg).join(", ")
      : `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 4000);
}

// ---- clients / overview ---------------------------------------------------

async function loadClients() {
  state.clients = await api("/api/clients");
  $("client-tabs").innerHTML = state.clients.map((c) => `
    <button class="tab" data-id="${esc(c.id)}">
      ${esc(c.name)}<small>${esc(c.city)} · ${c.post_count} posts</small>
    </button>`).join("");
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => selectClient(b.dataset.id)));
}

async function selectClient(id) {
  state.clientId = id;
  state.report = null;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
  try { localStorage.setItem("client", id); } catch (_) { /* storage unavailable */ }
  showReport(null);
  await Promise.all([loadOverview(), loadHistory()]);
}

const KPI_LABELS = [
  ["reach", "Reach"], ["impressions", "Impressions"], ["engagements", "Engagements"],
  ["engagement_rate", "Engagement rate"], ["link_clicks", "Link clicks"], ["posts", "Posts"],
];

async function loadOverview() {
  const { client, post_count, metrics } = await api(`/api/clients/${state.clientId}/overview`);
  const c = state.clients.find((x) => x.id === client.id);
  $("data-info").textContent = post_count
    ? `${post_count} posts imported (${c.first_date} → ${c.last_date}).`
    : "No data yet - import a CSV.";

  if (!metrics) {
    $("kpis").innerHTML = "";
    $("chart-platform").innerHTML = $("chart-format").innerHTML = "";
    return;
  }
  const label = new Date(metrics.period + "-15").toLocaleString("en-US", { month: "long", year: "numeric" });
  $("period-title").textContent = `${client.name} - ${label}`;
  $("period-sub").textContent = metrics.previous_period ? `compared with ${metrics.previous_period}` : "";

  $("kpis").innerHTML = KPI_LABELS.map(([key, name]) => {
    const v = metrics.totals[key];
    const d = metrics.change_pct?.[key];
    const delta = d == null ? "" : d === 0 ? "no change"
      : `<span class="${d > 0 ? "up" : "down"}">${d > 0 ? "▲" : "▼"} ${Math.abs(d)}%</span> vs last month`;
    return `<div class="kpi"><div class="k-label">${name}</div>
      <div class="k-value">${key === "engagement_rate" ? v + "%" : fmt(v)}</div>
      <div class="k-delta muted">${delta}</div></div>`;
  }).join("");

  drawBars($("chart-platform"), metrics.by_platform, "platform");
  drawBars($("chart-format"), metrics.by_format, "format");
}

function drawBars(el, rows, key) {
  const max = Math.max(...rows.map((r) => r.engagement_rate), 1);
  el.innerHTML = rows.map((r) => `
    <div class="bar-row" data-tip="${esc(pretty(r[key]))}: ${r.engagement_rate}% engagement · ${r.posts} posts · ${fmt(r.reach)} reach">
      <span class="bar-label">${esc(pretty(r[key]))}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${(r.engagement_rate / max) * 100}%; display:block"></span></span>
      <span class="bar-value">${r.engagement_rate}%</span>
    </div>`).join("");
}

// hover tooltip for chart rows
document.addEventListener("mousemove", (e) => {
  const row = e.target.closest?.("[data-tip]");
  const tip = $("tooltip");
  if (!row) { tip.hidden = true; return; }
  tip.textContent = row.dataset.tip;
  tip.hidden = false;
  tip.style.left = Math.min(e.clientX + 12, window.innerWidth - 230) + "px";
  tip.style.top = e.clientY + 14 + "px";
});

// ---- history & audit -------------------------------------------------------

async function loadHistory() {
  const reports = await api(`/api/clients/${state.clientId}/reports`);
  $("history").innerHTML = reports.length ? reports.map((r) => `
    <li data-id="${r.id}" class="${state.report?.id === r.id ? "active" : ""}">
      <span>#${r.id} · ${esc(r.period)}<br><span class="muted">${esc(r.created_at.replace("T", " ").slice(0, 16))}</span></span>
      <span class="badge ${r.status}">${r.status}</span>
    </li>`).join("") : `<li class="muted">No reports yet.</li>`;
  document.querySelectorAll("#history li[data-id]").forEach((li) =>
    li.addEventListener("click", () => openReport(Number(li.dataset.id))));
}

async function openReport(id) {
  const r = await api(`/api/clients/${state.clientId}/reports/${id}`);
  showReport(r);
  loadHistory();
}

function renderAudit(audit) {
  $("audit").innerHTML = audit?.length ? audit.map((a) => `
    <li><b>${esc(a.action.replace(/_/g, " "))}</b> by ${esc(a.actor)}
      <div class="muted">${esc(a.at.replace("T", " ").slice(0, 19))}${a.note ? " - " + esc(a.note) : ""}</div></li>`).join("")
    : `<li class="muted">Open a report to see its history.</li>`;
}

// ---- report view -------------------------------------------------------------

function evidenceTable(ev) {
  const values = Object.entries(ev.values).map(([k, v]) => `${esc(k)}: <b>${esc(v)}</b>`).join("<br>");
  const sample = Object.entries(ev.sample).map(([k, v]) => `${esc(k)}: ${v} posts`).join("<br>");
  return `<table class="evidence">
    <tr><td>Metric</td><td>${esc(ev.metric)}</td></tr>
    <tr><td>Values</td><td>${values}</td></tr>
    ${sample ? `<tr><td>Sample size</td><td>${sample}</td></tr>` : ""}
    ${ev.post_ids.length ? `<tr><td>Posts (${ev.post_ids.length})</td><td class="mono">${ev.post_ids.map(esc).join(", ")}</td></tr>` : ""}
  </table>`;
}

function showReport(r) {
  state.report = r;
  $("report").hidden = !r;
  $("report-empty").hidden = !!r;
  renderAudit(r?.audit);
  if (!r) return;

  const p = r.payload;
  const isDraft = r.status === "draft";
  const gen = p.generation || {};

  $("r-status").className = `badge ${r.status}`;
  $("r-status").textContent = r.status;
  $("r-meta").textContent = `Report #${r.id} · ${p.period_label} · ` + (gen.used
    ? `wording by ${gen.model}, every number checked against the evidence`
    : "template wording (no LLM)")
    + (r.reviewer ? ` · ${r.status} by ${r.reviewer}` : "");

  $("r-summary").value = p.summary;
  $("r-summary").readOnly = !isDraft;

  const rejected = (gen.rejected || []).length;
  $("r-insight-note").textContent = `(${p.insights.length})` +
    (rejected ? ` · ${rejected} LLM sentence(s) failed the number check and fell back to template text` : "");

  $("r-insights").innerHTML = p.insights.map((i) => `
    <div class="insight" data-id="${esc(i.id)}">
      <div class="insight-head">
        <span class="insight-title">${esc(i.title)}</span>
        ${isDraft ? `<label class="include"><input type="checkbox" checked> include</label>`
                  : `<span class="src">${i.source === "llm" ? "LLM-phrased" : "template"}</span>`}
      </div>
      <p>${esc(i.text)}</p>
      <p class="rec"><b>Recommendation:</b> ${esc(i.recommendation)}</p>
      <details><summary>Show evidence</summary>${evidenceTable(i.evidence)}</details>
    </div>`).join("");

  document.querySelectorAll(".insight .include input").forEach((cb) =>
    cb.addEventListener("change", () => cb.closest(".insight").classList.toggle("excluded", !cb.checked)));

  $("review-box").hidden = !isDraft;
  document.querySelectorAll(".export [data-fmt]").forEach((a) => {
    const ok = r.status === "approved";
    a.classList.toggle("disabled", !ok);
    a.href = ok ? `/api/clients/${state.clientId}/reports/${r.id}/export?fmt=${a.dataset.fmt}` : "#";
  });
  $("export-hint").textContent = r.status === "approved" ? "Approved - ready to send to the client."
    : r.status === "rejected" ? "Rejected reports can't be exported. Generate a new draft." : "Available after approval.";
}

// ---- actions --------------------------------------------------------------

$("btn-generate").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  btn.textContent = "Generating…";
  try {
    const r = await api(`/api/clients/${state.clientId}/reports`, { method: "POST" });
    await openReport(r.id);
    toast("Draft report created - review it below.");
  } catch (err) { toast(err.message); }
  finally { btn.disabled = false; btn.textContent = "Generate report"; }
});

function reviewer() {
  const name = $("reviewer").value.trim();
  if (name.length < 2) { $("reviewer").focus(); throw new Error("Enter your name to sign off."); }
  try { localStorage.setItem("reviewer", name); } catch (_) { /* ignore */ }
  return name;
}

$("btn-approve").addEventListener("click", async () => {
  try {
    const excluded = [...document.querySelectorAll(".insight")]
      .filter((el) => !el.querySelector(".include input")?.checked).map((el) => el.dataset.id);
    const r = await api(`/api/clients/${state.clientId}/reports/${state.report.id}/approve`, {
      method: "POST",
      body: JSON.stringify({
        reviewer: reviewer(), summary: $("r-summary").value,
        excluded_insights: excluded, note: $("review-note").value.trim() || null,
      }),
    });
    $("review-note").value = "";
    showReport(r); loadHistory();
    toast("Approved. Export is now available.");
  } catch (err) { toast(err.message); }
});

$("btn-reject").addEventListener("click", async () => {
  try {
    const note = $("review-note").value.trim();
    if (note.length < 3) { $("review-note").focus(); throw new Error("Add a note explaining the rejection."); }
    const r = await api(`/api/clients/${state.clientId}/reports/${state.report.id}/reject`, {
      method: "POST", body: JSON.stringify({ reviewer: reviewer(), note }),
    });
    $("review-note").value = "";
    showReport(r); loadHistory();
    toast("Rejected and logged.");
  } catch (err) { toast(err.message); }
});

$("file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await api(`/api/clients/${state.clientId}/import`, { method: "POST", body: form, headers: {} });
    toast(`Imported ${res.imported} posts.`);
    await loadClients();
    await selectClient(state.clientId);
  } catch (err) { toast(err.message); }
  e.target.value = "";
});

$("btn-reset").addEventListener("click", async () => {
  if (!confirm("Reset all demo data and delete generated reports?")) return;
  await api("/api/demo/reset", { method: "POST" });
  await loadClients();
  await selectClient(state.clients[0].id);
  toast("Demo data restored.");
});

// ---- start ----------------------------------------------------------------

(async function init() {
  try {
    const s = await api("/api/status");
    $("llm-status").textContent = s.llm_enabled ? `LLM: ${s.llm_model}` : "LLM off - template wording";
  } catch (_) { $("llm-status").textContent = "status unknown"; }

  try { $("reviewer").value = localStorage.getItem("reviewer") || ""; } catch (_) { /* ignore */ }
  await loadClients();
  let saved = null;
  try { saved = localStorage.getItem("client"); } catch (_) { /* ignore */ }
  const first = state.clients.find((c) => c.id === saved) || state.clients[0];
  if (first) await selectClient(first.id);
})();
