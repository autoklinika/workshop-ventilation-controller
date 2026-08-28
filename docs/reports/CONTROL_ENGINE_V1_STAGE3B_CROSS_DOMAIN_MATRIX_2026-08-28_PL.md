# Control Engine V1 — Stage3B: macierz Calendar × AQ × temperatura × awarie

Data: 2026-08-28

## Cel

Stage3B rozszerza deterministyczny Scenario / Replay Engine o niezależną macierz przekrojową Control Engine V1. Etap jest przeznaczony do walidacji algorytmu w LAB bez uzależniania wyniku od aktualnych warunków środowiskowych i bez jakiejkolwiek fizycznej aktuacji.

Wartości używane w macierzy są jawnie syntetycznym tuningiem testowym. Nie są nastawami produkcyjnymi i nie mogą być interpretowane jako wartości docelowe dla warsztatu.

## Implementacja

Dodano:

- `src/ventilation_core/application/control_engine_matrix.py`
- `tools/run_control_engine_matrix.py`
- `config/control-engine-scenarios/lab-cross-domain-matrix-v1.json`
- `tests/test_control_engine_matrix.py`
- `tests/test_control_engine_matrix_cli.py`

Każdy przypadek macierzy uruchamia świeży `ControlEngineScenarioRunner`, który z kolei korzysta z tego samego `PolicyShadowAutomationEvaluator`, co runtime. Stan dynamiki i histerezy nie przecieka pomiędzy kombinacjami.

Runner macierzy nie ma dostępu do:

- DAC,
- GPIO,
- AERO executor,
- socketów runtime,
- systemd,
- host-power,
- fizycznego CM5.

Dodatkowe guardy wymagają w każdym wyniku:

- `actuation_supported=false`,
- `proposed_supply_voltage=null`,
- `proposed_extract_voltage=null`.

## Wymiary macierzy

Macierz zawiera 4 wymiary.

### Calendar — 6 wariantów

- `inactive_off`
- `inactive_standby`
- `preventilation_auto`
- `active_auto`
- `purge_auto`
- `active_fixed`

### Air Quality — 4 warianty syntetyczne

- `normal`
- `boost_voc`
- `high_voc`
- `max_voc`

### Temperatura wewnętrzna — 4 warianty syntetyczne

- `normal`
- `limiting`
- `minimum`
- `protection`

### Awarie / degradacje — 10 wariantów

- `none`
- `sensor1_loss`
- `sensor2_loss`
- `both_sensor_loss`
- `zigbee_supply_stale`
- `zigbee_supply_offline`
- `critical_alarm`
- `output_unknown`
- `hardware_not_ready`
- `sensor1_loss_critical`

Łącznie:

`6 × 4 × 4 × 10 = 960` niezależnych przypadków.

## Zweryfikowane priorytety i semantyka

### Safety

`critical_alarm`, `output_unknown`, `hardware_not_ready` oraz połączenie `sensor1_loss_critical` mają najwyższy priorytet:

- status `BLOCKED_SAFETY`,
- `automation_state=FAULT`,
- brak finalnych procentów sterowania,
- brak propozycji AERO,
- fallback nie może ominąć safety block.

### Calendar + dobra jakość powietrza

Przy `NORMAL` AQ:

- poza aktywnym lifecycle (`INACTIVE`) wynik pozostaje 0/0,
- w aktywnym lifecycle bazą jest `max(Calendar, normal AQ request)`,
- ograniczenie temperaturowe może obniżyć wynik.

### Calendar + pogorszona jakość powietrza

Przy `BOOST/HIGH/MAX`:

- zapotrzebowanie AQ może przebić Calendar OFF/STANDBY,
- finalny request jest co najmniej równy zapotrzebowaniu AQ,
- limit cieplny nie ogranicza pogorszonej jakości powietrza,
- niski zakres temperatury jest oznaczony przez `air_quality_override`.

Przykład syntetyczny: `inactive_off + high_voc + protection` daje logiczny SHADOW request 70/75%. To jest wyłącznie sprawdzenie priorytetu algorytmu, nie nastawa produkcyjna.

### Utrata SEN55 strefy wentylatorów

Przy `sensor1_loss` / `both_sensor_loss`:

- wejścia AQ i temperatura wewnętrzna nie są konsumowane,
- `automation_state=FAULT`,
- w aktywnym lifecycle używany jest jawnie skonfigurowany fallback testowy,
- poza aktywnym lifecycle nie jest wymyślana wentylacja tła,
- nawet przy świeżej temperaturze Zigbee `delta_t=null`, ponieważ nie ma używalnej temperatury wewnętrznej.

### Utrata SEN55 strefy AERO

Przy `sensor2_loss` / `both_sensor_loss`:

- aktywny lifecycle używa jawnego syntetycznego fallbacku AERO,
- nieaktywny lifecycle proponuje 0,
- nadal jest to wyłącznie propozycja SHADOW.

### Zigbee supply stale/offline

Dwa dodatkowe warianty potwierdzają obecną politykę V1:

- `zigbee_supply_stale` → `TEMPERATURE_STALE`, outside temperature unusable, `delta_t=null`,
- `zigbee_supply_offline` → `ZIGBEE_DEVICE_OFFLINE`, outside temperature unusable, `delta_t=null`.

Utrata kontekstu temperatury zewnętrznej nie zmienia obecnie finalnego AQ control request ani `automation_state`, ponieważ Zigbee supply nie jest jeszcze zależnością sterującą. Wyłącza wyłącznie obliczenie / możliwość przyszłej optymalizacji `delta_t`.

## Wynik zbiorczy

Dla 960 przypadków:

- `READY`: 288
- `DEGRADED`: 288
- `BLOCKED_SAFETY`: 384
- przypadki z `safety_override`: 384
- przypadki z `sensor_fallback_applied`: 192

Każdy z 960 przypadków zachował kontrakt SHADOW-only.

## Walidacja CI

Stage3B code checkpoint:

`04736ee574681f067eb47921058ca04e43e977dc`

GitHub Actions:

- workflow: `Ventilation Core Tests`
- run: `33158386237`
- compile: PASS
- pełny unit-test suite: PASS
- wynik: SUCCESS

Wcześniejsze czerwone checkpointy w trakcie budowy macierzy wynikały z testów kontraktowych macierzy (limit długości technicznej nazwy scenariusza, rozszerzenie 768 → 960 oraz oczekiwanie `delta_t` przy utracie SEN55). Nie wymagały poluzowania logiki Control Engine; zostały poprawione przez doprecyzowanie runnera i oczekiwań testowych.

## Wniosek

Stage3B PASS.

Control Engine V1 ma obecnie deterministycznie zwalidowaną przekrojową macierz Calendar × AQ × temperatura × awarie, obejmującą 960 niezależnych przypadków. Etap nie nadaje żadnego prawa do fizycznej aktuacji i nie ustanawia produkcyjnych wartości tuningu.

Przed dopuszczeniem rzeczywistej automatycznej aktuacji nadal wymagane są osobne etapy: produkcyjne strojenie w rzeczywistym warsztacie, walidacja polityki awarii zależności sterujących (w tym TACHO), jawny actuation gate oraz fizyczna walidacja wykonawcza.
