# KAmod Service OTA Stage 1 — bootstrap i handoff sprzętowy

Data: 2026-08-06

## 1. Zakres checkpointu

Gałąź:

```text
agent/kamod-service-ota-stage1
```

Draft PR:

```text
#14
```

Checkpoint przygotowuje pierwszy firmware KAmod posiadający ręczny, uwierzytelniony kanał OTA oraz klienta OTA na CM5.

Obowiązują niezmienniki:

```text
RS-485 Modbus RTU: jedyny kanał produkcyjny
heartbeat Wi-Fi: best effort
OTA: operacja serwisowa uruchamiana jawnie przez operatora
aktualizacja: jeden węzeł naraz
```

Nie wykonywać merge ani nie oznaczać PR jako Ready for Review bez wyraźnego polecenia użytkownika.

## 2. Firmware bootstrap

Wersja:

```text
0.5.0-stage1
packed Modbus version: 0x0005
```

Firmware udostępnia na prywatnym interfejsie Wi-Fi:

```text
GET  http://NODE_IP:45552/v1/ota/challenge
GET  http://NODE_IP:45552/v1/ota/status
POST http://NODE_IP:45552/v1/ota/image
```

Modyfikacja firmware wymaga HMAC-SHA256 per node nad jednorazowym nonce, `boot_id`, rozmiarem oraz SHA-256 obrazu.

Obraz jest zapisywany strumieniowo do nieaktywnej partycji przez:

```text
esp_ota_begin
esp_ota_write
esp_ota_end
esp_ota_set_boot_partition
```

Przerwany, niepełny lub niezgodny transfer wykonuje `esp_ota_abort` i nie zmienia partycji startowej.

Nowy obraz pozostaje niepotwierdzony do czasu 30 sekund ciągłej zdrowej pracy. Potwierdzenie wymaga:

- działającego GPIO,
- działającego I2C,
- działającego RS-485,
- gotowego monitora Modbus,
- SEN55 w stanie `running`,
- pierwszego poprawnego i świeżego pomiaru,
- braku aktywnego błędu platformy.

Brak spełnienia warunków prowadzi do rollbacku przy ponownym uruchomieniu.

## 3. CM5 Service Agent

Lokalne komendy:

```text
wvc-servicectl ota-status NODE_ID
wvc-servicectl ota-install NODE_ID IMAGE.bin
```

Agent:

- pobiera klucz z chronionego rejestru `/etc/wvc-service-heartbeat/keys.json`,
- liczy SHA-256 obrazu,
- weryfikuje magiczny bajt aplikacji ESP `0xE9`,
- pobiera challenge bezpośrednio z właściwego KAmod,
- podpisuje metadane HMAC-em,
- wykonuje transfer w osobnym wątku,
- po restarcie sprawdza tożsamość węzła, partycję oraz wynik 30-sekundowego self-testu,
- rozpoznaje sukces, błąd, rollback i stan niepewny,
- nie restartuje `ventilation-core`,
- nie dotyka SENSOR BUS, DAC ani AERO BUS.

Firewall CM5 nie otwiera portu TCP. Dopuszcza wyłącznie odpowiedzi `established,related` na połączenie zainicjowane przez CM5.

## 4. Kolejność wdrożenia

Najpierw wdrażamy kod CM5. Dopiero po przejściu walidatora flashujemy jeden fizyczny KAmod.

### 4.1 CM5

```bash
cd /home/wentylacja/workshop-ventilation-controller

git fetch origin

git switch agent/kamod-service-ota-stage1 2>/dev/null || \
  git switch --track origin/agent/kamod-service-ota-stage1

git pull --ff-only

git rev-parse HEAD
```

Następnie:

```bash
sudo bash tools/install_cm5_service_agent.sh \
  /etc/wvc-service-heartbeat/keys.json

sudo bash tools/validate_cm5_service_agent.sh
```

Wymagany wynik:

- Service Agent active,
- legacy receiver inactive,
- chronione keys i Unix socket,
- UDP/45551 związany z `10.55.0.1`,
- reguła heartbeat i `established,related`,
- brak portów TCP otwartych na CM5,
- routing wyłączony,
- komendy `ota-install` i `ota-status` dostępne.

### 4.2 Windows — tylko sensor-node-1

Podłączyć przez USB wyłącznie KAmod skonfigurowany jako:

```text
node_id: sensor-node-1
Modbus:  1
```

W terminalu ESP-IDF 6.0.2:

```powershell
cd C:\PROJEKTY\workshop-ventilation-controller

git fetch origin

git switch agent/kamod-service-ota-stage1 2>$null
if ($LASTEXITCODE -ne 0) {
    git switch --track origin/agent/kamod-service-ota-stage1
}

git pull --ff-only

git rev-parse HEAD

. "C:\Espressif\esp-idf-v6.0.2\export.ps1"

cd firmware\sensor-node

idf.py set-target esp32
idf.py fullclean
idf.py build
idf.py -p COM9 app-flash monitor
```

NIE wykonywać:

```text
erase-flash
erase_flash
pełnego kasowania NVS
ponownego provisioningu
```

`app-flash` aktualizuje wyłącznie aplikację i zachowuje:

- `sensor-node-1`,
- adres Modbus 1,
- SSID `WVC-SERVICE`,
- klucz HMAC,
- pinowanie MAC.

Oczekiwane logi:

```text
firmware 0.5.0-stage1
resolved Modbus slave address=1
manual authenticated OTA server started ... port=45552
optional service task started ...
sensor_state=running
```

Wyjście z monitora:

```text
Ctrl+]
```

## 5. Kontrola po bootstrapie

Na CM5 odczekać około 40 sekund i wykonać:

```bash
wvc-servicectl ota-status sensor-node-1
```

Oczekiwane pola z endpointu:

```text
node_id:    sensor-node-1
firmware:   0.5.0-stage1
partition:  ota_0
pending:    false
state:      idle
```

Następnie:

```bash
wvc-servicectl nodes

cd /home/wentylacja/workshop-ventilation-controller
PYTHONPATH=src python3 -m ventilation_core.ctl sensors
```

Wymagane:

- node 1 online lub chwilowo best-effort offline bez wpływu na produkcję,
- heartbeat node 1 raportuje firmware `0.5.0-stage1`,
- slave 1 i slave 2 pozostają `online` i `usable`,
- pomiary obu węzłów są valid i non-stale,
- brak nowych kolejnych błędów Modbus,
- `ventilation-core` nie został zrestartowany przez wdrożenie OTA.

## 6. Czego jeszcze nie robimy

Po tym checkpointcie:

- nie flashujemy `sensor-node-2`,
- nie uruchamiamy jeszcze `ota-install` z tym samym obrazem `0.5.0-stage1`,
- nie wykonujemy merge ani Ready for Review.

Pierwszy właściwy test OTA wymaga kolejnego obrazu testowego z inną wersją, np. `0.5.1-stage1`. Test zostanie wykonany najpierw wyłącznie na `sensor-node-1` i obejmie:

1. poprawne przejście `ota_0 -> ota_1`,
2. 30-sekundowy self-test i potwierdzenie obrazu,
3. kontrolę Modbus podczas i po aktualizacji,
4. przerwany transfer bez zmiany działającej partycji,
5. błędny HMAC i błędny SHA-256,
6. wymuszony rollback niezdrowego obrazu.

Dopiero po pełnym PASS bootstrap zostanie wgrany przez USB na `sensor-node-2`.
