// static/js/main.js
/**
 * Entry point for the MeetingAI frontend.
 * Sets up global state, theme toggling, view routing, and wires all modular components.
 */

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
  document.dispatchEvent(new CustomEvent("view-change", { detail: { view: id } }));
}

function initTheme() {
  const saved = localStorage.getItem("theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
  $("#theme-toggle")?.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
  });
}

function initApp() {
  initTheme();

  import("./uploadComponent.js").then((m) => m.initUpload(state, showView));
  import("./chatComponent.js").then((m) => m.initChat(state));
  import("./resultsComponent.js").then((m) => m.initResults(state, showView));

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-view]");
    if (!btn) return;
    e.preventDefault();
    showView(btn.dataset.view);
  });

  document.addEventListener("view-change", (e) => {
    const view = e.detail.view;
    if (view === "view-processing") {
      import("./resultsComponent.js").then((m) => m.startProcessing(state, showView));
    } else if (view === "view-results") {
      import("./resultsComponent.js").then((m) => m.loadResults(state));
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}
