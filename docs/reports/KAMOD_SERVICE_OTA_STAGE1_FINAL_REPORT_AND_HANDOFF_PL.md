# KAmod Service OTA Stage 1 — raport końcowy i handoff

Data: 2026-08-08

## 1. Status etapu

`KAmod Service OTA Stage 1` jest zakończony i zwalidowany sprzętowo na obu fizycznych węzłach `KAmod ESP32 POW RS485 + SEN55`.

Końcowy wynik:

```text
sensor-node-1: FULL PASS
sensor-node-2: FULL PASS
DUAL-NODE SERVICE OTA STAGE 1: FULL PASS
```

Nie są wymagane dalsze testy sprzętowe OTA w ramach Stage 1.

## 2. Architektura, która pozostaje obowiązująca

```text
RS-485 Modbus RTU: jedyny kanał produkcyjny
Wi-Fi WVC-SERVICE: best-effort kanał serwisowy
OTA: ręczna operacja serwisowa, jeden węzeł naraz
A/B + rollback: aktywne
ventilation-core: niezależny od OTA i Wi-Fi
```

OTA nie może:

- dostarczać pomiarów do logiki sterowania,
- zastępować SENSOR BUS,
- restartować `ventilation-core`,
- modyfikować AERO BUS ani DAC,
- wykonywać aktualizacji równolegle na dwóch węzłach.

## 3. Końcowy firmware obu węzłów

Docelowy firmware po walidacji:

```text
service firmware: 0.5.1-stage1-fix1
app metadata: 0.5.1.1
packed Modbus firmware version: 0x0005
```

Zweryfikowany obraz OTA:

```text
/home/wentylacja/ota/kamod_sen55_sensor_node-0.5.1-stage1-fix1.bin
size: 1005312 B
SHA-256: 8103de1f81c286f43d69826c458b03af47150706742afe38c810a0052097d32b
```

Końcowy stan:

```text
sensor-node-1: firmware 0.5.1-stage1-fix1, ota_1, valid, pending=false
sensor-node-2: firmware 0.5.1-stage1-fix1, ota_1, valid, pending=false
```

## 4. sensor-node-1 — pełna walidacja mechanizmu

Na node 1 wykonano kompletną walidację dodatnią i negatywną:

```text
poprawne OTA: PASS
przerwany transfer: PASS
błędny HMAC: PASS
błędny SHA-256: PASS
niepotwierdzony obraz + rollback: PASS
```

Podczas pierwszych prób wykryto i naprawiono problem stosu zadania HTTP OTA. Finalny firmware zawiera m.in. większy stos serwera OTA, bufor odbiorczy na heapie, stack canary, watchpoint końca stosu, strong stack protection i zabezpieczony zapis coredumpu.

Po stronie CM5 dodano także bezpieczne retry wyłącznie dla idempotentnych `GET /status` i `GET /challenge`, aby tolerować chwilowe timeouty best-effort Wi-Fi. Transfer `POST /image` nie jest automatycznie ponawiany.

Szczegółowy raport:

`docs/reports/KAMOD_SERVICE_OTA_STAGE1_NEGATIVE_PATH_VALIDATION_PL.md`

## 5. sensor-node-2 — bootstrap i normalna aktualizacja OTA

Node 2 startował z:

```text
node_id: sensor-node-2
Modbus address: 2
firmware: 0.4.0-stage1
IP: 10.55.0.110
MAC: 88:13:BF:01:37:28
```

Wykonano jednorazowy bootstrap USB przez `app-flash`, bez `erase-flash`, dzięki czemu zachowano NVS, `node_id`, adres Modbus, konfigurację Wi-Fi i indywidualny provisioning HMAC.

Bootstrap:

```text
firmware: 0.5.0-stage1-fix1
app metadata: 0.5.0.1
size: 1005312 B
lokalny SHA-256 builda: 3F8D17CB3B2067D2E4B688A19FE327259645FA19B4152F16859A4A2A742EF1EF
partition: ota_0
pending: false
image_state: valid
```

Po bootstrapie potwierdzono:

```text
node_id: sensor-node-2
modbus_address: 2
sensor_state: running
rs485_ready: true
modbus_monitor_ready: true
```

Następnie wykonano jedną właściwą aktualizację OTA:

```text
operation_id: 1786185893-7b259ba8
source_partition: ota_0
target_partition: ota_1
bytes_sent: 1005312
bytes_written: 1005312
state: queued -> uploading -> rebooting -> validating -> succeeded
```

Stan końcowy node 2:

```text
firmware: 0.5.1-stage1-fix1
partition: ota_1
pending: false
image_state: valid
state: idle
last_error: ""
```

Nie powtarzano na node 2 testów przerwania, błędnego HMAC, błędnego SHA ani wymuszonego rollbacku, ponieważ mechanizm i ten sam kod zostały wcześniej pełnie zwalidowane na node 1. Node 2 przeszedł właściwy smoke test egzemplarza: bootstrap, provisioning, SEN55, Modbus i normalne OTA.

Szczegółowy raport dual-node:

`docs/reports/KAMOD_SERVICE_OTA_STAGE1_DUAL_NODE_FINAL_VALIDATION_PL.md`

## 6. Końcowy postcheck SENSOR BUS

Po zakończeniu OTA node 2:

```text
port: /dev/ttyAMA0
baudrate: 19200
addresses: [1, 2]
ready: true
worker_alive: true
worker_restarts: 0
last_error: null
```

Oba węzły jednocześnie:

```text
online: true
usable: true
measurement_valid: true
measurement_stale: false
sensor_present: true
sensor_errors: 0
modbus_service_errors: 0
consecutive_failures: 0
```

Zachowano niezależność produkcyjnego SENSOR BUS od operacji OTA.

## 7. Obrazy, których nie wolno używać produkcyjnie

### Stary podatny obraz

```text
/home/wentylacja/ota/kamod_sen55_sensor_node-0.5.1-stage1.bin
```

Ten obraz zawiera starą, podatną wersję handlera OTA i nie może być ponownie używany.

### Obraz rollback-test

```text
/home/wentylacja/ota/kamod_sen55_sensor_node-0.5.2-stage1-rollback-test.bin
```

Jest to wyłącznie obraz testowy. Nigdy nie używać go jako obrazu produkcyjnego.

Po testach lokalny Windows build został oczyszczony i normalna konfiguracja ma:

```text
CONFIG_WVC_OTA_ROLLBACK_TEST_IMAGE is not set
normal version marker: present
rollback-test version marker: absent
```

## 8. Stan GitHub na moment zamknięcia etapu

Repozytorium:

`autoklinika/workshop-ventilation-controller`

Gałąź Stage 1:

`agent/kamod-service-ota-stage1`

Draft PR:

`#14 — KAmod Service OTA Stage 1: authenticated A/B update bootstrap`

PR pozostaje celowo `Draft`, `Open` i nie został scalony. Nie wolno wykonywać merge ani oznaczać go jako Ready for Review bez osobnego polecenia użytkownika.

Checkpoint bezpośrednio po dual-node hardware validation:

`83de49494a69fab179a36353701dff6f0213bf4d`

Powiązane stacked Draft PR-y warstwy serwisowej nadal należy traktować jako osobne elementy historii integracji i nie zamykać/scalać ich automatycznie tylko dlatego, że hardware OTA został zwalidowany.

## 9. Co uznajemy za zakończone

- firmware OTA-capable na obu fizycznych KAmod,
- ręczne OTA po prywatnym Wi-Fi,
- HMAC per-node,
- A/B,
- 30 s self-test i confirmation,
- automatyczny rollback obrazu niepotwierdzonego,
- rozpoznawanie rollbacku przez CM5,
- bezpieczna obsługa przerwanego transferu,
- odrzucenie błędnego HMAC,
- odrzucenie błędnego SHA,
- post-transfer reconciliation,
- retry bezpiecznych GET-ów serwisowych,
- potwierdzenie zachowania NVS/provisioningu przy bootstrapie,
- potwierdzenie niezależności SENSOR BUS,
- pełne wdrożenie docelowego firmware na obu węzłach.

## 10. Handoff

W kolejnej rozmowie nie należy ponownie otwierać Stage 1 ani wykonywać kolejnych destrukcyjnych testów OTA bez nowej, konkretnej przyczyny.

Nowa rozmowa powinna najpierw:

1. sprawdzić rzeczywisty aktualny HEAD repo i stan otwartych PR-ów,
2. przeczytać ten raport oraz raport dual-node i negative-path,
3. uznać `KAmod Service OTA Stage 1` za zakończony sprzętowo,
4. nie flashować żadnego KAmod podczas samej orientacji,
5. nie wykonywać merge/Ready bez wyraźnego polecenia użytkownika,
6. dopiero potem przejść do kolejnego wybranego etapu projektu.
