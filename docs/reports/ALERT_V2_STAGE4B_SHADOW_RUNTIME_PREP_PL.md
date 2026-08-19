# AlertV2 — Stage 4B live shadow runtime preparation

**Data:** 2026-08-19  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/core-alert-v2-design-stage1`  
**Draft PR:** #44

## 1. Cel

Stage 4B ma uruchomić na rzeczywistym CM5 osobny proces AlertV2, który pracuje równolegle do produkcyjnego `ventilation-core`, ale **nie posiada żadnego sprzętu i nie ma żadnej ścieżki sterującej**.

Proces testowy wykorzystuje rzeczywiste dane produkcyjne wyłącznie przez lokalne interfejsy read-only:

```text
ventilation-core.sock: status, alerts
wvc-service-agent: status
```

Na tych danych wykonuje:

- rzeczywistą walidowaną politykę AlertV2 TOML,
- rzeczywisty Stage 3 `ServicePlaneCorrelatingAlertRegistry`,
- mapowanie aktywnych alertów,
- wyliczenie najwyższej aktywnej wagi i koloru HMI,
- diagnostykę korelacji.

Nie używa produkcyjnego SQLite Alert Registry i nie wykonuje `reaction` z TOML.

## 2. Bezpieczeństwo

Stage 4B ma twardą allowlistę poleceń produkcyjnego core:

```text
status
alerts
```

Każda próba użycia innego polecenia jest odrzucana przed transportem.

Proces nie posiada:

- DAC,
- UART SENSOR BUS,
- UART AERO,
- GPIO TACHO,
- Zigbee control API,
- schedule write API,
- OTA,
- ACK alertów,
- dostępu do produkcyjnego `alerts.sqlite3`.

Przed pierwszym snapshotem i przy każdym kolejnym odświeżeniu wymagane jest:

```text
mode=STOP
supply_voltage=0.0
extract_voltage=0.0
output_state_known=true
```

Jeżeli produkcja opuści STOP/0 V, Stage 4B zgłasza błąd i przestaje publikować zdrowy snapshot. Nie wysyła sam polecenia STOP.

Twarde pole runtime:

```text
write_commands_sent=0
control_policy_applied=false
```

## 3. Implementacja

Dodano:

```text
src/ventilation_core/alert_v2_stage4b_runtime.py
tools/run_alert_v2_stage4b_shadow_runtime.py
tools/validate_alert_v2_stage4b_cm5.py
tests/test_alert_v2_stage4b_shadow_runtime.py
```

### Shadow runtime

`Stage4BShadowRuntime`:

1. czyta produkcyjny `status`,
2. wymusza warunek STOP/0 V,
3. czyta produkcyjne aktywne alerty przez `alerts`,
4. zamienia je na aktualne `AlertSignal`,
5. wykonuje Stage 3 correlation w `MemoryAlertStore`,
6. mapuje wynik przez `RuntimeAlertPolicyManager`,
7. publikuje wyłącznie lokalne `status` przez osobny Unix socket.

Domyślny socket testowy:

```text
/tmp/wvc-alert-v2-stage4b.sock
```

Walidator używa jednak socketu we własnym katalogu tymczasowym, więc po teście nie zostaje stały runtime endpoint.

## 4. Walidator CM5

`tools/validate_alert_v2_stage4b_cm5.py` automatycznie:

- sprawdza `ventilation-core.service` i `wvc-service-agent.service`,
- zapamiętuje oba PID,
- potwierdza produkcyjne STOP/0 V,
- uruchamia Stage 4B jako osobny proces użytkownika,
- czeka na jego read-only socket,
- pobiera serię snapshotów produkcji i shadow runtime,
- sprawdza politykę 49 alertów,
- wymaga `unmapped_active_alerts=0`,
- wymaga `correlation.reason=correlation_complete`,
- wymaga `control_policy_applied=false`,
- wymaga `write_commands_sent=0`,
- mierzy latencję produkcyjnego `status`, shadow `status` i pełnego refreshu shadow runtime,
- po teście potwierdza brak zmiany PID produkcyjnego core i Service Agent,
- kończy proces shadow runtime i usuwa jego socket.

Opcjonalny parametr:

```text
--baseline-core-p95-ms
```

służy wyłącznie do porównania z Stage 4A. Nie jest jeszcze automatycznym progiem PASS/FAIL.

## 5. Oczekiwany wynik na aktualnym CM5

Po Stage 4A oczekujemy:

- produkcja przez cały test `STOP / 0 V / 0 V`,
- PID `ventilation-core` bez zmian,
- PID `wvc-service-agent` bez zmian,
- `write_commands_sent=0`,
- `control_policy_applied=false`,
- wszystkie aktywne alerty z produkcji mapują się do AlertV2,
- brak nowych skorelowanych błędów Service Plane przy zdrowych obu KAmod,
- kolor i aktywna waga wynikają z rzeczywistych bieżących alertów (obecnie mogą być inne niż zielony z powodu niezależnych alarmów AERO/Zigbee),
- latencja produkcyjnego core pozostaje zbliżona do baseline Stage 4A.

## 6. Stage 4A baseline

Z rzeczywistej walidacji CM5:

```text
core p95 = 2.431 ms
service agent p95 = 0.570 ms
core PID remained unchanged
STOP / 0 V throughout
node mapping 1->1, 2->2 PASS
```

Stage 4B porówna nowy pomiar `core p95` z wartością 2.431 ms, ale bez arbitralnego automatycznego limitu.

## 7. Granica etapu

Stage 4B nadal NIE zawiera:

- fault injection,
- heartbeat dropout,
- odpinania Modbus,
- nowych reakcji sterujących,
- operational TACHO,
- fizycznego sterowania RGB HMI.

Dopiero po PASS Stage 4B można przygotować Stage 4C z kontrolowanym fault injection. Pierwszym testem Stage 4C powinien być service-heartbeat-only dropout przy działającym produkcyjnym Modbus; następnie osobno korelacja heartbeat + SENSOR BUS dropout.
