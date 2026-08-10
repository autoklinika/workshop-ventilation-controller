# CM5 → AI Bridge Telemetry Sync — Stage 1 systemd validation

**Data:** 10.08.2026  
**Status:** PASS — systemd + reboot CM5 + automatyczny powrót pełnego toru  
**Gałąź:** `agent/cm5-telemetry-sync-stage1`

## Cel

Potwierdzić, że zwalidowany proces telemetryczny CM5 działa jako trwała usługa `systemd`, używa trwałej lokalnej bazy, startuje automatycznie wraz z CM5 oraz po restarcie hosta samodzielnie wraca do pełnej pracy z `ventilation-core`, SENSOR BUS, dwoma SEN55 i AI Bridge.

## Konfiguracja

Zainstalowano:

```text
/etc/systemd/system/wvc-telemetry-sync.service
```

Konfiguracja połączenia:

```text
/etc/default/wvc-telemetry-sync
```

z:

```text
WVC_AI_BRIDGE_URL=http://192.168.1.55:8080
WVC_TELEMETRY_SOURCE_ID=workshop-ventilation-cm5-01
```

Usługa używa trwałej lokalnej bazy:

```text
/var/lib/workshop-ventilation/telemetry.sqlite3
```

Parametry Stage 1:

- capture interval: 5 s,
- sync interval: 5 s,
- batch size: 100,
- HTTP timeout: 5 s,
- retencja lokalna: 30 dni.

## Pierwsze uruchomienie systemd

Wykonano:

```text
systemctl daemon-reload
systemctl enable --now wvc-telemetry-sync.service
```

`systemctl status` potwierdził:

```text
Loaded: loaded (/etc/systemd/system/wvc-telemetry-sync.service; enabled)
Active: active (running)
```

Proces był uruchomiony jako:

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

Journal potwierdził start telemetry sync oraz kolejne poprawne ACK:

```text
Telemetry batch synced ... samples=1 stored=1 duplicates=0
```

## Test restartu całego CM5

CM5 został zrestartowany przy pozostawionym działającym AI Serverze.

Po ponownym uruchomieniu nie uruchamiano ręcznie żadnej usługi. Sprawdzono:

```text
systemctl is-enabled ventilation-core.service      -> enabled
systemctl is-active ventilation-core.service       -> active
systemctl is-enabled wvc-telemetry-sync.service    -> enabled
systemctl is-active wvc-telemetry-sync.service     -> active
```

Oznacza to, że zarówno podstawowy sterownik wentylacji, jak i telemetry sync wróciły automatycznie po boot.

## CoreState po restarcie CM5

Read-only `status` potwierdził zdrowy stan systemu:

- `mode = STOP`,
- `supply_voltage = 0.0`,
- `extract_voltage = 0.0`,
- `hardware_ready = true`,
- `output_state_known = true`,
- `consecutive_hardware_failures = 0`,
- brak aktywnych alarmów.

SENSOR BUS po restarcie:

- port `/dev/ttyAMA0`,
- 19200 bit/s,
- adresy `[1, 2]`,
- `ready = true`,
- `worker_alive = true`,
- `worker_restarts = 0`,
- `last_error = null`.

Oba węzły SEN55 po restarcie były:

- `online = true`,
- `usable = true`,
- `measurement_valid = true`,
- `measurement_stale = false`,
- `sensor_present = true`,
- `communication_errors = 0`,
- `consecutive_failures = 0`,
- `invalid_measurements = 0`,
- `stale_measurements = 0`,
- `map_version_errors = 0`.

Przykładowy snapshot po restarcie:

### Slave 1

- PM2.5: `6.7 µg/m³`,
- temperatura: `24.67 °C`,
- wilgotność: `45.53 %`,
- VOC index: `115.0`.

### Slave 2

- PM2.5: `5.8 µg/m³`,
- temperatura: `24.52 °C`,
- wilgotność: `46.93 %`,
- VOC index: `56.0`.

## Telemetria po restarcie CM5

Journal z bieżącego bootu potwierdził ciągłą poprawną synchronizację z nowego procesu telemetrycznego, m.in.:

```text
12:21:07 Telemetry batch synced ... samples=1 stored=1 duplicates=0
12:21:12 Telemetry batch synced ... samples=1 stored=1 duplicates=0
12:21:17 Telemetry batch synced ... samples=1 stored=1 duplicates=0
...
12:22:24 Telemetry batch synced ... samples=1 stored=1 duplicates=0
```

Po stronie AI Servera `ai-bridge.service` równolegle potwierdził kolejne rzeczywiste żądania z CM5 `192.168.1.64`:

```text
POST /api/v1/ventilation/telemetry/batches HTTP/1.1 -> 200 OK
```

w normalnym rytmie około 5 s.

## Potwierdzony tor po restarcie CM5

```text
CM5 boot
  ↓
ventilation-core.service
  ↓
SENSOR BUS / RS-485
  ↓
SEN55 slave 1 + slave 2
  ↓
wvc-telemetry-sync.service
  ↓
local SQLite / pending
  ↓
LAN / HTTP
  ↓
ai-bridge.service
  ↓
PostgreSQL
```

Cały tor wrócił do pracy bez ręcznej ingerencji.

## Granica bezpieczeństwa

Nie zmieniono architektury sterowania:

- `ventilation-core` pozostaje autonomicznym sterownikiem,
- telemetry sync korzysta wyłącznie z read-only `status`,
- jednostka telemetryczna nie ma `Requires=ventilation-core.service`,
- awaria AI Bridge lub telemetry sync nie ma ścieżki do sterowania DAC, trybu pracy ani SENSOR BUS,
- lokalny pending pozostaje buforem awaryjnym na CM5,
- Qwen/Ollama nie uczestniczą w sterowaniu ani w ACK telemetrycznym.

## Wynik

**PASS — `ventilation-core.service` i `wvc-telemetry-sync.service` startują automatycznie po restarcie CM5, SENSOR BUS i oba SEN55 wracają do zdrowego stanu, a telemetria automatycznie dociera do AI Bridge i PostgreSQL.**

Stage 1 po stronie CM5 jest operacyjnie zwalidowany także w scenariuszu pełnego restartu hosta.

PR pozostaje Draft i nie powinien być merge'owany ani oznaczany Ready for Review bez wyraźnej decyzji użytkownika.
