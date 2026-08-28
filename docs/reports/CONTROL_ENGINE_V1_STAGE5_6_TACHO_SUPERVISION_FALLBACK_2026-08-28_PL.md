# Automation Control Engine V1 — Stage 5/6 TACHO supervision i fallback

Data: 2026-08-28

Branch: `agent/automation-v1-control-engine`

PR: #86 — Draft, stacked na `agent/automation-v1-scheduler-assumptions`

## 1. Cel

Stage 5/6 rozszerza nieaktuacyjny Control Engine SHADOW o nadzór rzeczywistego sygnału TACHO lokalnych wentylatorów EC oraz jawny kontrakt polityki awaryjnej zależnej od uszkodzonego kanału.

Kluczowa zasada: brak impulsów TACHO przy rzeczywistym zadaniu 0 V jest stanem normalnym i nie może być klasyfikowany jako awaria.

Supervisor analizuje wyłącznie rzeczywiste `CoreState.setpoints` 0–10 V. Nigdy nie uzbraja nadzoru na podstawie procentów proponowanych przez SHADOW. Dzięki temu podczas obecnego shadow mode propozycja np. 70% przy fizycznym 0 V nie generuje fałszywego faultu.

## 2. Stage 5 — supervision foundation

Dodano stanowy `TachoSupervisionTracker` oraz integrację `TachoShadowSupervisor`.

Statusy kanału:

- `NOT_REQUIRED` — kanał ma 0 V, feedback nie jest wymagany,
- `HEALTHY` — kanał jest wysterowany i TACHO jest poprawne,
- `CONFIRMING` — kanał jest wysterowany, feedback nie jest jeszcze poprawny, trwa jawny czas potwierdzenia/spin-up,
- `CONFIRMATION_TUNING_REQUIRED` — wymagany jest feedback, ale nie skonfigurowano czasu potwierdzenia,
- `FEEDBACK_MISSING_CONFIRMED` — brak feedbacku został potwierdzony po skonfigurowanym czasie,
- `MONITOR_UNAVAILABLE` — monitor TACHO jest niedostępny przy wymaganym feedbacku,
- `CHANNEL_UNAVAILABLE` — wymagany kanał TACHO nie istnieje w monitorze.

Nowy parametr konfiguracyjny:

` tacho_failure_confirmation_seconds `

Domyślnie pozostaje `None`. Control Engine nie ma ukrytego domyślnego czasu startu ani potwierdzenia awarii.

## 3. Zachowanie stanowe

Zweryfikowany lifecycle syntetyczny:

1. 0 V / 0 V -> oba kanały `NOT_REQUIRED`,
2. rzeczywiste 2 V / 2 V bez impulsów -> `CONFIRMING`,
3. przed upływem czasu -> nadal `CONFIRMING`,
4. po upływie czasu -> `FEEDBACK_MISSING_CONFIRMED`,
5. recovery jednego kanału -> drugi fault pozostaje aktywny,
6. recovery obu kanałów -> oba `HEALTHY`, logiczny request wraca,
7. STOP / 0 V -> stan pending jest kasowany, oba `NOT_REQUIRED`.

Recovery oraz STOP zerują oczekujący licznik awarii. Nie ma dziedziczenia starego pending po ponownym uruchomieniu kanału.

## 4. Stage 6 — jawny fallback kanałowy

Nie zastosowano jednej wspólnej reakcji ani reguły kombinującej. Polityka rozróżnia dokładnie trzy maski faultu:

- `SUPPLY`,
- `EXTRACT`,
- `BOTH`.

Każda maska ma własną, niezależną parę logicznych nastaw:

- `tacho_supply_fault_fallback_supply_pct`
- `tacho_supply_fault_fallback_extract_pct`
- `tacho_extract_fault_fallback_supply_pct`
- `tacho_extract_fault_fallback_extract_pct`
- `tacho_both_fault_fallback_supply_pct`
- `tacho_both_fault_fallback_extract_pct`

Wszystkie sześć pól produkcyjnie pozostaje `None`.

Nie ma:

- automatycznego `max()`,
- kopiowania nastawy z innej maski,
- domyślnego STOP,
- domyślnego MAX,
- wyliczania reakcji z innych parametrów.

Każda para musi zostać osobno określona po walidacji fizycznej.

## 5. Walidacja konfiguracji

Kontrakt konfiguracji wymusza:

- zakres 0..100%,
- brak coercion bool/string -> number,
- kompletność pary supply/extract dla każdej maski,
- `None` jako jawny stan nieskonfigurowany,
- persistence w istniejącym `automation.sqlite3`,
- poprawny round-trip po restarcie store.

Częściowa konfiguracja, np. tylko supply dla maski `SUPPLY`, jest odrzucana przed zapisem.

## 6. Priorytety decyzji

Jeżeli TACHO fault jest potwierdzony:

- przy braku odpowiedniego fallbacku: `automation_state=FAULT`, finalny request jest `None`,
- przy skonfigurowanym dokładnym fallbacku i poprawnym bazowym kontekście: SHADOW publikuje dokładną skonfigurowaną parę jako logiczny fallback,
- jeżeli bazowy kontekst sterowania jest niedostępny z innej przyczyny: fallback TACHO nie maskuje tej awarii i nie tworzy requestu,
- `BLOCKED_SAFETY` ma pierwszeństwo nad fallbackiem TACHO; fallback nie może odtworzyć requestu przez aktywną blokadę safety.

Diagnostyka publikuje m.in.:

- `tacho_fault_pattern`,
- `tacho_fallback_applied`,
- `tacho_fallback_supply_pct`,
- `tacho_fallback_extract_pct`,
- status/required/valid/rpm/pending/fault dla obu kanałów.

## 7. Granica bezpieczeństwa

Cały Stage 5/6 pozostaje SHADOW-only:

- `actuation_supported=false`,
- `proposed_supply_voltage=null`,
- `proposed_extract_voltage=null`,
- brak portu do GP8403,
- brak GPIO output,
- brak AERO executor,
- brak host-power/systemd boundary.

Logiczny fallback procentowy nie jest obecnie wysyłany do fizycznych wentylatorów.

## 8. Testy i checkpointy

Stage 5 lifecycle / supervision:

- checkpoint `b861fe614e69bf471daa6b583a0c6d45f8fed4d4`
- GitHub Actions `33161599037` — SUCCESS

Stage 5 strict config / persistence:

- checkpoint `4e1cd475f48d1ec0045f7558aaf3660a740a3975`
- GitHub Actions `33161671629` — SUCCESS

Stage 6 fault-mask diagnostics:

- checkpoint `76e0d4b63c92eb03ad882f12ed9806b6c3eb4b5f`
- GitHub Actions `33161929850` — SUCCESS

Stage 6 explicit fallback + persistence:

- checkpoint `d963e6a135515977ff2f5780076c25da114bcfb4`
- GitHub Actions `33162095767` — SUCCESS
- compile — PASS
- unit tests — PASS

Testowe wartości fallbacku używane w unit tests są wyłącznie syntetyczne i nie są nastawami produkcyjnymi.

## 9. Co pozostaje przed produkcyjnym użyciem TACHO fallback

Wymagana jest walidacja na fizycznym CM5 i obu rzeczywistych wentylatorach EC w celu określenia co najmniej:

1. realnego czasu spin-up / `tacho_failure_confirmation_seconds`,
2. reakcji przy awarii tylko nawiewu,
3. reakcji przy awarii tylko wyciągu,
4. reakcji przy awarii obu kanałów,
5. bezpiecznych procentów fallback dla każdej z trzech masek,
6. zachowania przy fizycznym zatrzymaniu/zablokowaniu wentylatora oraz przy awarii samego przewodu TACHO.

Do czasu tej walidacji pola produkcyjne mają pozostać `None`.

## 10. Status

Stage 5 supervision foundation: **PASS**.

Stage 6 software contract dla channel-specific TACHO fallback: **PASS**.

Produkcjne strojenie i fizyczna walidacja fallbacku: **PENDING**.

Automatyczna fizyczna aktuacja Control Engine: **DISABLED / poza zakresem tego etapu**.
