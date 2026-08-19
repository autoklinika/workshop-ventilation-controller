# AlertV2 Stage 5 — production read-only rollout, przygotowanie

**Data:** 2026-08-19  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/core-alert-v2-design-stage1`  
**Draft PR:** #44  
**Status:** przygotowane do kontrolowanego rollout na CM5; bez merge do `main`

## 1. Cel

Stage 5 przenosi zwalidowany AlertV2 z shadow/test runtime do rzeczywistego produkcyjnego `ventilation-core`, ale nadal z twardą granicą:

```text
AlertV2 reaction execution = DISABLED
control_policy_applied = false
```

To jest rollout **read-only względem sterowania**. Core nadal jest jedynym właścicielem hardware i istniejących komend sterujących, a AlertV2 tylko:

- mapuje aktywne alerty do weight/severity/color/reaction metadata,
- publikuje `state.alert_v2`,
- uruchamia zwalidowaną korelację Service Agent ↔ SENSOR BUS,
- nie wykonuje `reaction` z TOML.

## 2. Ważne rozróżnienie: sterowanie vs. alert store

Stage 5 nie jest read-only względem lifecycle alertów. Po przejściu produkcyjnego core na gałąź AlertV2 korelator Service Plane pracuje wewnątrz produkcyjnego rejestru alertów.

To oznacza, że rzeczywiste zdarzenia diagnostyczne mogą tworzyć i czyścić produkcyjne rekordy AlertV2 w istniejącym `alerts.sqlite3` zgodnie z normalnym lifecycle core.

To jest zamierzone. Nie jest to reakcja sterująca. Rollback Stage 5:

- nie kasuje historii alertów,
- nie cofa rekordów diagnostycznych,
- nie przywraca kopii bazy,
- jedynie przełącza runtime core z powrotem na bazowy `main`.

## 3. Sposób rollout bez merge

Produkcja nadal ma bazowy unit:

```text
deploy/systemd/ventilation-core.service
```

Stage 5 nie zastępuje `ExecStart` i nie kopiuje długiej listy parametrów sprzętowych. Dodaje wyłącznie tymczasowy drop-in:

```text
/etc/systemd/system/ventilation-core.service.d/97-alert-v2-stage5-read-only.conf
```

zawierający:

```ini
[Service]
WorkingDirectory=/home/wentylacja/wvc-alert-v2-stage4
Environment=PYTHONPATH=/home/wentylacja/wvc-alert-v2-stage4/src
```

W efekcie wszystkie istniejące parametry produkcyjnego unit pozostają bez zmian, a `python3 -m ventilation_core.main` ładuje kod ze zwalidowanego worktree AlertV2.

## 4. Runtime policy

Docelowa edytowalna polityka produkcyjna:

```text
/etc/workshop-ventilation/alerts-v2.toml
```

Podczas pierwszego `apply`:

- jeśli plik nie istnieje, kopiowany jest `config/alerts-v2.default.toml`,
- jeśli już istnieje, jest zachowany bez nadpisania,
- przed restartem core musi przejść pełne `wvc-alertctl validate`.

Rollback nie usuwa tego pliku.

## 5. Preflight bezpieczeństwa

Przed instalacją drop-in i restartem produkcyjnego core uruchamiany jest istniejący Stage 4A preflight.

Wymagane m.in.:

```text
ventilation-core.service = active
wvc-service-agent.service = active
mode = STOP
supply = 0.0 V
extract = 0.0 V
output_state_known = true
SENSOR BUS ready/alive
slave 1 i 2 healthy
Service Agent i mapowanie node↔Modbus healthy
```

Jeżeli preflight nie przejdzie, Stage 5 nie modyfikuje systemd i nie restartuje core.

## 6. Kontrolowany restart

Rollout wymaga jednego świadomego restartu `ventilation-core.service`.

Oczekiwane:

- PID core zmieni się dokładnie w wyniku restartu,
- PID Service Agent pozostanie bez zmian,
- po starcie produkcja nadal będzie `STOP / 0 V / 0 V`,
- core będzie pracował z CWD `/home/wentylacja/wvc-alert-v2-stage4`.

Nie są restartowane:

- Service Agent,
- Web GUI,
- telemetry sync,
- Zigbee2MQTT,
- weather service.

## 7. Validator Stage 5

Dodano:

```text
tools/validate_alert_v2_stage5_production_read_only_cm5.py
```

Validator korzysta wyłącznie z read-only komend core:

```text
status
alerts
```

Sprawdza przez domyślnie 30 próbek:

```text
STOP / 0 V / output_state_known
hardware_ready = true
core PID stabilny
Service Agent PID stabilny
core CWD = Stage 5 worktree
```

oraz produkcyjne AlertV2:

```text
runtime_mode = read_only_mapping
loaded = true
policy_version zgodny z /etc
sha256 zgodny z /etc
alert_count = 49
control_policy_applied = false
unmapped_active_alerts = 0
```

Sprawdzana jest też spójność:

```text
active_weight 0..4 -> green/blue/yellow/orange/red
```

oraz Service Plane:

```text
monitor.available = true
correlation.mode = read_only
service_plane.control_policy_applied = false
```

Każdy aktywny rekord z produkcyjnego `alerts` musi posiadać `alert_v2.mapped=true`.

Validator rejestruje p50/p95/max latencji `status` i `alerts`, ale w Stage 5 nie narzuca arbitralnego twardego progu latency. Wynik służy jako produkcyjny baseline.

## 8. Deployment helper

Dodano:

```text
tools/deploy_alert_v2_stage5_read_only_cm5.sh
```

Tryby:

```text
apply
status
rollback
```

### `apply`

Kolejność:

1. sprawdzenie ścieżek i usług,
2. Stage 4A preflight,
3. instalacja/zachowanie i walidacja `/etc/workshop-ventilation/alerts-v2.toml`,
4. zapis wyłącznie Stage 5 drop-in,
5. `systemctl daemon-reload`,
6. restart tylko `ventilation-core.service`,
7. kontrola PID core i Service Agent,
8. pełny Stage 5 validator.

Jeżeli restart albo validator nie przejdzie, skrypt automatycznie:

```text
usuwa 97-alert-v2-stage5-read-only.conf
systemctl daemon-reload
restartuje ventilation-core.service
```

czyli wraca do bazowego runtime z `/home/wentylacja/workshop-ventilation-controller`.

### `rollback`

Rollback jest dozwolony tylko z `STOP / 0 V / output_state_known=true`.

Usuwa wyłącznie Stage 5 drop-in i restartuje core do bazowego runtime. Polityka TOML i historia alertów pozostają nietknięte.

## 9. Granice bezpieczeństwa

Stage 5 nie dodaje mechanizmu wykonywania reakcji.

W szczególności:

```text
control_policy_applied = false
```

pozostaje twardym wymaganiem validatora.

Nadal obowiązuje niezmiennik:

```text
TACHO_* nie może wywołać globalnego STOP / safe_state
```

Weight alertu nadal nie jest równoznaczny z wykonaniem reakcji.

## 10. Kryterium PASS na CM5

Stage 5 będzie uznany za zakończony dopiero po rzeczywistym `apply` na CM5 i wyniku:

```text
result = PASS
production core CWD = /home/wentylacja/wvc-alert-v2-stage4
AlertV2 loaded = true
policy SHA/version/count match
unmapped_active_alerts = 0
Service Plane correlation = read_only
control_policy_applied = false
STOP / 0 V przez cały validator
Service Agent PID unchanged
core PID stable po rollout restart
validator control commands = 0
```

Do tego czasu status Stage 5: **PREPARED, NOT YET PRODUCTION-VALIDATED**.
