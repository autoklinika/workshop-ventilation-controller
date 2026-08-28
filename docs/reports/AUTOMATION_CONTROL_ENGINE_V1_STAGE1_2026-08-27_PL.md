# Automation Control Engine V1 — Stage 1

Data: 2026-08-27

## 1. Status

Stage 1 wprowadza stanową logikę automatyki wyłącznie w istniejącym kontrakcie `shadow_automation`.

Nie dodano żadnej nowej ścieżki aktuacyjnej. Wynik automatyki jest diagnostyczny i nie może zmienić DAC, AERO ani host-power.

Bazą prac jest zamrożony HEAD PR #85:

`afd726809c85e94869f42206082516dadd2959d8`

Gałąź rozwojowa:

`agent/automation-v1-control-engine`

Draft PR:

`#86 Add Automation Control Engine V1 shadow dynamics`

PR #86 jest stacked na gałęzi PR #85, dzięki czemu jego diff zawiera wyłącznie zmiany Control Engine.

## 2. Cel Stage 1

Dotychczasowa polityka SHADOW klasyfikowała każdą próbkę niezależnie. Parametry histerezy i czasów istniały w `ShadowOutputTuning`, ale nie wpływały jeszcze na stan decyzji.

Stage 1 dodaje pamięć stanu per strefa, aby późniejsza automatyka nie reagowała na pojedyncze próbki i nie oscylowała wokół progów.

## 3. Zaimplementowane mechanizmy

### 3.1. Air-quality dynamics

Dodano `AirQualityDynamicsTracker` z osobnym stanem dla każdej strefy.

Obsługiwane są:

- histereza PM2.5,
- histereza VOC,
- histereza NOx,
- potwierdzenie wejścia PM2.5 do `BOOST`,
- natychmiastowe wejście do wyższych poziomów `HIGH` / `MAX`,
- minimalny czas utrzymania stanu przed obniżeniem,
- opóźnione wygaszanie / decay przed obniżeniem poziomu,
- jawny stan oczekującego przejścia.

Dla bezpieczeństwa eskalacja do poważniejszych poziomów nie jest opóźniana przez mechanizm decay.

### 3.2. Temperature dynamics

Dodano `ThermalDynamicsTracker`.

Zasada:

- przejście do bardziej restrykcyjnej temperatury następuje natychmiast,
- powrót do mniej restrykcyjnego pasma wymaga przekroczenia progu powrotnego o skonfigurowaną histerezę.

### 3.3. Jawne stany logiczne

SHADOW publikuje teraz `automation_state`:

- `OFF`,
- `STANDBY`,
- `PREVENTILATION`,
- `NORMAL`,
- `BOOST`,
- `PURGE`,
- `TEMP_LIMIT`,
- `EMERGENCY_VENT`,
- `FAULT`.

`HIGH` pozostaje poziomem jakości powietrza, natomiast stan wykonawczy mapuje go do `BOOST`. `MAX` mapuje się do `EMERGENCY_VENT`.

### 3.4. Diagnostyka raw vs effective

Dla każdej strefy publikowane są m.in.:

- `raw_air_quality_level`,
- `raw_air_quality_driver`,
- `air_quality_level` — poziom efektywny po dynamice,
- `air_quality_driver`,
- `air_quality_effective_since_utc`,
- `dynamics_pending_level`,
- `dynamics_pending_driver`,
- `dynamics_pending_since_utc`,
- `dynamics_transition_reason`,
- `raw_thermal_band`,
- `thermal_band`,
- `automation_state`.

Pozwala to zobaczyć różnicę pomiędzy chwilową próbką a decyzją, która obowiązywałaby po histerezie i potwierdzeniu.

## 4. Tuning produkcyjny

Stage 1 nie ustala docelowych wartości procentowych ani czasów.

Wartości produkcyjne w `ShadowOutputTuning` pozostają `None` do czasu świadomego strojenia i walidacji na obiekcie.

Jeżeli tuning dynamics jest niekompletny, tracker działa transparentnie i zachowuje dotychczasową natychmiastową klasyfikację. Core raportuje wtedy `TUNING_REQUIRED`.

Jawny tuning laboratoryjny jest używany wyłącznie w testach jednostkowych.

## 5. Bezpieczeństwo i brak aktuacji

Niezmienione zasady:

- `actuation_supported=false`,
- `proposed_supply_voltage=None`,
- `proposed_extract_voltage=None`,
- evaluator nie posiada portu do DAC,
- evaluator nie posiada portu do AERO,
- evaluator nie posiada portu do `wvc-host-power`,
- stan krytyczny hardware / output-state / AlertV2 powoduje logiczne `FAULT` i blokuje propozycje procentowe,
- GUI pozostaje klientem,
- Home Assistant pozostaje read-only.

## 6. Testy

Dodano:

- `tests/test_shadow_dynamics.py`,
- `tests/test_control_engine_stage1.py`.

Testy obejmują m.in.:

- inicjalizację bez sztucznego opóźnienia po starcie,
- PM2.5 BOOST confirmation,
- natychmiastową eskalację HIGH/MAX,
- histerezę progową,
- minimum state hold,
- decay przy obniżaniu,
- temperaturową histerezę recovery,
- priorytet jakości powietrza nad ograniczeniem temperatury,
- mapowanie faz Calendar Engine na stany automatyki,
- `EMERGENCY_VENT`,
- `FAULT`,
- brak fizycznych napięć w SHADOW,
- propozycję AERO bez aktuacji.

CI dla Stage 1 HEAD przy pierwszym pełnym przebiegu:

- SHA: `f7861bfe7acb7bf7583b5465dd40d82475b8539e`,
- workflow: `Ventilation Core Tests`,
- run: `33091190773`,
- compile: PASS,
- unit tests: PASS,
- conclusion: SUCCESS.

## 7. Kolejne etapy

Następne kroki Control Engine powinny być realizowane nadal w SHADOW:

1. dołączenie jawnego bazowego żądania z aktywnego profilu Calendar Engine,
2. reguła `max(calendar_request, air_quality_request, safety_request)` z temperaturowym limitem wyłącznie tam, gdzie nie narusza priorytetu jakości powietrza,
3. jawny fallback po utracie SEN55,
4. integracja temperatury nawiewu/zewnętrznej z Zigbee i `delta_t`,
5. operator `MANUAL` jako warstwa core, nie Calendar Engine,
6. długotrwała walidacja SHADOW na fizycznym CM5,
7. dopiero później osobny etap dopuszczający aktuację.

Stage 1 nie zmienia zasad Power Scheduler ani nie wymaga merge PR #85 do rozpoczęcia dalszych prac na gałęzi stacked.
