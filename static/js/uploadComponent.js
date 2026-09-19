import { upload } from "./api.js";
import { showToast } from "./toast.js";

const YT_RE = /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/|embed\/)|youtu\.be\/)[\w-]{6,}/i;
const ALLOWED = ["mp3", "mp4", "wav", "m4a", "webm"];

export function initUpload(state, showView) {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function setAnalyseEnabled() {
    const ok = state.tab === "file" ? !!state.file : YT_RE.test(state.url);
    const btn = $("#analyse-btn");
    if (btn) btn.disabled = !ok;
  }

  function formatBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  }

  function setFile(file) {
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    if (!ALLOWED.includes(ext)) {
      showToast("Accepted formats: MP3 MP4 WAV M4A WEBM", "error");
      return;
    }
    state.file = file;
    const meta = $("#file-meta");
    meta.hidden = false;
    meta.innerHTML = `<strong>${file.name}</strong> · ${formatBytes(file.size)} · <span class="file-badge">${ext.toUpperCase()}</span>`;
    setAnalyseEnabled();
  }

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

  const urlInput = $("#youtube-url");
  const urlField = urlInput.closest(".url-field");
  urlInput.addEventListener("input", () => {
    state.url = urlInput.value.trim();
    const empty = !state.url;
    const valid = YT_RE.test(state.url);
    urlField.classList.toggle("is-valid", valid);
    urlField.classList.toggle("is-invalid", !empty && !valid);
    $("#url-check").hidden = !valid;
    $("#url-error").hidden = empty || valid;
    setAnalyseEnabled();
  });

  async function submitUpload() {
    const btn = $("#analyse-btn");
    const spinner = btn.querySelector(".spinner");
    const label = btn.querySelector(".btn__label");
    if (state.tab === "file" && !state.file) {
      showToast("Choose an audio or video file first", "error");
      return;
    }
    if (state.tab !== "file" && !YT_RE.test(state.url)) {
      showToast("Enter a valid YouTube URL", "error");
      return;
    }
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
        res = await upload(fd);
      } else {
        const body = { url: state.url, language, quality };
        state.lastPayload = body;
        res = await upload(body);
      }
      state.sessionId = res.session_id;
      $("#pill-whisper-size").textContent = quality;
      showView("view-processing");
    } catch (err) {
      showToast(err.message || "Upload failed", "error");
    } finally {
      spinner.hidden = true;
      label.textContent = "Analyse meeting";
      setAnalyseEnabled();
    }
  }

  $("#analyse-btn").addEventListener("click", submitUpload);
  $("#retry-btn")?.addEventListener("click", submitUpload);
}
