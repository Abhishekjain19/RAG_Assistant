(() => {
  const STEPS = [
    ["downloading", "Downloading"],
    ["extracting", "Extracting audio"],
    ["transcribing", "Transcribing"],
    ["translating", "Translating"],
    ["generating_title", "Generating title"],
    ["summarising", "Summarising"],
    ["indexing", "Indexing"],
  ];
  const YT_RE = /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/|embed\/)|youtu\.be\/)[\w-]{6,}/i;
  const ALLOWED = ["mp3", "mp4", "wav", "m4a", "webm"];

  const state = {
    view: "view-landing",
    sessionId: null,
    file: null,
    url: "",
    tab: "file",
    results: null,
    lastPayload: null,
    ws: null,
    abort: null,
    streaming: false,
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function showView(id) {
    state.view = id;
    $$(".view").forEach((v) => v.classList.toggle("view--active", v.id === id));
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (id === "view-processing") startProcessing();
    if (id === "view-results") loadResults();
    if (id === "view-chat") setupChat();
  }

  function initTheme() {
    const saved = localStorage.getItem("theme") || "light";
    document.documentElement.setAttribute("data-theme", saved);
    $("#theme-toggle").addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
    });
  }

  function setAnalyseEnabled() {
    const ok = state.tab === "file" ? !!state.file : YT_RE.test(state.url);
    $("#analyse-btn").disabled = !ok;
  }

  function formatBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  }

  function setFile(file) {
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    if (!ALLOWED.includes(ext)) {
      alert("Accepted formats: MP3 MP4 WAV M4A WEBM");
      return;
    }
    state.file = file;
    const meta = $("#file-meta");
    meta.hidden = false;
    meta.innerHTML = `<strong>${file.name}</strong> · ${formatBytes(file.size)} · <span class="file-badge">${ext.toUpperCase()}</span>`;
    setAnalyseEnabled();
  }

  function initUpload() {
    $$(".tabs__btn[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.tab = btn.dataset.tab;
        $$(".tabs__btn[data-tab]").forEach((b) => b.classList.toggle("is-active", b === btn));
        $("#panel-file").classList.toggle("is-active", state.tab === "file");
        $("#panel-youtube").classList.toggle("is-active", state.tab === "youtube");
        setAnalyseEnabled();
      });
    });
    const zone = $("#dropzone");
    zone.addEventListener("click", () => $("#file-input").click());
    $("#file-input").addEventListener("change", (e) => e.target.files[0] && setFile(e.target.files[0]));
    ["dragenter", "dragover"].forEach((ev) =>
      zone.addEventListener(ev, (e) => {
        e.preventDefault();
        zone.classList.add("is-dragover");
      })
    );
    ["dragleave", "drop"].forEach((ev) =>
      zone.addEventListener(ev, (e) => {
        e.preventDefault();
        zone.classList.remove("is-dragover");
      })
    );
    zone.addEventListener("drop", (e) => {
      const file = e.dataTransfer.files[0];
      if (file) setFile(file);
    });
    const input = $("#youtube-url");
    const field = input.closest(".url-field");
    input.addEventListener("input", () => {
      state.url = input.value.trim();
      const empty = !state.url;
      const valid = YT_RE.test(state.url);
      field.classList.toggle("is-valid", valid);
      field.classList.toggle("is-invalid", !empty && !valid);
      $("#url-check").hidden = !valid;
      $("#url-error").hidden = empty || valid;
      setAnalyseEnabled();
    });
    $("#analyse-btn").addEventListener("click", submitUpload);
    $("#retry-btn").addEventListener("click", () => submitUpload(true));
  }

  async function submitUpload(isRetry) {
    const btn = $("#analyse-btn");
    const spinner = btn.querySelector(".spinner");
    const label = btn.querySelector(".btn__label");
    btn.disabled = true;
    spinner.hidden = false;
    label.textContent = "Starting…";
    try {
      const language = $("#language").value;
      const quality = $("#quality").value;
      let res;
      if (state.tab === "file") {
        const fd = new FormData();
        fd.append("file", state.file);
        fd.append("language", language);
        fd.append("quality", quality);
        state.lastPayload = { type: "file", language, quality };
        res = await fetch("/api/upload", { method: "POST", body: fd });
      } else {
        const body = { url: state.url, language, quality };
        state.lastPayload = body;
        res = await fetch("/api/upload", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      }
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      state.sessionId = data.session_id;
      $("#pill-whisper-size").textContent = quality;
      showView("view-processing");
    } catch (err) {
      alert(err.message || "Upload failed");
    } finally {
      spinner.hidden = true;
      label.textContent = "Analyse meeting";
      setAnalyseEnabled();
    }
  }

  function renderSteps(events) {
    const byName = Object.fromEntries((events || []).map((e) => [e.step, e]));
    const list = $("#process-steps");
    list.innerHTML = STEPS.map(([id, label]) => {
      const ev = byName[id] || { status: "pending", detail: "", elapsed_ms: 0 };
      const iconClass = ev.status === "active" ? "active" : ev.status === "done" ? "done" : ev.status === "error" ? "error" : "";
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
    $$(".pill").forEach((p) => p.classList.remove("is-active"));
    if (active) {
      const map = { transcribing: "whisper", downloading: "whisper", extracting: "whisper", translating: "whisper", generating_title: "gemini", summarising: "gemini", indexing: "chroma" };
      const pill = map[active.step];
      if (pill) $(`.pill[data-pill="${pill}"]`)?.classList.add("is-active");
    }
  }

  function startProcessing() {
    $("#process-error").hidden = true;
    $("#retry-btn").hidden = true;
    $("#complete-burst").hidden = true;
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
        $("#process-error").hidden = false;
        $("#process-error").textContent = event.detail;
        $("#retry-btn").hidden = false;
      }
      if (event.step === "indexing" && event.status === "done") {
        const burst = $("#complete-burst");
        burst.hidden = false;
        setTimeout(() => showView("view-results"), 1000);
      }
    };
  }

  function moveIndicator() {
    const tabs = $$("#results-tabs .tabs__btn");
    const active = tabs.find((t) => t.classList.contains("is-active"));
    const ind = $("#results-indicator");
    if (!active || !ind) return;
    ind.style.width = `${active.offsetWidth}px`;
    ind.style.transform = `translateX(${active.offsetLeft}px)`;
  }

  async function loadResults() {
    $$(".skeleton").forEach((s) => (s.hidden = false));
    const res = await fetch(`/api/results/${state.sessionId}`);
    if (!res.ok) return;
    const data = await res.json();
    state.results = data;
    $("#meeting-title").textContent = data.title || "Untitled meeting";
    $("#chat-title").textContent = data.title || "Untitled meeting";
    const date = data.created_at ? new Date(data.created_at).toLocaleString() : "";
    $("#meta-row").innerHTML = `<span>${date}</span><span>${data.duration_seconds || 0}s</span><span>${data.word_count || 0} words</span>`;
    $("#sk-summary").hidden = true;
    $("#summary-text").innerHTML = formatRichText(data.summary || "");
    $("#sk-decisions").hidden = true;
    $("#decisions-list").innerHTML = renderInsightCards(data.key_decisions, "No key decisions found.");
    $("#sk-discussion").hidden = true;
    const discussion = renderInsightCards(data.discussion_points, "No discussion points found.");
    $("#discussion-list").innerHTML = discussion;
    renderActions(data.action_items || []);
    $("#transcript-view").textContent = data.transcript || "";
    requestAnimationFrame(moveIndicator);
  }

  function renderActions(items) {
    const empty = $("#actions-empty");
    const table = $("#actions-table");
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
        return `<tr><td>${escapeHtml(row.owner)}</td><td>${escapeHtml(row.task)}</td><td>${escapeHtml(row.due)}</td><td><span class="prio prio-${p}">${escapeHtml(row.priority)}</span></td></tr>`;
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

  function initResults() {
    $$("#results-tabs .tabs__btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$("#results-tabs .tabs__btn").forEach((b) => b.classList.toggle("is-active", b === btn));
        $$(".rtab").forEach((p) => p.classList.toggle("is-active", p.id === `rtab-${btn.dataset.rtab === "actions" ? "actions" : btn.dataset.rtab}`));
        const map = { summary: "rtab-summary", actions: "rtab-actions", transcript: "rtab-transcript" };
        $$(".rtab").forEach((p) => p.classList.toggle("is-active", p.id === map[btn.dataset.rtab]));
        moveIndicator();
      });
    });
    $$("[data-export]").forEach((btn) =>
      btn.addEventListener("click", () => downloadExport(btn.dataset.export))
    );
    $("#new-analysis").addEventListener("click", async () => {
      try {
        await fetch("/api/cleanup", { method: "POST" });
      } catch (err) {
        console.warn("Cleanup request error:", err);
      }
      state.sessionId = null;
      state.results = null;
      state.file = null;
      showView("view-upload");
    });
    $$(".copy-btn").forEach((btn) =>
      btn.addEventListener("click", async () => {
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
      })
    );
    $("#export-csv").addEventListener("click", exportCsv);
    let t;
    $("#transcript-search").addEventListener("input", (e) => {
      clearTimeout(t);
      t = setTimeout(() => highlightTranscript(e.target.value), 200);
    });
    $("#title-edit").addEventListener("click", () => $("#meeting-title").focus());
    $("#open-chat")?.addEventListener("click", () => {
      $("#chat-idle").hidden = true;
      $("#chat-thread").hidden = false;
      setupChat();
      $("#chat-input")?.focus();
    });
    $("#close-chat")?.addEventListener("click", () => {
      $("#chat-thread").hidden = true;
      $("#chat-idle").hidden = false;
    });
  }

  function highlightTranscript(q) {
    const raw = state.results?.transcript || "";
    const view = $("#transcript-view");
    if (!q) {
      view.textContent = raw;
      $("#match-count").textContent = "";
      return;
    }
    const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    const matches = raw.match(re) || [];
    view.innerHTML = escapeHtml(raw).replace(re, (m) => `<mark>${m}</mark>`);
    const marks = $$("mark", view);
    $("#match-count").textContent = matches.length ? `1 of ${matches.length} matches` : "0 of 0 matches";
    let i = 0;
    if (marks[0]) {
      $("#match-count").textContent = `${i + 1} of ${matches.length} matches`;
    }
  }

  async function downloadExport(kind) {
    const res = await fetch(`/api/export/${kind}/${state.sessionId}`);
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    
    let filename = 'meeting';
    if (kind === 'chat-pdf') filename += '_chat';
    let ext = 'json';
    if (kind === 'txt') ext = 'txt';
    if (kind === 'pdf' || kind === 'chat-pdf') ext = 'pdf';
    
    a.download = `${filename}.${ext}`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function exportCsv() {
    const rows = [["Owner", "Task", "Due date", "Priority"], ...(state.results?.action_items || []).map((r) => [r.owner, r.task, r.due, r.priority])];
    const csv = rows.map((r) => r.map((c) => `"${String(c || "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "action-items.csv";
    a.click();
  }

  function setupChat() {
    $("#chat-title").textContent = state.results?.title || $("#meeting-title").textContent;
    const box = $("#messages");
    box.addEventListener("scroll", () => {
      const dist = box.scrollHeight - box.scrollTop - box.clientHeight;
      $("#scroll-fab").hidden = dist < 200;
    });
    $("#scroll-fab").onclick = () => box.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
    renderStarterChips();
  }

  function renderStarterChips() {
    const container = $("#starter-chips");
    if (!container) return;

    // 1. Check direct suggested questions from analysis
    let questions = (state.results?.suggested_questions || [])
      .concat(state.results?.discussion_points || [])
      .map((q) => String(q || "").trim())
      .filter((q) => q && !/^no\s+.+\s+found\.?$/i.test(q))
      .map((q) => {
        let clean = q.replace(/^(\d+[\.\)]\s*|[-*•]\s*)/, "").trim();
        // Convert discussion points to question format if needed
        if (!clean.endsWith("?")) {
          clean = `What was discussed regarding ${clean.toLowerCase().replace(/\.$/, "")}?`;
        }
        if (clean.length > 70) clean = clean.slice(0, 67) + "…";
        return clean;
      });

    // Deduplicate questions
    questions = Array.from(new Set(questions));

    // If still empty, formulate context-based questions using meeting title or transcript key topics
    if (!questions.length) {
      const title = (state.results?.title || "").replace(/meeting notes/i, "").trim();
      if (title) {
        questions.push(
          `What are the main takeaways regarding ${title}?`,
          `What challenges were mentioned about ${title}?`
        );
      }
    }

    if (!questions.length) {
      container.hidden = true;
      container.innerHTML = "";
      return;
    }

    const chipsToShow = questions.slice(0, 5);
    container.innerHTML = chipsToShow
      .map((q) => `<button type="button">${escapeHtml(q)}</button>`)
      .join("");
    container.hidden = false;

    $$("button", container).forEach((btn) => {
      btn.addEventListener("click", () => sendChat(btn.textContent));
    });
  }

  function appendMessage(role, text) {
    const el = document.createElement("div");
    el.className = role === "user" ? "msg msg-user" : "msg msg-ai";
    const avatar = document.createElement("div");
    avatar.className = "msg-avatar";
    avatar.innerHTML = role === "user" ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>` : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"></path></svg>`;
    const content = document.createElement("div");
    content.className = "msg-content";
    if (role === "user") content.textContent = text;
    else content.innerHTML = `<div class="md"></div><span class="cursor"></span>`;
    const meta = document.createElement("div");
    meta.className = "msg-meta";
    meta.innerHTML = `<span>${new Date().toLocaleTimeString()}</span>`;
    content.appendChild(meta);
    el.appendChild(avatar);
    el.appendChild(content);
    $("#messages").appendChild(el);
    $("#messages").scrollTop = $("#messages").scrollHeight;
    return el;
  }

  function renderSources(sources) {
    const empty = $("#sources-empty");
    const list = $("#sources-list");
    if (!sources || !sources.length) {
      empty.hidden = false;
      list.innerHTML = "";
      return;
    }
    empty.hidden = true;
    list.innerHTML = sources
      .map(
        (s) => `<article class="source-card"><span class="score">${s.score}% match</span><p>${escapeHtml(s.excerpt)}</p>${s.timestamp != null ? `<small>chunk ${s.timestamp}</small>` : ""}</article>`
      )
      .join("");
  }

  async function sendChat(text) {
    if (!text || state.streaming) return;
    $("#starter-chips").hidden = true;
    appendMessage("user", text);
    const ai = appendMessage("assistant", "");
    const md = ai.querySelector(".md");
    const cursor = ai.querySelector(".cursor");
    state.streaming = true;
    $("#send-btn").disabled = false;
    $(".icon-send").hidden = true;
    $(".icon-stop").hidden = false;
    let full = "";
    const controller = new AbortController();
    state.abort = controller;
    try {
      const res = await fetch(`/api/chat/${state.sessionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: controller.signal,
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop();
        for (const part of parts) {
          const line = part.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          const payload = JSON.parse(line.slice(5).trim());
          if (payload.token) {
            full += payload.token;
            md.innerHTML = window.marked.parse(full);
            md.querySelectorAll("pre code").forEach((b) => window.hljs.highlightElement(b));
          }
          if (payload.done && payload.sources) renderSources(payload.sources);
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") md.textContent = "Could not get a reply.";
    } finally {
      cursor?.remove();
      state.streaming = false;
      state.abort = null;
      $(".icon-send").hidden = false;
      $(".icon-stop").hidden = true;
      $("#chat-input").value = "";
      autoResize($("#chat-input"));
      setSendEnabled();
    }
  }

  function setSendEnabled() {
    $("#send-btn").disabled = state.streaming ? false : !$("#chat-input").value.trim();
  }

  function autoResize(el) {
    el.style.height = "auto";
    const line = 22;
    el.style.height = Math.min(el.scrollHeight, line * 5) + "px";
  }

  function initChat() {
    const input = $("#chat-input");
    input.addEventListener("input", () => {
      autoResize(input);
      setSendEnabled();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (state.streaming) {
          state.abort?.abort();
          return;
        }
        sendChat(input.value.trim());
      }
    });
    $("#composer").addEventListener("submit", (e) => {
      e.preventDefault();
      if (state.streaming) {
        state.abort?.abort();
        return;
      }
      sendChat(input.value.trim());
    });
    $("#sources-toggle")?.addEventListener("click", () => $("#sources-panel")?.classList.toggle("is-open"));
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-view]");
    if (btn) {
      e.preventDefault();
      showView(btn.dataset.view);
    }
  });

  initTheme();
  initUpload();
  initResults();
  initChat();
})();
