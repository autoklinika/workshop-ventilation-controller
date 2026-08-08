# KAmod Service OTA Stage 1 — końcowa walidacja dwóch węzłów

Data: 2026-08-08

## Wynik

`KAmod Service OTA Stage 1` został zwalidowany sprzętowo na obu fizycznych węzłach `KAmod ESP32 POW RS485 + SEN55`.

Końcowy wynik:

```text
sensor-node-1: FULL PASS
sensor-node-2: FULL PASS
DUAL-NODE SERVICE OTA STAGE 1: FULL PASS
```

## Architektura zachowana podczas walidacji

```text
RS-485 Modbus RTU: jedyny kanał produkcyjny
Wi-Fi: best-effort kanał serwisowy
OTA: ręczna operacja serwisowa, jeden węzeł naraz
A/B + rollback: aktywne
ventilation-core: niezależny od OTA
```

## sensor-node-1 — pełna walidacja mechanizmu

Na `sensor-node-1` wykonano pełny zakres walidacji dodatniej i negatywnej:

```text
poprawna aktualizacja OTA: PASS
kontrolowane przerwanie transferu: PASS
błędny HMAC: PASS
błędny SHA-256: PASS
niepotwierdzony obraz + automatyczny rollback: PASS
```

Końcowy stan node 1 po testach:

```text
firmware: 0.5.1-stage1-fix1
partition: ota_1
pending: false
image_state: valid
```

Szczegółowa walidacja ścieżek negatywnych znajduje się w:

`docs/reports/KAMOD_SERVICE_OTA_STAGE1_NEGATIVE_PATH_VALIDATION_PL.md`

## sensor-node-2 — bootstrap i właściwe OTA

Po zamknięciu pełnej walidacji mechanizmu na node 1 wykonano skróconą walidację egzemplarza node 2 bez powtarzania destrukcyjnych testów negatywnych.

### Bootstrap USB

Node 2 przed bootstrapem pracował jako:

```text
node_id: sensor-node-2
Modbus address: 2
firmware: 0.4.0-stage1
partition: ota_0
```

Zbudowano zwalidowany bootstrap z checkpointu `6f6efcb113b9fe6cb427ff21a72867dc2ed89348`:

```text
service firmware: 0.5.0-stage1-fix1
app metadata: 0.5.0.1
size: 1005312 B
SHA-256: 3F8D17CB3B2067D2E4B688A19FE327259645FA19B4152F16859A4A2A742EF1EF
CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y
```

USB wykonano wyłącznie przez `app-flash`, bez `erase-flash` i bez nadpisywania NVS.

Weryfikacja zapisu:

```text
Wrote 1005312 bytes
Verifying written data...
Hash of data verified.
Hard resetting via RTS pin...
Done
```

Po bootstrapie endpoint OTA potwierdził zachowanie provisioningu i poprawny stan:

```text
node_id: sensor-node-2
address: 10.55.0.110
firmware: 0.5.0-stage1-fix1
partition: ota_0
pending: false
image_state: valid
state: idle
```

Heartbeat potwierdził również:

```text
MAC: 88:13:BF:01:37:28
key_id: sensor-node-2-v1
modbus_address: 2
sensor_state: running
rs485_ready: true
modbus_monitor_ready: true
```

### Postcheck SENSOR BUS przed OTA

Po ponownym podłączeniu RS-485 slave 2 był poprawnie widoczny przez CM5:

```text
slave_address: 2
online: true
usable: true
measurement_valid: true
measurement_stale: false
sensor_present: true
modbus_service_errors: 0
consecutive_failures: 0
firmware_version: 0.5
```

### Właściwa aktualizacja OTA node 2

Docelowy obraz:

```text
kamod_sen55_sensor_node-0.5.1-stage1-fix1.bin
size: 1005312 B
SHA-256: 8103de1f81c286f43d69826c458b03af47150706742afe38c810a0052097d32b
```

Operacja:

```text
operation_id: 1786185893-7b259ba8
source_partition: ota_0
target_partition: ota_1
```

Pełny transfer został zaakceptowany:

```text
bytes_sent: 1005312
bytes_written: 1005312
result: accepted
target_partition: ota_1
rebooting: true
```

Koordynator przeszedł przez:

```text
queued -> uploading -> rebooting -> validating -> succeeded
```

Stan końcowy:

```text
firmware: 0.5.1-stage1-fix1
partition: ota_1
pending: false
image_state: valid
state: idle
last_error: ""
```

## Końcowy postcheck produkcyjnego SENSOR BUS

Po zakończeniu OTA node 2 CM5 raportował:

```text
port: /dev/ttyAMA0
baudrate: 19200
addresses: [1, 2]
ready: true
worker_alive: true
worker_restarts: 0
last_error: null
```

Node 1:

```text
slave_address: 1
online: true
usable: true
measurement_valid: true
measurement_stale: false
sensor_present: true
availability_mask: 255
status_mask: 3
sensor_errors: 0
modbus_service_errors: 0
consecutive_failures: 0
last_error: null
```

Node 2:

```text
slave_address: 2
online: true
usable: true
measurement_valid: true
measurement_stale: false
sensor_present: true
availability_mask: 255
status_mask: 3
sensor_errors: 0
modbus_service_errors: 0
consecutive_failures: 0
last_error: null
```

Historyczne liczniki `communication_errors`, `invalid_measurements` i `stale_measurements` obejmują wcześniejsze kontrolowane rozłączenia i testy. Nie wskazują aktywnej awarii: oba węzły mają świeże pomiary, `consecutive_failures=0`, a worker nie został zrestartowany.

## Końcowy stan dwóch węzłów

```text
sensor-node-1:
  firmware: 0.5.1-stage1-fix1
  partition: ota_1
  pending: false
  Modbus address: 1

sensor-node-2:
  firmware: 0.5.1-stage1-fix1
  partition: ota_1
  pending: false
  Modbus address: 2
```

## Decyzja walidacyjna

Nie ma potrzeby powtarzania na `sensor-node-2` testów przerwanego transferu, błędnego HMAC, błędnego SHA-256 ani wymuszonego rollbacku. Mechanizm został wcześniej pełnie zwalidowany sprzętowo na `sensor-node-1`; node 2 potwierdził poprawność własnego provisioningu, fizycznego egzemplarza, endpointu OTA, aktualizacji A/B i powrotu do pracy produkcyjnej po aktualizacji.

```text
KAmod Service OTA Stage 1 — hardware validation complete
sensor-node-1: FULL PASS
sensor-node-2: FULL PASS
SENSOR BUS continuity: FULL PASS
```

PR #14 pozostaje Draft. Nie wykonywać merge ani Ready for Review bez wyraźnego polecenia użytkownika.
