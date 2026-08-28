# Control Engine V1 — Stage10: read-only workshop commissioning capture

Data: 2026-08-28

## 1. Cel

Stage10 przygotowuje narzędzia do zebrania reprezentatywnych danych dopiero po montażu systemu w finalnym warsztacie. Nie służy do strojenia na danych LAB.

Capture i validator są rozdzielone od Control Engine configuration oraz od aktuatorów.

## 2. Capture

Dodano:

`tools/control_engine_commissioning_capture.py`

Właściwości:

- wymaga jawnego `--confirm-workshop-commissioning YES`,
- dataset zawsze ma `environment = WORKSHOP`,
- do core wysyłana jest wyłącznie komenda `status`,
- zapisuje pełny autorytatywny `CoreState` jako JSONL,
- nagłówek sesji zawiera `actuation_authority_granted=false` oraz `core_writes_performed=false`,
- każdy sample wymaga `shadow_automation.actuation_supported=false`,
- plik jest tworzony w trybie exclusive — istniejący dataset nie jest cicho nadpisywany,
- brak `set`, `stop`, `shutdown`, `control-engine-replace`, AERO commands, `systemctl` i `subprocess`.

Stage10 nie uruchamia wentylatorów. Jeśli podczas przyszłego commissioning operator lub osobny zatwierdzony test sprzętowy zmienia rzeczywiste setpointy, capture jedynie obserwuje ich autorytatywny stan.

## 3. Offline dataset validator

Dodano:

`tools/control_engine_validate_commissioning_dataset.py`

Validator:

- nie łączy się z core,
- nie wykonuje writes,
- nie generuje tuning recommendation,
- wymaga nagłówka `WORKSHOP` i źródła `ventilation-core:status`,
- wymaga SHADOW-only w każdym sample,
- sprawdza spójność session id, sequence i timestampów,
- raportuje pokrycie m.in.:
  - hardware ready / output state known,
  - SEN55 zone-1 usability,
  - supply-temperature usability,
  - zakres rzeczywistych setpointów 0–10 V,
  - zakres RPM supply/extract,
  - zakres temperatur inside/outside,
  - poziomy AQ,
  - fazy Calendar,
  - statusy SHADOW.

Przykładowe coverage warnings:

- `HARDWARE_NOT_READY_IN_SOME_SAMPLES`
- `OUTPUT_STATE_UNKNOWN_IN_SOME_SAMPLES`
- `NO_USABLE_ZONE1_SEN55_SAMPLES`
- `NO_USABLE_SUPPLY_TEMPERATURE_SAMPLES`
- `NO_NONZERO_LOCAL_FAN_SETPOINTS`
- `AIR_QUALITY_COVERAGE_TOO_NARROW_FOR_DYNAMICS_TUNING`
- `CALENDAR_PHASE_COVERAGE_TOO_NARROW`

Brak warningów oznacza wyłącznie, że dataset ma minimalne pokrycie do **manual commissioning review**. Nie oznacza automatycznej akceptacji nastaw ani BHP.

## 4. Testy

Dodano:

`tests/test_control_engine_commissioning_capture.py`

Testy potwierdzają:

- capture wysyła tylko `{ "command": "status" }`,
- dataset jest oznaczony jako WORKSHOP/read-only,
- syntetyczny dataset z różnym AQ/Calendar i niezerowymi setpointami przechodzi minimalne coverage,
- dataset z samymi 0 V jest poprawnie odrzucony jako niewystarczający do manual tuning review,
- validator nie generuje rekomendacji i nie grantuje authority,
- capture source nie zawiera ścieżek sterujących.

Checkpoint:

`d606296b3e89150a6b6bd6adfdd2ccee11538ce4`

GitHub Actions `33175908322`: SUCCESS — compile PASS, unit tests PASS.

## 5. Związek ze Stage9

Stage9 definiuje poziom evidence i commissioning candidate. Stage10 dostarcza materiał dowodowy, który będzie można podpiąć pod grupy wymagające `WORKSHOP_VALIDATED`.

Obecnie nadal:

- tylko `tacho_confirmation` spełnia wymagany poziom,
- wszystkie pozostałe wartości produkcyjne pozostają `null`,
- runtime nie ma związanego validation profile,
- `ACTUATION_AUTHORITY_NOT_IMPLEMENTED` pozostaje twardą blokadą,
- PR #86 pozostaje SHADOW-only.

## 6. Wynik

**PASS — pipeline zbierania i offline walidacji przyszłych danych commissioning jest gotowy software’owo.**

Nie jest potrzebny kolejny test fizyczny w LAB. Następny istotny krok dla brakujących 8/9 grup nastąpi dopiero po zainstalowaniu systemu w reprezentatywnym warsztacie i zebraniu rzeczywistych sesji Stage10.
