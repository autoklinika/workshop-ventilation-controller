# AlertV2 Stage 4D — wynik walidacji skorelowanej utraty węzła na CM5

**Data:** 2026-08-19  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/core-alert-v2-design-stage1`  
**Walidowany HEAD:** `44c0465445d9c7474566a70072b2cf323778bdb9`  
**Draft PR:** #44  
**Status:** **PASS — hardware validated**, bez merge do `main`, bez produkcyjnego deploymentu AlertV2, bez wykonywania `reaction` z TOML

## 1. Zakres testu

Stage 4D zweryfikował na rzeczywistym CM5 skorelowaną utratę jednego kompletnego węzła:

```text
sensor-node-1 / Modbus slave 1
```

Fault injection był fizyczny: operator odłączył zasilanie wyłącznie testowanego węzła KAmod + SEN55, pozostawiając CM5, `sensor-node-2`, Service Agent oraz wspólną magistralę pracujące.

Oczekiwany przebieg:

```text
production SENSOR_NODE_UNAVAILABLE
+
service heartbeat targetu OFFLINE
=
shadow KAMOD_NODE_UNAVAILABLE
```

Polityka AlertV2:

```text
weight = 3
hmi_color = orange
reaction = fallback_local
affects_control = true
control_policy_applied = false
```

## 2. Wynik ogólny

Validator zakończył test:

```text
result = PASS
```

Potwierdzone zostało:

- produkcyjny `SENSOR_NODE_UNAVAILABLE` dla slave 1,
- korelacja do `KAMOD_NODE_UNAVAILABLE`,
- weight 3 / orange / `fallback_local`,
- `affects_control=true` wyłącznie jako metadata polityki,
- `control_policy_applied=false`,
- brak komend sterujących,
- poprawny recovery obu kanałów targetu,
- poprawne wyczyszczenie alertów,
- brak wpływu na drugi węzeł,
- brak restartu core i Service Agent,
- przez cały test `STOP / 0 V / 0 V`.

## 3. Faza fault — produkcyjny SENSOR BUS

Po fizycznym wyłączeniu `sensor-node-1` produkcyjny core wykrył:

```text
code = SENSOR_NODE_UNAVAILABLE
key = sensor-node:1:communication
alert_id = 65
```

Czas od potwierdzenia ręcznego power-off do wykrycia produkcyjnego alertu:

```text
1.114 s
```

Test nie modyfikował detektora ani debounce produkcyjnego core.

## 4. Faza korelacji

Po utracie heartbeat targetu shadow runtime utworzył:

```text
code = KAMOD_NODE_UNAVAILABLE
key = sensor-node:1:correlated-unavailable
```

Czas od potwierdzenia ręcznego power-off do potwierdzonej korelacji:

```text
30.616 s
```

Zmapowana polityka:

```text
weight = 3
hmi_color = orange
reaction = fallback_local
affects_control = true
```

Jednocześnie:

```text
control_policy_applied = false
write_commands_sent = 0
hardware_owned_by_shadow = false
software_fault_injection = false
```

Legacy `SENSOR_NODE_UNAVAILABLE` został stłumiony tylko w projekcji shadow AlertV2; produkcyjny incydent nadal pozostał własnością istniejącego Alert Stage 1.

## 5. Nietestowany węzeł

`sensor-node-2 / Modbus slave 2` pozostał zdrowy przez cały test.

Validator potwierdził:

```text
non_target_node_healthy = true
```

Stan końcowy slave 2:

```text
online = true
usable = true
measurement_valid = true
consecutive_failures = 0
communication_errors = 0
```

Nie wystąpiła awaria wspólnej magistrali ani wpływ fizycznego faultu targetu na drugi węzeł.

## 6. Recovery targetu

Po przywróceniu zasilania `sensor-node-1` validator potwierdził:

```text
target_sensor_bus_healthy = true
target_heartbeat_online = true
production_alert_cleared = true
correlated_alert_cleared = true
production_test_incident_retained_in_history = true
```

Czas raportowany przez validator od potwierdzenia przez operatora rozpoczęcia fazy recovery:

```text
0.127 s
```

Ta wartość nie jest czasem fizycznego bootu KAmod. Operator przywraca zasilanie przed naciśnięciem Enter; licznik recovery zaczyna się dopiero po Enter. Stan końcowy targetu potwierdza rzeczywisty restart węzła:

```text
uptime_seconds = 6
sequence = 6
firmware_version = 0.6
```

Stan końcowy slave 1:

```text
online = true
usable = true
measurement_valid = true
measurement_stale = false
consecutive_failures = 0
communication_errors = 43
```

Wzrost `communication_errors` na slave 1 jest oczekiwanym śladem fizycznej niedostępności podczas testu.

## 7. Lifecycle alertu produkcyjnego

Incydent testowy:

```text
alert_id = 65
code = SENSOR_NODE_UNAVAILABLE
```

został po recovery wyczyszczony i pozostawiony w produkcyjnej historii jako `CLEARED`, zgodnie z projektem Stage 4D.

Validator nie wykonywał ACK, nie usuwał historii i nie otwierał produkcyjnej bazy do zapisu.

## 8. Stabilność procesów i sterowania

Przed i po teście:

```text
ventilation-core PID = 1174
wvc-service-agent PID = 1130
```

PIDs nie zmieniły się.

Stan końcowy core:

```text
mode = STOP
supply_voltage = 0.0
extract_voltage = 0.0
hardware_ready = true
output_state_known = true
consecutive_hardware_failures = 0
```

Shadow runtime:

```text
control_policy_applied = false
write_commands_sent = 0
hardware_owned_by_shadow = false
```

Stage 4D nie wykonał żadnej reakcji sterującej z TOML.

## 9. TACHO — potwierdzenie niezmiennika bezpieczeństwa

W końcowym stanie oba kanały TACHO miały:

```text
frequency_hz = 0.0
rpm = 0.0
valid = false
```

Jednocześnie core pozostał:

```text
mode = STOP
hardware_ready = true
output_state_known = true
```

Nie wystąpił żaden efekt sterujący wynikający z braku prawidłowego TACHO. Jest to zgodne z twardym założeniem AlertV2, że utrata TACHO nie może powodować globalnego STOP/safe_state.

## 10. Niezależne aktywne alerty

Po zakończeniu testu aktywne pozostały wyłącznie wcześniej istniejące ostrzeżenia Zigbee:

```text
ZIGBEE_DEVICE_DATA_STALE — temp_nawiew
ZIGBEE_DEVICE_DATA_STALE — temp_wywiew
ZIGBEE_BRIDGE_OFFLINE
```

Nie są one skutkiem Stage 4D.

## 11. Wniosek

Stage 4D potwierdził sprzętowo na realnym CM5, że AlertV2 poprawnie rozróżnia i koreluje dwa niezależne dowody awarii jednego węzła:

```text
production Modbus node unavailable
+
service heartbeat unavailable
=
KAMOD_NODE_UNAVAILABLE
```

Korelacja daje bardziej przyczynowy alert:

```text
weight 3 / orange / fallback_local
```

ale nadal pozostaje wyłącznie read-only:

```text
control_policy_applied = false
```

**Status Stage 4D: PASS — HARDWARE VALIDATED.**
