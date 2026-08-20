"use strict";

/*
 * History H4.3: scalable alert archive browsing.
 *
 * The browser receives only lightweight date summaries. Alert records are loaded
 * from the read-only WebUI history backend when a date folder is opened, with a
 * cursor for additional records from that same day. Older date windows are also
 * loaded explicitly. No alert classification, retention or lifecycle logic lives
 * in this module.
 */

const HISTORY_H43_INDEX_WINDOW_DAYS = 90;
const HISTORY_H43_DAY_PAGE_SIZE = 100;
const HISTORY_H43_INDEX_POLL_MS = 60000;

const historyH43State = {
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  indexLoading: false,
  indexReady: false,
  indexError: null,
  days: new Map(),
  dayOrder: [],
  dayCache: new Map(),
  totalClosed: null,
  hasOlder: false,
  nextBeforeDay: null,
  indexSignature: null,
};

function historyH43Post(path, body) {
  return fetch(path, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(async (response) => {
    const payload = await response.json();
    if (!response.ok || payload.ok !== true) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    return payload.alert_history;
  });
}

function historyH43DayLabel(day) {
  const parts = String(day || "").split("-").map(Number);
  if (parts.length !== 3 || parts.some((value) => !Number.isFinite(value))) {
    return "Data nieznana";
  }
  const localNoon = new Date(parts[0], parts[1] - 1, parts[2], 12, 0, 0, 0);
  return new Intl.DateTimeFormat("pl-PL", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(localNoon);
}

function historyH43SummaryText(summary) {
  const fragments = [`${summary.count} ${summary.count === 1 ? "wpis" : "wpisów"}`];
  if (summary.critical) fragments.push(`${summary.critical} kryt.`);
  if (summary.warning) fragments.push(`${summary.warning} ostrz.`);
  if (summary.other) fragments.push(`${summary.other} inne`);
  return fragments.join(" · ");
}

function historyH43SortDays() {
  historyH43State.dayOrder = [...historyH43State.days.keys()].sort().reverse();
}

function historyH43IndexSignature() {
  return JSON.stringify({
    days: historyH43State.dayOrder.map((day) => {
      const item = historyH43State.days.get(day);
      return [day, item?.count, item?.critical, item?.warning, item?.other];
    }),
    hasOlder: historyH43State.hasOlder,
    nextBeforeDay: historyH43State.nextBeforeDay,
  });
}

function historyH43MergeIndex(payload, { appendOlder = false } = {}) {
  const incoming = Array.isArray(payload.days) ? payload.days : [];
  incoming.forEach((summary) => {
    if (!summary || typeof summary.day !== "string") return;
    const previous = historyH43State.days.get(summary.day);
    historyH43State.days.set(summary.day, summary);
    const cached = historyH43State.dayCache.get(summary.day);
    if (cached && previous && previous.count !== summary.count) {
      historyH43State.dayCache.delete(summary.day);
    }
  });

  historyH43State.totalClosed = Number.isInteger(payload.total_closed)
    ? payload.total_closed
    : historyH43State.totalClosed;

  if (!historyH43State.indexReady || appendOlder) {
    historyH43State.hasOlder = payload.has_older === true;
    historyH43State.nextBeforeDay = typeof payload.next_before_day === "string"
      ? payload.next_before_day
      : null;
  } else if (!historyH43State.nextBeforeDay) {
    historyH43State.hasOlder = payload.has_older === true;
    historyH43State.nextBeforeDay = typeof payload.next_before_day === "string"
      ? payload.next_before_day
      : null;
  }

  historyH43SortDays();
  historyH43State.indexReady = true;
  historyH43State.indexError = null;

  if (!historyH42FolderStateInitialized && historyH43State.dayOrder.length > 0) {
    historyH42OpenFolderKeys = new Set([historyH43State.dayOrder[0]]);
    historyH42FolderStateInitialized = true;
  }
}

async function historyH43LoadIndex({ beforeDay = null, appendOlder = false, refresh = false } = {}) {
  if (historyH43State.indexLoading) return;
  historyH43State.indexLoading = true;
  if (!refresh) historyH43RenderArchive();

  try {
    const body = {
      timezone: historyH43State.timezone,
      window_days: HISTORY_H43_INDEX_WINDOW_DAYS,
    };
    if (beforeDay) body.before_day = beforeDay;
    const payload = await historyH43Post("/api/v1/history/alerts/days", body);
    historyH43MergeIndex(payload, { appendOlder });
  } catch (error) {
    historyH43State.indexError = `Nie udało się pobrać katalogu alertów: ${String(error.message || error)}`;
  } finally {
    historyH43State.indexLoading = false;
    historyH43RenderArchive();
    historyH43LoadOpenDays();
  }
}

function historyH43EnsureIndex() {
  if (!historyH43State.indexReady && !historyH43State.indexLoading) {
    historyH43LoadIndex();
  }
}

function historyH43CacheFor(day) {
  let cache = historyH43State.dayCache.get(day);
  if (!cache) {
    cache = {
      records: [],
      loading: false,
      loaded: false,
      hasMore: false,
      cursor: null,
      total: null,
      error: null,
    };
    historyH43State.dayCache.set(day, cache);
  }
  return cache;
}

async function historyH43LoadDay(day, { more = false } = {}) {
  const cache = historyH43CacheFor(day);
  if (cache.loading) return;
  if (!more && cache.loaded) {
    historyH43RenderDay(day);
    return;
  }
  if (more && (!cache.loaded || !cache.hasMore || !cache.cursor)) return;

  cache.loading = true;
  cache.error = null;
  historyH43RenderDay(day);

  try {
    const body = {
      day,
      timezone: historyH43State.timezone,
      limit: HISTORY_H43_DAY_PAGE_SIZE,
    };
    if (more) body.cursor = cache.cursor;
    const payload = await historyH43Post("/api/v1/history/alerts/day", body);
    const incoming = Array.isArray(payload.records) ? payload.records : [];

    if (more) {
      const known = new Set(cache.records.map((record) => record.alert_id));
      incoming.forEach((record) => {
        if (!known.has(record.alert_id)) cache.records.push(record);
      });
    } else {
      cache.records = incoming.slice();
    }

    cache.loaded = true;
    cache.hasMore = payload.has_more === true;
    cache.cursor = payload.next_cursor || null;
    cache.total = Number.isInteger(payload.total_for_day)
      ? payload.total_for_day
      : cache.records.length;
    cache.error = null;
  } catch (error) {
    cache.error = `Nie udało się pobrać alertów z tego dnia: ${String(error.message || error)}`;
  } finally {
    cache.loading = false;
    historyH43RenderDay(day);
  }
}

function historyH43RenderDay(day) {
  const host = document.querySelector(`[data-history-day-list="${day}"]`);
  if (!host) return;
  const cache = historyH43CacheFor(day);

  host.replaceChildren();

  if (cache.error) {
    const error = document.createElement("div");
    error.className = "v2-history-alert-empty is-error";
    error.textContent = cache.error;
    host.appendChild(error);
    return;
  }

  if (!cache.loaded && cache.loading) {
    const loading = document.createElement("div");
    loading.className = "v2-history-alert-day-loading";
    loading.textContent = "Ładowanie wpisów…";
    host.appendChild(loading);
    return;
  }

  if (!cache.loaded) {
    const hint = document.createElement("div");
    hint.className = "v2-history-alert-day-loading";
    hint.textContent = "Otwórz katalog, aby pobrać wpisy z tego dnia.";
    host.appendChild(hint);
    return;
  }

  if (cache.records.length === 0) {
    const empty = document.createElement("div");
    empty.className = "v2-history-alert-empty";
    empty.textContent = "Brak zakończonych alertów w tym dniu.";
    host.appendChild(empty);
    return;
  }

  cache.records.forEach((alert) => host.appendChild(historyH41AlertCard(alert)));

  if (cache.hasMore) {
    const more = document.createElement("button");
    more.type = "button";
    more.className = "v2-history-alert-load-more";
    more.textContent = cache.loading ? "ŁADOWANIE…" : "POKAŻ KOLEJNE WPISY";
    more.disabled = cache.loading;
    more.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      historyH43LoadDay(day, { more: true });
    });
    host.appendChild(more);
  }
}

function historyH43RenderFolder(summary) {
  const details = document.createElement("details");
  details.className = "v2-history-alert-folder";
  details.dataset.historyDateKey = summary.day;
  details.open = historyH42OpenFolderKeys.has(summary.day);

  const summaryNode = document.createElement("summary");
  summaryNode.className = "v2-history-alert-folder-summary";

  const folderIcon = document.createElement("span");
  folderIcon.className = "v2-history-alert-folder-icon";
  folderIcon.setAttribute("aria-hidden", "true");

  const text = document.createElement("div");
  text.className = "v2-history-alert-folder-text";
  const title = document.createElement("strong");
  title.textContent = historyH43DayLabel(summary.day);
  const meta = document.createElement("span");
  meta.textContent = historyH43SummaryText(summary);
  text.append(title, meta);

  const chevron = document.createElement("span");
  chevron.className = "v2-history-alert-folder-chevron";
  chevron.textContent = "›";
  chevron.setAttribute("aria-hidden", "true");

  summaryNode.append(folderIcon, text, chevron);

  const list = document.createElement("div");
  list.className = "v2-history-alert-folder-list";
  list.dataset.historyDayList = summary.day;

  details.append(summaryNode, list);
  details.addEventListener("toggle", () => {
    historyH42RememberFolderState(details);
    if (details.open) historyH43LoadDay(summary.day);
  });

  queueMicrotask(() => historyH43RenderDay(summary.day));
  if (details.open) queueMicrotask(() => historyH43LoadDay(summary.day));
  return details;
}

function historyH43RenderOlderButton(host) {
  if (!historyH43State.hasOlder || !historyH43State.nextBeforeDay) return;
  const footer = document.createElement("div");
  footer.className = "v2-history-alert-older-footer";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "v2-history-alert-load-older";
  button.textContent = historyH43State.indexLoading
    ? "ŁADOWANIE…"
    : `POKAŻ STARSZE DNI · ${HISTORY_H43_INDEX_WINDOW_DAYS} DNI`;
  button.disabled = historyH43State.indexLoading;
  button.addEventListener("click", () => {
    historyH43LoadIndex({
      beforeDay: historyH43State.nextBeforeDay,
      appendOlder: true,
    });
  });
  footer.appendChild(button);
  host.appendChild(footer);
}

function historyH43LoadOpenDays() {
  if (historyH42Mode !== "alerts") return;
  historyH42OpenFolderKeys.forEach((day) => {
    if (historyH43State.days.has(day)) historyH43LoadDay(day);
  });
}

function historyH43RenderArchive() {
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
  if (title) title.textContent = "Historia alertów · pełny rejestr";
  if (description) {
    description.textContent = "Katalogi dat są lekkie. Wpisy z konkretnego dnia są pobierane dopiero po otwarciu katalogu.";
  }
  if (state) {
    state.textContent = historyH43State.indexLoading
      ? "AKTUALIZACJA…"
      : "PEŁNY REJESTR · NA ŻĄDANIE";
  }
  if (count) {
    count.textContent = Number.isInteger(historyH43State.totalClosed)
      ? `${historyH43State.totalClosed} zakończonych`
      : "—";
  }

  if (historyH43State.indexError && !historyH43State.indexReady) {
    host.replaceChildren();
    const error = document.createElement("div");
    error.className = "v2-history-alert-empty is-error";
    error.textContent = historyH43State.indexError;
    host.appendChild(error);
    return;
  }

  if (!historyH43State.indexReady) {
    if (!historyH43State.indexLoading) historyH43EnsureIndex();
    if (!host.querySelector(".v2-history-alert-day-loading")) {
      host.replaceChildren();
      const loading = document.createElement("div");
      loading.className = "v2-history-alert-day-loading";
      loading.textContent = "Ładowanie katalogu dat…";
      host.appendChild(loading);
    }
    return;
  }

  const signature = historyH43IndexSignature();
  if (signature === historyH43State.indexSignature && host.querySelector(".v2-history-alert-folder")) {
    return;
  }

  historyH42CaptureFolderState(host);
  historyH43State.indexSignature = signature;
  host.replaceChildren();

  if (historyH43State.dayOrder.length === 0) {
    const empty = document.createElement("div");
    empty.className = "v2-history-alert-empty";
    empty.textContent = "Brak zakończonych alertów w rejestrze.";
    host.appendChild(empty);
    return;
  }

  historyH43State.dayOrder.forEach((day) => {
    const summary = historyH43State.days.get(day);
    if (summary) host.appendChild(historyH43RenderFolder(summary));
  });
  historyH43RenderOlderButton(host);
}

historyH41RenderArchive = historyH43RenderArchive;

window.setInterval(() => {
  if (historyH42Mode === "alerts" && !historyH43State.indexLoading) {
    historyH43LoadIndex({ refresh: true });
  }
}, HISTORY_H43_INDEX_POLL_MS);

if (historyH42Mode === "alerts") historyH43RenderArchive();
