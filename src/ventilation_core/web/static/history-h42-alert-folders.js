"use strict";

/*
 * History H4.2: ALERTY becomes a third History tile.
 *
 * The archive uses only ended incidents returned by ventilation-core. Backend
 * storage owns the 30-day retention policy. The browser groups those existing
 * records by their cleared calendar date for presentation only.
 */

let historyH42Mode = "zone";

function historyH42EnsureAlertTile() {
  const host = document.getElementById("historyZoneButtons");
  if (!host) return null;

  let button = host.querySelector('[data-history-zone="alerts"]');
  if (button) return button;

  button = document.createElement("button");
  button.type = "button";
  button.className = "v2-history-btn v2-history-alert-tile";
  button.dataset.historyZone = "alerts";
  button.textContent = "ALERTY";
  button.setAttribute("aria-label", "Historia alertów z ostatnich 30 dni");
  button.addEventListener("click", () => historyH42SelectAlerts());
  host.appendChild(button);
  return button;
}

function historyH42SetChartControlsVisible(visible) {
  const ranges = document.getElementById("historyRangeButtons");
  const metrics = document.getElementById("historyMetricButtons");
  const chart = document.getElementById("historyChartCard");
  if (ranges) ranges.hidden = !visible;
  if (metrics) metrics.hidden = !visible;
  if (chart) chart.hidden = !visible;
}

function historyH42PlaceArchiveForAlertMode() {
  const archive = historyH41EnsureArchiveSection();
  const controls = document.querySelector("#historyView .v2-history-controls");
  if (!archive || !controls || !controls.parentElement) return archive;
  controls.insertAdjacentElement("afterend", archive);
  return archive;
}

function historyH42SelectAlerts() {
  historyH42Mode = "alerts";
  historyH42SetChartControlsVisible(false);
  const archive = historyH42PlaceArchiveForAlertMode();
  if (archive) archive.hidden = false;
  historyRenderZoneButtons();
  historyH41RenderArchive();
}

function historyH42SelectZone() {
  if (historyH42Mode !== "alerts") return;
  historyH42Mode = "zone";
  historyH42SetChartControlsVisible(true);
  const archive = document.getElementById("historyAlertArchive");
  if (archive) archive.hidden = true;
  historyRenderZoneButtons();
  historyH42BaseLoadChart();
}

const historyH42BaseRenderZoneButtons = historyRenderZoneButtons;
historyRenderZoneButtons = function historyH42RenderZoneButtons() {
  historyH42BaseRenderZoneButtons();
  const alertTile = historyH42EnsureAlertTile();
  document.querySelectorAll('#historyZoneButtons [data-history-zone="zone1"], #historyZoneButtons [data-history-zone="zone2"]').forEach((button) => {
    if (historyH42Mode === "alerts") button.classList.remove("is-active");
  });
  if (alertTile) alertTile.classList.toggle("is-active", historyH42Mode === "alerts");
};

const historyH42BaseLoadChart = historyLoadChart;
historyLoadChart = function historyH42LoadChart() {
  if (historyH42Mode === "alerts") return Promise.resolve();
  return historyH42BaseLoadChart();
};

function historyH42WireZoneReturn() {
  document.querySelectorAll('#historyZoneButtons [data-history-zone="zone1"], #historyZoneButtons [data-history-zone="zone2"]').forEach((button) => {
    if (button.dataset.historyH42Wired === "true") return;
    button.dataset.historyH42Wired = "true";
    button.addEventListener("click", historyH42SelectZone);
  });
}

function historyH42DateKey(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  const pad = (number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function historyH42DateLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data nieznana";
  return new Intl.DateTimeFormat("pl-PL", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(date);
}

function historyH42GroupByDate(records) {
  const groups = new Map();
  records.forEach((alert) => {
    const key = historyH42DateKey(alert.cleared_at);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(alert);
  });
  return [...groups.entries()].map(([key, items]) => ({ key, items }));
}

function historyH42FolderSummary(items) {
  const critical = items.filter((alert) => String(alert.severity || "").toLowerCase() === "critical").length;
  const warning = items.filter((alert) => String(alert.severity || "").toLowerCase() === "warning").length;
  const fragments = [`${items.length} ${items.length === 1 ? "wpis" : "wpisów"}`];
  if (critical) fragments.push(`${critical} kryt.`);
  if (warning) fragments.push(`${warning} ostrz.`);
  return fragments.join(" · ");
}

function historyH42RenderDateFolder(group, index) {
  const details = document.createElement("details");
  details.className = "v2-history-alert-folder";
  details.open = index === 0;

  const summary = document.createElement("summary");
  summary.className = "v2-history-alert-folder-summary";

  const folderIcon = document.createElement("span");
  folderIcon.className = "v2-history-alert-folder-icon";
  folderIcon.setAttribute("aria-hidden", "true");

  const text = document.createElement("div");
  text.className = "v2-history-alert-folder-text";
  const title = document.createElement("strong");
  title.textContent = historyH42DateLabel(group.items[0].cleared_at);
  const meta = document.createElement("span");
  meta.textContent = historyH42FolderSummary(group.items);
  text.append(title, meta);

  const chevron = document.createElement("span");
  chevron.className = "v2-history-alert-folder-chevron";
  chevron.textContent = "›";
  chevron.setAttribute("aria-hidden", "true");

  summary.append(folderIcon, text, chevron);

  const list = document.createElement("div");
  list.className = "v2-history-alert-folder-list";
  group.items.forEach((alert) => list.appendChild(historyH41AlertCard(alert)));

  details.append(summary, list);
  return details;
}

historyH41RenderArchive = function historyH42RenderArchive() {
  const section = historyH41EnsureArchiveSection();
  if (!section) return;

  section.hidden = historyH42Mode !== "alerts";
  if (historyH42Mode !== "alerts") return;

  const title = section.querySelector(".v2-history-alert-head h2");
  const description = section.querySelector(".v2-history-alert-head p");
  const kicker = section.querySelector(".v2-history-alert-head > div:first-child > span");
  const state = document.getElementById("historyAlertArchiveState");
  const count = document.getElementById("historyAlertArchiveCount");
  const host = document.getElementById("historyAlertArchiveGroups");
  if (!host) return;

  if (kicker) kicker.textContent = "CM5 · REJESTR SYSTEMOWY";
  if (title) title.textContent = "Historia alertów · ostatnie 30 dni";
  if (description) description.textContent = "Zakończone alerty uporządkowane według dnia zakończenia. Kliknij datę, aby otworzyć katalog.";

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
  if (state) state.textContent = "RETENCJA 30 DNI";
  if (count) count.textContent = `${records.length} zakończonych`;

  host.replaceChildren();
  if (records.length === 0) {
    const empty = document.createElement("div");
    empty.className = "v2-history-alert-empty";
    empty.textContent = "Brak zakończonych alertów z ostatnich 30 dni.";
    host.appendChild(empty);
    return;
  }

  historyH42GroupByDate(records).forEach((group, index) => {
    host.appendChild(historyH42RenderDateFolder(group, index));
  });
};

historyH42EnsureAlertTile();
historyH42WireZoneReturn();
historyH42SetChartControlsVisible(true);
const historyH42ArchiveAtStart = document.getElementById("historyAlertArchive");
if (historyH42ArchiveAtStart) historyH42ArchiveAtStart.hidden = true;
historyRenderZoneButtons();
