# KAmod Service OTA Stage 1 — incydent pierwszego transferu i odzyskanie ścieżki OTA

Data: 2026-08-06 / aktualizacja: 2026-08-08

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

Pierwotny obraz:

```text
rozmiar: 972848 B
SHA-256: 91f6dd48a6a9c1755f4f7b4c98af9fe36399ea623102a56fd4e594f9391c911c
```

Stan wejściowy obu pierwszych prób był prawidłowy:

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

## 6. Wniosek bezpieczeństwa z dwóch pierwszych prób

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

Panika nastąpiła po przesłaniu pełnego obrazu, w rejonie najgłębszej ścieżki stosu: finalizacja SHA-256, `esp_ota_end` albo przygotowanie końcowej odpowiedzi. Najbardziej prawdopodobne jest przepełnienie stosu zadania HTTP.

## 8. Poprawka firmware

Bootstrap diagnostyczny i naprawczy:

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
- checkpointy raportują wolny heap i high-water mark stosu zadania HTTP,
- włączony FreeRTOS stack canary,
- włączony hardware watchpoint końca stosu,
- włączony `CONFIG_COMPILER_STACK_CHECK_MODE_STRONG`,
- osobny stos 2048 B dla zapisu coredumpu.

## 9. Zabezpieczony coredump i wynik analizy

Coredump odczytano przed przebudowaniem lokalnego obrazu:

```text
plik: ota_panic_sensor-node-1_coredump.raw
rozmiar: 262144 B
offset partycji: 0x3C0000
SHA-256: 4C2696D08BF796E0396C4ABFA57E35EAED05A5AC35CE9C7F286997B528EF7E95
```

`idf.py coredump-info` potwierdził:

```text
EXCCAUSE: 0x1c LoadProhibitedCause
EXCVADDR: 0x800d879f
PC: 0x4008b9a1 prvSelectHighestPriorityTaskSMP
A2: 0xA5A5A5A5
A3: 0xA5A5A5A5
```

Coredump nie odtworzył nazw zadań ani pełnego stosu aplikacji. Dane TCB i raportowane rozmiary stosów były niespójne, co jest dodatkowym dowodem uszkodzenia pamięci zadania przed wejściem w obsługę paniki.

Mapowanie adresów z ELF działającego `0.5.0-stage1`:

```text
0x400d875b: uart_write, uart_vfs.c:237
0x400d879f: uart_fstat, uart_vfs.c:350
0x40081312: spi_flash_op_block_func, cache_utils.c:108
0x4008b9a1: prvSelectHighestPriorityTaskSMP, tasks.c:3619
0x4008bd21: vTaskSwitchContext / prvTaskExitCriticalSafeSMPOnly
```

Adresy `uart_write` i `uart_fstat` są fragmentami uszkodzonej ramki wywołań lub zakodowanymi adresami powrotu, a nie dowodem awarii sprzętowego UART. Wyjątek został zarejestrowany w schedulerze podczas operacji zapisu flash, gdy FreeRTOS używał już uszkodzonego TCB/stosu. Całość jest spójna z przepełnieniem stosu zadania HTTP podczas jednoczesnego odbioru, zapisu flash, SHA-256 i logowania.

## 10. Walidacja bootstrapu `0.5.0-stage1-fix1`

Bootstrap został wgrany przez USB wyłącznie na `sensor-node-1` poleceniem `app-flash`, bez kasowania NVS i bez zmiany tablicy partycji.

Stan po uruchomieniu:

```text
firmware: 0.5.0-stage1-fix1
partition: ota_0
pending: false
image_state: valid
state: idle
reset_reason: 1
SEN55: running
RS-485: ready
```

Brak zapytań Modbus widoczny w pierwszym postchecku był wynikiem fizycznie odłączonego przewodu RS-485 podczas serwisu, a nie regresją firmware.

## 11. Trzecia próba — pierwszy pełny sukces OTA

Po ponownym zbudowaniu obrazu z tym samym utwardzeniem i wyższą wersją przygotowano:

```text
ESP app version: 0.5.1.1
heartbeat/status: 0.5.1-stage1-fix1
plik: kamod_sen55_sensor_node-0.5.1-stage1-fix1.bin
rozmiar: 1005312 B
SHA-256: 8103de1f81c286f43d69826c458b03af47150706742afe38c810a0052097d32b
checksum obrazu: valid
validation hash: valid
```

Operacja CM5:

```text
operation_id: 1786174325-ae4558c2
source_partition: ota_0
target_partition: ota_1
```

Zaobserwowany przebieg:

```text
queued
uploading
bytes_sent: 1005312 / 1005312
rebooting
validating
succeeded
```

Końcowa odpowiedź firmware przed restartem potwierdziła pełny zapis obrazu:

```text
result: accepted
bytes_written: 1005312
image_sha256: 8103de1f81c286f43d69826c458b03af47150706742afe38c810a0052097d32b
target_partition: ota_1
rebooting: true
```

Po restarcie i pełnym oknie walidacji węzeł raportował:

```text
firmware: 0.5.1-stage1-fix1
partition: ota_1
pending: false
image_state: valid
state: idle
last_error: ""
```

Wynik:

```text
OTA transfer + commit: PASS
ota_0 -> ota_1 boot switch: PASS
30 s health validation: PASS
mark image valid / cancel rollback: PASS
final Service Agent state: succeeded
panic/reset during transfer: BRAK
```

Jest to pierwszy pełny sprzętowy PASS dodatniej ścieżki OTA Stage 1 na `sensor-node-1`.

## 12. Pozostałe testy Stage 1

Przed dopuszczeniem `sensor-node-2` do bootstrapu OTA należy wykonać nadal wyłącznie na `sensor-node-1`:

1. postcheck produkcyjnego SENSOR BUS po udanym OTA,
2. przerwany transfer — brak zmiany aktywnej partycji,
3. błędny HMAC — odrzucenie bez zapisu,
4. błędny SHA-256 — odrzucenie/abort bez zmiany boot partition,
5. wymuszony niezdrowy obraz — automatyczny rollback.

Dopiero po pełnym PASS powyższych scenariuszy można rozważyć bootstrap OTA dla `sensor-node-2`.

PR #14 pozostaje Draft. Nie wykonywać merge ani Ready for Review bez wyraźnego polecenia użytkownika.
