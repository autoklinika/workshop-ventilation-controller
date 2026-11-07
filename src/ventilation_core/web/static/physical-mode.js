"use strict";
(() => {
  // Real actuator mode, not the legacy non-actuating SHADOW operator intent.
  // Instantiated only after the STREFY view has been hydrated into the DOM.
  const modeHeading = document.getElementById("wvcModeHeading");
  const manualButton = document.getElementById("wvcManualMode");
  const autoButton = document.getElementById("wvcAutoMode");
  const note = document.getElementById("wvcModeNote");
  if (!modeHeading || !manualButton || !autoButton || !note) return;

  let pending = false;
  let current = null;
  let reachable = false;
  let refreshPending = false;

  function info(message, isError = false) {
    note.textContent = message || "";
    note.dataset.error = isError ? "true" : "false";
  }

  function paint() {
    const a = current && typeof current.active_auto === "object"
      ? current.active_auto : {};
    const isAuto = reachable && a.enabled === true
      && a.active === true && a.hold !== true;
    const fault = a.fault_latched === true;
    const canAuto = reachable && a.enabled === true && !fault && !pending;

    modeHeading.textContent = isAuto ? "Sterowanie automatyczne" : "Sterowanie ręczne";
    manualButton.setAttribute("aria-pressed", String(!isAuto));
    autoButton.setAttribute("aria-pressed", String(isAuto));
    manualButton.disabled = pending || !reachable;
    autoButton.disabled = !canAuto || isAuto;
    manualButton.title = "Przejmij sterowanie ręczne bez zmiany obecnych nastaw";
    autoButton.title = !reachable ? "Brak połączenia z CM5"
      : fault ? "AUTO zablokowane po awarii. Wymagane potwierdzenie serwisowe"
      : !a.enabled ? "AUTO nie zostało jeszcze zatwierdzone lub włączone w CM5"
      : isAuto ? "AUTO jest aktywne" : "Przekaż sterowanie automatowi";
    if (!pending && reachable && fault) {
      info("AWARIA — wymagany serwis", true);
    } else if (!pending && reachable && !a.enabled && !note.dataset.userMessage) {
      info("AUTO wyłączone w CM5");
    }
  }

  async function request(path, options = {}) {
    const response = await fetch(path, {
      cache: "no-store",
      credentials: "same-origin",
      ...options,
    });
    let payload;
    try { payload = await response.json(); }
    catch (_) { throw new Error("Nieprawidłowa odpowiedź CM5"); }
    if (!response.ok || payload.ok !== true) {
      throw new Error(payload.error || ("HTTP " + response.status));
    }
    return payload;
  }

  async function refresh() {
    if (refreshPending || pending) return;
    refreshPending = true;
    try {
      const response = await request("/api/v1/state");
      current = response.state;
      reachable = true;
    } catch (_) {
      reachable = false;
      info("Brak połączenia z CM5", true);
    } finally {
      refreshPending = false;
      paint();
    }
  }

  async function choose(mode) {
    if (pending || !reachable) return;
    if (mode === "AUTO"
        && (current?.active_auto?.enabled !== true
        || current?.active_auto?.fault_latched === true
        || current?.active_auto?.active === true)) return;
    pending = true;
    note.dataset.userMessage = "true";
    info(mode === "AUTO" ? "Włączanie AUTO…" : "Wybieranie MANUAL…");
    paint();
    try {
      const result = await request("/api/v1/physical-mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      current = result.state || current;
      info(mode === "AUTO" ? "AUTO przyjęte przez Core" : "MANUAL aktywne");
    } catch (error) {
      info("Nie wykonano: " + error.message, true);
    } finally {
      pending = false;
      await refresh();
    }
  }

  manualButton.addEventListener("click", () => choose("MANUAL"));
  autoButton.addEventListener("click", () => choose("AUTO"));
  refresh();
  setInterval(refresh, 2000);
})();
