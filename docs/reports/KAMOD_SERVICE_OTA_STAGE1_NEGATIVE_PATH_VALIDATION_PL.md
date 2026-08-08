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

## 4. Pozostały test Stage 1

Nadal wyłącznie na `sensor-node-1` pozostaje:

1. wymuszony niezdrowy obraz — automatyczny rollback do poprzedniego obrazu.

Dopiero po pełnym PASS tego scenariusza można rozważyć bootstrap OTA dla `sensor-node-2`.

PR #14 pozostaje Draft. Nie wykonywać merge ani Ready for Review bez wyraźnego polecenia użytkownika.
