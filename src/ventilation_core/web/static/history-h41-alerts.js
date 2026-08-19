"use strict";

/*
 * History H4.1: move cleared alert archive from ALERTY to HISTORIA.
 *
 * ALERTY remains a current-state screen: only active alerts stay there.
 * HISTORIA renders the existing core alert-history payload without deriving new
 * alert semantics. Grouping uses the backend-provided severity field only.
 */

const HISTORY_H41_ALERT_POLL_MS = 15000;
const historyH41Archive = {
  loading: false,
  history: [],
  lastError: null,
};

function historyH41StripAlertsPageArchive() {
  const view = document.getElementById("alertsView");
  if (!view) return;

  const historyBody = view.querySelector("#alertsHistoryBody");
  if (historyBody) {
    const section = historyBody.closest(".v2-alert-section");
    if (section) section.remove();
  }

  const historyCount = view.querySelector("#alertsHistoryCount");
  if (historyCount) {
    const card = historyCount.closest("article");
    if (card) card.remove();
  }

  const headingText = view.querySelector(".v2-page-heading p");
  if (headingText) {
    headingText.textContent = "Bieżące alerty wymagające uwagi operatora";
  }
}

function historyH41EnsureArchiveSection() {
  const view = typeof ensureHistoryView === "function" ? ensureHistoryView() : document.getElementById("historyView");
  if (!view) return null;

  let section = document.getElementById("historyAlertArchive");
  if (section) return section;

  section = document.createElement("section");
  section.id = "historyAlertArchive";
  section.className = "v2-history-alert-archive";
  section.innerHTML = `
    <header class="v2-history-alert-head">
      <div>
        <span>CM5 · REJESTR SYSTEMOWY</span>
        <h2>Historia alertów</h2>
        <p>Zakończone alerty systemowe. Aktywne alerty pozostają w zakładce ALERTY.</p>
      </div>
      <div class="v2-history-alert-meta">
        <span id="historyAlertArchiveState">ŁADOWANIE…</span>
        <strong id="historyAlertArchiveCount">—</strong>
      </div>
    </header>
    <div id="historyAlertArchiveGroups" class="v2-history-alert-groups">
      <div class="v2-history-alert-empty">Ładowanie historii alertów…</div>
    </div>`;

  const chartCard = document.getElementById("historyChartCard");
  if (chartCard && chartCard.parentElement === view) {
    chartCard.insertAdjacentElement("afterend", section);
  } else {
    view.appendChild(section);
  }
  return section;
}

function historyH41FormatTime(value) {
  if (typeof value !== "string" || !value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pl-PL", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function historyH41SeverityLabel(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "critical") return "KRYTYCZNY";
  if (normalized === "warning") return "OSTRZEŻENIE";
  return "ALERT";
}

function historyH41SeverityClass(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "critical") return "critical";
  if (normalized === "warning") return "warning";
  return "other";
}

function historyH41ClosedRecords(history) {
  return (Array.isArray(history) ? history : [])
    .filter((alert) => alert && alert.active !== true && typeof alert.cleared_at === "string" && alert.cleared_at)
    .slice()
    .sort((left, right) => {
      const a = new Date(left.cleared_at || left.active_since || 0).getTime();
      const b = new Date(right.cleared_at || right.active_since || 0).getTime();
      return (Number.isFinite(b) ? b : 0) - (Number.isFinite(a) ? a : 0);
    });
}

function historyH41GroupRecords(records) {
  const groups = [
    { id: "critical", label: "KRYTYCZNE", items: [] },
    { id: "warning", label: "OSTRZEŻENIA", items: [] },
    { id: "other", label: "POZOSTAŁE", items: [] },
  ];
  const byId = new Map(groups.map((group) => [group.id, group]));

  records.forEach((alert) => {
    const id = historyH41SeverityClass(alert.severity);
    const group = byId.get(id) || byId.get("other");
    group.items.push(alert);
  });
  return groups.filter((group) => group.items.length > 0);
}

function historyH41AlertCard(alert) {
  const article = document.createElement("article");
  article.className = `v2-history-alert-card ${historyH41SeverityClass(alert.severity)}`;

  const titleRow = document.createElement("div");
  titleRow.className = "v2-history-alert-card-head";

  const severity = document.createElement("span");
  severity.className = "v2-history-alert-severity";
  severity.textContent = historyH41SeverityLabel(alert.severity);

  const state = document.createElement("span");
  state.className = "v2-history-alert-cleared";
  state.textContent = `ZAKOŃCZONO ${historyH41FormatTime(alert.cleared_at)}`;
  titleRow.append(severity, state);

  const title = document.createElement("h3");
  title.textContent = alert.message || alert.code || "Alert systemowy";

  const detail = document.createElement("p");
  detail.textContent = alert.detail || "Brak dodatkowych szczegółów.";

  const meta = document.createElement("div");
  meta.className = "v2-history-alert-card-meta";
  const acknowledged = alert.acknowledged === true
    ? historyH41FormatTime(alert.acknowledged_at)
    : "niepotwierdzony";
  meta.textContent = `#${alert.alert_id ?? "—"} · ${alert.source || "core"} · od ${historyH41FormatTime(alert.active_since)} · potwierdzenie: ${acknowledged} · wystąpienia: ${alert.occurrences ?? "—"}`;

  article.append(titleRow, title, detail, meta);
  return article;
}

function historyH41RenderArchive() {
  const section = historyH41EnsureArchiveSection();
  if (!section) return;

  const state = document.getElementById("historyAlertArchiveState");
  const count = document.getElementById("historyAlertArchiveCount");
  const host = document.getElementById("historyAlertArchiveGroups");
  if (!host) return;

  if (historyH41Archive.lastError) {
    if (state) state.textContent = "BŁĄD ODCZYTU";
    if (count) count.textContent = "—";
    host.replaceChildren();
    const empty = document.createElement("div");
    empty.className = "v2-history-alert-empty is-error";
    empty.textContent = historyH41Archive.lastError;
    host.appendChild(empty);
    return;
  }

  const records = historyH41ClosedRecords(historyH41Archive.history);
  if (state) state.textContent = "OSTATNIE WPISY Z CORE";
  if (count) count.textContent = `${records.length} zakończonych`;

  host.replaceChildren();
  if (records.length === 0) {
    const empty = document.createElement("div");
    empty.className = "v2-history-alert-empty";
    empty.textContent = "Brak zakończonych alertów w rejestrze.";
    host.appendChild(empty);
    return;
  }

  historyH41GroupRecords(records).forEach((group) => {
    const groupSection = document.createElement("section");
    groupSection.className = `v2-history-alert-group ${group.id}`;

    const header = document.createElement("header");
    const label = document.createElement("h3");
    label.textContent = group.label;
    const badge = document.createElement("span");
    badge.textContent = String(group.items.length);
    header.append(label, badge);

    const list = document.createElement("div");
    list.className = "v2-history-alert-list";
    group.items.forEach((alert) => list.appendChild(historyH41AlertCard(alert)));

    groupSection.append(header, list);
    host.appendChild(groupSection);
  });
}

async function historyH41PollArchive() {
  if (historyH41Archive.loading) return;
  historyH41Archive.loading = true;
  try {
    const response = await fetch("/api/v1/alerts", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || payload.ok !== true || !Array.isArray(payload.history)) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    historyH41Archive.history = payload.history;
    historyH41Archive.lastError = null;
  } catch (error) {
    historyH41Archive.lastError = `Nie udało się pobrać historii alertów: ${String(error.message || error)}`;
  } finally {
    historyH41Archive.loading = false;
    historyH41RenderArchive();
  }
}

historyH41StripAlertsPageArchive();
historyH41EnsureArchiveSection();
historyH41PollArchive();
window.setInterval(historyH41PollArchive, HISTORY_H41_ALERT_POLL_MS);
