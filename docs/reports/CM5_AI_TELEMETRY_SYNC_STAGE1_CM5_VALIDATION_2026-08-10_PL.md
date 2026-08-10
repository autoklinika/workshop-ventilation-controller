# CM5 → AI Bridge Telemetry Sync — Stage 1 CM5 validation

**Data:** 10.08.2026  
**Status:** PASS — one-shot i praca ciągła end-to-end na rzeczywistym CM5  
**Gałąź:** `agent/cm5-telemetry-sync-stage1`

## 1. Cel walidacji

Potwierdzić na rzeczywistym systemie, że CM5 może jednokierunkowo przekazać bieżący `CoreState` do AI Bridge, a AI Bridge zapisze go w PostgreSQL bez jakiegokolwiek udziału AI w sterowaniu wentylacją.

Walidacja objęła cały tor:

```text
SEN55 node 1 + SEN55 node 2
        |
        | RS-485 / Modbus RTU
        v
ventilation-core na CM5
        |
        | Unix socket / read-only status
        v
CM5 telemetry sync
        |
        | local SQLite durable queue
        v
HTTP POST /api/v1/ventilation/telemetry/batches
        |
        v
AI Bridge 0.1.0
        |
        v
PostgreSQL ai_bridge
```

## 2. Stan CM5 przed wysłaniem

`ventilation-core` zwrócił poprawny `CoreState`:

- `mode = STOP`,
- `supply_voltage = 0.0`,
- `extract_voltage = 0.0`,
- `hardware_ready = true`,
- `output_state_known = true`,
- brak aktywnych alarmów,
- SENSOR BUS `/dev/ttyAMA0`, 19200 bit/s,
- adresy Modbus 1 i 2,
- `sensor_bus.ready = true`,
- `worker_alive = true`,
- `worker_restarts = 0`.

Oba węzły były:

- `online = true`,
- `usable = true`,
- `measurement_valid = true`,
- `measurement_stale = false`,
- `sensor_present = true`,
- bez błędów komunikacji,
- z `map_version = 1`.

## 3. Łączność CM5 → AI Server

Z CM5 wykonano:

```text
GET http://192.168.1.55:8080/health
```

AI Bridge odpowiedział:

```json
{
  "status": "ok",
  "service": "ai-bridge",
  "version": "0.1.0",
  "control_commands_supported": false,
  "components": {
    "database": "ok",
    "ollama": "not_checked"
  }
}
```

Potwierdza to:

- prawidłową łączność LAN CM5 → AI Server,
- dostępność API na porcie 8080,
- dostępność PostgreSQL z AI Bridge,
- brak obsługi komend sterujących,
- brak zależności ingestu od Ollamy.

## 4. One-shot rzeczywistego CoreState

Na CM5 wykonano `telemetry.main --once` z tymczasową bazą SQLite w `/tmp`.

Log:

```text
2026-08-10 11:29:05,771 INFO __main__: Running one-shot real telemetry validation
2026-08-10 11:29:05,856 INFO ventilation_core.telemetry.agent: Telemetry batch synced batch_id=cd2cbb5f-3f16-4d1b-8e4b-fc48fa6d0613 samples=1 stored=1 duplicates=0
2026-08-10 11:29:05,856 INFO __main__: One-shot telemetry validation completed
```

Wynik:

- `samples = 1`,
- `stored = 1`,
- `duplicates = 0`,
- proces zakończył się poprawnie.

Batch ID:

```text
cd2cbb5f-3f16-4d1b-8e4b-fc48fa6d0613
```

## 5. Potwierdzenie w PostgreSQL

Rekord został odczytany bezpośrednio z `ventilation_telemetry_raw` i `ventilation_ingest_batches`.

Zapisany rekord:

- `sample_id = 9865138c-e8e8-44f7-abd6-610e19a22659`,
- `captured_at = 2026-08-10 11:29:05.772891+02`,
- `mode = STOP`,
- `sensor_bus.ready = true`.

W zapisanym payloadzie obecne były oba rzeczywiste węzły SEN55.

### Node 1 — Modbus slave 1

- PM2.5: `16.6 µg/m³`,
- temperatura: `24.16 °C`,
- wilgotność: `39.41 %`,
- VOC index: `466.0`.

### Node 2 — Modbus slave 2

- PM2.5: `17.1 µg/m³`,
- temperatura: `23.89 °C`,
- wilgotność: `41.15 %`,
- VOC index: `446.0`.

Wartości są rzeczywistym snapshotem z chwili `captured_at`; nie muszą być identyczne z wcześniejszym ręcznym `status`, ponieważ SENSOR BUS jest odpytywany cyklicznie.

## 6. Wynik architektoniczny

Walidacja potwierdziła pełny rzeczywisty przepływ:

```text
SEN55 #1 ─┐
          ├─ RS-485 → CM5 → CoreState → local telemetry store → HTTP → AI Bridge → PostgreSQL
SEN55 #2 ─┘
```

Jednocześnie zachowana została granica bezpieczeństwa:

- telemetria używa wyłącznie read-only `status`,
- proces telemetryczny nie wywołuje `set`, `stop` ani `shutdown`,
- awaria AI Servera lub HTTP nie ma ścieżki do DAC,
- `VentilationService` nie został zmodyfikowany,
- AI Bridge deklaruje `control_commands_supported = false`.

## 7. Walidacja pracy ciągłej

Proces telemetryczny uruchomiono ręcznie na CM5 z:

- `capture-interval = 5 s`,
- `sync-interval = 5 s`,
- `batch-size = 100`,
- bazą testową `/tmp/wvc-telemetry-continuous.sqlite3`.

Przy dostępnym AI Bridge kolejne rzeczywiste snapshoty były zapisywane poprawnie co około 5 s. Każdy normalny batch miał:

```text
samples=1 stored=1 duplicates=0
```

Potwierdza to stabilną pracę ciągłą CM5 → AI Bridge → PostgreSQL.

## 8. Walidacja awarii AI Bridge i trwałego pending

AI Bridge został celowo zatrzymany, podczas gdy proces telemetryczny CM5 pozostał uruchomiony.

CM5 zgłaszał oczekiwany błąd:

```text
RuntimeError: AI Bridge unavailable: [Errno 111] Connection refused
Telemetry sync failed; pending samples remain local
```

W tym samym czasie sprawdzono `ventilation-core`. Wynik pozostał prawidłowy:

- `mode = STOP`,
- `hardware_ready = true`,
- `output_state_known = true`,
- brak aktywnych alarmów,
- SENSOR BUS `ready = true`,
- `worker_alive = true`,
- oba SEN55 `online = true`,
- oba SEN55 `usable = true`,
- oba SEN55 `measurement_valid = true`,
- brak błędów Modbus i błędów pomiarowych.

Przy niedostępnym AI Bridge lokalna baza CM5 pokazała:

```text
total  : 42
synced : 28
pending: 14
```

Oznacza to, że awaria AI Servera nie wpłynęła na sterowanie ani SENSOR BUS, a niesynchronizowane próbki zostały zachowane lokalnie.

## 9. Automatyczny catch-up po powrocie AI Bridge

AI Bridge uruchomiono ponownie bez restartowania procesu telemetrycznego CM5.

CM5 automatycznie wznowił synchronizację. Kluczowy log:

```text
2026-08-10 11:46:31,554 INFO ventilation_core.telemetry.agent: Telemetry batch synced batch_id=1316b629-5fce-4c2e-ae65-2ec736023007 samples=34 stored=34 duplicates=0
```

Następnie proces wrócił do normalnego rytmu pojedynczych snapshotów:

```text
samples=1 stored=1 duplicates=0
```

Kontrolny stan lokalnej bazy podczas dalszej pracy ciągłej:

```text
total  : 73
synced : 72
pending: 1
```

`pending = 1` jest prawidłowym stanem chwilowym przy aktywnym capture co 5 s — jedna świeża próbka może znajdować się pomiędzy lokalnym zapisem a następnym ACK. Nie jest to zaległy backlog z okresu awarii.

Walidacja potwierdza:

- trwałość lokalnej kolejki podczas niedostępności AI Bridge,
- automatyczne retry,
- brak konieczności restartowania telemetry sync,
- automatyczny catch-up backlogu,
- zapis 34 zaległych próbek w jednym batchu,
- `duplicates = 0`,
- powrót do normalnego rytmu po opróżnieniu backlogu.

## 10. Status Stage 1 po pełnej walidacji

**PASS — rzeczywisty one-shot, praca ciągła, awaria AI Bridge i automatyczny catch-up.**

Potwierdzone:

- rzeczywisty odczyt dwóch SEN55 przez SENSOR BUS,
- serializacja aktualnego `CoreState`,
- read-only odczyt przez Unix socket,
- lokalny trwały zapis RAW/pending,
- HTTP CM5 → AI Server,
- poprawny ACK,
- zapis RAW w PostgreSQL,
- obecność obu węzłów i ich pomiarów w bazie,
- odporność na czasową niedostępność AI Bridge,
- brak utraty danych podczas testu awarii,
- automatyczne nadrobienie backlogu,
- brak wpływu awarii AI Servera na `ventilation-core`, DAC i SENSOR BUS.

## 11. Następny krok

Walidacja funkcjonalna i odpornościowa Stage 1 jest zakończona. Następnym etapem może być uruchomienie przygotowanej jednostki `wvc-telemetry-sync.service` z trwałą bazą `/var/lib/workshop-ventilation/telemetry.sqlite3` oraz analogiczne uporządkowanie AI Bridge jako usługi systemowej.

PR pozostaje Draft i nie powinien być merge'owany ani oznaczany Ready for Review bez wyraźnej decyzji użytkownika.
