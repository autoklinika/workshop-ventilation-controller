"use strict";

const MODES = ["AUTO", "FIXED", "STANDBY", "OFF"];
const RULE_KINDS = ["DEFAULT", "WEEKLY", "SEASON", "DATE_RANGE", "DATE_EXCEPTION"];
const MAX_PROFILES = 64;
const MAX_RULES = 512;
let calendarSnapshot = null;

function el(id) { return document.getElementById(id); }

async function api(path, options = {}) {
  const response = await fetch(path, {cache: "no-store", ...options});
  let payload;
  try { payload = await response.json(); }
  catch (_) { throw new Error(`Nieprawidłowa odpowiedź HTTP ${response.status}`); }
  if (!response.ok || payload.ok !== true) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("pl-PL", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).format(date);
}

function setText(id, value, className = "") {
  const target = el(id);
  if (!target) return;
  target.textContent = value == null || value === "" ? "—" : String(value);
  target.className = className;
}

function renderOverview(calendar) {
  const available = calendar && calendar.available === true;
  setText("calendarAvailability", available ? "DOSTĘPNY" : "NIEDOSTĘPNY", available ? "good" : "bad");
  setText("calendarRevision", calendar && calendar.revision != null ? calendar.revision : "—");
  const state = calendar && calendar.state && typeof calendar.state === "object" ? calendar.state : null;
  setText("calendarTimezoneState", state && state.timezone ? state.timezone : "—");
  setText("calendarPhase", state && state.phase ? state.phase : "—");
  setText("calendarMode", state && state.effective_mode ? state.effective_mode : "—");
  setText("calendarProfile", state && state.effective_profile ? state.effective_profile : "—");
  setText("calendarRuleSource", state && state.rule_source ? state.rule_source : "—");
  setText("calendarRuleId", state && state.rule_id ? state.rule_id : "—");
  setText("calendarNextTransition", state ? formatDateTime(state.next_transition) : "—");
  setText("calendarNextWake", state ? formatDateTime(state.next_wake) : "—");
  setText("calendarLocalTime", state ? formatDateTime(state.local_time) : "—");
  const error = calendar && calendar.last_error
    ? calendar.last_error
    : state && state.last_error
      ? state.last_error
      : "";
  setText("calendarError", error || (available ? "Calendar Engine działa" : "brak szczegółów"), error ? "bad" : "muted");
}

function input(field, value = "", type = "text", placeholder = "") {
  const node = document.createElement("input");
  node.dataset.field = field;
  node.type = type;
  node.value = value == null ? "" : String(value);
  if (placeholder) node.placeholder = placeholder;
  if (type === "number") node.step = "1";
  if (type === "time") node.step = "60";
  return node;
}

function select(field, values, selected) {
  const node = document.createElement("select");
  node.dataset.field = field;
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === selected;
    node.appendChild(option);
  }
  return node;
}

function nullableNumber(value) {
  return value == null ? "" : String(value);
}

function addDeleteButton(row, refresh) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "calendar-delete";
  button.textContent = "×";
  button.title = "Usuń";
  button.setAttribute("aria-label", "Usuń");
  button.addEventListener("click", () => { row.remove(); refresh(); markDirty(); });
  row.appendChild(button);
}

function addProfileRow(profile = {}) {
  const host = el("calendarProfilesRows");
  if (!host || host.children.length >= MAX_PROFILES) {
    setMessage(`Maksymalnie ${MAX_PROFILES} profili.`, false);
    return;
  }
  const row = document.createElement("div");
  row.className = "calendar-profile-row";
  row.dataset.calendarProfileRow = "true";
  row.appendChild(input("profile_id", profile.profile_id || "", "text", "np. NORMAL_WORKDAY"));
  row.appendChild(select("mode", MODES, profile.mode || "AUTO"));
  row.appendChild(input("preventilation_minutes", profile.preventilation_minutes ?? 0, "number"));
  row.appendChild(input("purge_minutes", profile.purge_minutes ?? 0, "number"));
  row.appendChild(input("minimum_supply_pct", nullableNumber(profile.minimum_supply_pct), "number"));
  row.appendChild(input("minimum_extract_pct", nullableNumber(profile.minimum_extract_pct), "number"));
  row.appendChild(input("fixed_supply_pct", nullableNumber(profile.fixed_supply_pct), "number"));
  row.appendChild(input("fixed_extract_pct", nullableNumber(profile.fixed_extract_pct), "number"));
  row.appendChild(input("label", profile.label || "", "text", "Opis"));
  addDeleteButton(row, refreshProfileEmpty);
  host.appendChild(row);
  refreshProfileEmpty();
}

function selectorText(rule) {
  if (rule.kind === "WEEKLY") return Array.isArray(rule.weekdays) ? rule.weekdays.join(",") : "";
  if (rule.kind === "SEASON") return Array.isArray(rule.months) ? rule.months.join(",") : "";
  if (rule.kind === "DATE_RANGE") return rule.start_date && rule.end_date ? `${rule.start_date}..${rule.end_date}` : "";
  if (rule.kind === "DATE_EXCEPTION") return rule.start_date || "";
  return "";
}

function addRuleRow(rule = {}) {
  const host = el("calendarRulesRows");
  if (!host || host.children.length >= MAX_RULES) {
    setMessage(`Maksymalnie ${MAX_RULES} reguł.`, false);
    return;
  }
  const row = document.createElement("div");
  row.className = "calendar-rule-row";
  row.dataset.calendarRuleRow = "true";
  row.appendChild(input("rule_id", rule.rule_id || "", "text", "np. MON_FRI"));
  row.appendChild(select("kind", RULE_KINDS, rule.kind || "WEEKLY"));
  row.appendChild(input("profile_id", rule.profile_id || "", "text", "profil"));
  row.appendChild(input("selector", selectorText(rule), "text", "1,2,3,4,5 / 2026-08-10"));
  row.appendChild(input("start_local", rule.start_local || "", "time"));
  row.appendChild(input("end_local", rule.end_local || "", "time"));
  row.appendChild(input("label", rule.label || "", "text", "Opis"));
  const enabledWrap = document.createElement("label");
  enabledWrap.className = "calendar-enabled";
  const enabled = document.createElement("input");
  enabled.type = "checkbox";
  enabled.dataset.field = "enabled";
  enabled.checked = rule.enabled !== false;
  enabledWrap.appendChild(enabled);
  row.appendChild(enabledWrap);
  addDeleteButton(row, refreshRuleEmpty);
  host.appendChild(row);
  refreshRuleEmpty();
}

function refreshProfileEmpty() {
  const host = el("calendarProfilesRows");
  const empty = el("calendarProfilesEmpty");
  if (host && empty) empty.hidden = host.children.length !== 0;
}

function refreshRuleEmpty() {
  const host = el("calendarRulesRows");
  const empty = el("calendarRulesEmpty");
  if (host && empty) empty.hidden = host.children.length !== 0;
}

function renderConfig(config) {
  el("calendarTimezone").value = config && config.timezone ? config.timezone : "Europe/Warsaw";
  const profilesHost = el("calendarProfilesRows");
  const rulesHost = el("calendarRulesRows");
  profilesHost.replaceChildren();
  rulesHost.replaceChildren();
  for (const profile of config && Array.isArray(config.profiles) ? config.profiles : []) addProfileRow(profile);
  for (const rule of config && Array.isArray(config.rules) ? config.rules : []) addRuleRow(rule);
  refreshProfileEmpty();
  refreshRuleEmpty();
}

function field(row, name) { return row.querySelector(`[data-field="${name}"]`); }

function readOptionalNumber(row, name) {
  const raw = field(row, name).value.trim();
  if (!raw) return null;
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`${name}: nieprawidłowa liczba`);
  return value;
}

function readProfiles() {
  const rows = [...el("calendarProfilesRows").querySelectorAll("[data-calendar-profile-row]")];
  if (rows.length > MAX_PROFILES) throw new Error(`Maksymalnie ${MAX_PROFILES} profili.`);
  return rows.map((row, index) => {
    const profile_id = field(row, "profile_id").value.trim();
    if (!profile_id) throw new Error(`Profil ${index + 1}: podaj ID.`);
    const mode = field(row, "mode").value;
    const preventilation_minutes = Number(field(row, "preventilation_minutes").value);
    const purge_minutes = Number(field(row, "purge_minutes").value);
    const profile = {
      profile_id, mode, preventilation_minutes, purge_minutes,
      minimum_supply_pct: readOptionalNumber(row, "minimum_supply_pct"),
      minimum_extract_pct: readOptionalNumber(row, "minimum_extract_pct"),
      fixed_supply_pct: readOptionalNumber(row, "fixed_supply_pct"),
      fixed_extract_pct: readOptionalNumber(row, "fixed_extract_pct"),
      label: field(row, "label").value.trim(),
    };
    if (!Number.isInteger(preventilation_minutes) || !Number.isInteger(purge_minutes)) {
      throw new Error(`Profil ${index + 1}: PRE i PURGE muszą być pełnymi minutami.`);
    }
    return profile;
  });
}

function parseIntegerList(text, min, max, label) {
  if (!text.trim()) throw new Error(`${label}: lista nie może być pusta.`);
  const values = text.split(",").map(item => Number(item.trim()));
  if (values.some(value => !Number.isInteger(value) || value < min || value > max)) {
    throw new Error(`${label}: dozwolony zakres ${min}..${max}.`);
  }
  if (new Set(values).size !== values.length) throw new Error(`${label}: wartości nie mogą się powtarzać.`);
  return values;
}

function readRules() {
  const rows = [...el("calendarRulesRows").querySelectorAll("[data-calendar-rule-row]")];
  if (rows.length > MAX_RULES) throw new Error(`Maksymalnie ${MAX_RULES} reguł.`);
  return rows.map((row, index) => {
    const rule_id = field(row, "rule_id").value.trim();
    const kind = field(row, "kind").value;
    const profile_id = field(row, "profile_id").value.trim();
    if (!rule_id || !profile_id) throw new Error(`Reguła ${index + 1}: podaj ID reguły i profilu.`);
    const selector = field(row, "selector").value.trim();
    const start = field(row, "start_local").value;
    const end = field(row, "end_local").value;
    if ((start && !end) || (!start && end)) throw new Error(`Reguła ${index + 1}: ustaw jednocześnie OD i DO albo pozostaw oba puste.`);
    if (start && start === end) throw new Error(`Reguła ${index + 1}: OD i DO nie mogą być takie same.`);
    const rule = {
      rule_id, kind, profile_id,
      weekdays: [], months: [], start_date: null, end_date: null,
      start_local: start || null,
      end_local: end || null,
      enabled: field(row, "enabled").checked,
      label: field(row, "label").value.trim(),
    };
    if (kind === "WEEKLY") rule.weekdays = parseIntegerList(selector, 1, 7, `Reguła ${index + 1} / dni tygodnia`);
    else if (kind === "SEASON") rule.months = parseIntegerList(selector, 1, 12, `Reguła ${index + 1} / miesiące`);
    else if (kind === "DATE_RANGE") {
      const parts = selector.split("..");
      if (parts.length !== 2 || !parts[0] || !parts[1]) throw new Error(`Reguła ${index + 1}: zakres dat wpisz jako YYYY-MM-DD..YYYY-MM-DD.`);
      rule.start_date = parts[0]; rule.end_date = parts[1];
    } else if (kind === "DATE_EXCEPTION") {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(selector)) throw new Error(`Reguła ${index + 1}: wyjątek daty wpisz jako YYYY-MM-DD.`);
      rule.start_date = selector; rule.end_date = selector;
    }
    return rule;
  });
}

function readConfig() {
  const timezone = el("calendarTimezone").value.trim();
  if (!timezone) throw new Error("Podaj strefę czasową.");
  return {schema_version: 1, timezone, profiles: readProfiles(), rules: readRules()};
}

function setMessage(text, ok = null) {
  const target = el("calendarMessage");
  target.textContent = text || "";
  target.className = `calendar-message${ok === true ? " good" : ok === false ? " bad" : ""}`;
}

function markDirty() { setMessage("Zmiany niezapisane."); }

function setBusy(busy) {
  document.querySelectorAll("[data-calendar-action]").forEach(button => { button.disabled = busy; });
}

async function loadCalendar() {
  try {
    setBusy(true);
    setMessage("Wczytywanie…");
    const payload = await api("/api/v1/calendar");
    calendarSnapshot = payload.calendar;
    renderOverview(calendarSnapshot);
    if (calendarSnapshot && calendarSnapshot.config) renderConfig(calendarSnapshot.config);
    else renderConfig({timezone: "Europe/Warsaw", profiles: [], rules: []});
    setMessage("Wczytano konfigurację z ventilation-core.", true);
  } catch (error) {
    renderOverview({available: false, last_error: String(error.message || error)});
    setMessage(String(error.message || error), false);
  } finally { setBusy(false); }
}

async function saveCalendar() {
  try {
    setBusy(true);
    setMessage("Zapisywanie…");
    const config = readConfig();
    const payload = await api("/api/v1/calendar", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({config}),
    });
    calendarSnapshot = payload.calendar;
    renderOverview(calendarSnapshot);
    if (calendarSnapshot && calendarSnapshot.config) renderConfig(calendarSnapshot.config);
    setMessage("Zapisano atomowo w Calendar Engine.", true);
  } catch (error) {
    setMessage(String(error.message || error), false);
  } finally { setBusy(false); }
}

document.addEventListener("click", event => {
  const action = event.target.closest("[data-calendar-action]");
  if (!action) return;
  if (action.dataset.calendarAction === "add-profile") { addProfileRow(); markDirty(); }
  if (action.dataset.calendarAction === "add-rule") { addRuleRow(); markDirty(); }
  if (action.dataset.calendarAction === "reload") loadCalendar();
  if (action.dataset.calendarAction === "save") saveCalendar();
});

document.addEventListener("input", event => {
  if (event.target.closest("[data-calendar-editor]")) markDirty();
});

loadCalendar();
