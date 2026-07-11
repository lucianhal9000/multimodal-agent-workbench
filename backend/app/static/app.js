const form = document.querySelector("#agent-form");
const chat = document.querySelector("#chat");
const queryInput = document.querySelector("#query");
const fileInput = document.querySelector("#files");
const fileSummary = document.querySelector("#file-summary");
const submitButton = document.querySelector("#submit");

fileInput.addEventListener("change", () => {
  const names = [...fileInput.files].map((file) => file.name);
  fileSummary.textContent = names.length ? `${names.length} selected: ${names.join(", ")}` : "JPG, PNG, PDF, MP3, WAV, or M4A · up to 8 files";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  const files = [...fileInput.files];
  if (!query && !files.length) {
    renderError("Add a request or attach at least one file.");
    return;
  }
  if (files.length > 8) {
    renderError("Please upload no more than 8 files at once.");
    return;
  }

  renderUser(query, files);
  const loading = document.createElement("article");
  loading.className = "message assistant-message loading";
  loading.textContent = "Working through the minimum viable tool sequence…";
  chat.append(loading);
  chat.scrollIntoView({ block: "end", behavior: "smooth" });
  submitButton.disabled = true;
  submitButton.textContent = "Running…";

  try {
    const payload = new FormData();
    payload.append("query", query);
    files.forEach((file) => payload.append("files", file));
    const response = await fetch("/api/run", { method: "POST", body: payload });
    const body = await response.json();
    loading.remove();
    if (!response.ok) throw new Error(body.detail || "The agent could not complete this request.");
    renderResult(body);
    form.reset();
    fileSummary.textContent = "JPG, PNG, PDF, MP3, WAV, or M4A · up to 8 files";
  } catch (error) {
    loading.remove();
    renderError(error.message || "The agent could not complete this request.");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Run agent";
  }
});

function renderUser(query, files) {
  const node = document.querySelector("#user-template").content.firstElementChild.cloneNode(true);
  node.querySelector(".user-query").textContent = query || "[No text query supplied]";
  const list = node.querySelector(".attachment-list");
  files.forEach((file) => {
    const item = document.createElement("li");
    item.textContent = `${file.name} (${formatBytes(file.size)})`;
    list.append(item);
  });
  if (!files.length) list.remove();
  chat.append(node);
}

function renderResult(response) {
  const node = document.querySelector("#result-template").content.firstElementChild.cloneNode(true);
  node.querySelector(".answer").textContent = response.answer;
  const plan = node.querySelector(".plan");
  response.plan.forEach((step) => {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = humanize(step.tool);
    const reason = document.createTextNode(` — ${step.reason}`);
    const meta = document.createElement("span");
    meta.className = `step-meta status-${step.status}`;
    const detail = step.detail ? ` · ${step.detail}` : "";
    meta.textContent = `${step.status}${step.elapsed_ms != null ? ` · ${step.elapsed_ms} ms` : ""}${detail}`;
    item.append(title, reason, meta);
    plan.append(item);
  });
  const estimate = response.cost_estimate;
  node.querySelector(".cost").textContent = `≈ ${estimate.estimated_input_tokens.toLocaleString()} input + ${estimate.estimated_output_tokens.toLocaleString()} output tokens · ≈ $${estimate.estimated_usd.toFixed(5)}\n${estimate.note}`;
  const documentList = node.querySelector(".document-list");
  response.extracted_documents.forEach((document) => documentList.append(renderDocument(document)));
  if (!response.extracted_documents.length) documentList.textContent = "No files were attached.";
  if (response.warnings.length) {
    const warning = node.querySelector(".warnings");
    warning.hidden = false;
    warning.textContent = `Note: ${response.warnings.join(" ")}`;
  }
  chat.append(node);
  node.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function renderDocument(extractedDocument) {
  const wrapper = document.createElement("details");
  const summary = document.createElement("summary");

  const extras = [extractedDocument.kind];

  if (extractedDocument.confidence != null) {
    extras.push(
      `confidence ${Math.round(extractedDocument.confidence * 100)}%`
    );
  }

  if (extractedDocument.duration_seconds != null) {
    extras.push(`${extractedDocument.duration_seconds}s`);
  }

  summary.textContent =
    `${extractedDocument.filename} · ${extras.join(" · ")}`;

  const text = extractedDocument.text
    ? extractedDocument.text
    : "No readable text was extracted.";

  const pre = document.createElement("pre");
  pre.textContent = text;

  wrapper.append(summary, pre);

  extractedDocument.warnings.forEach((message) => {
    const warning = document.createElement("p");
    warning.className = "warning";
    warning.textContent = message;
    wrapper.append(warning);
  });

  return wrapper;
}

function renderError(message) {
  const node = document.createElement("article");
  node.className = "message assistant-message";
  const text = document.createElement("p");
  text.className = "warning";
  text.textContent = message;
  node.append(text);
  chat.append(node);
}

function humanize(value) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatBytes(bytes) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
