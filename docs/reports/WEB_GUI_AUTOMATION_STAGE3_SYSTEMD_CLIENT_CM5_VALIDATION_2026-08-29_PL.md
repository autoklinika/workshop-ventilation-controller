# WebGUI Automation Stage 3 — walidacja CM5 klienta systemd

Data: 2026-08-29

## Wynik

**PHYSICAL CM5 PASS**

Walidacja zakończyła się kodem `STAGE3 RC=0` dla dokładnego kandydata:

`7d29c09a842a2888294a57d1611ea1f0609f4a39`

Produkcja podczas testu była przypięta do:

`7628c407cfc9c0ea72d262566759ea2d4598fec8`

## Architektura potwierdzona w teście

- WebGUI pozostaje wyłącznie klientem authoritative `ventilation-core`.
- Docelowy port WebGUI: `18091`.
- Fizyczna walidacja używała rzeczywistego `wvc-web-ui.service`, a nie procesu uruchomionego ręcznie.
- WebGUI nie posiada authority do fizycznego sterowania wentylacją.
- Żądania operatora WebGUI korzystają z kontraktu `require_shadow_only=true`, egzekwowanego przez core.

## CI

Dla dokładnego SHA `7d29c09a842a2888294a57d1611ea1f0609f4a39`:

- GitHub Actions: `Ventilation Core Tests`, run `33253940189` — PASS.
- `python -m compileall -q src` — PASS.
- `Ran 1061 tests in 7.379s`.
- `OK`.

## Pierwsza próba fizyczna

Pierwszy kandydat `427fad5d2a80cfec5255a07b4287bca01eb07bac` przeszedł kroki uruchomienia realnego WebGUI systemd i round-trip SHADOW, ale zakończył się `RC=1` na początku testu restartu samego WebGUI. Rollback był poprawny.

Nie uznano tej próby za PASS. Harness został utwardzony tak, aby restart WebGUI czekał na stabilny `MainPID` i właściwy CWD oraz publikował diagnostykę `systemctl status` / `journalctl` w przypadku błędu.

Po zmianie powstał kandydat `7d29c09a842a2888294a57d1611ea1f0609f4a39`, który przeszedł pełne CI i późniejszą walidację fizyczną.

## Przebieg końcowej walidacji

### 1. Preflight produkcji

PASS:

- produkcyjny core działał z `main`,
- EC = `0 V`,
- brak obserwowanego ruchu wentylatorów,
- boot bez zmian,
- proces i stan `wvc-host-power.service` bez zmian,
- RTC wakealarm bez zmian,
- produkcyjny WebGUI był `active`, `enabled`, port environment `18091`.

### 2. Dokładny worktree Stage 3 i izolowany realny core

PASS:

- detached worktree na dokładnym SHA `7d29c09a842a2888294a57d1611ea1f0609f4a39`,
- branch core używał izolowanej bazy automatyki,
- scheduled shutdown pozostawał wyłączony,
- EC = `0 V`, brak ruchu,
- Control Engine pozostawał SHADOW / non-actuating,
- boot, host-power i RTC bez zmian.

### 3. Walidowany parametr TACHO 4.0 s

PASS:

- do izolowanego Control Engine zastosowano wyłącznie fizycznie zwalidowane `tacho_failure_confirmation_seconds = 4.0 s`,
- EC nadal `0 V`, brak ruchu,
- SHADOW non-actuating,
- host/RTC/boot bez zmian.

### 4. Rzeczywisty `wvc-web-ui.service` na porcie 18091

PASS:

- `wvc-web-ui.service` uruchomił kod Stage 3 z worktree,
- WebGUI działał jako klient na porcie `18091`,
- WebGUI był podłączony do rzeczywistego socketu branch core,
- fizyczne wyjścia pozostały w stanie bezpiecznym.

### 5. Round-trip klienta przez realny systemd WebGUI

PASS:

- `/automation` udostępniał czterozakładkowy interfejs SHADOW,
- realny stan `ventilation-core` docierał do WebGUI,
- AUTO SHADOW, EC = `0 V`, TACHO confirmation = `4.0 s`,
- WebGUI poprawnie normalizował operator response realnego core,
- początkowy operator był volatile AUTO,
- Harmonogram WebGUI -> real Calendar Engine: revision `1 -> 2`,
- tuning ledger read-only/unbound: dokładnie `1/9`,
- MANUAL z WebGUI dotarł wyłącznie do realnego Control Engine SHADOW,
- fizyczne EC pozostały `0 V`,
- powrót AUTO był non-actuating.

### 6. Restart wyłącznie klienta WebGUI

PASS:

- `wvc-web-ui.service` otrzymał nowy PID,
- authoritative core nie został zrestartowany,
- stan operatora i Calendar Engine należący do core pozostał zachowany,
- WebGUI po restarcie ponownie działał jako klient na `18091`,
- tuning ledger nadal `1/9`,
- EC = `0 V`, brak ruchu,
- SHADOW non-actuating,
- boot/host-power/RTC bez zmian.

Wniosek: restart klienta WebGUI nie wpływa na authoritative runtime i nie przejmuje własności stanu automatyki.

### 7. Restart authoritative core przy działającym WebGUI

PASS:

- branch core został zrestartowany z dokładnym worktree i izolowaną DB,
- `wvc-web-ui.service` zachował ten sam PID,
- WebGUI jako niezależny klient przeżył restart core,
- volatile operator history został wyczyszczony,
- operator wrócił do `AUTO revision 0`,
- Calendar Engine zachował persisted revision `2`,
- tuning ledger nadal read-only/unbound `1/9`,
- WebGUI po restarcie core pozostał związany z non-actuating Control Engine runtime,
- EC = `0 V`, brak ruchu,
- boot/host-power/RTC bez zmian.

### 8. Końcowe invarianty bezpieczeństwa

PASS:

- WebGUI pozostawał klientem authoritative `ventilation-core`,
- operator writes używały core-enforced SHADOW-only contract,
- physical EC/AERO pozostały zatrzymane,
- `actuation_authorized=false`,
- `readiness=false`,
- brak fizycznego authority,
- produkcyjne wiersze SQLite Calendar/Control Engine nie zostały zmienione,
- rollback przywrócił produkcyjny `main`,
- produkcyjny `wvc-web-ui.service` przywrócony z portem `18091`,
- produkcyjny `main` pozostał czysty na SHA `7628c407cfc9c0ea72d262566759ea2d4598fec8`.

## Klasyfikacja

**Stage 3 = PHYSICAL CM5 PASS dla kodu `7d29c09a842a2888294a57d1611ea1f0609f4a39`.**

Commit zawierający ten raport jest wyłącznie commitem dokumentacyjnym i nie zmienia SHA kodu fizycznie przetestowanego.

## Workflow

- Bez merge do `main`.
- PR pozostaje Draft.
- Bez Ready for Review bez wyraźnego polecenia użytkownika.
- Control Engine pozostaje SHADOW / non-actuating.
