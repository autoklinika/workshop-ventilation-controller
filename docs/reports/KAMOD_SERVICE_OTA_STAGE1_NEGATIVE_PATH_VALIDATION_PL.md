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

## 3. Pozostałe testy

Nadal wyłącznie na `sensor-node-1`:

1. błędny SHA-256 przy prawidłowym HMAC — pełny zapis do nieaktywnej partycji ma zakończyć się `esp_ota_abort` bez zmiany boot partition,
2. wymuszony niezdrowy obraz — automatyczny rollback do poprzedniego obrazu.

Dopiero po pełnym PASS obu scenariuszy można rozważyć bootstrap OTA dla `sensor-node-2`.

PR #14 pozostaje Draft. Nie wykonywać merge ani Ready for Review bez wyraźnego polecenia użytkownika.
