# AlertV2 Stage 4C — wynik walidacji heartbeat-only na CM5

**Data:** 2026-08-19  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź testowa:** `agent/core-alert-v2-design-stage1`  
**Walidowany HEAD:** `c978d6a7ca80432513a8db216e34603617428dae`  
**Worktree CM5:** `/home/wentylacja/wvc-alert-v2-stage4`  
**Target:** `sensor-node-1` / Modbus slave `1`  
**Wynik:** **PASS**

## 1. Cel testu

Zweryfikować na rzeczywistym CM5 przypadek utraty wyłącznie serwisowego heartbeat jednego węzła KAmod przy zachowanym zdrowym produkcyjnym SENSOR BUS/Modbus RTU.

Oczekiwany rezultat:

```text
KAMOD_HEARTBEAT_LOST
weight = 2
hmi_color = yellow
affects_control = false
```

Test nadal nie wykonuje `reaction` z polityki AlertV2 i nie posiada ścieżki sterowania sprzętem.

## 2. Stan produkcji przed testem

Przed fault injection:

- `ventilation-core.service`: `active`, PID `1174`,
- `wvc-service-agent.service`: `active`, PID `1130`,
- core: `STOP`,
- supply: `0.0 V`,
- extract: `0.0 V`,
- `output_state_known=true`.

Oryginalny firewall `WVC-SERVICE` zawierał m.in.:

```text
iifname "wlan0" ip daddr 10.55.0.1 udp dport 45551 accept # handle 6
```

## 3. Fault injection

Walidator odczytał bieżący adres źródłowy targetu z Service Agent:

```text
node_id = sensor-node-1
modbus_address = 1
source_ip = 10.55.0.106
```

Następnie dodał pojedynczą tymczasową regułę nftables blokującą wyłącznie heartbeat:

```text
10.55.0.106 -> 10.55.0.1:45551/UDP
```

Tymczasowy uchwyt reguły:

```text
handle = 10
```

Nie blokowano Modbus RTU, drugiego KAmod, DHCP, AP, DAC, TACHO, AERO ani Zigbee.

## 4. Detekcja

Heartbeat targetu został uznany za offline po:

```text
34.847 s
```

Powstał dokładnie oczekiwany AlertV2:

```text
KAMOD_HEARTBEAT_LOST
weight = 2
hmi_color = yellow
affects_control = false
```

Produkcja SENSOR BUS w tym samym czasie pozostała zdrowa:

```text
sensor_bus_error_counters_unchanged = true
```

To potwierdza poprawne rozróżnienie:

```text
service heartbeat OFFLINE
+
production Modbus/SEN55 healthy
=
KAMOD_HEARTBEAT_LOST
```

bez eskalacji do `KAMOD_NODE_UNAVAILABLE`.

## 5. Recovery

Po potwierdzeniu alertu tymczasowa reguła została usunięta.

Heartbeat powrócił po:

```text
14.764 s
```

Walidator potwierdził:

```text
target_online = true
non_target_online = true
alert_cleared = true
```

Po teście `nft -a list chain inet wvc_sensor_service input` nie zawierał tymczasowego `handle 10`; pozostały wyłącznie oryginalne reguły firewall.

## 6. Safety invariants

Walidator potwierdził:

```text
control_policy_applied = false
hardware_owned_by_shadow = false
write_commands_sent = 0
temporary_firewall_rule_removed = true
```

Produkcja przez cały test pozostała:

```text
mode = STOP
supply = 0.0 V
extract = 0.0 V
```

Nie wykonano żadnego polecenia sterowania wentylatorami, DAC, AERO, Zigbee ani TACHO.

## 7. Stan po teście

Po recovery:

- `ventilation-core.service`: `active`, PID `1174`,
- `wvc-service-agent.service`: `active`, PID `1130`,
- brak tymczasowej reguły nftables,
- heartbeat obu węzłów online,
- `KAMOD_HEARTBEAT_LOST` wyczyszczony,
- produkcyjny SENSOR BUS bez wzrostu liczników błędów.

## 8. Wniosek

Stage 4C heartbeat-only spełnił wszystkie kryteria PASS:

- utrata tylko kanału serwisowego została poprawnie wykryta,
- AlertV2 przypisał właściwy kod, wagę i kolor,
- brak fałszywej eskalacji do awarii całego węzła,
- produkcyjny Modbus RTU pozostał zdrowy,
- nie wystąpił restart core ani Service Agent,
- system pozostał `STOP / 0 V / 0 V`,
- brak wpływu na sterowanie,
- recovery i lifecycle `CLEARED` zadziałały poprawnie,
- firewall został w pełni przywrócony.

**Status: ALERT V2 STAGE 4C HEARTBEAT-ONLY — PASS.**

## 9. Następny etap

Po tym PASS można przygotować osobny, kontrolowany Stage 4D:

```text
heartbeat OFFLINE
+
production SENSOR BUS/Modbus OFFLINE dla tego samego węzła
=
KAMOD_NODE_UNAVAILABLE
```

Stage 4D powinien nadal działać bez wykonywania `reaction` z TOML i z twardym wymaganiem `control_policy_applied=false`.

Operational TACHO (`FAN_NO_ROTATION_FEEDBACK`) pozostaje poza tym etapem do czasu osobnego zatwierdzenia progów i debounce.