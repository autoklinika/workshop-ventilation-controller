# CM5 Service Plane / OTA Reconciliation — walidacja końcowa

**Data:** 2026-08-11  
**Status:** PASS  
**Gałąź:** `agent/reconcile-service-plane-ota-main`  
**Commit bazowy reconciliation:** `90fab9047adaf07857caadd8795082a032fcd794`

## 1. Cel

Celem było uporządkowanie rozjazdu między aktualnym `main` a rzeczywistym deploymentem CM5 bez utraty żadnej zwalidowanej funkcjonalności.

Zakres zachowany po reconciliation:

- `ventilation-core`,
- dwa kanały 0–10 V / DAC supervision,
- SENSOR BUS z dwoma KAmod + SEN55,
- WVC-SERVICE,
- heartbeat HMAC/replay,
- CM5 Service Agent,
- ręczne OTA po Wi-Fi,
- A/B + rollback,
- CM5 -> AI Server telemetry,
- AI Server -> CM5 advisory read-only.

AERO BUS pozostaje poza zakresem.

## 2. Repozytorium i testy

Na CM5 przełączono checkout na:

```text
agent/reconcile-service-plane-ota-main
90fab9047adaf07857caadd8795082a032fcd794
```

Lokalne testy po reconciliation:

```text
Ran 104 tests
OK
```

GitHub Actions dla commitu reconciliation:

```text
Ventilation Core Tests: PASS
Sensor node firmware:  PASS
```

## 3. Przywrócenie Service Agent

Przed wdrożeniem wykonano lokalny backup deploymentu:

```text
/root/wvc-reconcile-20260811-102325
```

Następnie wdrożono `wvc-service-agent.service` z aktualnej gałęzi reconciliation, wykorzystując istniejący rejestr kluczy HMAC.

Stan końcowy:

```text
wvc-service-agent.service:      enabled, active
wvc-service-heartbeat.service:  inactive
```

Agent nasłuchuje:

```text
UDP 10.55.0.1:45551
/run/wvc-service-agent/service-agent.sock
```

Walidator `tools/validate_cm5_service_agent.sh` przeszedł w całości:

```text
PASS: service agent active
PASS: legacy receiver inactive
PASS: key registry protected
PASS: local service API socket protected
PASS: authenticated heartbeat UDP endpoint bound
PASS: minimal heartbeat and OTA reply rules present
PASS: no service TCP ports exposed on CM5
PASS: routing remains disabled
PASS: OTA-capable service agent installed
PASS: local service API status valid
PASS: service API and manual OTA commands available
```

## 4. Stan obu KAmod po reconciliation

Oba węzły wróciły online po restarcie agenta.

### sensor-node-1

```text
online: true
IP: 10.55.0.106
MAC: 88:13:BF:00:52:D0
firmware: 0.5.1-stage1-fix1
RS-485 ready: true
Modbus address: 1
OTA partition: ota_1
OTA pending: false
sensor_state: running
```

### sensor-node-2

```text
online: true
IP: 10.55.0.110
MAC: 88:13:BF:01:37:28
firmware: 0.5.1-stage1-fix1
RS-485 ready: true
Modbus address: 2
OTA partition: ota_1
OTA pending: false
sensor_state: running
```

Heartbeat obu węzłów jest poprawnie uwierzytelniany i odbierany przez Service Agent.

## 5. OTA read-only postcheck

`wvc-servicectl ota-status sensor-node-1` zwrócił poprawnie aktualny zdalny stan:

```text
firmware: 0.5.1-stage1-fix1
partition: ota_1
pending: false
image_state: valid
state: idle
```

Historia operacji node 1 zawiera oczekiwany wcześniejszy test rollback:

```text
state: rolled_back
image: 0.5.2-stage1-rollback-test
final firmware: 0.5.1-stage1-fix1
```

`wvc-servicectl ota-status sensor-node-2` zwrócił:

```text
state history: succeeded
firmware: 0.5.1-stage1-fix1
partition: ota_1
pending: false
image_state: valid
state: idle
```

Nie uruchamiano nowej aktualizacji OTA i nie flashowano żadnego węzła podczas reconciliation.

## 6. SENSOR BUS postcheck

Po reconciliation oba urządzenia produkcyjnego SENSOR BUS pozostają zdrowe:

```text
/dev/ttyAMA0
19200 8N1
addresses: [1, 2]
ready: true
worker_alive: true
worker_restarts: 0
last_error: null
```

Dla obu węzłów:

```text
online: true
usable: true
measurement_valid: true
measurement_stale: false
sensor_present: true
communication_errors: 0
consecutive_failures: 0
invalid_measurements: 0
stale_measurements: 0
map_version_errors: 0
```

W momencie końcowego postchecku każdy węzeł miał ponad 11 000 poprawnych odpytań bez błędów komunikacji.

## 7. Izolacja pozostałych domen

Po wdrożeniu Service Agent pozostały aktywne:

```text
ventilation-core.service
wvc-telemetry-sync.service
wvc-ai-advisory.service
wvc-sensor-dhcp.service
wvc-sensor-firewall.service
```

Reconciliation nie spowodowało restartu ani degradacji `ventilation-core`, SENSOR BUS, telemetryki ani advisory.

## 8. Wniosek

**CM5 Service Plane / OTA Reconciliation: PASS.**

Aktualna gałąź reconciliation zawiera spójny zestaw funkcji odpowiadający rzeczywistemu, zwalidowanemu deploymentowi:

```text
core + DAC + SENSOR BUS + Wi-Fi service-plane + OTA + AI telemetry + AI advisory
```

Stare stacked PR-y #11–#14 mogą zostać zamknięte jako zastąpione przez PR #17. PR #17 powinien pozostać Draft do osobnej decyzji o merge do `main`.
