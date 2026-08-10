# CM5 → AI Bridge Telemetry Sync — Stage 1 implementation

**Data:** 10.08.2026  
**Status:** implementacja na gałęzi roboczej, przed walidacją na rzeczywistym CM5  
**Punkt startowy `main`:** `2ed28a8a5ba2e219493984732eca890ae0700cab`

## 1. Cel etapu

Uruchomić rzeczywiste, jednokierunkowe przesyłanie stanu `CoreState` z CM5 do AI Bridge bez jakiegokolwiek wpływu na sterowanie wentylacją.

Stage 1 nie uruchamia jeszcze Qwena i nie dodaje żadnego kanału sterującego z AI Servera do CM5.

## 2. Granica bezpieczeństwa

`VentilationService` pozostaje niezmieniony. Telemetria działa jako osobny proces i korzysta wyłącznie z istniejącej, read-only komendy Unix socket:

```json
{"command":"status"}
```

Przepływ:

```text
ventilation-core
    |
    | Unix socket / status (read-only)
    v
telemetry process
    |
    +--> local SQLite history + durable pending queue
    |
    +--> HTTP POST /api/v1/ventilation/telemetry/batches
             |
             v
          AI Bridge
```

Awaria AI Servera, HTTP, DNS/LAN lub lokalnego procesu telemetrycznego nie zmienia trybu, setpointów, alarmów DAC ani działania SENSOR BUS. Proces telemetryczny nie posiada żadnej ścieżki wywołującej `set`, `stop` lub inne komendy sterujące.

## 3. Źródło danych

Źródłem danych jest dokładny wynik `CoreState.to_dict()` z aktualnego `ventilation-core`:

- `mode`,
- `setpoints`,
- `hardware_ready`,
- `output_state_known`,
- `consecutive_hardware_failures`,
- `active_alarms`,
- `sensor_bus`, w tym oba węzły SEN55 i ich bieżące odczyty/diagnostykę.

CM5 nie agreguje i nie interpretuje tych danych na potrzeby AI. Snapshot jest zapisywany jako RAW stan aplikacyjny.

## 4. Lokalna baza CM5

SQLite przechowuje:

- `sequence` — monotoniczny licznik lokalny,
- stabilny `sample_id`,
- oryginalny `captured_at`,
- pełny `metrics_json`,
- stabilny `batch_id` i `batch_created_at` po rezerwacji do wysyłki,
- `synced_at`,
- liczbę prób i ostatni błąd synchronizacji.

Zasady:

- rekord pozostaje `pending`, dopóki AI Bridge nie zwróci poprawnego ACK,
- utrata ACK powoduje retransmisję z tym samym `batch_id` i `sample_id`,
- po restarcie procesu niedokończony batch zachowuje swoją tożsamość,
- retencja usuwa wyłącznie rekordy już zsynchronizowane,
- rekord `pending` nie może zostać usunięty przez zwykłą retencję.

Domyślna retencja Stage 1: 30 dni.

## 5. Synchronizacja HTTP

Endpoint:

```text
POST /api/v1/ventilation/telemetry/batches
```

Domyślne parametry:

- capture interval: 5 s,
- idle sync interval: 5 s,
- batch size: 100,
- HTTP timeout: 5 s,
- retry: 5 s → 15 s → 30 s → 60 s → 60 s...

Po udanej transmisji backlog jest opróżniany bez czekania pełnego interwału między batchami.

ACK jest akceptowany tylko gdy:

- `schema_version == 1`,
- `source_id` zgadza się z CM5,
- `batch_id` zgadza się z wysłanym batchem,
- `status == accepted`,
- `received == liczba wysłanych próbek`,
- `rejected == 0`,
- `stored + duplicates == liczba wysłanych próbek`.

Dopiero po takim ACK rekordy są oznaczane lokalnie jako zsynchronizowane.

## 6. Identyfikatory

Stage 1 używa UUID4, co jest zgodne z kontraktem (ULID jest preferowany, ale UUID jest dopuszczalny).

Domyślny `source_id`:

```text
workshop-ventilation-cm5-01
```

Może być nadpisany przez `WVC_TELEMETRY_SOURCE_ID`.

## 7. Walidacja przed uruchomieniem usługi

Najpierw należy wykonać **one-shot** na rzeczywistym CM5. Nie włączamy jeszcze `wvc-telemetry-sync.service`.

Przykład:

```bash
cd /home/wentylacja/workshop-ventilation-controller
export PYTHONPATH=$PWD/src
python3 -m ventilation_core.telemetry.main \
  --ai-bridge-url http://<IP_AI_SERVERA>:8080 \
  --database /tmp/wvc-telemetry-stage1.sqlite3 \
  --once \
  --log-level INFO
```

Tryb `--once`:

1. odczytuje jeden rzeczywisty `CoreState` z działającego `ventilation-core`,
2. zapisuje go lokalnie,
3. tworzy batch,
4. wysyła do AI Bridge,
5. waliduje ACK,
6. oznacza rekord jako zsynchronizowany,
7. kończy proces.

Dopiero po potwierdzeniu rekordu w PostgreSQL AI Servera należy przejść do pracy ciągłej.

## 8. Przyszła usługa systemd

Repo zawiera przygotowaną, ale na tym etapie jeszcze **nieuruchamianą** jednostkę:

```text
deploy/systemd/wvc-telemetry-sync.service
```

oraz przykład konfiguracji:

```text
deploy/cm5/telemetry/wvc-telemetry-sync.env.example
```

Jednostka:

- działa jako użytkownik `wentylacja`,
- nie ma `Requires=ventilation-core.service`, więc jej awaria nie może zatrzymać core,
- ma jedynie `After=ventilation-core.service`,
- przechowuje bazę pod `/var/lib/workshop-ventilation/telemetry.sqlite3`,
- korzysta z `/etc/default/wvc-telemetry-sync` do adresu AI Bridge.

## 9. Walidacja kodu przed publikacją

W środowisku deweloperskim wykonano:

```text
python -m compileall: PASS
unittest:             13/13 PASS
```

Testy obejmują:

- stabilność `batch_id` po błędzie sieci,
- ochronę `pending` przed retencją,
- monotoniczny `sequence`,
- ACK `stored`,
- ACK `duplicates`,
- błędny ACK bez utraty danych lokalnych,
- read-only `status` po Unix socket,
- POST na dokładny endpoint AI Bridge,
- brak `Requires=ventilation-core.service` w przyszłej usłudze systemd.

## 10. Poza zakresem Stage 1

- Qwen/Ollama i analiza 15-minutowa,
- agregacja/statystyki po stronie CM5,
- sterowanie przez AI,
- AERO BUS,
- tacho/RPM,
- zmiana logiki DAC,
- zmiana logiki SENSOR BUS,
- stałe uruchomienie systemd przed realną walidacją one-shot.
