# WebGUI Automation Stage2 — integracja z realnym Control Engine

Data: 2026-08-29

## Cel

Stage2 waliduje ekran `/automation` przeciwko prawdziwemu `ventilation-core` uruchomionemu na CM5, a nie przeciwko fake-core użytemu w Stage1.

Control Engine pozostaje wyłącznie SHADOW. Stage2 nie dodaje authority ani fizycznej ścieżki sterowania.

## Architektura testu CM5

- produkcyjny `main` pozostaje źródłem prawdy i jest pinowany do `7628c407cfc9c0ea72d262566759ea2d4598fec8`,
- exact CI-tested Stage2 SHA jest uruchamiany w detached worktree,
- branch `ventilation-core` używa realnych interfejsów sprzętowych CM5,
- Calendar Engine i Control Engine używają wyłącznie izolowanego `/var/tmp/wvc-webgui-automation-stage2-runtime/automation.sqlite3`,
- staged WebGUI działa lokalnie na `127.0.0.1:18094`,
- staged WebGUI łączy się z realnym branch core socketem `/run/workshop-ventilation/ventilation-core.sock`,
- scheduled shutdown pozostaje wyłączony,
- host-power i RTC są tylko obserwowane pod kątem niezmienności.

## Walidowane round-tripy

1. `/api/v1/state` — realny stan core, SHADOW, TACHO i readiness przy fizycznym 0 V.
2. `/api/v1/automation/operator` — realny operator runtime.
3. `AUTO -> MANUAL -> AUTO` — wyłącznie operator intent SHADOW; fizyczne EC/AERO muszą pozostać zatrzymane.
4. `/api/v1/calendar` — zapis tej samej konfiguracji przez WebGUI do realnego Calendar Engine w izolowanym SQLite; revision musi wzrosnąć dokładnie o 1.
5. Restart branch core — Calendar config/revision musi przetrwać, natomiast volatile operator intent musi wrócić do `AUTO`, revision `0`.
6. Tuning ledger — read-only, unbound, dokładnie `1/9`.
7. TACHO confirmation — fizycznie zwalidowane `4.0 s` musi być widoczne w live SHADOW state.

## Poprawka kontraktu odkryta przed CM5

Realny `ControlEngineCoreServer` zwraca stan operatora jako pole `operator`. Stage1 fake-core używał pola `control_engine_operator`.

Stage2 normalizuje realną odpowiedź w warstwie WebAPI do stabilnego kontraktu:

- core: `operator`,
- WebAPI: `control_engine_operator`.

Request `AUTO` pozostaje kanoniczny i jest wysyłany do core jako dokładnie `{"mode":"AUTO"}`. Diagnostyczny stan operatora zwracany przez core może zawierać trzy pola MANUAL ustawione na `null`, zgodnie z `OperatorControlIntent.to_dict()`.

## Safety invariants

- `actuation_supported=false`,
- `actuation_authorized=false`,
- `readiness=false`,
- fizyczne setpointy EC `0.0 V`,
- brak obserwowanego ruchu TACHO,
- brak komend `set`, `stop`, `aero-speed`, `aero-airing`, shutdown/reboot,
- produkcyjne wiersze `calendar_configuration` i `control_engine_configuration` muszą być identyczne przed/po teście,
- boot ID, host-power PID/status i RTC wakealarm muszą pozostać bez zmian,
- po rollbacku `ventilation-core` musi wrócić do CWD produkcyjnego `main`.

## Pliki

- `tools/validate_web_gui_automation_stage2_runtime_cm5.py`
- `tools/install_validate_web_gui_automation_stage2_runtime_cm5.sh`
- `tests/test_web_gui_automation_stage2_runtime.py`

## Status

Software/CI: PENDING.

Physical CM5 validation: PENDING.
