"use strict";
(() => {
  // This widget controls the actual ventilation-core authority, NOT SHADOW.
  // Existing dashboard / STREFY scripts remain unchanged.
  const els = {
    mode: document.getElementById("wvcPhysicalMode"),
    description: document.getElementById("wvcModeDescription"),
    manual: document.getElementById("wvcManualMode"),
    auto: document.getElementById("wvcAutoMode"),
    pin: document.getElementById("wvcAutoPin"),
    confirm: document.getElementById("wvcAutoConfirm"),
    message: document.getElementById("wvcModeMessage"),
  };
  if (Object.values(els).some(node => !node)) return;
  let latest = null;
  let coreOnline = false;
  let pinConfigured = false;
  let pending = false;
  let pollPending = false;

  function message(text, kind = "") {
    els.message.textContent = text;
    els.message.dataset.kind = kind;
  }

  function render() {
    const a = latest && typeof latest.active_auto === "object" ? latest.active_auto : {};
    const autoActive = a.active === true && a.hold !== true;
    const fault = a.fault_latched === true;
    const enabled = a.enabled === true;
    const manual = !autoActive;
    els.mode.textContent = !coreOnline ? "BRAK ŁĄCZNOŚCI"
      : fault ? "MANUAL · AWARIA"
      : autoActive ? "AUTO · AKTYWNE" : "MANUAL";
    els.mode.dataset.state = fault ? "fault" : autoActive ? "auto" : "manual";

    let detail = "Stan fizycznego sterowania jest niedostępny.";
    if (coreOnline) {
      if (fault) {
        detail = "AWARIA: " + (a.hold_reason || "nieznana")
          + ". Przerwij emisję zanieczyszczeń; wymagany serwis.";
      } else if (!enabled) {
        detail = "AUTO wyłączone w CM5 lub brak zatwierdzenia. Sterowanie ręczne działa w STREFACH.";
      } else if (autoActive) {
        detail = "CM5 steruje EC i AERO. MANUAL blokuje dalsze automatyczne polecenia.";
      } else {
        detail = "MANUAL: ustaw wentylatory ręcznie w STREFACH. Aktualne wyjścia nie zmieniają się przy przełączeniu.";
      }
      if (!pinConfigured && enabled && !fault) {
        detail += " PIN operatora nie jest skonfigurowany.";
      }
    }
    els.description.textContent = detail;
    els.manual.disabled = pending || !coreOnline;
    els.manual.setAttribute("aria-pressed", String(manual));
    const canResume = coreOnline && enabled && !fault && !autoActive && pinConfigured && !pending;
    els.pin.disabled = !canResume;
    els.confirm.disabled = !canResume;
    els.auto.disabled = !canResume || els.confirm.checked !== true
      || !/^[0-9]{6,12}$/.test(els.pin.value);
    els.auto.setAttribute("aria-pressed", String(autoActive));
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      cache: "no-store",
      credentials: "same-origin",
      ...options,
    });
    let payload;
    try { payload = await response.json(); }
    catch (_) { throw new Error("Nieprawidłowa odpowiedź CM5: HTTP " + response.status); }
    if (!response.ok || payload.ok !== true) {
      throw new Error(payload.error || ("HTTP " + response.status));
    }
    return payload;
  }

  async function poll() {
    if (pollPending || pending) return;
    pollPending = true;
    try {
      const [state, status] = await Promise.all([
        api("/api/v1/state"),
        api("/api/v1/auto"),
      ]);
      latest = state.state;
      pinConfigured = status.web_auto_pin_configured === true;
      coreOnline = true;
    } catch (_) {
      coreOnline = false;
      pinConfigured = false;
    } finally {
      pollPending = false;
      render();
    }
  }

  els.pin.addEventListener("input", render);
  els.confirm.addEventListener("change", render);
  els.manual.addEventListener("click", async () => {
    if (pending || !coreOnline) return;
    pending = true;
    render();
    message("Przełączam na sterowanie ręczne…");
    try {
      await api("/api/v1/physical-mode", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({mode: "MANUAL"}),
      });
      message("MANUAL potwierdzony. AUTO nie wyda nowych poleceń. Ustawienia EC i AERO pozostają bez zmian.", "success");
    } catch (error) {
      message("Nie potwierdzono przejścia na MANUAL: " + error.message, "error");
    } finally {
      pending = false;
      await poll();
    }
  });

  els.auto.addEventListener("click", async () => {
    if (pending || !coreOnline || !pinConfigured || latest?.active_auto?.enabled !== true
        || latest?.active_auto?.fault_latched === true
        || els.confirm.checked !== true
        || !/^[0-9]{6,12}$/.test(els.pin.value)) return;
    pending = true;
    render();
    message("Weryfikuję PIN i warunki bezpiecznego AUTO…");
    try {
      await api("/api/v1/physical-mode", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({mode:"AUTO", pin:els.pin.value, confirm:true}),
      });
      message("AUTO potwierdzone przez ventilation-core.", "success");
    } catch (error) {
      message("AUTO zablokowane: " + error.message, "error");
    } finally {
      els.pin.value = "";
      els.confirm.checked = false;
      pending = false;
      await poll();
    }
  });

  render();
  poll();
  setInterval(poll, 3000);
})();
