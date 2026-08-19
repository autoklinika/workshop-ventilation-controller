# AlertV2 Stage 4C — heartbeat-only dropout, przygotowanie

**Data:** 2026-08-19  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/core-alert-v2-design-stage1`  
**Draft PR:** #44  
**Status:** przygotowane do walidacji na CM5, bez merge i bez produkcyjnego deploymentu

## 1. Cel

Stage 4C ma potwierdzić pierwszy kontrolowany scenariusz awaryjny AlertV2 na rzeczywistym CM5:

```text
utrata heartbeat jednego KAmod
+
produkcyjny SENSOR BUS / Modbus tego samego węzła nadal zdrowy
=
KAMOD_HEARTBEAT_LOST
```

Oczekiwana polityka:

```text
weight = 2
hmi_color = yellow
affects_control = false
control_policy_applied = false
```

Po przywróceniu heartbeat alert ma automatycznie zniknąć z aktywnego stanu shadow runtime.

## 2. Metoda fault injection

Nie zatrzymujemy KAmod, Service Agent, AP ani produkcyjnego SENSOR BUS.

Walidator dynamicznie odczytuje aktualny `source_ip` wskazanego węzła z `wvc-service-agent` i instaluje jedną tymczasową regułę nftables na CM5:

```text
family: inet
table: wvc_sensor_service
chain: input
interface: wlan0
source: dokładnie source_ip testowanego KAmod
destination: 10.55.0.1
protocol: UDP
destination port: 45551
action: drop
```

Reguła dotyczy wyłącznie heartbeat testowanego węzła. Nie blokuje:

- Modbus RTU,
- drugiego KAmod,
- DHCP,
- ICMP,
- produkcyjnego core,
- DAC,
- TACHO,
- AERO,
- Zigbee.

Reguła jest wstawiana przed istniejącym `accept` dla heartbeat i posiada unikalny komentarz `wvc-alert-v2-stage4c-heartbeat-drop-*`.

## 3. Ochrona przed błędnym targetem

Walidator odrzuca:

- adres spoza `10.55.0.0/24`,
- adres CM5 `10.55.0.1`,
- nieznany lub offline target,
- niezgodne mapowanie `sensor-node-1 -> Modbus 1` / `sensor-node-2 -> Modbus 2`,
- istniejącą starą regułę Stage 4C,
- niesprawną sieć WVC-SERVICE.

Domyślny target:

```text
sensor-node-1
```

## 4. Safety preconditions

Przed fault injection walidator wymaga:

```text
ventilation-core.service = active
wvc-service-agent.service = active
mode = STOP
supply = 0.0 V
extract = 0.0 V
output_state_known = true
oba SENSOR BUS slave online + usable
oba heartbeat KAmod online
```

Zapisywane są PID obu usług oraz baseline liczników SENSOR BUS:

```text
communication_errors
invalid_measurements
stale_measurements
map_version_errors
```

## 5. Kontrola podczas fault injection

Przez cały test walidator cyklicznie sprawdza:

- niezmieniony PID core,
- niezmieniony PID Service Agent,
- `STOP / 0 V / 0 V`,
- `output_state_known=true`,
- oba slave Modbus nadal `online + usable`,
- brak wzrostu liczników błędów SENSOR BUS,
- drugi KAmod nadal heartbeat online,
- tymczasowa reguła nft nadal istnieje dokładnie raz,
- shadow runtime nadal `control_policy_applied=false`.

Nie jest wysyłane żadne polecenie sterujące do core.

## 6. Oczekiwana detekcja

Service Agent ma własny próg offline 35 s. Walidator daje domyślnie 55 s na przejście targetu do `online=false`.

Po tym shadow runtime musi pokazać dokładnie jeden skorelowany alert:

```text
KAMOD_HEARTBEAT_LOST
```

Dodatkowo walidowane jest:

```text
weight = 2
hmi_color = yellow
affects_control = false
correlation.derived_codes = ["KAMOD_HEARTBEAT_LOST"]
```

W tym samym czasie SENSOR BUS targetu musi pozostać zdrowy.

## 7. Recovery

Natychmiast po potwierdzeniu alertu tymczasowa reguła nft jest usuwana.

Walidator czeka domyślnie do 30 s na:

```text
target heartbeat online = true
KAMOD_HEARTBEAT_LOST = cleared / nieaktywny
```

Drugi KAmod musi pozostawać online przez cały recovery.

Po recovery sprawdzane jest również, że żadna reguła Stage 4C nie pozostała w nftables.

## 8. Cleanup

Reguła nft jest usuwana w `finally`, także przy:

- błędzie walidacji,
- wyjątku,
- Ctrl+C,
- SIGTERM.

Jeżeli cleanup sam się nie powiedzie, walidator wypisuje jawny komunikat:

```text
CRITICAL CLEANUP FAILURE
```

`SIGKILL`/nagła utrata zasilania procesu nie może uruchomić `finally`, dlatego przed każdym nowym testem walidator wykrywa pozostawione reguły Stage 4C i odmawia startu.

## 9. Pliki

Dodano:

```text
src/ventilation_core/alert_v2_stage4c_fault.py
tools/validate_alert_v2_stage4c_heartbeat_dropout_cm5.py
tests/test_alert_v2_stage4c_heartbeat_fault.py
```

## 10. Granice etapu

Stage 4C heartbeat-only NIE testuje jeszcze:

- jednoczesnego heartbeat + Modbus dropout,
- fizycznego odłączenia SEN55,
- operational TACHO,
- wykonania `reaction` z TOML,
- sterowania RGB HMI,
- merge do `main`.

Po PASS tego podetapu można osobno przygotować kolejny test skorelowany:

```text
heartbeat fail + SENSOR BUS fail -> KAMOD_NODE_UNAVAILABLE
```

ale dopiero po potwierdzeniu pełnego recovery po heartbeat-only dropout.
