# CM5 → AI Bridge Telemetry Sync — Stage 1 CM5 validation

**Data:** 10.08.2026  
**Status:** PASS — one-shot end-to-end na rzeczywistym CM5  
**Gałąź:** `agent/cm5-telemetry-sync-stage1`

## 1. Cel walidacji

Potwierdzić na rzeczywistym systemie, że CM5 może jednokierunkowo przekazać bieżący `CoreState` do AI Bridge, a AI Bridge zapisze go w PostgreSQL bez jakiegokolwiek udziału AI w sterowaniu wentylacją.

Walidacja miała objąć cały tor:

```text
SEN55 node 1 + SEN55 node 2
        |
        | RS-485 / Modbus RTU
        v
ventilation-core na CM5
        |
        | Unix socket / read-only status
        v
CM5 telemetry sync --once
        |
        | HTTP POST /api/v1/ventilation/telemetry/batches
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

## 7. Status Stage 1 po walidacji

**PASS w zakresie one-shot end-to-end na rzeczywistym CM5.**

Potwierdzone:

- rzeczywisty odczyt dwóch SEN55 przez SENSOR BUS,
- serializacja aktualnego `CoreState`,
- read-only odczyt przez Unix socket,
- lokalny zapis próbki,
- HTTP CM5 → AI Server,
- poprawny ACK,
- zapis RAW w PostgreSQL,
- obecność obu węzłów i ich pomiarów w bazie.

## 8. Co pozostaje przed stałym uruchomieniem

Nie uruchomiono jeszcze `wvc-telemetry-sync.service` jako stałej usługi.

Przed merge Stage 1 zalecana jest jeszcze krótka walidacja pracy ciągłej obejmująca:

1. kilka kolejnych snapshotów w normalnym rytmie,
2. czasowe wyłączenie AI Bridge lub odcięcie LAN,
3. potwierdzenie pozostania próbek jako `pending`,
4. ponowne uruchomienie AI Bridge,
5. automatyczny catch-up backlogu,
6. brak wpływu całego testu na `ventilation-core`, DAC i SENSOR BUS.

Dopiero po tym można zdecydować o włączeniu jednostki systemd i późniejszym merge PR.
