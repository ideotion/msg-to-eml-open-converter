"use strict";

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const fileList = document.getElementById("file-list");
const emptyState = document.getElementById("empty-state");
const convertButton = document.getElementById("convert-button");
const downloadAllButton = document.getElementById("download-all-button");
const clearButton = document.getElementById("clear-button");

// Each entry: { file: File, status: "pending"|"converting"|"converted"|"skipped"|"failed",
//               warnings: string[], error: string|null, downloadUrl: string|null, downloadName: string|null }
let entries = [];

function addFiles(fileListLike) {
  const incoming = Array.from(fileListLike).filter((f) =>
    f.name.toLowerCase().endsWith(".msg")
  );
  for (const file of incoming) {
    entries.push({
      file,
      status: "pending",
      warnings: [],
      error: null,
      downloadUrl: null,
      downloadName: null,
    });
  }
  render();
}

function clearAll() {
  for (const entry of entries) {
    if (entry.downloadUrl) URL.revokeObjectURL(entry.downloadUrl);
  }
  entries = [];
  fileInput.value = "";
  render();
}

function statusLabel(status) {
  return {
    pending: "Pending",
    converting: "Converting…",
    converted: "Converted",
    skipped: "Skipped",
    failed: "Failed",
  }[status];
}

function render() {
  const hasEntries = entries.length > 0;
  emptyState.hidden = hasEntries;
  fileList.hidden = !hasEntries;
  fileList.textContent = "";

  let anyConverted = false;
  let anyPending = false;

  for (const entry of entries) {
    if (entry.status === "converted") anyConverted = true;
    if (entry.status === "pending") anyPending = true;

    const row = document.createElement("li");
    row.className = "file-row";

    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = entry.file.name;
    if (entry.warnings.length || entry.error) {
      const detail = document.createElement("span");
      detail.className = "file-warning";
      detail.textContent = entry.error || entry.warnings.join(" — ");
      name.appendChild(document.createElement("br"));
      name.appendChild(detail);
    }
    row.appendChild(name);

    const badge = document.createElement("span");
    badge.className = `badge badge-${entry.status}`;
    badge.textContent = statusLabel(entry.status);
    row.appendChild(badge);

    if (entry.status === "converted" && entry.downloadUrl) {
      const link = document.createElement("a");
      link.className = "file-download";
      link.href = entry.downloadUrl;
      link.download = entry.downloadName;
      link.textContent = "Download";
      row.appendChild(link);
    }

    fileList.appendChild(row);
  }

  convertButton.disabled = !anyPending;
  downloadAllButton.hidden = !anyConverted;
  clearButton.hidden = !hasEntries;
}

function base64ToBlob(base64, mimeType) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Blob([bytes], { type: mimeType });
}

const MIME_TYPES_BY_FORMAT = {
  eml: "message/rfc822",
  ics: "text/calendar",
  vcf: "text/vcard",
};

async function convertPending() {
  const pending = entries.filter((e) => e.status === "pending");
  if (pending.length === 0) return;

  for (const entry of pending) entry.status = "converting";
  convertButton.disabled = true;
  render();

  const formData = new FormData();
  for (const entry of pending) formData.append("files", entry.file);

  let payload;
  try {
    const response = await fetch("/convert", { method: "POST", body: formData });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || `Server error (${response.status})`);
    }
    payload = await response.json();
  } catch (err) {
    for (const entry of pending) {
      entry.status = "failed";
      entry.error = err instanceof Error ? err.message : "Could not reach the local server.";
    }
    render();
    return;
  }

  payload.results.forEach((result, i) => {
    const entry = pending[i];
    entry.status = result.status;
    entry.warnings = result.warnings || [];
    entry.error = result.error;
    if (result.outputBase64) {
      const mimeType = MIME_TYPES_BY_FORMAT[result.outputFormat] || "application/octet-stream";
      entry.downloadUrl = URL.createObjectURL(base64ToBlob(result.outputBase64, mimeType));
      entry.downloadName = result.outputFilename;
    }
  });

  render();
}

function downloadAll() {
  const links = fileList.querySelectorAll("a.file-download");
  links.forEach((link) => link.click());
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});
dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  addFiles(event.dataTransfer.files);
});

fileInput.addEventListener("change", () => addFiles(fileInput.files));
convertButton.addEventListener("click", convertPending);
downloadAllButton.addEventListener("click", downloadAll);
clearButton.addEventListener("click", clearAll);

render();
