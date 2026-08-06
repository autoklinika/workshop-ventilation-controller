# KAmod Service OTA Stage 1 — coredump paniki i bootstrap fix1

Data: 2026-08-06

## 1. Potwierdzony stan

Druga próba OTA na `sensor-node-1` zakończyła się restartem firmware:

```text
firmware po restarcie: 0.5.0-stage1
partycja: ota_0
image_state: valid
reset_reason: 4 = ESP_RST_PANIC
```

`CONFIG_ESP_COREDUMP_ENABLE_TO_FLASH=y`, a tablica partycji zawiera partycję `coredump`. Coredump należy odczytać przed ewentualną kolejną paniką.

## 2. Odczyt coredumpu — Windows

Podłączyć przez USB wyłącznie `sensor-node-1`. Nie wykonywać jeszcze `app-flash`, `fullclean` ani `erase-flash`.

W PowerShellu ESP-IDF 6.0.2:

```powershell
cd C:\PROJEKTY\workshop-ventilation-controller\firmware\sensor-node
. "C:\Espressif\esp-idf-v6.0.2\export.ps1"

Test-Path .\build\kamod_sen55_sensor_node.elf
idf.py -p COM9 coredump-info 2>&1 |
  Tee-Object -FilePath .\ota_panic_sensor-node-1_coredump.txt
```

Plik ELF musi odpowiadać obrazowi `0.5.0-stage1`, który był wgrany podczas paniki. Jeśli lokalny katalog `build` został przebudowany inną wersją, nie wykonywać analizy na niedopasowanym ELF.

Oczekiwane informacje:

- typ paniki,
- nazwa zadania, prawdopodobnie `httpd`,
- backtrace z liniami `service_ota.cpp`,
- stack high-water / uszkodzenie canary, jeśli przyczyną było przepełnienie stosu.

## 3. Poprawiony bootstrap

```text
ESP app version: 0.5.0.1
heartbeat/status: 0.5.0-stage1-fix1
Modbus packed version: 0x0005
```

Zmiany:

- bufor 4096 B przeniesiony ze stosu na heap,
- stos HTTP zwiększony do 16384 B,
- restart po odpowiedzi opóźniony do 3000 ms,
- checkpointy SHA, `esp_ota_end`, wyboru partycji i odpowiedzi,
- logowanie wolnego heap i high-water mark stosu.

## 4. Flash poprawionego bootstrapu

Dopiero po zielonym CI i zapisaniu coredumpu:

```powershell
cd C:\PROJEKTY\workshop-ventilation-controller

git fetch origin
git switch agent/kamod-service-ota-stage1
git pull --ff-only
git rev-parse HEAD

. "C:\Espressif\esp-idf-v6.0.2\export.ps1"
cd firmware\sensor-node

idf.py set-target esp32
idf.py fullclean
idf.py build
idf.py -p COM9 app-flash monitor
```

Nie wykonywać:

```text
erase-flash
erase_flash
kasowania NVS
pełnego flashowania bootloadera i tablicy partycji
```

## 5. Walidacja po USB

W monitorze wymagane:

```text
firmware=0.5.0-stage1-fix1
running_partition=ota_0
resolved Modbus slave address=1
sensor_state=running
manual authenticated OTA server started ... stack=16384
service Wi-Fi connected
```

Na CM5:

```bash
wvc-servicectl ota-status sensor-node-1
wvc-servicectl nodes
cd /home/wentylacja/workshop-ventilation-controller
PYTHONPATH=src python3 -m ventilation_core.ctl sensors
```

Wymagane:

- `sensor-node-1` online, `ota_0`, `valid`, `pending=false`,
- slave 1 online/usable/valid/non-stale,
- slave 2 bez zmian,
- `worker_restarts=0`,
- `consecutive_failures=0`.

## 6. Następny obraz OTA

Po walidacji bootstrapu należy zbudować nowy obraz docelowy zawierający tę samą poprawkę i wyższą wersję. Nie używać ponownie starego obrazu `0.5.1-stage1`, ponieważ po uruchomieniu zawierałby wadliwy handler dla kolejnych aktualizacji.

Pierwszy test po poprawce nadal obejmuje wyłącznie `sensor-node-1` i przejście `ota_0 -> ota_1`.

PR #14 pozostaje Draft. Nie wykonywać merge ani Ready for Review bez wyraźnego polecenia użytkownika.
