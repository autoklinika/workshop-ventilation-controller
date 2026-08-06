# KAmod Service OTA Stage 1 — incydent pierwszego transferu

Data: 2026-08-06

## 1. Zakres testu

Pierwszy rzeczywisty transfer OTA wykonywano wyłącznie na:

```text
node_id: sensor-node-1
adres: 10.55.0.106
wersja źródłowa: 0.5.0-stage1
partycja źródłowa: ota_0
wersja docelowa: 0.5.1-stage1
oczekiwana partycja docelowa: ota_1
```

Obraz:

```text
rozmiar: 972848 B
SHA-256: 91f6dd48a6a9c1755f4f7b4c98af9fe36399ea623102a56fd4e594f9391c911c
```

Stan wejściowy obu prób był prawidłowy:

- endpoint `WVC-OTA1` dostępny,
- obraz źródłowy `valid`, `pending=false`, `state=idle`,
- oba slave Modbus online i usable,
- `worker_alive=true`,
- `worker_restarts=0`,
- `consecutive_failures=0` dla obu slave.

## 2. Wynik pierwszej próby

Operacja CM5:

```text
operation_id: 1786030678-f2fdd438
```

Zaobserwowany przebieg:

```text
queued
uploading: 245760 / 972848 B
lokalne bytes_sent: 972848 / 972848 B
terminalny stan klienta: uncertain
```

Komunikat:

```text
OTA image body was sent completely but the final response was lost;
operation state is uncertain and must be verified with ota-status
```

Po operacji węzeł raportował:

```text
firmware: 0.5.0-stage1
partition: ota_0
pending: false
image_state: valid
state: idle
```

Obraz `0.5.1-stage1` nie został przełączony. Nie był potrzebny rollback ani flash USB.

## 3. Poprawka klienta CM5 po pierwszej próbie

Zmiany:

- timeout transferu i końcowego commit-response zwiększony z 20 s do 180 s,
- status aktywnej operacji nie otwiera drugiego połączenia HTTP do ESP32,
- przed transferem zapisywana jest partycja źródłowa i wyznaczana oczekiwana partycja docelowa,
- utrata odpowiedzi po wysłaniu pełnego body uruchamia reconciliation zamiast natychmiastowego terminalnego `uncertain`,
- reconciliation rozpoznaje sukces, rollback albo brak commitowania obrazu,
- okno walidacji po transferze zwiększone do 180 s,
- dodane testy timeoutu, izolacji statusu podczas uploadu i reconciliation po utracie odpowiedzi.

Walidacja na CM5:

```text
testy OTA: 7/7 PASS
pełny zestaw Python: 78/78 PASS
walidator instalacji Service Agenta: wszystkie pozycje PASS
```

## 4. Wynik drugiej próby

Operacja CM5:

```text
operation_id: 1786031853-12fcc386
```

Zaobserwowany przebieg:

```text
queued
preflight: ota_0 -> ota_1
uploading
bytes_sent: 972848 / 972848 B
reconciling
failed
```

Stan terminalny:

```text
error: complete image send was not committed; node remains on the source partition
firmware: 0.5.0-stage1
partition: ota_0
pending: false
image_state: valid
state: idle
```

Klient CM5 poprawnie rozstrzygnął utratę odpowiedzi jako brak commitowania, a nie pozostawił operacji w stanie niepewnym.

## 5. Dowód resetu firmware

Service Agent zarejestrował zmianę sesji startowej dokładnie podczas drugiej próby:

```text
previous boot_id: 0e018774e333f058
current boot_id: 53d330c4e5be42f9
boot_changes: 6
reset_reason: 4
```

W ESP-IDF kod `4` odpowiada `ESP_RST_PANIC`, czyli resetowi po wyjątku/panice. Nie był to kontrolowany `esp_restart()` po przyjęciu obrazu, ponieważ taki restart raportowałby `ESP_RST_SW`.

Brak zachowanego stanu `error`, `bytes_written` i `expected_bytes` po powrocie endpointu wynika z restartu procesu firmware, a nie z normalnej ścieżki `esp_ota_abort`.

## 6. Wniosek bezpieczeństwa

Mechanizm fail-safe zachował działający firmware źródłowy podczas obu prób. Incydent nie spowodował:

- zmiany aktywnej partycji,
- utraty konfiguracji NVS,
- wpływu na `sensor-node-2`,
- restartu `ventilation-core`,
- trwałej niedostępności Modbus.

Obie próby są FAIL dla transferu, ale PASS dla zachowania bezpieczeństwa A/B.

## 7. Najbardziej prawdopodobna przyczyna firmware

Handler `POST /v1/ota/image` działał w zadaniu HTTP o stosie 8192 B. Na jego stosie znajdowały się między innymi:

- bufor odbiorczy 4096 B,
- sześć buforów nagłówków po 128 B,
- bufor kanonicznej wiadomości HMAC 512 B,
- konteksty SHA-256 i HMAC,
- bufory digestów i odpowiedzi,
- ramki wywołań `esp_ota_write`, PSA Crypto i `esp_ota_end`.

Panika nastąpiła po przesłaniu pełnego obrazu, w rejonie najgłębszej ścieżki stosu: finalizacja SHA-256, `esp_ota_end` albo przygotowanie końcowej odpowiedzi. Najbardziej prawdopodobne jest przepełnienie stosu zadania HTTP. Dokładną linię ma potwierdzić zapisany w flash coredump.

## 8. Poprawka firmware

Nowy bootstrap diagnostyczny:

```text
ESP app version: 0.5.0.1
heartbeat/status: 0.5.0-stage1-fix1
```

Zmiany:

- bufor odbiorczy 4096 B przeniesiony ze stosu na heap przez `std::unique_ptr` i `std::nothrow`,
- stos zadania HTTP zwiększony z 8192 B do 16384 B,
- kontrola błędu alokacji bufora przed `esp_ota_begin`,
- opóźnienie restartu zwiększone z 1000 ms do 3000 ms,
- stos zadania restartu zwiększony do 3072 B,
- checkpointy logowania:
  - przed `esp_ota_begin`,
  - po zakończeniu odbioru,
  - po zgodnym SHA-256,
  - przed i po `esp_ota_end`,
  - po `esp_ota_set_boot_partition`,
  - po wysłaniu końcowej odpowiedzi,
- checkpointy raportują wolny heap i high-water mark stosu zadania HTTP.

## 9. Dalsza procedura

1. Nie wykonywać kolejnej próby OTA na `0.5.0-stage1`.
2. Przed zmianą lokalnego builda odczytać zapisany coredump przez USB poleceniem `idf.py coredump-info`.
3. Zbudować i wykonać `app-flash` wyłącznie `sensor-node-1` obrazem `0.5.0-stage1-fix1`, bez kasowania NVS.
4. Potwierdzić oba slave Modbus, SEN55, heartbeat i endpoint OTA.
5. Zbudować osobny docelowy obraz z tą samą poprawką i wyższą wersją.
6. Powtórzyć `ota_0 -> ota_1` wyłącznie na `sensor-node-1`.
7. Nie aktualizować `sensor-node-2` przed pełnym PASS transferu, przerwania i rollbacku.

PR #14 pozostaje Draft. Nie wykonywać merge ani Ready for Review bez wyraźnego polecenia użytkownika.
