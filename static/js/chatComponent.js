export function initChat(state) {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  $("#open-chat")?.addEventListener("click", () => {
    $("#chat-idle").hidden = true;
    $("#chat-thread").hidden = false;
    renderStarterChips();
    $("#chat-input")?.focus();
  });

  $("#close-chat")?.addEventListener("click", () => {
    $("#chat-thread").hidden = true;
    $("#chat-idle").hidden = false;
  });

  const box = $("#messages");
  if (box) {
    box.addEventListener("scroll", () => {
      const dist = box.scrollHeight - box.scrollTop - box.clientHeight;
      $("#scroll-fab").hidden = dist < 200;
    });
  }
  $("#scroll-fab")?.addEventListener("click", () => {
    box?.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
  });

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderStarterChips() {
    const container = $("#starter-chips");
    if (!container) return;

    let questions = (state.results?.suggested_questions || [])
      .concat(state.results?.discussion_points || [])
      .map((q) => String(q || "").trim())
      .filter((q) => q && !/^no\s+.+\s+found\.?$/i.test(q))
      .map((q) => {
        let clean = q.replace(/^(\d+[.)]\s*|[-*•]\s*)/, "").trim();
        if (!clean.endsWith("?")) {
          clean = `What was discussed regarding ${clean.toLowerCase().replace(/\.$/, "")}?`;
        }
        if (clean.length > 70) clean = clean.slice(0, 67) + "…";
        return clean;
      });

    questions = Array.from(new Set(questions));

    if (!questions.length) {
      const title = (state.results?.title || "").replace(/meeting notes/i, "").trim();
      if (title) {
        questions.push(`What are the main takeaways regarding ${title}?`);
      }
    }

    if (!questions.length) {
      container.hidden = true;
      container.innerHTML = "";
      return;
    }

    container.innerHTML = questions
      .slice(0, 5)
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
    avatar.innerHTML =
      role === "user"
        ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>`
        : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"></path></svg>`;
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
        (s) =>
          `<article class="source-card"><span class="score">${s.score}% match</span><p>${escapeHtml(s.excerpt)}</p>${s.timestamp != null ? `<small>chunk ${s.timestamp}</small>` : ""}</article>`
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
      if (!res.ok) throw new Error("Chat request failed");
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
            md.innerHTML = window.marked ? window.marked.parse(full) : escapeHtml(full);
            md.querySelectorAll("pre code").forEach((b) => window.hljs?.highlightElement(b));
          }
          if (payload.done && payload.error && !full) md.textContent = payload.error;
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
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 22 * 5) + "px";
  }

  const input = $("#chat-input");
  input?.addEventListener("input", () => {
    autoResize(input);
    setSendEnabled();
  });
  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (state.streaming) {
        state.abort?.abort();
        return;
      }
      sendChat(input.value.trim());
    }
  });
  $("#composer")?.addEventListener("submit", (e) => {
    e.preventDefault();
    if (state.streaming) {
      state.abort?.abort();
      return;
    }
    sendChat(input.value.trim());
  });

  document.addEventListener("results-loaded", renderStarterChips);
}
