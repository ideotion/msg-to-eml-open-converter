"use strict";

const breadcrumbsEl = document.getElementById("breadcrumbs");
const upButton = document.getElementById("up-button");
const scanButton = document.getElementById("scan-button");
const entryList = document.getElementById("entry-list");
const browserMessage = document.getElementById("browser-message");

const resultsSection = document.getElementById("results-section");
const resultsTitle = document.getElementById("results-title");
const resultsList = document.getElementById("results-list");
const forceCheckbox = document.getElementById("force-checkbox");
const convertButton = document.getElementById("convert-button");
const closeResultsButton = document.getElementById("close-results-button");

let currentPath = null;
let currentParent = null;
let scanFiles = []; // [{path, name, relativeFolder}]

async function apiGet(url) {
  const response = await fetch(url);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Server error (${response.status})`);
  return body;
}

async function apiPost(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Server error (${response.status})`);
  return body;
}

function showMessage(text, isError) {
  browserMessage.textContent = text;
  browserMessage.hidden = !text;
  browserMessage.classList.toggle("is-error", Boolean(isError));
}

function statusLabel(status) {
  return (
    { pending: "Pending", converting: "Converting…", converted: "Converted", skipped: "Skipped", failed: "Failed" }[
      status
    ] || status
  );
}

function setBadgeStatus(badge, status) {
  // Swap only the badge-* modifier class, never the full className: entry-list
  // badges also carry a marker class ("entry-status") that a full className
  // replacement would silently wipe out, breaking any later lookup of it.
  for (const cls of Array.from(badge.classList)) {
    if (cls.startsWith("badge-")) badge.classList.remove(cls);
  }
  badge.classList.add(`badge-${status}`);
  badge.textContent = statusLabel(status);
  badge.hidden = false;
}

function basename(path) {
  const parts = path.split("/");
  return parts[parts.length - 1];
}

function joinPath(dir, name) {
  return dir.endsWith("/") ? dir + name : `${dir}/${name}`;
}

function makeNameSpan(icon, name) {
  const span = document.createElement("span");
  span.className = "entry-name";
  const iconSpan = document.createElement("span");
  iconSpan.className = "entry-icon";
  iconSpan.setAttribute("aria-hidden", "true");
  iconSpan.textContent = icon;
  span.appendChild(iconSpan);
  span.appendChild(document.createTextNode(` ${name}`));
  return span;
}

function renderBreadcrumbs(path) {
  breadcrumbsEl.innerHTML = "";
  const segments = path.split("/").filter(Boolean);
  let accumulated = "";

  const rootCrumb = document.createElement("button");
  rootCrumb.type = "button";
  rootCrumb.className = "crumb";
  rootCrumb.textContent = "/";
  rootCrumb.addEventListener("click", () => browseTo("/"));
  breadcrumbsEl.appendChild(rootCrumb);

  for (const segment of segments) {
    accumulated += `/${segment}`;
    const sep = document.createElement("span");
    sep.className = "crumb-sep";
    sep.textContent = "›";
    breadcrumbsEl.appendChild(sep);

    const crumb = document.createElement("button");
    crumb.type = "button";
    crumb.className = "crumb";
    crumb.textContent = segment;
    const target = accumulated;
    crumb.addEventListener("click", () => browseTo(target));
    breadcrumbsEl.appendChild(crumb);
  }
}

function renderEntries(folders, msgFiles) {
  entryList.innerHTML = "";

  if (folders.length === 0 && msgFiles.length === 0) {
    showMessage("This folder is empty.", false);
    return;
  }
  showMessage("", false);

  for (const name of folders) {
    const row = document.createElement("li");
    row.className = "entry-row entry-folder";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "entry-name-button";
    button.appendChild(makeNameSpan("📁", name));
    button.addEventListener("click", () => browseTo(joinPath(currentPath, name)));
    row.appendChild(button);
    entryList.appendChild(row);
  }

  for (const name of msgFiles) {
    const fullPath = joinPath(currentPath, name);
    const row = document.createElement("li");
    row.className = "entry-row entry-file";
    row.dataset.path = fullPath;
    row.appendChild(makeNameSpan("📄", name));

    const status = document.createElement("span");
    status.className = "badge badge-pending entry-status";
    status.hidden = true;
    row.appendChild(status);

    const convertOneButton = document.createElement("button");
    convertOneButton.type = "button";
    convertOneButton.className = "button button-secondary entry-convert";
    convertOneButton.textContent = "Convert";
    convertOneButton.addEventListener("click", () => convertSingle(fullPath, row));
    row.appendChild(convertOneButton);

    entryList.appendChild(row);
  }
}

function hideResults() {
  resultsSection.hidden = true;
  scanFiles = [];
  resultsList.innerHTML = "";
}

async function browseTo(path) {
  const url = path ? `/api/browse?path=${encodeURIComponent(path)}` : "/api/browse";
  try {
    const data = await apiGet(url);
    currentPath = data.path;
    currentParent = data.parent;
    upButton.disabled = !currentParent;
    renderBreadcrumbs(currentPath);
    renderEntries(data.folders, data.msgFiles);
    hideResults();
  } catch (err) {
    showMessage(err.message || "Could not open that folder.", true);
  }
}

function applyConvertResults(results, container) {
  const byPath = new Map(results.map((r) => [r.path, r]));
  for (const row of container.querySelectorAll("[data-path]")) {
    const result = byPath.get(row.dataset.path);
    if (!result) continue;

    setBadgeStatus(row.querySelector(".badge"), result.status);

    let detail = row.querySelector(".file-detail, .entry-detail");
    if (!detail) {
      detail = document.createElement("span");
      detail.className = container === resultsList ? "file-detail" : "entry-detail";
      row.appendChild(detail);
    }
    if (result.status === "converted" && result.outputPath) {
      detail.textContent = `→ ${basename(result.outputPath)}`;
    } else if (result.error) {
      detail.textContent = result.error;
    } else if (result.warnings && result.warnings.length) {
      detail.textContent = result.warnings.join(" — ");
    } else {
      detail.textContent = "";
    }
  }
}

async function convertSingle(path, row) {
  const button = row.querySelector(".entry-convert");
  const status = row.querySelector(".entry-status");
  button.disabled = true;
  setBadgeStatus(status, "converting");
  try {
    const data = await apiPost("/api/convert", { paths: [path], force: false });
    applyConvertResults(data.results, row.parentElement);
  } catch (err) {
    setBadgeStatus(status, "failed");
  } finally {
    button.disabled = false;
  }
}

function showResults() {
  if (scanFiles.length === 0) {
    resultsSection.hidden = true;
    showMessage("No .msg files found in this folder or its subfolders.", false);
    return;
  }
  showMessage("", false);
  resultsTitle.textContent = `Found ${scanFiles.length} .msg file${scanFiles.length === 1 ? "" : "s"}`;
  resultsList.innerHTML = "";

  let lastFolder = null;
  for (const file of scanFiles) {
    if (file.relativeFolder !== lastFolder) {
      const header = document.createElement("li");
      header.className = "group-header";
      header.textContent = file.relativeFolder === "" ? "(this folder)" : file.relativeFolder;
      resultsList.appendChild(header);
      lastFolder = file.relativeFolder;
    }

    const row = document.createElement("li");
    row.className = "file-row";
    row.dataset.path = file.path;

    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = file.name;
    row.appendChild(name);

    const badge = document.createElement("span");
    badge.className = "badge badge-pending";
    badge.textContent = statusLabel("pending");
    row.appendChild(badge);

    resultsList.appendChild(row);
  }

  resultsSection.hidden = false;
  convertButton.disabled = false;
  convertButton.textContent = `Convert ${scanFiles.length} file${scanFiles.length === 1 ? "" : "s"}`;
}

scanButton.addEventListener("click", async () => {
  if (!currentPath) return;
  scanButton.disabled = true;
  try {
    const data = await apiPost("/api/scan", { path: currentPath });
    scanFiles = data.files;
    showResults();
  } catch (err) {
    showMessage(err.message || "Could not scan that folder.", true);
  } finally {
    scanButton.disabled = false;
  }
});

convertButton.addEventListener("click", async () => {
  if (scanFiles.length === 0) return;
  convertButton.disabled = true;
  for (const row of resultsList.querySelectorAll(".file-row")) {
    setBadgeStatus(row.querySelector(".badge"), "converting");
  }
  try {
    const data = await apiPost("/api/convert", {
      paths: scanFiles.map((f) => f.path),
      force: forceCheckbox.checked,
    });
    applyConvertResults(data.results, resultsList);
  } catch (err) {
    showMessage(err.message || "Conversion failed.", true);
  } finally {
    convertButton.disabled = false;
  }
});

upButton.addEventListener("click", () => {
  if (currentParent) browseTo(currentParent);
});

closeResultsButton.addEventListener("click", hideResults);

browseTo();
