"use strict";

const ALERT_POLL_MS = 2000;
const coreAlertUi = {
  activeCount: document.getElementById("alertsActiveCount"),
  unackCount: document.getElementById("alertsUnackCount"),
  historyCount: document.getElementById("alertsHistoryCount"),
  connection: document.getElementById("alertsConnectionStatus"),
  activeList: document.getElementById("alertsActiveList"),
  historyBody: document.getElementById("alertsHistoryBody"),
};

let coreAlertSnapshot = { active: [], history: [] };
let alertAckInFlight = false;

function formatAlertTime(value) {
  if (typeof value !== "string" || !value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pl-PL", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function alertSeverityLabel(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "critical") return "KRYTYCZNY";
  if (normalized === "warning") return "OSTRZEŻENIE";
  return normalized ? normalized.toUpperCase() : "ALERT";
}

function alertSeverityClass(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "critical") return "critical";
  if (normalized === "warning") return "warning";
  return "info";
}

function ensureCoreAlertModal() {
  let overlay = document.getElementById("globalSystemAlert");
  if (overlay) return overlay;

  overlay = document.createElement("div");
  overlay.id = "globalSystemAlert";
  overlay.className = "v2-system-alert";
  overlay.hidden = true;
  overlay.setAttribute("role", "alertdialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", "globalSystemAlertTitle");
  overlay.setAttribute("aria-describedby", "globalSystemAlertDescription");
  overlay.innerHTML = `
    <section class="v2-system-alert-card">
      <div class="v2-system-alert-head">
        <span class="v2-system-alert-icon" aria-hidden="true">!</span>
        <div>
          <span class="v2-system-alert-kicker">ALARM</span>
          <h2 id="globalSystemAlertTitle">BŁĄD SYSTEMU</h2>
        </div>
      </div>
      <p id="globalSystemAlertDescription" class="v2-system-alert-description">ventilation-core zgłosił problem wymagający uwagi operatora.</p>
      <ul id="globalSystemAlertList" class="v2-system-alert-list"></ul>
      <p id="globalSystemAlertNote" class="v2-system-alert-note">Potwierdzenie zostanie zapisane przez ventilation-core.</p>
      <button id="globalSystemAlertOk" class="v2-system-alert-ok" type="button">OK</button>
    </section>`;
  document.body.appendChild(overlay);

  document.getElementById("globalSystemAlertOk").addEventListener("click", acknowledgeModalAlerts);
  document.addEventListener("keydown", (event) => {
    if (!overlay.hidden && event.key === "Escape") {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  });
  return overlay;
}

function renderCoreAlertModal(active) {
  const overlay = ensureCoreAlertModal();
  const pending = active.filter((alert) => alert && alert.active === true && alert.acknowledged !== true);
  if (pending.length === 0) {
    overlay.hidden = true;
    return;
  }

  const list = document.getElementById("globalSystemAlertList");
  list.replaceChildren();
  pending.forEach((alert) => {
    const row = document.createElement("li");
    const message = alert.message || alert.code || "Alert systemowy";
    const detail = typeof alert.detail === "string" && alert.detail.trim() ? ` · ${alert.detail.trim()}` : "";
    row.textContent = `${message}${detail}`;
    list.appendChild(row);
  });

  document.getElementById("globalSystemAlertNote").textContent = "Kliknięcie OK zapisze potwierdzenie tych alertów w ventilation-core.";
  const button = document.getElementById("globalSystemAlertOk");
  button.disabled = alertAckInFlight;
  button.textContent = alertAckInFlight ? "POTWIERDZANIE…" : "OK";
  const wasHidden = overlay.hidden;
  overlay.hidden = false;
  if (wasHidden) button.focus({ preventScroll: true });
}

async function acknowledgeAlert(alertId) {
  const response = await fetch("/api/v1/alerts/ack", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ alert_id: alertId }),
  });
  const payload = await response.json();
  if (!response.ok || payload.ok !== true) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function acknowledgeModalAlerts() {
  if (alertAckInFlight) return;
  const pending = coreAlertSnapshot.active.filter(
    (alert) => alert && alert.active === true && alert.acknowledged !== true && Number.isInteger(alert.alert_id),
  );
  if (pending.length === 0) return;

  alertAckInFlight = true;
  renderCoreAlertModal(coreAlertSnapshot.active);
  try {
    for (const alert of pending) await acknowledgeAlert(alert.alert_id);
    await pollCoreAlerts();
  } catch (error) {
    document.getElementById("globalSystemAlertNote").textContent = `Nie udało się zapisać potwierdzenia w core: ${String(error.message || error)}`;
  } finally {
    alertAckInFlight = false;
    renderCoreAlertModal(coreAlertSnapshot.active);
  }
}

function makeAlertEmptyRow(text) {
  const row = document.createElement("div");
  row.className = "v2-alert-empty";
  row.textContent = text;
  return row;
}

function renderActiveAlerts(active) {
  if (!coreAlertUi.activeList) return;
  coreAlertUi.activeList.replaceChildren();
  if (active.length === 0) {
    coreAlertUi.activeList.appendChild(makeAlertEmptyRow("Brak aktywnych alertów."));
    return;
  }

  active.forEach((alert) => {
    const card = document.createElement("article");
    card.className = `v2-alert-card ${alertSeverityClass(alert.severity)}`;

    const head = document.createElement("div");
    head.className = "v2-alert-card-head";
    const severity = document.createElement("span");
    severity.className = "v2-alert-severity";
    severity.textContent = alertSeverityLabel(alert.severity);
    const state = document.createElement("span");
    state.className = `v2-alert-state ${alert.acknowledged === true ? "acknowledged" : "active"}`;
    state.textContent = alert.acknowledged === true ? "AKTYWNY · POTWIERDZONY" : "AKTYWNY";
    head.append(severity, state);

    const title = document.createElement("h3");
    title.textContent = alert.message || alert.code || "Alert systemowy";
    const detail = document.createElement("p");
    detail.textContent = alert.detail || "Brak dodatkowych szczegółów.";

    const meta = document.createElement("div");
    meta.className = "v2-alert-meta";
    meta.textContent = `#${alert.alert_id} · ${alert.source || "core"} · od ${formatAlertTime(alert.active_since)} · wystąpienia: ${alert.occurrences ?? "—"}`;

    card.append(head, title, detail, meta);
    if (alert.acknowledged !== true && Number.isInteger(alert.alert_id)) {
      const ack = document.createElement("button");
      ack.type = "button";
      ack.className = "v2-alert-ack";
      ack.dataset.alertAck = String(alert.alert_id);
      ack.textContent = "POTWIERDŹ";
      card.appendChild(ack);
    }
    coreAlertUi.activeList.appendChild(card);
  });
}

function renderAlertHistory(history) {
  if (!coreAlertUi.historyBody) return;
  coreAlertUi.historyBody.replaceChildren();
  if (history.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.className = "v2-alert-table-empty";
    td.textContent = "Historia alertów jest pusta.";
    tr.appendChild(td);
    coreAlertUi.historyBody.appendChild(tr);
    return;
  }

  history.forEach((alert) => {
    const tr = document.createElement("tr");
    tr.className = alert.active === true ? "is-active" : "is-cleared";
    const values = [
      `#${alert.alert_id}`,
      alertSeverityLabel(alert.severity),
      alert.message || alert.code || "—",
      alert.source || "—",
      formatAlertTime(alert.active_since),
      alert.acknowledged === true ? formatAlertTime(alert.acknowledged_at) : "—",
      alert.active === true ? "AKTYWNY" : formatAlertTime(alert.cleared_at),
    ];
    values.forEach((value, index) => {
      const td = document.createElement("td");
      td.textContent = value;
      if (index === 1) td.className = `severity-${alertSeverityClass(alert.severity)}`;
      tr.appendChild(td);
    });
    coreAlertUi.historyBody.appendChild(tr);
  });
}

function renderCoreAlerts(payload) {
  const active = Array.isArray(payload.active) ? payload.active : [];
  const history = Array.isArray(payload.history) ? payload.history : [];
  coreAlertSnapshot = { active, history };

  const unacknowledged = active.filter((alert) => alert && alert.acknowledged !== true).length;
  if (coreAlertUi.activeCount) coreAlertUi.activeCount.textContent = String(active.length);
  if (coreAlertUi.unackCount) coreAlertUi.unackCount.textContent = String(unacknowledged);
  if (coreAlertUi.historyCount) coreAlertUi.historyCount.textContent = String(history.length);
  if (coreAlertUi.connection) {
    coreAlertUi.connection.textContent = "Dane z ventilation-core";
    coreAlertUi.connection.className = "v2-alert-connection good";
  }

  renderActiveAlerts(active);
  renderAlertHistory(history);
  renderCoreAlertModal(active);
}

function renderAlertTransportFailure(error) {
  if (coreAlertUi.connection) {
    coreAlertUi.connection.textContent = `Brak dostępu do rejestru alertów core: ${String(error.message || error)}`;
    coreAlertUi.connection.className = "v2-alert-connection bad";
  }
}

async function pollCoreAlerts() {
  try {
    const response = await fetch("/api/v1/alerts", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || payload.ok !== true || !Array.isArray(payload.active) || !Array.isArray(payload.history)) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    renderCoreAlerts(payload);
  } catch (error) {
    renderAlertTransportFailure(error);
  }
}

if (coreAlertUi.activeList) {
  coreAlertUi.activeList.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-alert-ack]");
    if (!button) return;
    const alertId = Number(button.dataset.alertAck);
    if (!Number.isInteger(alertId) || alertId < 1) return;
    button.disabled = true;
    try {
      await acknowledgeAlert(alertId);
      await pollCoreAlerts();
    } catch (error) {
      renderAlertTransportFailure(error);
      button.disabled = false;
    }
  });
}

ensureCoreAlertModal();
pollCoreAlerts();
setInterval(pollCoreAlerts, ALERT_POLL_MS);
