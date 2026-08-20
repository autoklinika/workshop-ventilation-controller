"use strict";

(() => {
  const POWER_ENDPOINT = "/api/v1/system/power";
  let overlay = null;
  let actionInFlight = false;

  function ensurePowerTile() {
    let tile = document.getElementById("hostPowerNav");
    if (tile) return tile;

    const candidates = Array.from(document.querySelectorAll("a.v2-nav"));
    const service = candidates.find((anchor) => {
      const spans = Array.from(anchor.querySelectorAll("span"));
      const label = spans.length ? spans[spans.length - 1].textContent : anchor.textContent;
      return String(label || "").trim().toUpperCase() === "SERWIS";
    });
    if (!service || !service.parentElement) return null;

    tile = document.createElement("button");
    tile.id = "hostPowerNav";
    tile.type = "button";
    tile.className = "v2-nav v2-power-nav";
    tile.setAttribute("aria-label", "Zasilanie CM5");
    tile.innerHTML = `
      <span class="v2-nav-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="M12 3v8"/><path d="M7.05 5.95a8 8 0 1 0 9.9 0"/></svg>
      </span>
      <span>ZASILANIE</span>`;
    service.insertAdjacentElement("afterend", tile);
    tile.addEventListener("click", openModal);
    return tile;
  }

  function ensureModal() {
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.id = "hostPowerModal";
    overlay.className = "v2-host-power";
    overlay.hidden = true;
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "hostPowerTitle");
    overlay.innerHTML = `
      <section class="v2-host-power-card">
        <div class="v2-host-power-head">
          <span class="v2-host-power-icon" aria-hidden="true">⏻</span>
          <div>
            <span class="v2-host-power-kicker">CM5</span>
            <h2 id="hostPowerTitle">ZASILANIE SYSTEMU</h2>
          </div>
        </div>
        <p class="v2-host-power-description">Wybierz operację dla sterownika CM5.</p>
        <p class="v2-host-power-note">Operacja zostanie wykonana przez system Linux. Wyłączenie zatrzyma CM5 do czasu ponownego włączenia zasilania; restart uruchomi system ponownie.</p>
        <p id="hostPowerStatus" class="v2-host-power-status"></p>
        <div class="v2-host-power-actions">
          <button id="hostPowerShutdown" class="v2-host-power-action shutdown" type="button">WYŁĄCZ</button>
          <button id="hostPowerRestart" class="v2-host-power-action restart" type="button">RESTART</button>
        </div>
      </section>`;
    document.body.appendChild(overlay);

    document.getElementById("hostPowerShutdown").addEventListener("click", () => submitAction("shutdown"));
    document.getElementById("hostPowerRestart").addEventListener("click", () => submitAction("restart"));
    overlay.addEventListener("click", (event) => {
      if (!actionInFlight && event.target === overlay) closeModal();
    });
    document.addEventListener("keydown", (event) => {
      if (!actionInFlight && !overlay.hidden && event.key === "Escape") {
        event.preventDefault();
        closeModal();
      }
    });
    return overlay;
  }

  function openModal() {
    const modal = ensureModal();
    actionInFlight = false;
    setButtonsDisabled(false);
    setStatus("");
    modal.hidden = false;
    document.getElementById("hostPowerRestart").focus({ preventScroll: true });
  }

  function closeModal() {
    if (!overlay || actionInFlight) return;
    overlay.hidden = true;
  }

  function setButtonsDisabled(disabled) {
    const shutdown = document.getElementById("hostPowerShutdown");
    const restart = document.getElementById("hostPowerRestart");
    if (shutdown) shutdown.disabled = disabled;
    if (restart) restart.disabled = disabled;
  }

  function setStatus(text, bad = false) {
    const status = document.getElementById("hostPowerStatus");
    if (!status) return;
    status.textContent = text;
    status.className = bad ? "v2-host-power-status bad" : "v2-host-power-status";
  }

  async function submitAction(action) {
    if (actionInFlight) return;
    if (action !== "shutdown" && action !== "restart") return;

    actionInFlight = true;
    setButtonsDisabled(true);
    setStatus(action === "shutdown" ? "Wysyłanie polecenia wyłączenia…" : "Wysyłanie polecenia restartu…");

    try {
      const response = await fetch(POWER_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const payload = await response.json();
      if (!response.ok || payload.ok !== true || payload.accepted !== true || payload.action !== action) {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      setStatus(action === "shutdown" ? "Polecenie przyjęte. CM5 wyłącza się…" : "Polecenie przyjęte. CM5 restartuje się…");
    } catch (error) {
      actionInFlight = false;
      setButtonsDisabled(false);
      setStatus(`Nie udało się wykonać operacji: ${String(error.message || error)}`, true);
    }
  }

  ensurePowerTile();
  ensureModal();
})();
