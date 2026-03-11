const ingestBtn = document.getElementById("ingestBtn");
const rebuildChk = document.getElementById("rebuildChk");
const ingestStatus = document.getElementById("ingestStatus");
const askBtn = document.getElementById("askBtn");
const question = document.getElementById("question");
const answer = document.getElementById("answer");
const citations = document.getElementById("citations");
const topK = document.getElementById("topK");
const apiKey = document.getElementById("apiKey");
const userId = document.getElementById("userId");
const uploadInput = document.getElementById("uploadInput");
const uploadBtn = document.getElementById("uploadBtn");
const uploadStatus = document.getElementById("uploadStatus");

function setStatus(el, text, kind = "") {
  el.textContent = text;
  el.className = `status ${kind}`.trim();
}

function authHeaders() {
  const headers = {};
  const key = apiKey?.value?.trim();
  const user = userId?.value?.trim();
  if (key) headers["X-API-Key"] = key;
  if (user) headers["X-User"] = user;
  return headers;
}

function requireApiKey(targetEl) {
  const key = apiKey?.value?.trim();
  if (!key) {
    if (targetEl) setStatus(targetEl, "Missing API key.", "error");
    return false;
  }
  return true;
}

async function ingest() {
  if (!requireApiKey(ingestStatus)) return;
  setStatus(ingestStatus, "Ingesting...", "pending");
  const url = new URL("/ingest", window.location.origin);
  if (rebuildChk.checked) url.searchParams.set("rebuild", "true");
  const res = await fetch(url.toString(), { method: "POST", headers: authHeaders() });
  const data = await res.json();
  if (!res.ok) {
    setStatus(ingestStatus, data.detail || "Ingest failed", "error");
    return;
  }
  setStatus(ingestStatus, `Processed ${data.files_processed} file(s), added ${data.chunks_added} chunk(s).`, "ok");
}

async function upload() {
  if (!requireApiKey(uploadStatus)) return;
  if (!uploadInput.files.length) {
    setStatus(uploadStatus, "Select files to upload.", "error");
    return;
  }
  setStatus(uploadStatus, "Uploading...", "pending");
  const form = new FormData();
  for (const file of uploadInput.files) {
    form.append("files", file);
  }
  const res = await fetch("/upload", {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  const data = await res.json();
  if (!res.ok) {
    setStatus(uploadStatus, data.detail || "Upload failed", "error");
    return;
  }
  const failed = data.files_failed || 0;
  const saved = data.files_saved || 0;
  const suffix = failed ? ` (${failed} failed)` : "";
  setStatus(uploadStatus, `Uploaded ${saved} file(s).${suffix}`, failed ? "error" : "ok");
  if (data.failures?.length) {
    console.warn("Upload failures:", data.failures);
  }
  uploadInput.value = "";
}

async function ask() {
  if (!requireApiKey()) {
    answer.textContent = "Missing API key.";
    return;
  }
  answer.textContent = "";
  citations.innerHTML = "";
  const payload = {
    question: question.value.trim(),
    top_k: Number(topK.value) || 5,
  };
  if (!payload.question) {
    answer.textContent = "Please enter a question.";
    return;
  }
  answer.textContent = "Thinking...";
  const res = await fetch("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    answer.textContent = data.detail || "Query failed";
    return;
  }
  answer.textContent = data.answer || "";
  if (data.citations?.length) {
    const list = document.createElement("ul");
    for (const c of data.citations) {
      const li = document.createElement("li");
      li.textContent = `${c.source} (chunk ${c.chunk_id})`;
      list.appendChild(li);
    }
    citations.appendChild(list);
  }
}

ingestBtn.addEventListener("click", () => ingest().catch((e) => {
  setStatus(ingestStatus, e.message || "Ingest failed", "error");
}));

uploadBtn.addEventListener("click", () => upload().catch((e) => {
  setStatus(uploadStatus, e.message || "Upload failed", "error");
}));

askBtn.addEventListener("click", () => ask().catch((e) => {
  answer.textContent = e.message || "Query failed";
}));
