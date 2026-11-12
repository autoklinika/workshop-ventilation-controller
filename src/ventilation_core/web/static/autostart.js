"use strict";

/* Autostart planning UI. No actuator, power or RTC commands originate here. */
(() => {
  const $ = id => document.getElementById("autostart" + id);
  const WEEK = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"];
  const MONTH = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"];
  const currentYear = Number(new Intl.DateTimeFormat("en", {timeZone: "Europe/Warsaw", year: "numeric"}).format(new Date()));
  const state = {year: Math.max(2025, Math.min(2100, currentYear)), snapshot: null, draft: null, dirty: false, selected: null, busy: false};

  async function request(path, options = {}) {
    const response = await fetch(path, {cache: "no-store", ...options});
    let result;
    try { result = await response.json(); }
    catch (_) { throw new Error("Serwer nie zwrócił poprawnego JSON."); }
    if (!response.ok || result.ok !== true) throw new Error(result.error || "HTTP " + response.status);
    return result.autostart;
  }
  function message(text, bad = false) {
    $("Message").textContent = text;
    $("Message").className = bad ? "error" : "";
  }
  function clone(data) { return JSON.parse(JSON.stringify(data)); }
  function markDirty() {
    state.dirty = true;
    message("Zmiany niezapisane.");
    $("Save").disabled = !state.snapshot || state.busy;
  }
  function validTime(value) { return /^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(value); }

  function renderWeek() {
    const host = $("Week");
    host.replaceChildren();
    for (const day of state.draft.week) {
      const row = document.createElement("div");
      row.className = "autostart-week-row";
      const label = document.createElement("label");
      label.className = "autostart-week-name";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = day.enabled;
      checkbox.setAttribute("aria-label", "Włącz " + WEEK[day.weekday - 1]);
      checkbox.addEventListener("change", () => {
        day.enabled = checkbox.checked;
        markDirty();
        renderMonths();
        renderSelected();
      });
      const name = document.createElement("strong");
      name.textContent = WEEK[day.weekday - 1];
      label.append(checkbox, name);
      row.append(label);
      for (const [key, text] of [["start_local", "Włączenie"], ["end_local", "Wyłączenie"]]) {
        const wrapper = document.createElement("label");
        const caption = document.createElement("span");
        caption.textContent = text;
        const input = document.createElement("input");
        input.type = "time";
        input.step = "60";
        input.value = day[key] || "";
        input.setAttribute("aria-label", text + ": " + WEEK[day.weekday - 1]);
        input.addEventListener("change", () => { day[key] = input.value || null; markDirty(); renderSelected(); });
        wrapper.append(caption, input);
        row.append(wrapper);
      }
      host.append(row);
    }
  }

  function baseEnabled(day) {
    if (day.holiday || day.weekday === 7) return false;
    return state.draft.week[day.weekday - 1].enabled;
  }
  function effectiveDay(day) {
    const custom = state.draft.overrides.find(item => item.date === day.date);
    return {
      enabled: custom ? custom.enabled : baseEnabled(day),
      custom: Boolean(custom),
      source: custom ? "override" : day.holiday ? "holiday" : day.weekday === 7 ? "sunday" : "weekly"
    };
  }
  function modifyDay(dateKey, newValue, restore = false) {
    const day = state.snapshot.days.find(item => item.date === dateKey);
    if (!day) return;
    state.draft.overrides = state.draft.overrides.filter(item => item.date !== dateKey);
    if (!restore && newValue !== baseEnabled(day)) state.draft.overrides.push({date: dateKey, enabled: newValue});
    state.draft.overrides.sort((a, b) => a.date.localeCompare(b.date));
    markDirty();
    renderMonths();
    renderSelected();
  }

  function renderMonths() {
    const host = $("Months");
    host.replaceChildren();
    let working = 0, resting = 0;
    for (let month = 0; month < 12; month++) {
      const box = document.createElement("section");
      box.className = "autostart-month";
      const heading = document.createElement("h3");
      heading.textContent = MONTH[month];
      box.append(heading);
      const grid = document.createElement("div");
      grid.className = "autostart-day-grid";
      for (const name of ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"]) {
        const item = document.createElement("span");
        item.className = "autostart-day-heading";
        item.textContent = name;
        grid.append(item);
      }
      const weekdayOffset = (new Date(Date.UTC(state.year, month, 1)).getUTCDay() + 6) % 7;
      for (let i = 0; i < weekdayOffset; i++) {
        const empty = document.createElement("span");
        empty.className = "autostart-empty-day";
        grid.append(empty);
      }
      const days = state.snapshot.days.filter(day => Number(day.date.slice(5, 7)) === month + 1);
      for (const day of days) {
        const mode = effectiveDay(day);
        if (mode.enabled) working++; else resting++;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "autostart-day " + (mode.enabled ? "is-on" : "is-off") +
          (day.holiday ? " is-holiday" : "") +
          (mode.custom ? " is-override" : "") +
          (day.date === state.selected ? " is-selected" : "");
        button.textContent = String(Number(day.date.slice(-2)));
        button.title = day.date + " · " + (day.holiday || WEEK[day.weekday - 1]) +
          " · " + (mode.enabled ? "autostart włączony" : "autostart wyłączony");
        button.setAttribute("aria-label", button.title);
        button.setAttribute("aria-pressed", String(mode.enabled));
        button.addEventListener("click", () => {
          state.selected = day.date;
          modifyDay(day.date, !mode.enabled);
        });
        grid.append(button);
      }
      box.append(grid);
      host.append(box);
    }
    $("Counts").textContent = "Rok " + state.year + ": " + working + " dni włączonych · " + resting + " wyłączonych.";
    $("Year").textContent = String(state.year);
    $("YearPrev").disabled = state.year <= 2025 || state.busy;
    $("YearNext").disabled = state.year >= 2100 || state.busy;
  }

  function renderSelected() {
    const day = state.snapshot?.days.find(item => item.date === state.selected);
    $("Selected").hidden = !day;
    if (!day) return;
    const mode = effectiveDay(day);
    const times = state.draft.week[day.weekday - 1];
    const hours = times.start_local && times.end_local ? times.start_local + "–" + times.end_local : "godziny nieustawione";
    $("SelectedTitle").textContent = day.date + " · " + WEEK[day.weekday - 1] +
      (day.holiday ? " · " + day.holiday : "");
    $("SelectedDescription").textContent = (mode.enabled ? "Włączony" : "Wyłączony") +
      " · " + hours + " · " +
      ({override: "zmiana ręczna", holiday: "święto państwowe", sunday: "niedziela", weekly: "szablon tygodniowy"}[mode.source]);
    $("ToggleDay").textContent = mode.enabled ? "Wyłącz ten dzień" : "Włącz ten dzień";
    $("ResetDay").disabled = !mode.custom;
  }

  function render() {
    $("Status").textContent = "PLAN ZAPISANY · R" + state.snapshot.revision;
    $("Enabled").disabled = false;
    $("ScheduleEnabled").disabled = false;
    $("Enabled").checked = state.draft.enabled;
    $("ScheduleEnabled").checked = state.draft.schedule_enabled;
    $("Save").disabled = !state.dirty || state.busy;
    renderWeek();
    renderMonths();
    renderSelected();
  }

  async function load(year = state.year) {
    state.busy = true;
    $("Save").disabled = true;
    message("Wczytywanie planu…");
    try {
      const snapshot = await request("/api/v1/autostart/" + year);
      if (snapshot.available !== true || snapshot.actuation_enabled !== false || !Array.isArray(snapshot.days)) {
        throw new Error("Nieoczekiwany kontrakt API Autostartu.");
      }
      state.year = year;
      state.snapshot = snapshot;
      state.draft = clone(snapshot.config);
      state.dirty = false;
      if (state.selected && !state.selected.startsWith(year + "-")) state.selected = null;
      render();
      message("Konfiguracja wczytana. Zapis nie uruchamia CM5 ani wentylatorów.");
    } catch (error) {
      state.snapshot = null;
      state.draft = null;
      $("Status").textContent = "NIEDOSTĘPNY";
      $("Enabled").disabled = true;
      $("ScheduleEnabled").disabled = true;
      $("Week").replaceChildren();
      $("Months").replaceChildren();
      $("Selected").hidden = true;
      message(String(error.message || error), true);
    } finally {
      state.busy = false;
    }
  }

  async function switchYear(offset) {
    if (state.dirty && !window.confirm("Masz niezapisane zmiany. Odrzucić je i zmienić rok?")) return;
    const year = state.year + offset;
    if (year < 2025 || year > 2100) return;
    await load(year);
  }
  async function save() {
    if (!state.snapshot || state.busy) return;
    for (const day of state.draft.week) {
      const start = day.start_local, end = day.end_local;
      if ((start === null) !== (end === null) ||
          (start !== null && (!validTime(start) || !validTime(end) || start >= end))) {
        message("Niepoprawne godziny: " + WEEK[day.weekday - 1] + ". Wypełnij obie i ustaw włączenie przed wyłączeniem.", true);
        return;
      }
    }
    state.busy = true;
    $("Save").disabled = true;
    message("Zapisywanie…");
    try {
      const snapshot = await request("/api/v1/autostart", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({year: state.year, expected_revision: state.snapshot.revision, config: state.draft}),
      });
      state.snapshot = snapshot;
      state.draft = clone(snapshot.config);
      state.dirty = false;
      render();
      message("Zapisano w CM5 (rewizja " + snapshot.revision + "). Bez wykonania poleceń zasilania.");
    } catch (error) {
      message(String(error.message || error) + " Wczytaj ponownie w razie konfliktu rewizji.", true);
      $("Save").disabled = false;
    } finally {
      state.busy = false;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (!$("App")) return;
    $("Enabled").addEventListener("change", event => {state.draft.enabled = event.target.checked; markDirty();});
    $("ScheduleEnabled").addEventListener("change", event => {state.draft.schedule_enabled = event.target.checked; markDirty();});
    $("YearPrev").addEventListener("click", () => switchYear(-1));
    $("YearNext").addEventListener("click", () => switchYear(1));
    $("ToggleDay").addEventListener("click", () => {
      const day = state.snapshot.days.find(item => item.date === state.selected);
      if (day) modifyDay(day.date, !effectiveDay(day).enabled);
    });
    $("ResetDay").addEventListener("click", () => modifyDay(state.selected, null, true));
    $("Reload").addEventListener("click", () => {
      if (!state.dirty || window.confirm("Odrzucić niezapisane zmiany?")) load();
    });
    $("Save").addEventListener("click", save);
    load();
  });
})();
