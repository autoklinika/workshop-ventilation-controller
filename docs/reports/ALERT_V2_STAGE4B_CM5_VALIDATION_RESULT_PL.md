# AlertV2 Stage 4B — wynik walidacji CM5

**Data:** 2026-08-19  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź testowa:** `agent/core-alert-v2-design-stage1`  
**Walidowany HEAD:** `1e21d87d55139e0b0cdae3e061d3f1a915fbb99f`  
**Worktree CM5:** `/home/wentylacja/wvc-alert-v2-stage4`  
**Wynik:** **PASS**

## 1. Zakres testu

Uruchomiono przygotowany Stage 4B live shadow runtime w osobnym worktree na rzeczywistym CM5.

Test nie przejmował sprzętu i nie zatrzymywał produkcyjnych usług. Shadow runtime miał wyłącznie odczytowy dostęp do:

- `ventilation-core`: `status`, `alerts`,
- `wvc-service-agent`: `status`.

Nie użyto produkcyjnych baz SQLite po stronie shadow runtime, nie wykonano ACK, konfiguracji, OTA ani żadnego polecenia sterującego.

## 2. Stan produkcji przed i po teście

Przed testem:

- `ventilation-core.service`: `active`, PID `1174`,
- `wvc-service-agent.service`: `active`, PID `1130`.

Po teście:

- `ventilation-core.service`: `active`, PID `1174`,
- `wvc-service-agent.service`: `active`, PID `1130`.

Nie wystąpił restart żadnej z tych usług.

Produkcja przez cały test pozostała w stanie:

```text
mode = STOP
supply_voltage = 0.0 V
extract_voltage = 0.0 V
output_state_known = true
```

## 3. Safety invariants

Walidator potwierdził:

```text
control_policy_applied = false
hardware_owned_by_shadow = false
production_databases_opened_by_shadow = false
write_commands_sent = 0
```

Wynik oznacza, że Stage 4B działał wyłącznie diagnostycznie/read-only i nie wykonywał `reaction` z polityki TOML.

## 4. AlertV2 mapping

Shadow runtime obserwował aktywne kody:

```text
ZIGBEE_BRIDGE_OFFLINE
ZIGBEE_DEVICE_DATA_STALE
```

Wszystkie aktywne alerty zostały poprawnie zmapowane przez politykę AlertV2:

```text
active_weights = [2]
hmi_colors = ["yellow"]
unmapped_active_alerts = 0
policy_alert_count = 49
```

Korelacja Service Plane zakończyła się:

```text
correlation_reason = "correlation_complete"
control_policy_applied = false
```

Nie powstały nieoczekiwane alerty skorelowane.

## 5. Latencja

### Produkcyjny core podczas Stage 4B

```text
mean = 1.546 ms
p50  = 1.462 ms
p95  = 2.059 ms
max  = 3.219 ms
```

### Baseline Stage 4A

```text
p95 = 2.431 ms
```

Porównanie:

```text
delta = -0.372 ms
ratio = 0.847
```

W Stage 4B p95 produkcyjnego core był niższy niż baseline Stage 4A. Nie zaobserwowano degradacji latencji core.

### Shadow runtime

Status socket:

```text
mean = 0.499 ms
p50  = 0.455 ms
p95  = 0.685 ms
max  = 1.203 ms
```

Czas pełnego `shadow refresh`:

```text
mean = 9.231 ms
p50  = 3.732 ms
p95  = 51.786 ms
max  = 62.901 ms
```

Pojedyncze wolniejsze odświeżenia shadow runtime nie przełożyły się na latencję produkcyjnego core i nie miały wpływu na sterowanie.

## 6. Podsumowanie

Stage 4B spełnił wszystkie kryteria PASS:

- produkcyjny core pozostał aktywny i bez restartu,
- Service Agent pozostał aktywny i bez restartu,
- produkcja pozostała `STOP / 0 V / 0 V`,
- shadow runtime nie posiadał sprzętu,
- nie otwierał produkcyjnych baz danych,
- wysłał `0` poleceń zapisu,
- wszystkie aktywne alerty zostały zmapowane,
- `control_policy_applied=false`,
- nie wystąpiła degradacja p95 produkcyjnego core.

**Status: ALERT V2 STAGE 4B — PASS.**

## 7. Następny etap

Po Stage 4B można przygotować Stage 4C jako kontrolowaną walidację fault-injection, nadal bez wykonywania `reaction` z TOML.

Kolejność zalecana:

1. heartbeat-only dropout jednego KAmod przy zachowanym zdrowym Modbus,
2. potwierdzenie `KAMOD_HEARTBEAT_LOST` i braku wpływu na sterowanie,
3. przywrócenie heartbeat i potwierdzenie `CLEARED`,
4. dopiero później osobny test skorelowanego heartbeat + SENSOR BUS dropout.

Operational TACHO pozostaje poza Stage 4C do czasu osobnego zatwierdzenia progów/debounce.