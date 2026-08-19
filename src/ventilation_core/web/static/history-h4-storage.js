"use strict";

/* Global read-only storage monitor. Backend owns warning/critical classification. */

const HISTORY_H4_STORAGE_POLL_MS = 60000;

function historyH4EnsureGlobalStorageAlert() {
  let alert = document.getElementById("historyGlobalStorageAlert");
  if (alert) return alert;
  alert = document.createElement("button");
  alert.type = "button";
  alert.id = "historyGlobalStorageAlert";
  alert.className = "v2-history-global-storage-alert";
  alert.hidden = true;
  alert.setAttribute("aria-live", "polite");
  alert.addEventListener("click", () => historySetView(true));
  document.body.appendChild(alert);
  return alert;
}

function historyH4RenderGlobalStorageAlert(status) {
  const alert = historyH4EnsureGlobalStorageAlert();
  const storage = status && status.storage;
  if (!storage || !["warning", "critical"].includes(storage.level)) {
    alert.hidden = true;
    alert.textContent = "";
    alert.classList.remove("is-warning", "is-critical");
    return;
  }

  const used = Number(storage.used_percent);
  alert.classList.toggle("is-warning", storage.level === "warning");
  alert.classList.toggle("is-critical", storage.level === "critical");
  alert.textContent = storage.level === "critical"
    ? `PAMIĘĆ CM5 ${used.toFixed(1)}% · KRYTYCZNE`
    : `PAMIĘĆ CM5 ${used.toFixed(1)}% · OSTRZEŻENIE`;
  alert.hidden = false;
}

async function historyH4StorageMonitorTick() {
  try {
    const payload = await historyRequest("/api/v1/history/status");
    historyH4RenderGlobalStorageAlert(payload.history || null);
  } catch (_error) {
    const alert = document.getElementById("historyGlobalStorageAlert");
    if (alert) alert.hidden = true;
  }
}

window.setTimeout(historyH4StorageMonitorTick, 1500);
window.setInterval(historyH4StorageMonitorTick, HISTORY_H4_STORAGE_POLL_MS);
