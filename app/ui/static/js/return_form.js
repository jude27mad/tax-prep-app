const slipContainer = document.getElementById("t4-slips");
const slipTemplate = document.getElementById("t4-slip-template");
const addSlipButton = document.getElementById("add-slip");
const dropzone = document.getElementById("t4-slip-dropzone");
const fileInput = document.getElementById("t4-slip-file-input");
const queueList = document.getElementById("t4-file-queue");
const applyButton = document.getElementById("apply-detections");

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
  if (!slipTemplate || !slipContainer) return;
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
    name.textContent = entry.file.name;
    const size = document.createElement("span");
    size.className = "file-size";
    size.textContent = formatSize(entry.file.size);
    const status = document.createElement("span");
    status.className = `file-status ${entry.status}`;
    status.textContent = statusText(entry);
    meta.append(name, size, status);

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "btn danger file-remove";
    removeButton.dataset.entryId = entry.id;
    removeButton.setAttribute("aria-label", `Remove ${entry.file.name}`);
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
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function statusText(entry) {
  if (entry.status === "error") {
    return entry.error || "Unable to read file";
  }
  if (entry.status === "ready") {
    return "Ready to apply";
  }
  if (entry.status === "processing") {
    return "Processing…";
  }
  return "Queued";
}

function stageFile(entry) {
  entry.status = "processing";
  entry.error = "";
  renderQueue();
  entry.file
    .text()
    .then((text) => {
      entry.status = "ready";
      entry.detection = {
        id: entry.id,
        name: entry.file.name,
        size: entry.file.size,
        preview: text.slice(0, 2000),
      };
      detectionStore.set(entry.id, entry.detection);
      renderQueue();
      updateApplyState();
    })
    .catch((error) => {
      console.error("Unable to stage slip file", error);
      entry.status = "error";
      entry.error = "Unable to read file";
      entry.detection = null;
      detectionStore.delete(entry.id);
      renderQueue();
      updateApplyState();
    });
}

function updateApplyState() {
  if (!applyButton) return;
  const hasDetections = detectionStore.size > 0;
  applyButton.disabled = !hasDetections;
  applyButton.setAttribute("aria-disabled", String(!hasDetections));
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
      status: "queued",
      detection: null,
      error: "",
    };
    fileQueue.push(entry);
    renderQueue();
    stageFile(entry);
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
  fileQueue.splice(index, 1);
  detectionStore.delete(entryId);
  renderQueue();
  updateApplyState();
  const preferredIndex =
    typeof options.preferredIndex === "number" ? options.preferredIndex : index;
  scheduleMicrotask(() => focusQueue(preferredIndex));
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
}

function init() {
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

export { removeQueuedFile, focusQueue, applyDetections };
