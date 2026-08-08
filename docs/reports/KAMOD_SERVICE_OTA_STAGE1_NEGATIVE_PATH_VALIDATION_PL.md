# KAmod Service OTA Stage 1 — walidacja ścieżek negatywnych

Data: 2026-08-08

## Zakres

Walidacja wykonywana wyłącznie na `sensor-node-1` po pierwszym pełnym PASS dodatniej ścieżki OTA:

```text
firmware: 0.5.1-stage1-fix1
partycja aktywna: ota_1
pending: false
image_state: valid
```

`sensor-node-2` pozostaje nietknięty na `0.4.0-stage1` / `ota_0`.

## 1. Kontrolowane przerwanie transferu — PASS

Transfer prawidłowego obrazu `kamod_sen55_sensor_node-0.5.1-stage1-fix1.bin` został celowo przerwany po wysłaniu 256 KiB:

```text
image_size: 1005312 B
abort_after: 262144 B
wynik klienta: EXPECTED_ABORT
```

Firmware po wykryciu niepełnego body zakończył operację błędem i zachował aktywny obraz:

```text
firmware: 0.5.1-stage1-fix1
partition: ota_1
pending: false
image_state: valid
state: error
bytes_written: 262144
expected_bytes: 1005312
target_partition: ""
last_error: ESP_FAIL
```

Nie wystąpił restart węzła. Heartbeat zachował ten sam `boot_id`. SENSOR BUS pozostał zdrowy, oba slave były `online=true` i `usable=true`, a `worker_restarts=0`.

Endpoint HTTP OTA po zakończeniu obsługi zerwanego żądania wrócił do normalnej pracy i zwrócił `HTTP 200` dla `/v1/ota/status`.

Wniosek:

```text
niepełny obraz nie został uruchomiony: PASS
brak zmiany boot partition: PASS
brak restartu node: PASS
ciągłość Modbus/SEN55: PASS
recovery endpointu OTA: PASS
```

## 2. Błędny HMAC — PASS

Wykonano kompletny minimalny `POST /v1/ota/image` z prawidłowym challenge/nonce, ale celowo nieprawidłowym `X-WVC-Authorization`.

Odpowiedź firmware:

```text
HTTP_STATUS: 401
BODY: {"ok":false,"error":"OTA HMAC authentication failed"}
BAD_HMAC_REJECTED: PASS
```

Po teście `sensor-node-1` raportował:

```text
online: true
firmware: 0.5.1-stage1-fix1
ota_partition: ota_1
ota_pending: false
heartbeat boot_id: 5efe6eab36bd9383
boot_changes: 14
uptime_s: 4221
modbus_requests_total: 3935
modbus_requests_last_60s: 56
rs485_ready: true
modbus_monitor_ready: true
sensor_state: running
```

Brak zmiany `boot_id` i rosnący uptime potwierdzają brak restartu. Błędny HMAC został odrzucony przed rozpoczęciem zapisu OTA.

Wniosek:

```text
odrzucenie złego HMAC: PASS
brak zapisu/commit OTA: PASS
brak zmiany boot partition: PASS
brak restartu node: PASS
ciągłość kanału produkcyjnego: PASS
```

## 3. Błędny SHA-256 przy prawidłowym HMAC — PASS

Wykonano pełny transfer poprawnego pliku binarnego o rozmiarze `1005312 B`, ale w metadanych zadeklarowano celowo błędny digest SHA-256 (`00` powtórzone 32 razy). HMAC został wyliczony prawidłowo dla właśnie tych metadanych, dzięki czemu test przeszedł uwierzytelnienie i dotarł do właściwej weryfikacji integralności po pełnym zapisie obrazu.

Przebieg klienta:

```text
sent=262144/1005312
sent=524288/1005312
sent=786432/1005312
sent=1005312/1005312
HTTP_STATUS: 400
BODY: {"ok":false,"error":"image SHA-256 mismatch"}
BAD_SHA_REJECTED: PASS
```

Stan endpointu OTA po odrzuceniu:

```text
firmware: 0.5.1-stage1-fix1
partition: ota_1
pending: false
image_state: valid
state: error
bytes_written: 1005312
expected_bytes: 1005312
image_sha256: 0000000000000000000000000000000000000000000000000000000000000000
target_partition: ""
last_error: image SHA-256 mismatch
```

`target_partition` pozostała pusta, czyli nie wykonano wyboru nowej partycji startowej po błędnej weryfikacji integralności.

Postcheck kanału produkcyjnego potwierdził ciągłość pracy bez restartu:

```text
heartbeat boot_id: 5efe6eab36bd9383
boot_changes: 14
uptime_s: 4982
firmware: 0.5.1-stage1-fix1
ota_partition: ota_1
ota_pending: false
modbus_requests_total: 4645
modbus_requests_last_60s: 56
rs485_ready: true
modbus_monitor_ready: true
sensor_state: running
```

SENSOR BUS:

```text
ready: true
worker_alive: true
worker_restarts: 0
last_error: null
slave 1: online=true, usable=true, measurement_valid=true, consecutive_failures=0
slave 2: online=true, usable=true, measurement_valid=true, consecutive_failures=0
```

Wniosek:

```text
pełny zapis obrazu do nieaktywnej partycji: PASS
wykrycie błędnego SHA-256: PASS
abort bez przełączenia boot partition: PASS
aktywny obraz ota_1 pozostał valid: PASS
brak restartu node: PASS
ciągłość Modbus/SEN55 i workera CM5: PASS
```

## 4. Wymuszony niepotwierdzony obraz i automatyczny rollback — PASS

Do deterministycznej walidacji przygotowano wyłącznie testowy obraz:

```text
service firmware: 0.5.2-stage1-rollback-test
plik: kamod_sen55_sensor_node-0.5.2-stage1-rollback-test.bin
rozmiar: 1005760 B
SHA-256: 26f4557aebe91c8e6615510aa06bf34c4d22798017f0aeecd31951afdc3bfe7a
```

Obraz testowy ma hook domyślnie wyłączony w normalnym buildzie. Po świadomym włączeniu przez `sdkconfig.rollback-test.defaults` wykonuje kontrolowany restart po 15 s tylko wtedy, gdy uruchomiona aplikacja znajduje się w stanie `ESP_OTA_IMG_PENDING_VERIFY`. Normalne okno potwierdzenia zdrowego obrazu pozostaje 30 s.

### 4.1 Incydent preflight i hardening klienta CM5

Pierwsza próba testu rollback zakończyła się bezpiecznie jeszcze przed transferem:

```text
state: failed
bytes_sent: 0
source_partition: null
target_partition: null
error: cannot reach OTA endpoint at 10.55.0.106:45552: timed out
```

Chwilę później ten sam endpoint odpowiadał poprawnie. Przyczyną był brak retry dla krótkich `GET /status` i `GET /challenge` w kanale Wi-Fi, który z założenia jest best-effort.

Klient CM5 został utwardzony:

```text
GET request attempts: 3
retry delay: 1.0 s
connect timeout per attempt: 5.0 s
POST firmware transfer: bez automatycznego retry
```

Odrzucone odpowiedzi protokołu, błędna tożsamość i błędy autoryzacji nadal nie są ponawiane. Automatyczne retry dotyczy wyłącznie przejściowych błędów transportowych krótkich GET-ów.

Commity hardeningu:

```text
eb09f2f338fda1f65b3070a777ce7787d90d5ffe  fix: retry transient OTA service GET timeouts
3011c3a6fbfb42d2c7621db0c247469958dc88ce  tests: cover transient OTA GET retries
```

`Ventilation Core Tests` dla `3011c3a6...` zakończyły się PASS.

### 4.2 Właściwy test rollback

Operacja:

```text
operation_id: 1786182636-a26cfd7c
source_partition: ota_1
target_partition: ota_0
image_size: 1005760 B
image_sha256: 26f4557aebe91c8e6615510aa06bf34c4d22798017f0aeecd31951afdc3bfe7a
```

Preflight i autoryzacja przeszły poprawnie. Cały obraz został wysłany i zaakceptowany:

```text
bytes_sent: 1005760
result: accepted
bytes_written: 1005760
target_partition: ota_0
rebooting: true
```

Koordynator przeszedł przez stan walidacji, zaobserwował nowy obraz jako niepotwierdzony, a następnie po kontrolowanym restarcie obrazu testowego rozpoznał automatyczny rollback do poprzedniej partycji.

Stan terminalny operacji:

```text
state: rolled_back
error: new image did not pass health validation and the node rolled back
```

Końcowy stan zdalny:

```text
firmware: 0.5.1-stage1-fix1
partition: ota_1
pending: false
image_state: valid
state: idle
bytes_written: 0
expected_bytes: 0
target_partition: ""
last_error: ""
```

Heartbeat po rollbacku:

```text
sensor-node-1:
  online: true
  firmware: 0.5.1-stage1-fix1
  ota_partition: ota_1
  ota_pending: false
  boot_changes: 16
  boot_id: 443c8973b338f502
  reset_reason: 3
  rs485_ready: true
  modbus_monitor_ready: true
  modbus_requests_last_60s: 56
  modbus_service_errors: 0
  sensor_state: running

sensor-node-2:
  online: true
  firmware: 0.4.0-stage1
  ota_partition: ota_0
  ota_pending: false
  boot_changes: 2
  boot_id: 6eaffdcd47514f84
```

Wzrost `boot_changes` dla `sensor-node-1` z 14 do 16 jest zgodny z dwoma restartami oczekiwanymi w teście: pierwszy boot nowego obrazu `ota_0`, następnie restart obrazu nadal `PENDING_VERIFY` i powrót bootloadera do poprzedniego `ota_1`.

### 4.3 Postcheck produkcyjnego SENSOR BUS

Po pełnym rollbacku CM5 raportował:

```text
port: /dev/ttyAMA0
baudrate: 19200
addresses: [1, 2]
ready: true
worker_alive: true
worker_restarts: 0
last_error: null
```

Slave 1 po rollbacku:

```text
online: true
usable: true
measurement_valid: true
measurement_stale: false
sensor_present: true
sensor_errors: 0
modbus_service_errors: 0
firmware_version: 0.5
consecutive_failures: 0
last_error: null
```

Slave 2 pozostał zdrowy i nietknięty:

```text
online: true
usable: true
measurement_valid: true
measurement_stale: false
sensor_present: true
modbus_service_errors: 0
firmware_version: 0.4
consecutive_failures: 0
last_error: null
```

Historyczne liczniki `communication_errors`, `invalid_measurements` i `stale_measurements` zawierają zdarzenia z wcześniejszych testów sprzętowych i rozłączeń. Bieżący stan jest czysty: oba węzły mają `consecutive_failures=0`, świeże pomiary i brak aktywnego błędu workera.

Wniosek:

```text
pełny transfer do nieaktywnej ota_0: PASS
przełączenie boot partition: PASS
uruchomienie obrazu PENDING_VERIFY: PASS
brak przedwczesnego potwierdzenia obrazu: PASS
automatyczny rollback bootloadera do ota_1: PASS
rozpoznanie rollbacku przez CM5 coordinator: PASS
powrót 0.5.1-stage1-fix1 jako VALID: PASS
ciągłość SENSOR BUS po rollbacku: PASS
sensor-node-2 bez zmian: PASS
```

## 5. Wynik końcowy ścieżek negatywnych Stage 1

Wszystkie wymagane scenariusze negatywne dla `sensor-node-1` zostały zwalidowane sprzętowo:

```text
przerwany transfer: FULL PASS
błędny HMAC: FULL PASS
błędny SHA-256: FULL PASS
niepotwierdzony obraz + automatyczny rollback: FULL PASS
```

Łączny wynik:

```text
KAMOD SERVICE OTA STAGE 1 — NEGATIVE PATH VALIDATION: FULL PASS
```

Kluczowe niezmienniki zostały zachowane:

```text
RS-485 Modbus RTU pozostaje jedynym kanałem produkcyjnym
Wi-Fi pozostaje best-effort kanałem serwisowym
OTA pozostaje operacją ręczną
aktualizacja odbywa się jeden węzeł naraz
ventilation-core nie jest restartowany przez OTA
sensor-node-2 pozostaje nietknięty do jawnej decyzji o kolejnym kroku
```

## 6. Końcowy sanity-check normalnego środowiska buildowego — PASS

Po zakończeniu walidacji rollback-test usunięto testowy overlay z aktywnego środowiska ESP-IDF i wygenerowano `sdkconfig` ponownie z normalnych `sdkconfig.defaults`.

Kontrola wygenerowanej konfiguracji:

```text
# CONFIG_WVC_OTA_ROLLBACK_TEST_IMAGE is not set
```

Kontrola zawartości normalnie zbudowanego obrazu aplikacji:

```text
0.5.1-stage1-fix1:             obecny
0.5.2-stage1-rollback-test:    nieobecny
```

Wynik:

```text
rollback-test hook wyłączony w normalnym buildzie: PASS
normalny identyfikator firmware obecny: PASS
testowy identyfikator firmware nieobecny: PASS
```

Obraz `0.5.2-stage1-rollback-test` pozostaje wyłącznie artefaktem walidacyjnym i nie może być używany jako firmware produkcyjny.

PR #14 pozostaje Draft. Nie wykonywać merge ani Ready for Review bez wyraźnego polecenia użytkownika.
