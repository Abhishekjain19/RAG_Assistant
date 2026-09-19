import { getResults, cleanup, exportData } from "./api.js";

const STEPS = [
  ["downloading", "Downloading"],
  ["extracting", "Extracting audio"],
  ["transcribing", "Transcribing"],
  ["translating", "Translating"],
  ["generating_title", "Generating title"],
  ["summarising", "Summarising"],
  ["indexing", "Indexing"],
];

let _state = null;

export function renderSteps(events) {
  const byName = Object.fromEntries((events || []).map((e) => [e.step, e]));
  const list = document.querySelector("#process-steps");
  list.innerHTML = STEPS.map(([id, label]) => {
    const ev = byName[id] || { status: "pending", detail: "", elapsed_ms: 0 };
    const iconClass =
      ev.status === "active" ? "active" : ev.status === "done" ? "done" : ev.status === "error" ? "error" : "";
    const check = ev.status === "done" ? "✓" : ev.status === "error" ? "×" : "";
    return `<li data-step="${id}">
      <span class="step-icon ${iconClass}">${check}</span>
      <div>
        <strong>${label}</strong>
        <span class="step-detail">${ev.detail || ""}</span>
      </div>
      <span class="elapsed">${ev.elapsed_ms ? (ev.elapsed_ms / 1000).toFixed(1) + "s" : ""}</span>
    </li>`;
  }).join("");
  const active = (events || []).find((e) => e.status === "active");
  document.querySelectorAll(".pill").forEach((p) => p.classList.remove("is-active"));
  if (active) {
    const map = {
      transcribing: "whisper",
      downloading: "whisper",
      extracting: "whisper",
      translating: "whisper",
      generating_title: "gemini",
      summarising: "gemini",
      indexing: "chroma",
    };
    const pill = map[active.step];
    if (pill) document.querySelector(`.pill[data-pill="${pill}"]`)?.classList.add("is-active");
  }
}

export async function startProcessing(state, showView) {
  _state = state;
  if (!state.sessionId) return;
  document.querySelector("#process-error").hidden = true;
  document.querySelector("#retry-btn").hidden = true;
  document.querySelector("#complete-burst").hidden = true;
  renderSteps(STEPS.map(([id]) => ({ step: id, status: "pending", detail: "", elapsed_ms: 0 })));
  if (state.ws) state.ws.close();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/${state.sessionId}`);
  state.ws = ws;
  const latest = {};
  ws.onmessage = (msg) => {
    const event = JSON.parse(msg.data);
    latest[event.step] = event;
    renderSteps(Object.values(latest));
    if (event.status === "error") {
      document.querySelector("#process-error").hidden = false;
      document.querySelector("#process-error").textContent = event.detail;
      document.querySelector("#retry-btn").hidden = false;
    }
    if (event.step === "indexing" && event.status === "done") {
      const burst = document.querySelector("#complete-burst");
      burst.hidden = false;
      setTimeout(() => showView("view-results"), 1000);
    }
  };
  ws.onclose = (ev) => {
    if (ev.code === 4404) {
      document.querySelector("#process-error").hidden = false;
      document.querySelector("#process-error").textContent = "Session not found or expired";
      document.querySelector("#retry-btn").hidden = false;
    }
  };
}

export async function loadResults(state) {
  _state = state;
  document.querySelectorAll(".skeleton").forEach((s) => (s.hidden = false));
  const data = await getResults(state.sessionId);
  state.results = data;
  document.querySelector("#meeting-title").textContent = data.title || "Untitled meeting";
  document.querySelector("#chat-title").textContent = data.title || "Untitled meeting";
  const date = data.created_at ? new Date(data.created_at).toLocaleString() : "";
  document.querySelector("#meta-row").innerHTML = `<span>${date}</span><span>${data.duration_seconds || 0}s</span><span>${data.word_count || 0} words</span>`;
  document.querySelector("#sk-summary").hidden = true;
  document.querySelector("#summary-text").innerHTML = formatRichText(data.summary || "");
  document.querySelector("#sk-decisions").hidden = true;
  document.querySelector("#decisions-list").innerHTML = renderInsightCards(data.key_decisions, "No key decisions found.");
  document.querySelector("#sk-discussion").hidden = true;
  document.querySelector("#discussion-list").innerHTML = renderInsightCards(
    data.discussion_points,
    "No discussion points found."
  );
  renderActions(data.action_items || []);
  document.querySelector("#transcript-view").textContent = data.transcript || "";
  document.dispatchEvent(new CustomEvent("results-loaded"));
}

function renderActions(items) {
  const empty = document.querySelector("#actions-empty");
  const table = document.querySelector("#actions-table");
  if (!items.length) {
    empty.hidden = false;
    table.hidden = true;
    return;
  }
  empty.hidden = true;
  table.hidden = false;
  table.querySelector("tbody").innerHTML = items
    .map((row) => {
      const p = (row.priority || "Medium").toLowerCase();
      return `<tr>
      <td>${escapeHtml(row.owner)}</td>
      <td>${escapeHtml(row.task)}</td>
      <td>${escapeHtml(row.due)}</td>
      <td><span class="prio prio-${p}">${escapeHtml(row.priority)}</span></td>
    </tr>`;
    })
    .join("");
}

function renderInsightCards(items, emptyMsg) {
  const clean = (items || []).filter((d) => {
    const text = String(d || "").trim();
    return text && !/^no\s+.+\s+found\.?$/i.test(text);
  });
  if (!clean.length) return `<p class="empty-note">${emptyMsg}</p>`;
  return clean.map((d) => `<div class="decision-card">${escapeHtml(d)}</div>`).join("");
}

function formatRichText(text) {
  const source = String(text || "").trim();
  if (!source) return "";
  if (window.marked) {
    return window.marked.parse(source, { breaks: true, gfm: true });
  }
  return escapeHtml(source).replace(/\n/g, "<br>");
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function initResults(state, showView) {
  _state = state;

  document.querySelectorAll("[data-export]").forEach((btn) => {
    btn.addEventListener("click", () => exportData(btn.dataset.export, state.sessionId));
  });

  document.querySelector("#new-analysis")?.addEventListener("click", async () => {
    try {
      await cleanup();
    } catch (e) {
      console.warn("Cleanup request error:", e);
    }
    state.sessionId = null;
    state.results = null;
    state.file = null;
    showView("view-upload");
  });

  document.querySelectorAll(".copy-btn[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const key = btn.dataset.copy;
      const text =
        key === "summary"
          ? state.results?.summary
          : key === "decisions"
            ? (state.results?.key_decisions || []).join("\n")
            : (state.results?.discussion_points || []).join("\n");
      await navigator.clipboard.writeText(text || "");
      btn.textContent = "Copied";
      setTimeout(() => (btn.textContent = "Copy"), 1200);
    });
  });

  document.querySelector("#export-csv")?.addEventListener("click", () => {
    const rows = [
      ["Owner", "Task", "Due date", "Priority"],
      ...(state.results?.action_items || []).map((r) => [r.owner, r.task, r.due, r.priority]),
    ];
    const csv = rows.map((r) => r.map((c) => `"${String(c || "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "action-items.csv";
    a.click();
  });

  document.querySelector("#title-edit")?.addEventListener("click", () => {
    document.querySelector("#meeting-title")?.focus();
  });

  let searchTimer;
  const searchInput = document.querySelector("#transcript-search");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => highlightTranscript(e.target.value), 200);
    });
  }
}

function highlightTranscript(q) {
  const raw = _state?.results?.transcript || "";
  const view = document.querySelector("#transcript-view");
  if (!q) {
    view.textContent = raw;
    document.querySelector("#match-count").textContent = "";
    return;
  }
  const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  const matches = raw.match(re) || [];
  view.innerHTML = escapeHtml(raw).replace(re, (m) => `<mark>${m}</mark>`);
  document.querySelector("#match-count").textContent = matches.length
    ? `${matches.length} match${matches.length === 1 ? "" : "es"}`
    : "0 matches";
}
