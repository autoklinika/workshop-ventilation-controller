# CM5 NVMe Data Tier — Stage 1 — finalna walidacja sprzętowa

Data: 2026-08-20

## Status

**PASS — Stage 1 został zwalidowany na docelowym CM5 z WD_BLACK SN770M 1 TB.**

Walidacja obejmowała przygotowanie dysku, migrację istniejących danych z eMMC, uruchomienie nowych unitów systemd, sprawdzenie rzeczywistych lokalizacji zapisu, pełny reboot oraz ponowną walidację usług i zasilania.

## Układ docelowy

- system operacyjny pozostaje na eMMC: `/dev/mmcblk0p2`, ext4, `rw,noatime`;
- warstwa danych działa na `/dev/nvme0n1p1`, ext4, label `WVC_DATA`;
- punkt montowania: `/srv/wvc-data`;
- opcje aktywnego mountu: `rw,noatime`;
- wpis `/etc/fstab` używa UUID i opcji `defaults,noatime,nofail,x-systemd.device-timeout=10s`;
- `fstrim.timer` jest enabled + active.

## Dane przeniesione na NVMe

Potwierdzono routing do SN770 dla:

- `telemetry.sqlite3`;
- `alerts.sqlite3`;
- `ai-advisory.json`;
- `weather.json`;
- stanu `wvc-service-heartbeat` / Service Agent;
- danych Zigbee2MQTT.

Dodatkowo:

- systemowy journal ma `Storage=volatile`, aby nie generować trwałego churnu na eMMC;
- lokalny Mosquitto ma wyłączoną persystencję;
- usługi zapisujące na NVMe mają precheck `mountpoint -q /srv/wvc-data`;
- `ventilation-core` nie ma twardej zależności od SSD; przy niedostępnej persystencji alert journal ma jawny fallback do RAM zamiast zapisu na eMMC.

## Migracja

Migracja została wykonana przy bezpiecznym stanie sterowania:

```text
safe baseline: STOP / 0 V
```

Skopiowano istniejące dane z eMMC na NVMe. Źródłowe pliki na eMMC pozostawiono jako snapshot rollback i nie zostały usunięte.

Po migracji aktywne były:

```text
ventilation-core.service      active
wvc-telemetry-sync.service    active
wvc-ai-advisory.service       active
wvc-weather.service           active
wvc-web-ui.service            active
wvc-service-agent.service     active
zigbee2mqtt.service           active
```

## Walidacja live write przed rebootem

W ciągu 30 s baza telemetryczna na NVMe zmieniła się:

```text
BEFORE size=476434432
AFTER  size=476504064
```

W tym samym czasie legacy snapshot na eMMC pozostał bez zmian:

```text
/var/lib/workshop-ventilation/telemetry.sqlite3
size=476184576
mtime=2026-08-20 16:31:30.616916592 +0200
```

To potwierdza, że nowe próbki telemetryczne trafiają na SN770, a nie na starą bazę na eMMC.

## Walidacja po pełnym reboot

Po restarcie CM5 potwierdzono automatyczny mount:

```text
/              /dev/mmcblk0p2   ext4   rw,noatime
/srv/wvc-data  /dev/nvme0n1p1   ext4   rw,noatime
```

Wszystkie wymagane usługi były aktywne:

```text
ventilation-core.service           active
wvc-telemetry-sync.service         active
wvc-ai-advisory.service            active
wvc-weather.service                active
wvc-web-ui.service                 active
wvc-service-agent.service          active
zigbee2mqtt.service                active
mosquitto.service                  active
```

Pełny validator zakończył się:

```text
NVME DATA TIER VALIDATION: PASS
```

Core po restarcie:

```text
mode=STOP
hardware_ready=True
output_state_known=True
```

## Live write po reboot

Telemetry nadal rosła na NVMe:

```text
BEFORE size=477421568  mtime=2026-08-20 16:40:35.641834650 +0200
AFTER  size=477540352  mtime=2026-08-20 16:41:05.735185117 +0200
```

Legacy snapshoty na eMMC nadal były nieruchome:

```text
/var/lib/workshop-ventilation/telemetry.sqlite3
size=476184576
mtime=2026-08-20 16:31:30.616916592 +0200

/var/lib/workshop-ventilation/alerts.sqlite3
size=69632
mtime=2026-08-20 16:31:46.088815962 +0200
```

## Zasilanie

Po reboot:

```text
EXT5V_V=5.07458000V
throttled=0x0
UNDERVOLTAGE THIS BOOT: NONE
```

Pełny validator wcześniej odczytał również:

```text
EXT5V_V=5.02768000V
throttled=0x0
```

Nie wystąpiło żadne nowe undervoltage ani sticky throttling.

## Pojemność

Po migracji:

```text
/dev/nvme0n1p1 ext4 916G total, około 458M użyte
```

Największy katalog:

```text
/srv/wvc-data/workshop-ventilation  ~456M
```

## Wniosek

Stage 1 spełnia założenie ochrony eMMC:

- intensywne i historyczne zapisy zostały skierowane na SN770;
- eMMC pozostaje nośnikiem systemowym i dla niskoczęstotliwościowej konfiguracji;
- stare bazy na eMMC nie są już aktywnie zapisywane;
- po reboot warstwa danych montuje się poprawnie i usługi wracają automatycznie;
- brak SSD nie powinien powodować cichego fallbacku write-pathów na eMMC;
- zasilanie CM5 + SN770 pozostaje stabilne.

**CM5 NVMe Data Tier Stage 1: FINAL HARDWARE VALIDATION PASS.**

Nie merge'ować do `main` bez wyraźnej zgody właściciela projektu.
