# CM5 → AI Bridge Telemetry Sync — Stage 1 systemd validation

**Data:** 10.08.2026  
**Status:** PASS — stała usługa CM5 uruchomiona i zwalidowana  
**Gałąź:** `agent/cm5-telemetry-sync-stage1`

## Cel

Potwierdzić, że zwalidowany wcześniej proces telemetryczny CM5 może działać jako trwała usługa `systemd`, startować automatycznie z systemem i używać trwałej lokalnej bazy bez zmiany granicy bezpieczeństwa wentylacji.

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

## Uruchomienie

Wykonano:

```text
systemctl daemon-reload
systemctl enable --now wvc-telemetry-sync.service
```

`systemctl status` potwierdził:

```text
Loaded: loaded (/etc/systemd/system/wvc-telemetry-sync.service; enabled)
Active: active (running)
Main PID: 5598 (python3)
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

## Walidacja transmisji po starcie systemd

Journal potwierdził poprawny start:

```text
CM5 telemetry sync started source_id=workshop-ventilation-cm5-01 ai_bridge=http://192.168.1.55:8080 capture_interval=5.000s
```

oraz kolejne poprawne zapisy:

```text
Telemetry batch synced ... samples=1 stored=1 duplicates=0
Telemetry batch synced ... samples=1 stored=1 duplicates=0
Telemetry batch synced ... samples=1 stored=1 duplicates=0
```

Oznacza to, że po przejściu z ręcznego procesu na `systemd` zachowano prawidłowy przepływ CM5 → AI Bridge → PostgreSQL.

## Granica bezpieczeństwa

Nie zmieniono architektury sterowania:

- `ventilation-core` pozostaje niezależnym procesem,
- telemetry sync korzysta wyłącznie z read-only `status`,
- jednostka telemetryczna nie ma `Requires=ventilation-core.service`,
- awaria AI Bridge lub telemetry sync nie ma ścieżki do sterowania DAC, trybu pracy ani SENSOR BUS,
- lokalny pending pozostaje buforem awaryjnym na CM5.

## Wynik

**PASS.**

Stage 1 po stronie CM5 jest obecnie uruchomiony jako stała, automatycznie startująca usługa systemowa z trwałą lokalną bazą.

Następny krok: analogiczne uporządkowanie AI Bridge na AI Serverze jako usługi `systemd`, bez zmiany PostgreSQL, Ollamy ani architektury CM5.
