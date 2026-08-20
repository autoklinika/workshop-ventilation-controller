"use strict";

/*
 * History H4: custom date range + read-only CM5 storage warning presentation.
 *
 * The browser only sends explicit ISO start/end timestamps for a custom range.
 * HistorySeriesService remains the sole owner of resolution selection and point data.
 */

const HISTORY_H4_MAX_CUSTOM_DAYS = 1825;
historyClient.customStart = null;
historyClient.customEnd = null;

const historyH4BasePost = historyPost;
historyPost = function historyH4Post(path, body) {
  if (
    path === "/api/v1/history/series/query" &&
    body &&
    body.range === "custom"
  ) {
    if (!historyClient.customStart || !historyClient.customEnd) {
      return Promise.reject(new Error("Nie wybrano własnego zakresu czasu"));
    }
    const request = { ...body };
    delete request.range;
    request.start_at = historyClient.customStart;
    request.end_at = historyClient.customEnd;
    return historyH4BasePost(path, request);
  }
  return historyH4BasePost(path, body);
};

const historyH4BaseRangeLabel = historyRangeLabel;
historyRangeLabel = function historyH4RangeLabel(rangeId) {
  if (rangeId === "custom") return "WŁASNY ZAKRES";
  return historyH4BaseRangeLabel(rangeId);
};

function historyH4LocalInputValue(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function historyH4EnsureCustomDialog() {
  let overlay = document.getElementById("historyCustomRangeDialog");
  if (overlay) return overlay;

  overlay = document.createElement("div");
  overlay.id = "historyCustomRangeDialog";
  overlay.className = "v2-history-custom-overlay";
  overlay.hidden = true;
  overlay.innerHTML = `
    <section class="v2-history-custom-panel" role="dialog" aria-modal="true" aria-labelledby="historyCustomRangeTitle">
      <header class="v2-history-custom-head">
        <div>
          <span>HISTORIA</span>
          <h2 id="historyCustomRangeTitle">Własny zakres czasu</h2>
        </div>
        <button type="button" class="v2-history-custom-close" data-history-custom-close aria-label="Zamknij">×</button>
      </header>
      <div class="v2-history-custom-fields">
        <label>
          <span>OD</span>
          <input id="historyCustomFrom" type="datetime-local" step="60">
        </label>
        <label>
          <span>DO</span>
          <input id="historyCustomTo" type="datetime-local" step="60">
        </label>
      </div>
      <p class="v2-history-custom-note">Maksymalny zakres: 5 lat. Backend automatycznie dobiera zapis RAW / 1 min / 15 min / 1 h / 1 dzień.</p>
      <div id="historyCustomError" class="v2-history-custom-error" hidden></div>
      <footer class="v2-history-custom-actions">
        <button type="button" class="v2-history-custom-secondary" data-history-custom-close>ANULUJ</button>
        <button type="button" class="v2-history-custom-primary" id="historyCustomApply">POKAŻ</button>
      </footer>
    </section>`;

  document.body.appendChild(overlay);

  overlay.querySelectorAll("[data-history-custom-close]").forEach((button) => {
    button.addEventListener("click", () => historyH4CloseCustomDialog());
  });
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) historyH4CloseCustomDialog();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !overlay.hidden) historyH4CloseCustomDialog();
  });

  const apply = overlay.querySelector("#historyCustomApply");
  if (apply) apply.addEventListener("click", historyH4ApplyCustomRange);
  return overlay;
}

function historyH4OpenCustomDialog() {
  const overlay = historyH4EnsureCustomDialog();
  const from = overlay.querySelector("#historyCustomFrom");
  const to = overlay.querySelector("#historyCustomTo");
  const error = overlay.querySelector("#historyCustomError");
  const now = new Date();
  const defaultEnd = historyClient.customEnd ? new Date(historyClient.customEnd) : now;
  const defaultStart = historyClient.customStart
    ? new Date(historyClient.customStart)
    : new Date(defaultEnd.getTime() - 30 * 24 * 60 * 60 * 1000);

  if (from) from.value = historyH4LocalInputValue(defaultStart);
  if (to) {
    to.value = historyH4LocalInputValue(defaultEnd);
    to.max = historyH4LocalInputValue(now);
  }
  if (error) {
    error.hidden = true;
    error.textContent = "";
  }
  overlay.hidden = false;
  document.body.classList.add("v2-history-custom-open");
  window.setTimeout(() => from && from.focus(), 0);
}

function historyH4CloseCustomDialog() {
  const overlay = document.getElementById("historyCustomRangeDialog");
  if (overlay) overlay.hidden = true;
  document.body.classList.remove("v2-history-custom-open");
}

function historyH4CustomError(message) {
  const error = document.getElementById("historyCustomError");
  if (!error) return;
  error.textContent = message;
  error.hidden = false;
}

function historyH4ApplyCustomRange() {
  const from = document.getElementById("historyCustomFrom");
  const to = document.getElementById("historyCustomTo");
  if (!from || !to || !from.value || !to.value) {
    historyH4CustomError("Wybierz datę i godzinę OD oraz DO.");
    return;
  }

  const start = new Date(from.value);
  const end = new Date(to.value);
  const now = new Date();
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime())) {
    historyH4CustomError("Nieprawidłowa data lub godzina.");
    return;
  }
  if (start >= end) {
    historyH4CustomError("Data OD musi być wcześniejsza niż data DO.");
    return;
  }
  if (end > now) {
    historyH4CustomError("Data DO nie może być w przyszłości.");
    return;
  }

  const spanDays = (end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000);
  if (spanDays > HISTORY_H4_MAX_CUSTOM_DAYS) {
    historyH4CustomError(`Zakres może obejmować maksymalnie ${HISTORY_H4_MAX_CUSTOM_DAYS} dni (5 lat).`);
    return;
  }

  historyClient.customStart = start.toISOString();
  historyClient.customEnd = end.toISOString();
  historyClient.range = "custom";
  historyH4CloseCustomDialog();
  historyRenderRanges();
  historyLoadChart();
}

const historyH4BaseRenderRanges = historyRenderRanges;
historyRenderRanges = function historyH4RenderRanges() {
  historyH4BaseRenderRanges();
  const host = document.getElementById("historyRangeButtons");
  if (!host) return;

  const button = document.createElement("button");
  button.type = "button";
  button.className = `v2-history-btn v2-history-custom-range${historyClient.range === "custom" ? " is-active" : ""}`;
  button.dataset.historyRange = "custom";
  button.textContent = "WŁASNY ZAKRES";
  button.addEventListener("click", historyH4OpenCustomDialog);
  host.appendChild(button);
};

const historyH4BaseTimeLabel = historyTimeLabel;
historyTimeLabel = function historyH4TimeLabel(timestamp, rangeId) {
  if (rangeId !== "custom") return historyH4BaseTimeLabel(timestamp, rangeId);
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";

  const start = historyClient.customStart ? new Date(historyClient.customStart) : null;
  const end = historyClient.customEnd ? new Date(historyClient.customEnd) : null;
  const spanDays = start && end
    ? (end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000)
    : 0;

  if (spanDays <= 2) {
    return new Intl.DateTimeFormat("pl-PL", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }
  if (spanDays <= 120) {
    return new Intl.DateTimeFormat("pl-PL", {
      day: "2-digit",
      month: "2-digit",
    }).format(date);
  }
  return new Intl.DateTimeFormat("pl-PL", {
    month: "short",
    year: "2-digit",
  }).format(date);
};

function historyH4EnsureStorageAlert() {
  let alert = document.getElementById("historyStorageAlert");
  if (alert) return alert;
  const head = document.querySelector("#historyView .v2-history-head");
  if (!head) return null;
  alert = document.createElement("div");
  alert.id = "historyStorageAlert";
  alert.className = "v2-history-storage-alert";
  alert.hidden = true;
  head.insertAdjacentElement("afterend", alert);
  return alert;
}

const historyH4BaseRenderStatus = historyRenderStatus;
historyRenderStatus = function historyH4RenderStatus() {
  historyH4BaseRenderStatus();
  const status = historyClient.status;
  const storage = status && status.storage;
  const state = document.getElementById("historyStorageState");
  const info = document.getElementById("historyStorageInfo");
  const alert = historyH4EnsureStorageAlert();
  if (!storage || !Number.isFinite(Number(storage.used_percent))) {
    if (alert) alert.hidden = true;
    return;
  }

  const used = Number(storage.used_percent);
  const free = Number(storage.free_bytes);
  if (info) {
    const baseText = info.textContent || "";
    info.textContent = `${baseText} · DYSK ${used.toLocaleString("pl-PL", { maximumFractionDigits: 1 })}% · wolne ${historyFormatBytes(free)}`;
  }
  if (state) {
    state.classList.toggle("is-storage-warning", storage.level === "warning");
    state.classList.toggle("is-storage-critical", storage.level === "critical");
  }
  if (!alert) return;

  alert.classList.remove("is-warning", "is-critical");
  if (storage.level === "critical") {
    alert.classList.add("is-critical");
    alert.textContent = `PAMIĘĆ CM5 ${used.toFixed(1)}% — KRYTYCZNIE MAŁO MIEJSCA. Próg krytyczny: ${storage.critical_percent}%.`;
    alert.hidden = false;
  } else if (storage.level === "warning") {
    alert.classList.add("is-warning");
    alert.textContent = `PAMIĘĆ CM5 ${used.toFixed(1)}% — OSTRZEŻENIE. Próg ostrzegawczy: ${storage.warning_percent}%.`;
    alert.hidden = false;
  } else {
    alert.hidden = true;
    alert.textContent = "";
  }
};
