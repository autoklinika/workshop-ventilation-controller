# WebGUI Automation Stage 2 — walidacja fizyczna CM5

Data: 2026-08-29
Repozytorium: `autoklinika/workshop-ventilation-controller`
Gałąź: `agent/web-gui-automation-stage2-runtime`
Walidowany SHA: `b6560697e8a1d2d0f28db7c762d1120d695e4999`
Produkcja `main`: `7628c407cfc9c0ea72d262566759ea2d4598fec8`

## Wynik

**PHYSICAL CM5 VALIDATION: PASS**

Kod wyjścia harnessu: `RC=0`.

Walidacja została wykonana na rzeczywistym CM5 z realnym `ventilation-core`, realnym socketem core i realną telemetrią sprzętową. Control Engine przez cały test pozostał wyłącznie w trybie SHADOW i bez uprawnień do sterowania fizycznego.

## Zakres walidacji

Harness:

`tools/install_validate_web_gui_automation_stage2_runtime_cm5.sh`

WebGUI testowe:

`http://127.0.0.1:18094`

Izolowana baza automatyki:

`/var/tmp/wvc-webgui-automation-stage2-runtime/automation.sqlite3`

## Potwierdzone warunki wejściowe

- produkcyjny checkout pozostał na `main`,
- produkcyjny `main` był czysty,
- `ventilation-core.service` działał z produkcyjnego katalogu,
- EC supply/extract: `0.0 V`,
- brak obserwowanego ruchu wentylatorów,
- host-power pozostał niezmieniony,
- RTC wakealarm pozostał niezmieniony,
- boot ID pozostał niezmieniony.

## Wyniki Stage 2

1. Dokładny SHA brancha został uruchomiony w izolowanym worktree.
2. Branch `ventilation-core` wystartował z izolowaną bazą automatyki i bez `--enable-scheduled-shutdown`.
3. Po starcie branch core:
   - EC pozostały na `0 V`,
   - brak ruchu wentylatorów,
   - Control Engine pozostał SHADOW-only,
   - `actuation_supported=false`,
   - `actuation_authorized=false`,
   - readiness pozostało `false`.
4. Fizycznie zwalidowany parametr TACHO `tacho_failure_confirmation_seconds=4.0 s` został zastosowany wyłącznie do izolowanej konfiguracji Stage 2.
5. WebGUI wystartował na porcie `18094` i połączył się z realnym socketem branch core.
6. `/automation` poprawnie obsłużyło cztery zakładki SHADOW z realnym runtime.
7. WebGUI odczytało realny stan `ventilation-core`, w tym:
   - AUTO SHADOW,
   - EC `0 V`,
   - TACHO confirmation `4.0 s`,
   - readiness i brak authority.
8. Realne pole operatora zwracane przez core zostało poprawnie znormalizowane przez WebAPI do kontraktu WebGUI.
9. Początkowy operator intent był `AUTO` i volatile.
10. Round-trip Harmonogramu przez WebGUI do realnego Calendar Engine zakończył się powodzeniem w izolowanej bazie:
    - revision `1 -> 2`.
11. Tuning ledger pozostał read-only, bez runtime binding i raportował dokładnie `1/9` grup ukończonych.
12. `AUTO -> MANUAL -> AUTO` został wykonany przez WebGUI do realnego Control Engine SHADOW:
    - MANUAL dotarł do realnego Control Engine,
    - EC pozostały fizycznie na `0 V`,
    - AERO pozostał zatrzymany,
    - powrót do AUTO zakończył się poprawnie.
13. Po restarcie realnego branch `ventilation-core`:
    - Calendar Engine zachował konfigurację i revision `2`,
    - volatile operator intent został wyzerowany do `AUTO revision 0`,
    - WebGUI ponownie połączyło się z realnym runtime,
    - Control Engine nadal pozostał non-actuating.
14. Po końcowej fazie verify:
    - EC nadal `0 V`,
    - brak obserwowanego ruchu,
    - SHADOW bez authority,
    - host-power bez zmian,
    - RTC bez zmian,
    - boot ID bez zmian.

## Rollback

Rollback zakończył się powodzeniem.

Potwierdzono:

- produkcyjny `ventilation-core` wrócił do katalogu `main`,
- EC po rollbacku: `0 V`,
- brak obserwowanego ruchu wentylatorów,
- produkcyjne rekordy SQLite `calendar_configuration` i `control_engine_configuration` pozostały niezmienione,
- host-power pozostał niezmieniony,
- RTC wakealarm pozostał niezmieniony,
- boot ID pozostał niezmieniony,
- produkcyjny checkout pozostał czysty na SHA `7628c407cfc9c0ea72d262566759ea2d4598fec8`.

## Bezpieczeństwo

Podczas walidacji nie przyznano Control Engine authority do fizycznego sterowania.

Nie wykonano przez Stage 2:

- fizycznego `set` dla EC,
- `stop` jako ścieżki sterowania Stage 2,
- `aero-speed`,
- `aero-airing`,
- shutdown,
- reboot,
- scheduled shutdown.

## Korekta incydentu z terminalem

Pierwsze uruchomienie walidacji zostało wykonane z wrapperem kończącym się `exit $RC`, co zamknęło sesję terminala i uniemożliwiło zachowanie końcowego kodu wyjścia. Nie był to restart CM5.

Diagnostyka wykazała, że aktualny boot CM5 rozpoczął się o `2026-08-29 14:09:55`, natomiast Stage 2 działał około `14:22`. Powtórna walidacja bez `exit` zakończyła się pełnym `RC=0` i jest wynikiem autorytatywnym dla tego raportu.

## Konkluzja

WebGUI Automation Stage 2 jest **fizycznie zwalidowane na CM5** dla integracji z realnym Control Engine runtime przy zachowaniu granicy SHADOW-only.

Stage 2 nie nadaje jeszcze Control Engine żadnej authority do fizycznego sterowania. Ten etap potwierdza wyłącznie poprawność integracji WebGUI ↔ realny runtime, persistence Harmonogramu, volatile operator intent, widoczność TACHO/readiness oraz brak efektów ubocznych na produkcji.

Nie wykonano merge do `main` i nie oznaczono PR jako Ready for Review.
