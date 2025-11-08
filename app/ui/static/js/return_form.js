const slipContainer = document.getElementById("t4-slips");
const slipTemplate = document.getElementById("t4-slip-template");
const addSlipButton = document.getElementById("add-slip");
const dropzone = document.getElementById("t4-slip-dropzone");
const fileInput = document.getElementById("t4-slip-file-input");
const queueList = document.getElementById("t4-file-queue");
const applyButton = document.getElementById("apply-detections");
const applyButtonGate = document.getElementById("apply-detections-gate");
const requestFrame =
  typeof window !== "undefined" && typeof window.requestAnimationFrame === "function"
    ? window.requestAnimationFrame.bind(window)
    : null;
const cancelFrame =
  typeof window !== "undefined" && typeof window.cancelAnimationFrame === "function"
    ? window.cancelAnimationFrame.bind(window)
    : null;
let pendingApplyEnableFrameId = null;

const formRoot = document.getElementById("return-form");
const stepper = formRoot?.querySelector("[data-stepper]") ?? null;
const stepButtons = stepper
  ? Array.from(stepper.querySelectorAll("button[data-step]"))
  : [];
const stepPanels = formRoot
  ? Array.from(formRoot.querySelectorAll("[data-step-panel]"))
  : [];
const currentStepField = document.getElementById("current-step-field");
const autosaveUrl = formRoot?.dataset.autosaveUrl || "";
const autosaveProfile = formRoot?.dataset.autosaveProfile || "";
const autosaveIntervalAttr = formRoot?.dataset.autosaveInterval || "";
const autosaveIntervalParsed = Number.parseInt(autosaveIntervalAttr || "", 10);
const autosaveIntervalMs = Number.isNaN(autosaveIntervalParsed)
  ? 20000
  : autosaveIntervalParsed;
const initialStep =
  formRoot?.dataset.currentStep ||
  formRoot?.dataset.initialStep ||
  stepButtons[0]?.dataset.step ||
  "identity";
let currentStep = initialStep;

const autosaveEnabled = Boolean(formRoot && autosaveUrl && autosaveProfile);
let autosaveDirty = false;
let autosavePending = false;
let autosaveTimerId;

let nextSlipIndex = 0;
let queueCounter = 0;
const fileQueue = [];
const detectionStore = new Map();
const pollTimers = new Map();
const SLIP_STATUS_POLL_INTERVAL = 2500;
const SLIP_PERSIST_VERSION = 1;
let lastPersistKey = "";

function getGlobalApi() {
  if (typeof window === "undefined") return null;
  if (!window.__returnForm) {
    window.__returnForm = {};
  }
  return window.__returnForm;
}

function getActiveProfile() {
  return formRoot?.dataset.activeProfile || "";
}

function getActiveYear() {
  return formRoot?.dataset.activeYear || "";
}

function buildSlipUploadUrl() {
  const profile = getActiveProfile();
  const year = getActiveYear();
  if (!profile || !year) {
    return "";
  }
  return `/ui/returns/${encodeURIComponent(profile)}/${encodeURIComponent(
    year,
  )}/slips/upload`;
}

function buildSlipStatusUrl(jobId) {
  const profile = getActiveProfile();
  const year = getActiveYear();
  if (!profile || !year || !jobId) {
    return "";
  }
  const base = `/ui/returns/${encodeURIComponent(profile)}/${encodeURIComponent(
    year,
  )}/slips/status`;
  const params = new URLSearchParams({ job_id: jobId });
  return `${base}?${params.toString()}`;
}

function persistStorageKey() {
  const profile = getActiveProfile();
  const year = getActiveYear();
  if (!profile || !year) {
    return "";
  }
  return `return-form:${profile}:${year}:slip-jobs:v${SLIP_PERSIST_VERSION}`;
}

function readSessionStorage(key) {
  if (!key || typeof window === "undefined") {
    return null;
  }
  try {
    return window.sessionStorage?.getItem(key) ?? null;
  } catch (error) {
    console.warn("Unable to read sessionStorage", error);
    return null;
  }
}

function writeSessionStorage(key, value) {
  if (!key || typeof window === "undefined") {
    return;
  }
  try {
    if (value === null) {
      window.sessionStorage?.removeItem(key);
    } else {
      window.sessionStorage?.setItem(key, value);
    }
  } catch (error) {
    console.warn("Unable to write sessionStorage", error);
  }
}

function updateGlobalSlipJobs(jobs) {
  const api = getGlobalApi();
  if (!api) return;
  api.slipJobs = jobs;
}

function persistQueueState() {
  if (!formRoot) return;
  const jobs = fileQueue
    .filter((entry) => Boolean(entry.jobId))
    .map((entry) => ({
      id: entry.id,
      jobId: entry.jobId,
      name: entry.name || entry.file?.name || "",
      size: entry.size ?? entry.file?.size ?? 0,
      status: entry.status,
      error: entry.error || "",
      detection: entry.detection || null,
    }));
  const serialized = JSON.stringify(jobs);
  formRoot.dataset.slipJobs = serialized;
  updateGlobalSlipJobs(jobs);
  const key = persistStorageKey();
  if (lastPersistKey && lastPersistKey !== key) {
    writeSessionStorage(lastPersistKey, null);
  }
  lastPersistKey = key;
  writeSessionStorage(key, serialized);
}

function loadPersistedJobs() {
  if (!formRoot) return [];
  const key = persistStorageKey();
  const stored = readSessionStorage(key) || formRoot.dataset.slipJobs || "";
  if (!stored) {
    const api = getGlobalApi();
    if (api?.slipJobs && Array.isArray(api.slipJobs)) {
      return api.slipJobs;
    }
    return [];
  }
  try {
    const parsed = JSON.parse(stored);
    if (Array.isArray(parsed)) {
      return parsed;
    }
  } catch (error) {
    console.warn("Unable to parse persisted slip jobs", error);
  }
  return [];
}

function cancelStatusPoll(entryId) {
  const timer = pollTimers.get(entryId);
  if (typeof timer === "number") {
    clearTimeout(timer);
  }
  pollTimers.delete(entryId);
}

function scheduleStatusPoll(entry, delay = SLIP_STATUS_POLL_INTERVAL) {
  cancelStatusPoll(entry.id);
  if (typeof window === "undefined") return;
  const timer = window.setTimeout(() => {
    void pollJobStatus(entry);
  }, delay);
  pollTimers.set(entry.id, timer);
}
const scheduleMicrotask =
  typeof queueMicrotask === "function"
    ? queueMicrotask
    : (callback) => {
        setTimeout(callback, 0);
      };

function syncExistingSlips() {
  if (!slipContainer) return;
  document.querySelectorAll(".t4-slip").forEach((node) => {
    const idx = Number.parseInt(node.dataset.slipIndex || "0", 10);
    if (!Number.isNaN(idx) && idx >= nextSlipIndex) {
      nextSlipIndex = idx + 1;
    }
    const numberSpan = node.querySelector(".slip-number");
    if (numberSpan) {
      numberSpan.textContent = idx + 1;
    }
  });
  updateRemoveButtons();
}

function addSlip(index = nextSlipIndex++) {
  if (!slipTemplate || !slipContainer) return null;
  const clone = slipTemplate.content.cloneNode(true);
  clone.querySelectorAll("[name]").forEach((input) => {
    const name = input.getAttribute("name");
    if (!name) return;
    input.setAttribute("name", name.replace(/__index__/g, String(index)));
  });
  const wrapper = clone.querySelector(".t4-slip");
  if (wrapper) {
    wrapper.dataset.slipIndex = String(index);
    const numberSpan = wrapper.querySelector(".slip-number");
    if (numberSpan) {
      numberSpan.textContent = index + 1;
    }
  }
  slipContainer.appendChild(clone);
  updateRemoveButtons();
  return wrapper instanceof HTMLElement ? wrapper : null;
}

function updateRemoveButtons() {
  if (!slipContainer) return;
  const slips = slipContainer.querySelectorAll(".t4-slip");
  const disable = slips.length === 1;
  slips.forEach((wrapper) => {
    const button = wrapper.querySelector(".remove-slip");
    if (button) {
      button.disabled = disable;
    }
    const numberSpan = wrapper.querySelector(".slip-number");
    if (numberSpan) {
      const idx = Number.parseInt(wrapper.dataset.slipIndex || "0", 10);
      numberSpan.textContent = idx + 1;
    }
  });
}

function handleSlipRemove(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (!target.classList.contains("remove-slip")) return;
  const wrapper = target.closest(".t4-slip");
  if (!wrapper || !slipContainer) return;
  if (slipContainer.querySelectorAll(".t4-slip").length === 1) return;
  wrapper.remove();
  updateRemoveButtons();
}

function renderQueue() {
  if (!queueList) return;
  queueList.innerHTML = "";
  if (fileQueue.length === 0) {
    queueList.hidden = true;
    queueList.setAttribute("data-empty", "true");
    return;
  }
  queueList.hidden = false;
  queueList.removeAttribute("data-empty");
  const fragment = document.createDocumentFragment();
  fileQueue.forEach((entry, index) => {
    const item = document.createElement("li");
    item.dataset.entryId = entry.id;
    const meta = document.createElement("div");
    meta.className = "file-meta";
    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent =
      entry.file?.name || entry.name || entry.detection?.original_filename || "Slip";
    const size = document.createElement("span");
    size.className = "file-size";
    const rawSize =
      entry.file?.size ??
      (typeof entry.size === "number" ? entry.size : null) ??
      entry.detection?.size ??
      null;
    size.textContent = formatSize(rawSize);
    const status = document.createElement("span");
    status.className = `file-status ${entry.status}`;
    status.textContent = statusText(entry);
    meta.append(name, size, status);

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "btn danger file-remove";
    removeButton.dataset.entryId = entry.id;
    const labelName =
      entry.file?.name || entry.name || entry.detection?.original_filename || "slip";
    removeButton.setAttribute("aria-label", `Remove ${labelName}`);
    removeButton.textContent = "Remove";
    removeButton.addEventListener("click", () => {
      removeQueuedFile(entry.id, { preferredIndex: index });
    });

    item.append(meta, removeButton);
    fragment.appendChild(item);
  });
  queueList.appendChild(fragment);
}

function formatSize(size) {
  if (typeof size !== "number" || Number.isNaN(size) || size < 0) {
    return "-";
  }
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function statusText(entry) {
  if (entry.status === "error") {
    return entry.error || "Unable to read file";
  }
  if (entry.status === "applied") {
    return "Applied to form";
  }
  if (entry.status === "ready") {
    return "Ready to apply";
  }
  if (entry.status === "processing") {
    return "Processing…";
  }
  return "Queued";
}

function applyJobStatus(entry, payload) {
  if (!payload || typeof payload !== "object") {
    return;
  }
  if (payload.job_id) {
    entry.jobId = payload.job_id;
  }
  const status = payload.status;
  if (status === "complete") {
    if (payload.detection) {
      entry.status = "ready";
      entry.error = "";
      entry.detection = payload.detection;
      entry.name = entry.name || payload.detection.original_filename || entry.name;
      if (typeof payload.detection.size === "number") {
        entry.size = payload.detection.size;
      }
      detectionStore.set(entry.id, payload.detection);
      return;
    }
    entry.status = "error";
    entry.error = "Slip processing completed without a detection";
    entry.detection = null;
    detectionStore.delete(entry.id);
    return;
  }
  if (status === "error") {
    entry.status = "error";
    entry.error = payload.error || "Unable to process slip";
    entry.detection = null;
    detectionStore.delete(entry.id);
    return;
  }
  entry.status = "processing";
  entry.error = "";
  entry.detection = null;
  detectionStore.delete(entry.id);
}

async function pollJobStatus(entry) {
  if (!entry || !entry.jobId) {
    return;
  }
  if (!fileQueue.some((item) => item.id === entry.id)) {
    cancelStatusPoll(entry.id);
    return;
  }
  const statusUrl = buildSlipStatusUrl(entry.jobId);
  if (!statusUrl) {
    entry.status = "error";
    entry.error = "Select a profile and tax year before uploading";
    entry.detection = null;
    detectionStore.delete(entry.id);
    renderQueue();
    updateApplyState();
    persistQueueState();
    return;
  }
  try {
    const response = await fetch(statusUrl, { method: "GET" });
    let data = null;
    try {
      data = await response.json();
    } catch (parseError) {
      throw new Error("Invalid status response");
    }
    if (!response.ok) {
      const detail = data?.detail || `Status check failed (${response.status})`;
      throw new Error(detail);
    }
    if (!data || typeof data !== "object") {
      throw new Error("Invalid status response");
    }
    applyJobStatus(entry, data);
    renderQueue();
    updateApplyState();
    persistQueueState();
    if (entry.status === "processing") {
      scheduleStatusPoll(entry);
    } else {
      cancelStatusPoll(entry.id);
    }
  } catch (error) {
    cancelStatusPoll(entry.id);
    entry.status = "error";
    entry.error =
      error instanceof Error ? error.message : "Unable to fetch slip status";
    entry.detection = null;
    detectionStore.delete(entry.id);
    renderQueue();
    updateApplyState();
    persistQueueState();
  }
}

async function stageFile(entry) {
  entry.status = "processing";
  entry.error = "";
  renderQueue();
  if (!entry.file) {
    entry.status = "error";
    entry.error = "File data is unavailable";
    entry.detection = null;
    detectionStore.delete(entry.id);
    renderQueue();
    updateApplyState();
    persistQueueState();
    return;
  }
  const uploadUrl = buildSlipUploadUrl();
  if (!uploadUrl) {
    entry.status = "error";
    entry.error = "Select a profile and tax year before uploading";
    entry.detection = null;
    detectionStore.delete(entry.id);
    renderQueue();
    updateApplyState();
    persistQueueState();
    return;
  }
  const formData = new FormData();
  formData.append("upload", entry.file);
  try {
    const response = await fetch(uploadUrl, {
      method: "POST",
      body: formData,
    });
    let data = null;
    try {
      data = await response.json();
    } catch (parseError) {
      throw new Error("Invalid upload response");
    }
    if (!response.ok) {
      const detail = data?.detail || `Upload failed (${response.status})`;
      throw new Error(detail);
    }
    if (!data || typeof data !== "object" || !data.job_id) {
      throw new Error("Upload did not return a job identifier");
    }
    applyJobStatus(entry, data);
    renderQueue();
    updateApplyState();
    persistQueueState();
    if (entry.status === "processing") {
      scheduleStatusPoll(entry);
    } else {
      cancelStatusPoll(entry.id);
    }
  } catch (error) {
    cancelStatusPoll(entry.id);
    console.error("Unable to stage slip file", error);
    entry.status = "error";
    entry.error =
      error instanceof Error ? error.message : "Unable to process slip";
    entry.detection = null;
    detectionStore.delete(entry.id);
    renderQueue();
    updateApplyState();
    persistQueueState();
  }
}

function setApplyElementsEnabled(enabled) {
  if (applyButtonGate) {
    applyButtonGate.disabled = !enabled;
  }
  if (applyButton) {
    applyButton.disabled = !enabled;
    const shouldBeAriaDisabled = !enabled || (applyButtonGate?.disabled ?? false);
    applyButton.setAttribute("aria-disabled", String(shouldBeAriaDisabled));
  }
}

function updateApplyState() {
  if (pendingApplyEnableFrameId !== null && cancelFrame) {
    cancelFrame(pendingApplyEnableFrameId);
    pendingApplyEnableFrameId = null;
  }
  const hasDetections = detectionStore.size > 0;
  if (!hasDetections) {
    setApplyElementsEnabled(false);
    return;
  }
  if (requestFrame) {
    pendingApplyEnableFrameId = requestFrame(() => {
      pendingApplyEnableFrameId = null;
      const stillHasDetections = detectionStore.size > 0;
      setApplyElementsEnabled(stillHasDetections);
    });
    return;
  }
  setApplyElementsEnabled(true);
}

function restoreQueueFromPersistence() {
  const persisted = loadPersistedJobs();
  if (!Array.isArray(persisted) || persisted.length === 0) {
    persistQueueState();
    return;
  }
  let highestCounter = queueCounter;
  const entriesToPoll = [];
  persisted.forEach((item) => {
    if (!item || typeof item !== "object" || !item.jobId) {
      return;
    }
    let entryId = typeof item.id === "string" && item.id ? item.id : "";
    if (!entryId) {
      highestCounter += 1;
      entryId = `file-${highestCounter}`;
    } else {
      const match = entryId.match(/file-(\d+)/);
      if (match) {
        const value = Number.parseInt(match[1] || "", 10);
        if (!Number.isNaN(value)) {
          highestCounter = Math.max(highestCounter, value);
        }
      }
    }
    const fallbackName =
      item.name || item.detection?.original_filename || item.jobId;
    const storedSize =
      typeof item.size === "number"
        ? item.size
        : typeof item.detection?.size === "number"
          ? item.detection.size
          : 0;
    const entry = {
      id: entryId,
      key: `${fallbackName}:${storedSize}`,
      file: null,
      name: fallbackName,
      size: storedSize,
      status: item.status || "processing",
      jobId: item.jobId,
      detection: item.detection || null,
      error: item.error || "",
    };
    if (entry.detection) {
      entry.status = "ready";
      detectionStore.set(entry.id, entry.detection);
    } else if (entry.status !== "error") {
      entry.status = "processing";
      entriesToPoll.push(entry);
    }
    fileQueue.push(entry);
  });
  queueCounter = Math.max(queueCounter, highestCounter);
  persistQueueState();
  entriesToPoll.forEach((entry) => {
    void pollJobStatus(entry);
  });
}

function addFiles(files) {
  const incoming = Array.from(files || []);
  incoming.forEach((file) => {
    const dedupeKey = `${file.name}:${file.size}`;
    if (fileQueue.some((entry) => entry.key === dedupeKey)) {
      return;
    }
    const entry = {
      id: `file-${++queueCounter}`,
      key: dedupeKey,
      file,
      name: file.name,
      size: file.size,
      status: "queued",
      detection: null,
      error: "",
      jobId: null,
    };
    fileQueue.push(entry);
    renderQueue();
    void stageFile(entry);
  });
  updateApplyState();
}

function clearDragState(event) {
  if (!dropzone) return;
  if (event?.type === "dragleave" && event.relatedTarget instanceof Node) {
    if (dropzone.contains(event.relatedTarget)) {
      return;
    }
  }
  dropzone.classList.remove("is-dragover");
  dropzone.removeAttribute("aria-busy");
}

function enableDropzone() {
  if (!dropzone) return;
  dropzone.addEventListener("click", () => {
    fileInput?.click();
  });
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInput?.click();
    }
  });
  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragover");
      dropzone.setAttribute("aria-busy", "true");
    });
  });
  ["dragleave", "dragend"].forEach((eventName) => {
    dropzone.addEventListener(eventName, clearDragState);
  });
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    const files = event.dataTransfer?.files;
    if (files) {
      addFiles(files);
    }
    if (fileInput) {
      fileInput.value = "";
    }
    clearDragState();
  });
}

function focusQueue(preferredIndex = 0) {
  if (!queueList) return;
  const buttons = queueList.querySelectorAll(".file-remove");
  if (buttons.length === 0) {
    dropzone?.focus();
    return;
  }
  const index = Math.max(0, Math.min(preferredIndex, buttons.length - 1));
  const button = buttons[index];
  if (button instanceof HTMLElement) {
    button.focus();
  }
}

function removeQueuedFile(entryId, options = {}) {
  const index = fileQueue.findIndex((entry) => entry.id === entryId);
  if (index === -1) return;
  const [entry] = fileQueue.splice(index, 1);
  cancelStatusPoll(entryId);
  detectionStore.delete(entryId);
  renderQueue();
  updateApplyState();
  persistQueueState();
  const preferredIndex =
    typeof options.preferredIndex === "number" ? options.preferredIndex : index;
  scheduleMicrotask(() => focusQueue(preferredIndex));
}

function markDetectionsApplied(detectionIds) {
  if (!Array.isArray(detectionIds) || detectionIds.length === 0) {
    return;
  }
  const applied = new Set(detectionIds.filter((value) => typeof value === "string" && value));
  if (applied.size === 0) {
    return;
  }
  let mutated = false;
  fileQueue.forEach((entry) => {
    if (!entry || !entry.detection) {
      return;
    }
    if (!applied.has(entry.detection.id)) {
      return;
    }
    entry.status = "applied";
    entry.error = "";
    entry.detection = null;
    detectionStore.delete(entry.id);
    mutated = true;
  });
  if (mutated) {
    renderQueue();
    updateApplyState();
    persistQueueState();
  }
}

function applyDetections() {
  if (!applyButton || applyButton.disabled) return;
  const payload = fileQueue
    .map((entry) => detectionStore.get(entry.id))
    .filter(Boolean);
  const event = new CustomEvent("t4-detections-apply", {
    bubbles: true,
    detail: { detections: payload },
  });
  applyButton.dispatchEvent(event);
}

function registerEvents() {
  if (addSlipButton) {
    addSlipButton.addEventListener("click", () => {
      addSlip();
    });
  }
  if (slipContainer) {
    slipContainer.addEventListener("click", handleSlipRemove);
  }
  enableDropzone();
  if (fileInput) {
    fileInput.addEventListener("change", (event) => {
      const target = event.target;
      if (target instanceof HTMLInputElement && target.files) {
        addFiles(target.files);
        target.value = "";
      }
    });
  }
  if (applyButton) {
    applyButton.addEventListener("click", applyDetections);
  }
  if (formRoot) {
    const taxYearField = formRoot.querySelector('input[name="tax_year"]');
    if (taxYearField instanceof HTMLInputElement) {
      const syncYear = () => {
        if (!formRoot) return;
        formRoot.dataset.activeYear = (taxYearField.value || "").trim();
        persistQueueState();
      };
      taxYearField.addEventListener("input", syncYear);
      taxYearField.addEventListener("change", syncYear);
    }
  }
}

function init() {
  restoreQueueFromPersistence();
  syncExistingSlips();
  renderQueue();
  updateApplyState();
  registerEvents();
}

function normalizedStep(step) {
  if (stepButtons.length === 0) {
    return "identity";
  }
  if (typeof step === "string" && step) {
    const match = stepButtons.find((button) => button.dataset.step === step);
    if (match?.dataset.step) {
      return match.dataset.step;
    }
  }
  return stepButtons[0]?.dataset.step || "identity";
}

function setStepperState(step, options = {}) {
  if (!formRoot || stepButtons.length === 0 || stepPanels.length === 0) {
    return;
  }
  const normalized = normalizedStep(step);
  currentStep = normalized;
  formRoot.dataset.currentStep = normalized;
  if (currentStepField) {
    currentStepField.value = normalized;
  }
  stepButtons.forEach((button) => {
    const isActive = button.dataset.step === normalized;
    button.setAttribute("aria-selected", String(isActive));
    button.tabIndex = isActive ? 0 : -1;
    if (isActive && options.focus) {
      button.focus();
    }
  });
  stepPanels.forEach((panel) => {
    panel.hidden = panel.dataset.stepPanel !== normalized;
  });
  const event = new CustomEvent("return-form-stepchange", {
    bubbles: true,
    detail: { step: normalized },
  });
  formRoot.dispatchEvent(event);
  if (options.updateUrl && typeof window !== "undefined") {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("step", normalized);
      window.history.replaceState({ step: normalized }, "", url);
    } catch (error) {
      console.warn("Unable to update step URL", error);
    }
  }
}

function stepIndex(value) {
  return stepButtons.findIndex((button) => button.dataset.step === value);
}

function handleStepperClick(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (!target.matches("button[data-step]")) return;
  const step = target.dataset.step;
  if (!step) return;
  setStepperState(step, { focus: false, updateUrl: true });
}

function handleStepperKeydown(event) {
  if (!stepButtons.length) return;
  const key = event.key;
  const horizontal = ["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown"].includes(key);
  const positional = key === "Home" || key === "End";
  if (!horizontal && !positional) {
    return;
  }
  event.preventDefault();
  let index = stepIndex(currentStep);
  if (index === -1) {
    index = 0;
  }
  if (key === "ArrowRight" || key === "ArrowDown") {
    index = (index + 1) % stepButtons.length;
  } else if (key === "ArrowLeft" || key === "ArrowUp") {
    index = (index - 1 + stepButtons.length) % stepButtons.length;
  } else if (key === "Home") {
    index = 0;
  } else if (key === "End") {
    index = stepButtons.length - 1;
  }
  const step = stepButtons[index]?.dataset.step;
  if (step) {
    setStepperState(step, { focus: true, updateUrl: true });
  }
}

function setupStepper() {
  if (!formRoot || !stepper || stepButtons.length === 0) {
    return;
  }
  stepper.addEventListener("click", handleStepperClick);
  stepper.addEventListener("keydown", handleStepperKeydown);
  if (typeof window !== "undefined") {
    window.addEventListener("popstate", (event) => {
      const stateStep = event.state?.step;
      let nextStep = typeof stateStep === "string" ? stateStep : null;
      if (!nextStep) {
        try {
          const url = new URL(window.location.href);
          nextStep = url.searchParams.get("step");
        } catch (error) {
          nextStep = null;
        }
      }
      setStepperState(nextStep, { focus: false, updateUrl: false });
    });
  }
  let initial = currentStep;
  if (typeof window !== "undefined") {
    try {
      const url = new URL(window.location.href);
      const queryStep = url.searchParams.get("step");
      if (queryStep) {
        initial = queryStep;
      }
    } catch (error) {
      // Ignore malformed URLs
    }
  }
  setStepperState(initial, { focus: false, updateUrl: false });
}

function markAutosaveDirty() {
  if (!autosaveEnabled) return;
  autosaveDirty = true;
}

async function performAutosave() {
  if (!autosaveEnabled) return;
  if (!autosaveDirty || autosavePending) {
    scheduleAutosave();
    return;
  }
  const api = typeof window !== "undefined" ? window.__returnForm : null;
  if (!api || typeof api.collectFormState !== "function") {
    scheduleAutosave();
    return;
  }
  const payload = {
    profile: autosaveProfile,
    step: currentStep,
    state: api.collectFormState(),
  };
  autosavePending = true;
  try {
    const response = await fetch(autosaveUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(`Autosave failed: ${response.status}`);
    }
    autosaveDirty = false;
  } catch (error) {
    console.warn("Autosave error", error);
  } finally {
    autosavePending = false;
    scheduleAutosave();
  }
}

function scheduleAutosave() {
  if (!autosaveEnabled) return;
  if (autosaveTimerId) {
    clearTimeout(autosaveTimerId);
  }
  autosaveTimerId = setTimeout(() => {
    void performAutosave();
  }, autosaveIntervalMs);
}

function flushAutosave() {
  if (!autosaveEnabled || !autosaveDirty) return;
  const api = typeof window !== "undefined" ? window.__returnForm : null;
  if (!api || typeof api.collectFormState !== "function") {
    return;
  }
  const payload = {
    profile: autosaveProfile,
    step: currentStep,
    state: api.collectFormState(),
  };
  if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    const blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
    navigator.sendBeacon(autosaveUrl, blob);
    autosaveDirty = false;
  }
}

function setupAutosave() {
  if (!autosaveEnabled || !formRoot) {
    return;
  }
  const markAndSchedule = () => {
    markAutosaveDirty();
    scheduleAutosave();
  };
  formRoot.addEventListener("input", markAndSchedule, true);
  formRoot.addEventListener("change", markAndSchedule, true);
  formRoot.addEventListener("return-form-stepchange", markAndSchedule);
  formRoot.addEventListener("submit", () => {
    markAutosaveDirty();
    flushAutosave();
  });
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        void performAutosave();
      }
    });
  }
  if (typeof window !== "undefined") {
    window.addEventListener("beforeunload", () => {
      flushAutosave();
    });
  }
  scheduleAutosave();
}

init();
setupStepper();
setupAutosave();

const globalApi = getGlobalApi();
if (globalApi) {
  Object.assign(globalApi, {
    addSlip,
    syncSlips: syncExistingSlips,
    markDetectionsApplied,
  });
}

export { removeQueuedFile, focusQueue, applyDetections };
