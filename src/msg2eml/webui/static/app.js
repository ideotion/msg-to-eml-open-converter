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
const progressContainer = document.getElementById("progress-container");
const progressFill = document.getElementById("progress-fill");
const progressLabel = document.getElementById("progress-label");

// Output settings elements
const outputSettings = document.getElementById("output-settings");
const outputPathInput = document.getElementById("output-path-input");
const browseOutputButton = document.getElementById("browse-output-button");
const clearOutputButton = document.getElementById("clear-output-button");
const preserveStructureCheckbox = document.getElementById("preserve-structure-checkbox");

// Modal elements
const outputBrowserModal = document.getElementById("output-browser-modal");
const outputBreadcrumbs = document.getElementById("output-breadcrumbs");
const outputUpButton = document.getElementById("output-up-button");
const outputEntryList = document.getElementById("output-entry-list");
const closeOutputBrowser = document.getElementById("close-output-browser");
const selectOutputButton = document.getElementById("select-output-button");
const cancelOutputButton = document.getElementById("cancel-output-button");

let currentPath = null;
let currentParent = null;
let scanFiles = []; // [{path, name, relativeFolder}]
let resultsRowsByPath = new Map(); // path -> <li> row in #results-list, rebuilt on each scan
let conversionInProgress = false;

// Output browser state
let outputCurrentPath = null;
let outputCurrentParent = null;

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
    { pending: "Pending", converting: "Converting\u2026", converted: "Converted", skipped: "Skipped", failed: "Failed" }[
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

// A folder scan can turn up many thousands of files. There's no request-size
// cap to work around here (this is a local, single-user tool -- the server
// has no real resource boundary to defend), but sending everything as one
// request would still leave the whole run blocked on one long synchronous
// call with no progress feedback, and one network hiccup would cost the
// entire run instead of a handful of files. Chunking keeps each request's
// processing time bounded and means a batch that fails to reach the server
// only costs that batch.
//
// The batch size scales with the total instead of being a fixed constant:
// a small fixed batch (e.g. always 10) gives great progress granularity on
// a modest folder but makes a huge one dramatically slower overall, since
// Flask's dev server has real fixed overhead per request that dominates
// once there are hundreds of them. Aiming for a roughly constant NUMBER of
// batches instead keeps that overhead bounded regardless of scale, while
// the floor (matching PROGRESS_BAR_THRESHOLD) still guarantees at least one
// real intermediate step for the smallest folder the bar shows up for.
const TARGET_BATCH_COUNT = 100;

// Below this many files, the whole run is quick enough that a progress bar
// would just flash by; the button's own "Converting\u2026" state is enough.
const PROGRESS_BAR_THRESHOLD = 10;

function convertBatchSize(total) {
  return Math.max(PROGRESS_BAR_THRESHOLD, Math.ceil(total / TARGET_BATCH_COUNT));
}

function chunk(array, size) {
  const chunks = [];
  for (let i = 0; i < array.length; i += size) {
    chunks.push(array.slice(i, i + size));
  }
  return chunks;
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
    sep.textContent = "\u203a";
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
  if (folders.length === 0 && msgFiles.length === 0) {
    entryList.replaceChildren();
    showMessage("This folder is empty.", false);
    return;
  }
  showMessage("", false);

  // Built off-DOM in a fragment and attached once: appending thousands of
  // rows one at a time directly to a live, connected list forces a layout
  // recalculation on every single append, which is what actually makes a
  // large folder feel like it's hung -- not the number of rows itself.
  const fragment = document.createDocumentFragment();

  for (const name of folders) {
    const row = document.createElement("li");
    row.className = "entry-row entry-folder";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "entry-name-button";
    button.appendChild(makeNameSpan("\ud83d\udcc1", name));
    button.addEventListener("click", () => browseTo(joinPath(currentPath, name)));
    row.appendChild(button);
    fragment.appendChild(row);
  }

  for (const name of msgFiles) {
    const fullPath = joinPath(currentPath, name);
    const row = document.createElement("li");
    row.className = "entry-row entry-file";
    row.dataset.path = fullPath;
    row.appendChild(makeNameSpan("\ud83d\udcc4", name));

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

    fragment.appendChild(row);
  }

  entryList.replaceChildren(fragment);
}

function hideResults() {
  resultsSection.hidden = true;
  scanFiles = [];
  resultsRowsByPath = new Map();
  resultsList.replaceChildren();
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

function applyResultToRow(result, row) {
  setBadgeStatus(row.querySelector(".badge"), result.status);

  let detail = row.querySelector(".file-detail, .entry-detail");
  if (!detail) {
    detail = document.createElement("span");
    detail.className = row.classList.contains("file-row") ? "file-detail" : "entry-detail";
    row.appendChild(detail);
  }
  if (result.status === "converted" && result.outputPath) {
    detail.textContent = `\u2192 ${basename(result.outputPath)}`;
  } else if (result.error) {
    detail.textContent = result.error;
  } else if (result.warnings && result.warnings.length) {
    detail.textContent = result.warnings.join(" \u2014 ");
  } else {
    detail.textContent = "";
  }
}

// Looks up each result's row via a path -> row Map built once when the list
// was rendered, rather than re-scanning the whole (potentially huge) results
// list on every batch: applying N batches against a list of M rows this way
// is O(N+M) total instead of O(N*M).
function applyResultsByPath(results, rowsByPath) {
  for (const result of results) {
    const row = rowsByPath.get(result.path);
    if (row) applyResultToRow(result, row);
  }
}

async function convertSingle(path, row) {
  const button = row.querySelector(".entry-convert");
  const status = row.querySelector(".entry-status");
  button.disabled = true;
  setBadgeStatus(status, "converting");
  try {
    const data = await apiPost("/api/convert", {
      paths: [path],
      force: false,
      outputPath: outputPathInput.value,
      preserveStructure: preserveStructureCheckbox.checked,
      scanRoot: currentPath,
    });
    applyResultToRow(data.results[0], row);
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

  // Built off-DOM in a fragment and attached once (see renderEntries() for
  // why), while also indexing every row by path so applyResultsByPath() never
  // has to re-scan the whole list to find the handful of rows one batch of
  // results actually touches.
  const fragment = document.createDocumentFragment();
  resultsRowsByPath = new Map();

  let lastFolder = null;
  for (const file of scanFiles) {
    if (file.relativeFolder !== lastFolder) {
      const header = document.createElement("li");
      header.className = "group-header";
      header.textContent = file.relativeFolder === "" ? "(this folder)" : file.relativeFolder;
      fragment.appendChild(header);
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

    fragment.appendChild(row);
    resultsRowsByPath.set(file.path, row);
  }
  resultsList.replaceChildren(fragment);

  resultsSection.hidden = false;
  convertButton.disabled = false;
  convertButton.textContent = `Convert ${scanFiles.length} file${scanFiles.length === 1 ? "" : "s"}`;
}

// A bulk conversion can run for a while (thousands of files, many sequential
// batches). Every other way to change what's on screen -- scanning again,
// navigating a folder, closing the results panel -- rebuilds or discards the
// exact DOM/state the running loop is still reading and writing, which both
// corrupts that state (results get stamped onto a since-replaced list) and,
// worse, re-enables the Convert button mid-run (showResults() unconditionally
// clears it), letting a second overlapping run start. Locking down every
// navigation control for the duration is the simplest way to make "one run
// at a time" actually true instead of just assumed.
function setBusy(busy) {
  convertButton.disabled = busy;
  forceCheckbox.disabled = busy;
  scanButton.disabled = busy;
  closeResultsButton.disabled = busy;
  upButton.disabled = busy || !currentParent;
  for (const el of document.querySelectorAll("#breadcrumbs button, #entry-list button")) {
    el.disabled = busy;
  }
  // Also disable output settings controls when busy
  browseOutputButton.disabled = busy;
  clearOutputButton.disabled = busy;
  preserveStructureCheckbox.disabled = busy;
}

// Deliberately simple: every file counts as one equal unit of progress
// (no weighting by file size, no time-based estimate) -- done/total is the
// whole formula.
function showProgress(done, total) {
  progressContainer.hidden = false;
  progressFill.style.width = `${total === 0 ? 0 : Math.round((done / total) * 100)}%`;
  progressLabel.textContent = `${done} / ${total} converted`;
}

function hideProgress() {
  progressContainer.hidden = true;
  progressFill.style.width = "0%";
}

// Output browser functions
function renderOutputBreadcrumbs(path) {
  outputBreadcrumbs.innerHTML = "";
  const segments = path.split("/").filter(Boolean);
  let accumulated = "";

  const rootCrumb = document.createElement("button");
  rootCrumb.type = "button";
  rootCrumb.className = "crumb";
  rootCrumb.textContent = "/";
  rootCrumb.addEventListener("click", () => browseOutputTo("/"));
  outputBreadcrumbs.appendChild(rootCrumb);

  for (const segment of segments) {
    accumulated += `/${segment}`;
    const sep = document.createElement("span");
    sep.className = "crumb-sep";
    sep.textContent = "\u203a";
    outputBreadcrumbs.appendChild(sep);

    const crumb = document.createElement("button");
    crumb.type = "button";
    crumb.className = "crumb";
    crumb.textContent = segment;
    const target = accumulated;
    crumb.addEventListener("click", () => browseOutputTo(target));
    outputBreadcrumbs.appendChild(crumb);
  }
}

// Clicking a folder navigates into it -- the same convention the main file
// browser already uses (renderEntries() above). "Select Folder" always picks
// whichever folder is currently being displayed (outputCurrentPath), so
// choosing a destination is just "browse to it, then confirm", with no
// separate highlight-a-row-without-entering-it state to reconcile.
function renderOutputEntries(folders) {
  // Built off-DOM in a fragment
  const fragment = document.createDocumentFragment();

  for (const name of folders) {
    const fullPath = joinPath(outputCurrentPath, name);
    const row = document.createElement("li");
    row.className = "output-entry-row";
    row.dataset.path = fullPath;

    const nameSpan = document.createElement("span");
    nameSpan.className = "output-entry-name";
    const iconSpan = document.createElement("span");
    iconSpan.className = "output-entry-icon";
    iconSpan.setAttribute("aria-hidden", "true");
    iconSpan.textContent = "\ud83d\udcc1";
    nameSpan.appendChild(iconSpan);
    nameSpan.appendChild(document.createTextNode(` ${name}`));
    row.appendChild(nameSpan);

    row.addEventListener("click", () => browseOutputTo(fullPath));

    fragment.appendChild(row);
  }

  outputEntryList.replaceChildren(fragment);
}

async function browseOutputTo(path) {
  const url = path ? `/api/browse-output?path=${encodeURIComponent(path)}` : "/api/browse-output";
  try {
    const data = await apiGet(url);
    outputCurrentPath = data.path;
    outputCurrentParent = data.parent;
    outputUpButton.disabled = !outputCurrentParent;
    selectOutputButton.disabled = false;
    renderOutputBreadcrumbs(outputCurrentPath);
    renderOutputEntries(data.folders);
  } catch (err) {
    // Show error in output browser; outputCurrentPath deliberately keeps its
    // last successfully-browsed value, so Select Folder still targets that
    // (rather than whatever failed to load) and Up/breadcrumbs still work.
    const errorEl = document.createElement("p");
    errorEl.className = "browser-message is-error";
    errorEl.textContent = err.message || "Could not open that folder.";
    outputEntryList.replaceChildren(errorEl);
  }
}

function showOutputBrowser() {
  // Start browsing at the previously-chosen destination, or root.
  outputCurrentPath = outputPathInput.value.trim() || "/";
  outputCurrentParent = outputCurrentPath !== "/" ? outputCurrentPath.substring(0, outputCurrentPath.lastIndexOf("/")) : null;

  // Reset modal state
  outputBrowserModal.hidden = false;
  outputUpButton.disabled = !outputCurrentParent;
  selectOutputButton.disabled = true;

  // Load the current path
  browseOutputTo(outputCurrentPath);

  // Disable main UI when modal is open
  document.getElementById("breadcrumbs").style.opacity = "0.5";
  document.getElementById("entry-list").style.opacity = "0.5";
}

function hideOutputBrowser() {
  outputBrowserModal.hidden = true;

  // Re-enable main UI
  document.getElementById("breadcrumbs").style.opacity = "";
  document.getElementById("entry-list").style.opacity = "";
}

function setOutputPath(path) {
  outputPathInput.value = path;
}

scanButton.addEventListener("click", async () => {
  if (!currentPath || conversionInProgress) return;
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
  if (scanFiles.length === 0 || conversionInProgress) return;
  conversionInProgress = true;
  setBusy(true);

  try {
    for (const row of resultsRowsByPath.values()) {
      setBadgeStatus(row.querySelector(".badge"), "converting");
    }

    const force = forceCheckbox.checked;
    const outputPath = outputPathInput.value;
    const preserveStructure = preserveStructureCheckbox.checked;
    const batches = chunk(scanFiles, convertBatchSize(scanFiles.length));
    const showBar = scanFiles.length > PROGRESS_BAR_THRESHOLD;
    let done = 0;
    let failedBatches = 0;

    if (showBar) {
      convertButton.textContent = "Converting\u2026";
      showProgress(done, scanFiles.length);
    }

    for (const batch of batches) {
      if (!showBar) convertButton.textContent = `Converting ${done}/${scanFiles.length}\u2026`;
      try {
        const data = await apiPost("/api/convert", {
          paths: batch.map((f) => f.path),
          force,
          outputPath,
          preserveStructure,
          scanRoot: currentPath, // Pass the scan root for relative path calculation
        });
        applyResultsByPath(data.results, resultsRowsByPath);
      } catch (err) {
        failedBatches += 1;
        // This batch's request itself didn't complete (not an individual
        // file failing) -- mark its rows as failed rather than leaving them
        // stuck on "Converting\u2026" forever, and keep going with the rest.
        for (const file of batch) {
          const row = resultsRowsByPath.get(file.path);
          if (row) setBadgeStatus(row.querySelector(".badge"), "failed");
        }
      }
      done += batch.length;
      if (showBar) showProgress(done, scanFiles.length);
    }

    if (failedBatches > 0) {
      showMessage(
        `${failedBatches} of ${batches.length} batch${batches.length === 1 ? "" : "es"} did not complete and ${failedBatches === 1 ? "was" : "were"} marked failed; the rest completed normally.`,
        true
      );
    }
  } finally {
    conversionInProgress = false;
    setBusy(false);
    hideProgress();
    convertButton.textContent = `Convert ${scanFiles.length} file${scanFiles.length === 1 ? "" : "s"}`;
  }
});

upButton.addEventListener("click", () => {
  if (currentParent) browseTo(currentParent);
});

closeResultsButton.addEventListener("click", hideResults);

// Output settings event listeners
browseOutputButton.addEventListener("click", () => {
  showOutputBrowser();
});

clearOutputButton.addEventListener("click", () => {
  outputPathInput.value = "";
});

// Output browser event listeners
closeOutputBrowser.addEventListener("click", hideOutputBrowser);
cancelOutputButton.addEventListener("click", hideOutputBrowser);

outputUpButton.addEventListener("click", () => {
  if (outputCurrentParent) browseOutputTo(outputCurrentParent);
});

selectOutputButton.addEventListener("click", () => {
  if (outputCurrentPath) {
    setOutputPath(outputCurrentPath);
  }
  hideOutputBrowser();
});

// Close modal when clicking outside
outputBrowserModal.addEventListener("click", (e) => {
  if (e.target === outputBrowserModal) {
    hideOutputBrowser();
  }
});

// Handle keyboard in output browser
outputBrowserModal.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    hideOutputBrowser();
  } else if (e.key === "Enter" && !selectOutputButton.disabled) {
    selectOutputButton.click();
  }
});

browseTo();
