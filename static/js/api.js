const EXPORT_NAMES = {
  pdf: "meeting.pdf",
  txt: "meeting.txt",
  json: "meeting.json",
  "chat-pdf": "meeting_chat.pdf",
};

export async function upload(payload) {
  const res = await fetch("/api/upload", {
    method: "POST",
    ...(payload instanceof FormData
      ? { body: payload }
      : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getResults(sessionId) {
  const res = await fetch(`/api/results/${sessionId}`);
  if (!res.ok) throw new Error("Failed to fetch results");
  return res.json();
}

export async function cleanup() {
  const res = await fetch("/api/cleanup", { method: "POST" });
  if (!res.ok) throw new Error("Cleanup failed");
  return res.json();
}

export async function exportData(kind, sessionId) {
  const res = await fetch(`/api/export/${kind}/${sessionId}`);
  if (!res.ok) throw new Error("Export failed");
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = EXPORT_NAMES[kind] || `meeting.${kind}`;
  a.click();
  URL.revokeObjectURL(a.href);
}
