# AlertV2 Stage 6 — reboot / soak / persistence, przygotowanie

**Data:** 2026-08-19  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/core-alert-v2-design-stage1`  
**Draft PR:** #44  
**Status:** przygotowane do walidacji na CM5; bez merge do `main`

## 1. Cel

Stage 6 nie wprowadza automatyki sterującej AlertV2.

Obowiązuje twarda granica:

```text
AlertV2 automatic control = DISABLED
reaction execution = DISABLED
control_policy_applied = false
```

Jedynym automatycznym zachowaniem związanym z utratą komunikacji pozostaje istniejący lokalny watchdog HMI/Web GUI `BRAK KOMUNIKACJI Z CM5`, który blokuje GUI i samoczynnie znika po odzyskaniu komunikacji. Nie jest to sterowanie wentylacją.

Stage 6 służy wyłącznie stabilizacji produkcyjnego read-only AlertV2 po Stage 5:

- reboot persistence,
- krótki soak produkcyjny,
- trwałość polityki TOML,
- trwałość lifecycle/history alertów,
- stabilność core i Service Agent,
- stabilność API Web GUI/HMI,
- potwierdzenie braku wykonywania reakcji z TOML.

## 2. Produkcyjny punkt startowy

Stage 5 działa na CM5 z:

```text
core runtime CWD = /home/wentylacja/wvc-alert-v2-stage4
runtime policy   = /etc/workshop-ventilation/alerts-v2.toml
systemd drop-in  = /etc/systemd/system/ventilation-core.service.d/97-alert-v2-stage5-read-only.conf
```

Stage 6 nie zmienia tego runtime i nie aktualizuje worktree Stage 5 podczas pracy produkcyjnego core.

Nowy validator powinien być uruchamiany z osobnego worktree Stage 6.

## 3. Validator

Dodano:

```text
tools/validate_alert_v2_stage6_reboot_soak_cm5.py
```

Ma dwa tryby:

```text
prepare
verify
```

### `prepare`

Przed rebootem validator wymaga:

```text
ventilation-core.service = active
wvc-service-agent.service = active
core CWD = /home/wentylacja/wvc-alert-v2-stage4
mode = STOP
supply = 0.0 V
extract = 0.0 V
output_state_known = true
hardware_ready = true
AlertV2 runtime_mode = read_only_mapping
control_policy_applied = false
unmapped_active_alerts = 0
Service Plane correlation = read_only
```

Waliduje także lokalny Web GUI na `127.0.0.1:18091` wyłącznie przez GET:

```text
/api/v1/state
/api/v1/alerts
/api/v1/health
```

Następnie zapisuje baseline do:

```text
/var/lib/workshop-ventilation/alert-v2-stage6-reboot-baseline.json
```

Baseline zawiera m.in.:

- kernel `boot_id`,
- PID core i Service Agent,
- runtime CWD,
- policy version/SHA/count,
- do 50 najnowszych identyfikatorów incydentów alertowych do kontroli trwałości historii,
- stan STOP/0 V,
- stan Web GUI.

Nie zapisuje do `alerts.sqlite3` i nie wykonuje ACK/CLEAR.

## 4. Reboot

Reboot jest wykonywany świadomie przez operatora osobną komendą systemową.

Validator sam nie restartuje CM5 ani żadnej usługi.

Po reboot systemd ma sam odtworzyć Stage 5 runtime z istniejącego drop-in.

## 5. `verify` + soak

Po restarcie validator wymaga:

```text
boot_id != pre-reboot boot_id
core PID != pre-reboot core PID
Service Agent PID != pre-reboot PID
core CWD = /home/wentylacja/wvc-alert-v2-stage4
policy version/SHA/count = identyczne jak przed rebootem
```

Następnie przez domyślnie 180 s wykonuje read-only soak.

W każdej iteracji sprawdzane są:

```text
core PID stabilny
Service Agent PID stabilny
STOP / 0 V
hardware_ready = true
AlertV2 loaded/read_only_mapping
control_policy_applied = false
unmapped_active_alerts = 0
Service Plane correlation = read_only
każdy aktywny alert ma alert_v2.mapped=true
Web GUI state/alerts/health = HTTP 200 i poprawny kontrakt
```

Rejestrowane są p50/p95/max dla:

- core `status`,
- core `alerts`,
- Web GUI `/api/v1/state`,
- Web GUI `/api/v1/alerts`,
- Web GUI `/api/v1/health`.

Nie wprowadzamy arbitralnego progu latency w Stage 6; zbieramy baseline produkcyjny.

## 6. Lifecycle/history

Po soak validator sprawdza, czy incydenty zapisane w baseline przed rebootem nadal są widoczne w aktywnych alertach albo historii po rebootem.

To potwierdza, że restart CM5 nie wyczyścił produkcyjnego lifecycle alertów.

Stage 6 nie generuje celowo nowego faultu i nie modyfikuje istniejących rekordów.

## 7. Granica Web GUI / HMI

Stage 6 sprawdza wyłącznie dostępność i spójność API HMI/Web GUI.

Nie wykonuje żadnego POST do Web GUI.

Jedyny dozwolony automatyczny wyjątek pozostaje poza AlertV2 control policy:

```text
HMI ↔ CM5 communication lost
-> lokalny full-screen block GUI
-> retry
-> auto-clear po odzyskaniu komunikacji
```

Nie zmienia to DAC, setpointów, AERO ani żadnego urządzenia wykonawczego.

## 8. Kryterium PASS

Stage 6 uznajemy za PASS, gdy po rzeczywistym reboot:

```text
boot_id changed
Stage 5 systemd runtime persisted
policy SHA/version/count unchanged
history incident IDs persisted
core PID stable during soak
Service Agent PID stable during soak
Web GUI API healthy throughout soak
STOP / 0 V throughout soak
control_policy_applied = false
reaction_execution_enabled = false
validator control commands = 0
```

## 9. Czego Stage 6 NIE robi

Stage 6 nie:

- wykonuje `reaction` z TOML,
- uruchamia `fallback_local`, `safe_state`, `recover_safe_outputs` na podstawie AlertV2,
- zmienia napięć wentylatorów,
- steruje AERO,
- steruje Zigbee,
- modyfikuje harmonogramów,
- robi ACK alertów,
- usuwa historii,
- restartuje usług w ramach samego validatora,
- aktualizuje produkcyjnego worktree Stage 5.

Istniejące niezależne zabezpieczenia `ventilation-core` pozostają bez zmian i nie są częścią automatyki AlertV2.

**Status przed CM5:** PREPARED, NOT YET REBOOT/SOAK VALIDATED.
