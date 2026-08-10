# CM5 → AI Server Telemetry — Stage 1 Final Report and Handoff

**Data:** 10.08.2026  
**Status:** PASS — etap operacyjnie zwalidowany  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/cm5-telemetry-sync-stage1`  
**Draft PR:** #15 `CM5 telemetry sync Stage 1`

## 1. Cel etapu

Celem Stage 1 było uruchomienie rzeczywistego, trwałego i odpornego na awarie toru telemetrycznego pomiędzy sterownikiem wentylacji CM5 a dedykowanym Serwerem AI, bez naruszania nadrzędnej zasady bezpieczeństwa systemu:

> CM5 steruje wentylacją. AI Server analizuje dane. AI nie posiada żadnej ścieżki sterującej do wentylacji.

Stage 1 nie obejmuje analizy przez Qwen. Jego zadaniem jest bezpieczne dostarczenie rzeczywistych danych do centralnego magazynu oraz zapewnienie lokalnego bufora na CM5.

## 2. Ostateczna architektura Stage 1

```text
SEN55 slave 1 ─┐
               ├─ RS-485 / Modbus RTU
SEN55 slave 2 ─┘
                    ↓
             ventilation-core
                    ↓
      Unix socket: read-only status
                    ↓
        wvc-telemetry-sync.service
                    ↓
       lokalna baza SQLite / pending
                    ↓
           LAN / HTTP / JSON
                    ↓
        AI Server 192.168.1.55:8080
                    ↓
              ai-bridge.service
                    ↓
               PostgreSQL
```

CM5 ma adres obserwowany przez AI Bridge jako `192.168.1.64`. AI Server działa pod adresem `192.168.1.55`.

## 3. Źródło danych na CM5

Telemetria nie odczytuje sprzętu bezpośrednio. Źródłem jest istniejący `CoreState` wystawiany przez `ventilation-core`.

Komunikacja lokalna odbywa się przez Unix socket:

```text
/run/workshop-ventilation/ventilation-core.sock
```

Klient telemetryczny wysyła dokładnie:

```json
{"command":"status"}
```

Jest to operacja wyłącznie read-only. Telemetry sync nie wywołuje `set`, `stop`, `shutdown` ani żadnej innej komendy zmieniającej stan sterowania.

Implementacja klienta:

```text
src/ventilation_core/telemetry/core_client.py
```

Timeout odczytu `CoreState` wynosi 2 s.

## 4. Dane zawarte w CoreState

Aktualny snapshot zawiera między innymi:

- `mode`: `STOP`, `MANUAL` lub `FAULT`,
- `setpoints.supply_voltage`,
- `setpoints.extract_voltage`,
- `hardware_ready`,
- `output_state_known`,
- `consecutive_hardware_failures`,
- `active_alarms`,
- pełny `sensor_bus`.

SENSOR BUS zawiera między innymi:

- port `/dev/ttyAMA0`,
- `baudrate = 19200`,
- adresy `[1, 2]`,
- `ready`,
- `worker_alive`,
- `worker_restarts`,
- `expected_map_version`,
- czasy pollingów,
- stan obu węzłów.

Każdy węzeł SEN55 przekazuje między innymi:

- `slave_address`,
- `online`,
- `usable`,
- `measurement_valid`,
- `measurement_stale`,
- `sensor_present`,
- PM1.0, PM2.5, PM4.0, PM10.0,
- wilgotność,
- temperaturę,
- VOC index,
- NOx index,
- liczniki błędów,
- uptime,
- firmware version,
- map version,
- sequence,
- last success,
- statystyki pollingów.

Nieobecne wartości są reprezentowane jako `null`; nie stosujemy sztucznych wartości zastępczych typu 0, -1 lub 9999.

## 5. Struktura modułu telemetrycznego CM5

Kod znajduje się w:

```text
src/ventilation_core/telemetry/
```

Pliki:

```text
__init__.py
agent.py
core_client.py
http_client.py
main.py
store.py
```

### `core_client.py`

Odpowiada wyłącznie za read-only odczyt `CoreState` z istniejącego Unix socket `ventilation-core`.

### `store.py`

Odpowiada za lokalną historię SQLite i trwałą kolejkę `pending`.

### `http_client.py`

Odpowiada za wysłanie batcha JSON do AI Bridge.

### `agent.py`

Rozdziela capture od synchronizacji, obsługuje retry, ACK, catch-up i retencję.

### `main.py`

CLI, parametry środowiskowe, sygnały SIGTERM/SIGINT, tryb ciągły i tryb `--once`.

## 6. Lokalna baza CM5

Docelowa ścieżka:

```text
/var/lib/workshop-ventilation/telemetry.sqlite3
```

SQLite działa z:

```text
PRAGMA journal_mode = WAL
PRAGMA synchronous = NORMAL
PRAGMA busy_timeout = 30000
```

Tabela:

```text
telemetry_samples
```

Najważniejsze pola:

```text
sequence INTEGER PRIMARY KEY AUTOINCREMENT
sample_id TEXT UNIQUE
captured_at TEXT
metrics_json TEXT
batch_id TEXT
batch_created_at TEXT
synced_at TEXT
attempts INTEGER
last_attempt_at TEXT
last_error TEXT
```

Indeksy:

```text
ix_telemetry_pending(synced_at, batch_id, sequence)
ix_telemetry_captured(captured_at)
```

`metrics_json` jest zapisywany jako kompaktowy JSON z `sort_keys=True` i bez dodatkowych separatorów whitespace.

## 7. Retencja CM5

Domyślna retencja lokalnej historii wynosi:

```text
30 dni
```

Mechanizm usuwa wyłącznie rekordy, które:

1. mają `synced_at IS NOT NULL`,
2. są starsze niż okres retencji.

Rekord oczekujący na synchronizację nie może zostać usunięty przez zwykłą retencję.

Przy interwale 5 s liczba rekordów na 30 dni wynosi:

```text
17 280 rekordów / dobę
518 400 rekordów / 30 dni
```

Dokładny budżet miejsca należy mierzyć na rzeczywistej bazie jako `page_count × page_size`, uwzględniając również bieżący WAL. Wstępny konserwatywny budżet dla obecnej struktury danych wynosi około 3 GiB, ale raport zaleca używanie pomiaru rzeczywistego po zgromadzeniu reprezentatywnej liczby rekordów.

Ważne: SQLite po `DELETE` nie musi zmniejszyć fizycznego pliku; zwolnione strony są ponownie wykorzystywane. Dlatego po osiągnięciu 30-dniowego okna baza powinna dążyć do stabilizacji rozmiaru bez konieczności cyklicznego `VACUUM`.

## 8. Identyfikacja próbek i batchy

Każda próbka otrzymuje stabilny:

```text
sample_id = UUID4
```

Każdy batch otrzymuje stabilny:

```text
batch_id = UUID4
```

Kluczowa właściwość: po nieudanej transmisji przypisany `batch_id` nie jest generowany ponownie. Ten sam batch jest ponawiany po restarcie procesu lub po odzyskaniu łączności.

Pozwala to AI Bridge wykrywać retransmisję bez duplikowania danych.

## 9. Capture i synchronizacja są rozdzielone

`TelemetryAgent` uruchamia dwa niezależne wątki:

```text
telemetry-capture
telemetry-sync
```

Domyślnie:

```text
capture interval = 5 s
sync interval = 5 s
batch size = 100
HTTP timeout = 5 s
retention = 30 dni
```

Awaria sieci lub AI Bridge nie zatrzymuje capture. Nowe snapshoty nadal trafiają do lokalnej bazy.

Awaria odczytu `CoreState` również nie wpływa na proces `ventilation-core`; błąd jest wyłącznie logowany przez proces telemetryczny.

## 10. Retry i catch-up

Retry po błędzie synchronizacji:

```text
5 s
15 s
30 s
60 s
60 s
...
```

Po poprawnym ACK licznik błędów jest resetowany.

Jeśli wysłano batch, synchronizacja nie czeka pełnych 5 s na kolejny batch — wykonuje kolejną próbę po około 50 ms. Dzięki temu backlog jest opróżniany szybko.

To zachowanie zostało zwalidowane w praktyce: po przywróceniu AI Bridge przesłano zaległy batch:

```text
samples=34 stored=34 duplicates=0
```

## 11. HTTP CM5 → AI Bridge

Bazowy adres Stage 1:

```text
http://192.168.1.55:8080
```

Endpoint:

```text
POST /api/v1/ventilation/telemetry/batches
```

Pełny URL:

```text
http://192.168.1.55:8080/api/v1/ventilation/telemetry/batches
```

Nagłówek:

```text
Content-Type: application/json
```

Przykładowa struktura batcha:

```json
{
  "schema_version": 1,
  "source_id": "workshop-ventilation-cm5-01",
  "batch_id": "<stable UUID>",
  "created_at": "<UTC timestamp>",
  "samples": [
    {
      "sample_id": "<stable UUID>",
      "sequence": 123,
      "captured_at": "<UTC timestamp>",
      "metrics": {"...": "CoreState"}
    }
  ]
}
```

## 12. Walidacja ACK

CM5 uznaje batch za zsynchronizowany dopiero po prawidłowym ACK.

Wymagania:

```text
schema_version == 1
source_id == wysłany source_id
batch_id == wysłany batch_id
status == accepted
received == liczba wysłanych próbek
rejected == 0
stored + duplicates == liczba wysłanych próbek
```

Dopiero wtedy lokalne rekordy dostają `synced_at`.

Jeśli odpowiedź HTTP jest niepoprawna lub ACK nie spełnia kontraktu, batch pozostaje `pending`.

## 13. Systemd na CM5

Jednostka repozytorium:

```text
deploy/systemd/wvc-telemetry-sync.service
```

Jednostka zainstalowana na CM5:

```text
/etc/systemd/system/wvc-telemetry-sync.service
```

Plik środowiskowy:

```text
/etc/default/wvc-telemetry-sync
```

Aktualne wartości operacyjne:

```text
WVC_AI_BRIDGE_URL=http://192.168.1.55:8080
WVC_TELEMETRY_SOURCE_ID=workshop-ventilation-cm5-01
```

Jednostka działa jako:

```text
User=wentylacja
Group=wentylacja
WorkingDirectory=/home/wentylacja/workshop-ventilation-controller
```

Ustawia:

```text
PYTHONPATH=/home/wentylacja/workshop-ventilation-controller/src
PYTHONUNBUFFERED=1
```

Używa:

```text
StateDirectory=workshop-ventilation
```

co zapewnia katalog:

```text
/var/lib/workshop-ventilation
```

Proces:

```text
/usr/bin/python3 -m ventilation_core.telemetry.main \
  --socket /run/workshop-ventilation/ventilation-core.sock \
  --database /var/lib/workshop-ventilation/telemetry.sqlite3 \
  --capture-interval 5 \
  --sync-interval 5 \
  --batch-size 100 \
  --http-timeout 5 \
  --retention-days 30 \
  --log-level INFO
```

Restart:

```text
Restart=on-failure
RestartSec=5
```

Jednostka celowo nie ma `Requires=ventilation-core.service`. Awaria telemetry sync nie może zatrzymać core.

## 14. Konfiguracja ścieżek

CLI umożliwia zmianę:

```text
--socket
--database
--ai-bridge-url
--source-id
--capture-interval
--sync-interval
--batch-size
--http-timeout
--retention-days
```

Dlatego fizyczna ścieżka lokalnej bazy CM5 nie jest zaszyta na stałe w logice aplikacji.

Mimo tej możliwości architektura zakłada, że lokalny SQLite pozostaje na lokalnym nośniku CM5. Nie należy przenosić tej bazy bezpośrednio na SMB/NFS z NAS, ponieważ pełni funkcję niezależnego bufora awaryjnego.

## 15. NAS — przyszła zmiana bez przebudowy CM5

Po uruchomieniu NAS nie zmieniamy protokołu CM5 → AI Bridge.

CM5 nadal wysyła:

```text
HTTP → 192.168.1.55:8080
```

Zmiana miejsca centralnego przechowywania będzie realizowana po stronie AI Servera / PostgreSQL / warstwy danych.

Dzięki temu CM5 nie musi znać fizycznej lokalizacji centralnego archiwum.

## 16. Walidacje wykonane na rzeczywistym systemie

### One-shot

PASS.

Rzeczywisty `CoreState` obu SEN55 został zapisany przez AI Bridge do PostgreSQL.

### Praca ciągła

PASS.

Snapshoty były wysyłane co około 5 s.

### Awaria AI Bridge

PASS.

Po zatrzymaniu AI Bridge:

- CM5 kontynuował pracę,
- SENSOR BUS pozostał zdrowy,
- oba SEN55 pozostały online,
- dane gromadziły się jako `pending`.

W jednym pomiarze:

```text
total=42
synced=28
pending=14
```

### Powrót AI Bridge

PASS.

Bez restartu CM5 nastąpił automatyczny catch-up:

```text
samples=34 stored=34 duplicates=0
```

### Systemd na CM5

PASS.

`wvc-telemetry-sync.service` działa jako `enabled` i `active`.

### Restart AI Servera

PASS.

CM5 zachował dane lokalnie i automatycznie wznowił wysyłkę po powrocie serwera.

### Restart całego CM5

PASS.

Po restarcie bez ręcznej ingerencji:

- `ventilation-core.service` wrócił jako `enabled`, `active`,
- `wvc-telemetry-sync.service` wrócił jako `enabled`, `active`,
- `hardware_ready=true`,
- `output_state_known=true`,
- `sensor_bus.ready=true`,
- `worker_alive=true`,
- `worker_restarts=0`,
- oba SEN55 `online=true`,
- oba SEN55 `usable=true`,
- oba SEN55 `measurement_valid=true`,
- brak błędów komunikacji,
- AI Bridge ponownie otrzymywał `POST ... 200 OK`.

## 17. Testy kodu

Stage 1 przeszedł:

```text
python -m compileall — PASS
unittest — 13/13 PASS
GitHub Actions Ventilation Core Tests — PASS dla implementacji
```

Testy obejmują storage, klientów, agenta i konfigurację systemd.

## 18. Granica bezpieczeństwa — stan końcowy

Najważniejsza własność systemu pozostaje zachowana:

```text
AI Server / PostgreSQL / Ollama / Qwen / NAS
                 │
                 X
        brak ścieżki sterującej
                 │
                 ↓
              CM5 DAC
```

CM5:

- steruje wentylatorami,
- wykonuje logikę bezpieczeństwa,
- działa bez sieci,
- działa bez AI Servera,
- działa bez PostgreSQL,
- działa bez Ollamy/Qwena,
- działa bez NAS.

AI Server otrzymuje dane i w przyszłości będzie przygotowywał analizę oraz rekomendacje.

## 19. Stan końcowy Stage 1

Stage 1 po stronie CM5 jest operacyjnie zakończony i zwalidowany.

Potwierdzony tor:

```text
SEN55 → CM5 → local durable history/pending → AI Bridge → PostgreSQL
```

Potwierdzono odporność na:

- niedostępność AI Bridge,
- restart AI Servera,
- restart CM5,
- przejściową niedostępność HTTP.

Nie stwierdzono wpływu telemetry sync na `ventilation-core`, DAC ani SENSOR BUS.

## 20. Następny etap

Po zamknięciu Stage 1 kolejnym logicznym etapem jest przygotowanie warstwy danych dla lokalnego modelu Qwen:

1. deterministyczne grupowanie i obliczenia po stronie Python,
2. okna analityczne, np. 15 minut,
3. przygotowanie kontrolowanego promptu,
4. analiza przez Qwen,
5. zapis rekomendacji i wykrytych anomalii,
6. brak jakiejkolwiek ścieżki wykonywania rekomendacji przez CM5.

Przyszłe wdrożenie NAS powinno dotyczyć centralnej warstwy przechowywania, a nie lokalnego bufora CM5.
