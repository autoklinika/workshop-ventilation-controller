"use strict";

(() => {
  const POWER_ENDPOINT = "/api/v1/system/power";
  let overlay = null;
  let actionInFlight = false;

  function installStyles() {
    if (document.getElementById("hostPowerStyles")) return;
    const style = document.createElement("style");
    style.id = "hostPowerStyles";
    style.textContent = `
      .v2-power-nav{appearance:none;width:100%;border:0;background:transparent;font-family:inherit;cursor:pointer}
      .v2-power-nav:hover{color:#d5f3ff;background:rgba(42,112,151,.12)}
      .v2-power-nav .v2-nav-icon{color:#78c8ee}
      .v2-host-power[hidden]{display:none!important}
      .v2-host-power{position:fixed;inset:0;z-index:1100;display:grid;place-items:center;padding:28px;background:rgba(2,8,14,.76);backdrop-filter:blur(5px);box-sizing:border-box}
      .v2-host-power-card{width:min(640px,calc(100vw - 56px));padding:28px;background:linear-gradient(180deg,#17242e,#0c1720);border:1px solid rgba(90,181,226,.46);border-radius:18px;box-shadow:0 28px 80px rgba(0,0,0,.55),inset 0 0 36px rgba(75,180,230,.04);color:#edf4f8}
      .v2-host-power-head{display:flex;align-items:center;gap:16px;margin-bottom:14px}
      .v2-host-power-icon{width:52px;height:52px;flex:0 0 52px;display:grid;place-items:center;border-radius:50%;background:rgba(42,126,170,.16);border:1px solid rgba(99,194,239,.48);color:#86d5f7;font-size:1.8rem;font-weight:800;line-height:1}
      .v2-host-power-kicker{display:block;margin-bottom:3px;color:#7ccced;font-size:.72rem;font-weight:800;letter-spacing:.16em}
      .v2-host-power-card h2{margin:0;color:#fff;font-size:1.55rem;letter-spacing:.03em}
      .v2-host-power-description{margin:0 0 14px;color:#c4d0d7;font-size:.98rem;line-height:1.5}
      .v2-host-power-note{margin:0 0 20px;padding:12px 14px;border:1px solid rgba(99,171,207,.2);border-radius:10px;background:rgba(28,70,94,.14);color:#9fb3c0;font-size:.83rem;line-height:1.45}
      .v2-host-power-status{min-height:22px;margin:0 0 14px;color:#8fb8cc;font-size:.82rem}
      .v2-host-power-status.bad{color:#ff9f9f}
      .v2-host-power-actions{display:grid;grid-template-columns:1fr 1fr;gap:14px}
      .v2-host-power-action{min-height:52px;border-radius:10px;font:inherit;font-weight:800;letter-spacing:.05em;cursor:pointer}
      .v2-host-power-action.shutdown{border:1px solid rgba(151,180,198,.48);background:linear-gradient(180deg,#314653,#253742);color:#edf6fa}
      .v2-host-power-action.restart{border:1px solid rgba(85,190,236,.58);background:linear-gradient(180deg,#1d6f98,#155573);color:#effbff}
      .v2-host-power-action:disabled{opacity:.6;cursor:wait}
      .v2-host-power-action:focus-visible{outline:3px solid rgba(150,221,255,.72);outline-offset:3px}
      @media(max-width:700px){.v2-host-power{padding:16px}.v2-host-power-card{width:calc(100vw - 32px);padding:22px}.v2-host-power-actions{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

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

  installStyles();
  ensurePowerTile();
  ensureModal();
})();
