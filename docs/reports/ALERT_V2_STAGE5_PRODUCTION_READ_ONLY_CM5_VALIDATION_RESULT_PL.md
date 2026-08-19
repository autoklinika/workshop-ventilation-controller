# AlertV2 Stage 5 — produkcyjny rollout read-only, wynik walidacji CM5

**Data:** 2026-08-19  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/core-alert-v2-design-stage1`  
**Draft PR:** #44  
**Wynik:** **PASS**

## 1. Zakres

Stage 5 uruchomił AlertV2 w rzeczywistym produkcyjnym `ventilation-core`, ale nadal bez wykonywania reakcji sterujących z TOML.

Granica bezpieczeństwa pozostała:

```text
reaction_execution_enabled = false
control_policy_applied = false
```

Rollout wykonano bez merge do `main`, przez tymczasowy systemd drop-in zmieniający wyłącznie `WorkingDirectory` i `PYTHONPATH` na worktree AlertV2.

## 2. Preflight przed rollout

Stage 4A passive preflight przed restartem produkcyjnego core zakończył się PASS.

Potwierdzono:

```text
core = active
service-agent = active
mode = STOP
supply = 0.0 V
extract = 0.0 V
control_policy_applied = false
write_commands_sent = 0
sensor-node-1 -> Modbus 1
sensor-node-2 -> Modbus 2
correlation.mode = read_only
correlation.reason = correlation_complete
```

Latencja preflight:

```text
core mean = 2.071 ms
core p50  = 1.871 ms
core p95  = 3.009 ms
core max  = 3.009 ms

service-agent mean = 0.402 ms
service-agent p50  = 0.350 ms
service-agent p95  = 0.599 ms
service-agent max  = 0.599 ms
```

## 3. Produkcyjna polityka AlertV2

Przy pierwszym rollout zainstalowano:

```text
/etc/workshop-ventilation/alerts-v2.toml
```

Walidacja polityki:

```text
schema = 1
policy_version = 2026-08-18.1
alerts = 49
sha256 = c197a28055ef05ab6c5e8663068068160d23fea5eef2935c1aa604906b5fc2a3
```

## 4. Restart produkcyjnego core

Przed rollout:

```text
ventilation-core PID = 1174
wvc-service-agent PID = 1130
```

Po rollout:

```text
ventilation-core PID = 44317
wvc-service-agent PID = 1130
```

Czyli nastąpił dokładnie jeden oczekiwany restart produkcyjnego core, a Service Agent pozostał bez restartu.

## 5. Produkcyjny runtime AlertV2

Po rollout produkcyjny core pracuje z:

```text
core CWD = /home/wentylacja/wvc-alert-v2-stage4
```

Aktywny drop-in:

```text
/etc/systemd/system/ventilation-core.service.d/97-alert-v2-stage5-read-only.conf
```

Treść:

```ini
[Service]
WorkingDirectory=/home/wentylacja/wvc-alert-v2-stage4
Environment=PYTHONPATH=/home/wentylacja/wvc-alert-v2-stage4/src
```

Bazowy `ExecStart` i parametry sprzętowe nie zostały zastąpione.

## 6. Wynik produkcyjnego validatora Stage 5

30 próbek zakończyło się PASS.

Potwierdzono:

```text
runtime.mode = read_only_mapping
control_policy_applied = false
service_plane_correlation = read_only
unmapped_active_alerts = 0
policy alert_count = 49
policy version/SHA zgodne z /etc
reaction_execution_enabled = false
control_commands_sent_by_validator = 0
production_alert_store_is_authoritative = true
```

Przez cały validator produkcja pozostała:

```text
mode = STOP
supply = 0.0 V
extract = 0.0 V
output_state_known = true
```

Obserwowane aktywne mapowanie HMI:

```text
observed_active_weights = [2]
observed_hmi_colors = [yellow]
mapped_active_alerts_max = 3
```

## 7. Latencja produkcyjna po rollout

`status`:

```text
mean = 1.996 ms
p50  = 1.823 ms
p95  = 2.817 ms
max  = 3.181 ms
```

`alerts`:

```text
mean = 3.127 ms
p50  = 2.655 ms
p95  = 4.310 ms
max  = 5.338 ms
```

Nie zastosowano arbitralnego progu PASS/FAIL dla latencji; wartości zapisano jako produkcyjny baseline AlertV2.

## 8. Stan po walidacji

```text
ventilation-core.service = active
PID = 44317
wvc-service-agent.service = active
PID = 1130
core CWD = /home/wentylacja/wvc-alert-v2-stage4
runtime policy = PRESENT + VALID
drop-in = INSTALLED
control policy execution = DISABLED
```

## 9. Niezmienniki bezpieczeństwa

Stage 5 potwierdził, że:

- `reaction` z TOML nadal nie jest wykonywane,
- `control_policy_applied=false`,
- validator nie wysyła komend sterujących,
- waga alertu jest nadal oddzielona od reakcji sterującej,
- brak TACHO nie może powodować globalnego STOP/safe_state,
- polityka nie jest edytowalna z HMI/Web GUI.

## 10. Konkluzja

**AlertV2 Stage 5 = PASS na produkcyjnym CM5.**

AlertV2 działa już w produkcyjnym `ventilation-core` jako runtime read-only względem sterowania, z aktywną korelacją Service Plane ↔ SENSOR BUS i produkcyjną polityką 49 alertów.

Do kolejnego etapu nie należy włączać wykonywania `reaction` z TOML bez osobnego projektu, testów i jawnej zgody operatora.
