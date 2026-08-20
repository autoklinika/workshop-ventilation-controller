# CM5 — NVMe data tier (SN770M)

## Cel

OS i kod produkcyjny pozostają na eMMC. WD_BLACK SN770M 1TB jest osobną warstwą danych montowaną jako `/srv/wvc-data` i przejmuje zapisy historyczne oraz wysokoczęstotliwościowy stan runtime, aby ograniczyć zużycie eMMC.

## Podział danych

### NVMe — dane historyczne / write-heavy

- `/srv/wvc-data/workshop-ventilation/telemetry.sqlite3` — surowa telemetria i rollupy,
- `/srv/wvc-data/workshop-ventilation/alerts.sqlite3` — pełna historia alertów,
- `/srv/wvc-data/workshop-ventilation/ai-advisory.json` — cache advisory,
- `/srv/wvc-data/workshop-ventilation/weather.json` — cache pogody,
- `/srv/wvc-data/wvc-service-heartbeat/` — anti-replay i diagnostyka Service Plane,
- `/srv/wvc-data/zigbee2mqtt/` — baza, backupy i stan Zigbee2MQTT.

Mosquitto jest wyłącznie lokalnym transportem MQTT i ma `persistence false`; historia sensorów jest utrzymywana przez warstwę telemetryczną na NVMe.

### eMMC — system i konfiguracja o małej liczbie zapisów

- system operacyjny,
- repo/kod aplikacji,
- `/var/lib/workshop-ventilation/automation.sqlite3` — konfiguracja harmonogramów,
- `/var/lib/workshop-ventilation/zigbee-roles.json` — przypisania ról Zigbee,
- konfiguracja `/etc`.

Te pliki nie są strumieniową historią i zmieniają się wyłącznie przy konfiguracji operatora. Nie uzależniamy od SSD podstawowej możliwości sterowania wentylacją.

## Zachowanie przy awarii / braku NVMe

Usługi generujące intensywne zapisy (`telemetry`, `advisory`, `weather`, Service Plane i Zigbee2MQTT) mają `RequiresMountsFor=/srv/wvc-data` oraz dodatkowy `mountpoint` precheck. Nie wolno im zapisywać do katalogu zastępczego na eMMC.

`ventilation-core` nie ma twardej zależności od NVMe. Alerty normalnie są zapisywane na SSD, ale przy braku dostępu do bazy przechodzą na jawnie włączony magazyn RAM. Sterowanie sprzętem działa dalej, a eMMC nie staje się automatycznym fallbackiem dla historii alertów.

WebGUI pozostaje klientem. Może działać bez NVMe i nadal korzystać z bieżącego stanu core; historia może być w tym czasie niedostępna.

## System journal

`journald` działa w trybie `Storage=volatile`. Jest to celowe: diagnostyka systemowa nie może generować stałych zapisów na eMMC ani uzależniać startu core od SSD. Historia domenowa, która ma wartość długoterminową, pozostaje na NVMe.

## Filesystem

Docelowo jeden filesystem ext4:

- GPT,
- label `WVC_DATA`,
- mount `/srv/wvc-data`,
- `noatime`,
- UUID w `/etc/fstab`,
- `fstrim.timer` aktywny.

Nie używamy NTFS do produkcyjnej pracy aplikacji Linux/SQLite.

## Procedura

1. Bez zmian produkcyjnego `main` przygotować i zwalidować gałąź.
2. Na CM5 zsynchronizować gałąź testową.
3. `sudo ./tools/prepare_cm5_nvme_data_disk.sh` — dry-run.
4. `sudo ./tools/prepare_cm5_nvme_data_disk.sh --apply` — kasowanie NTFS i utworzenie ext4.
5. `sudo ./tools/migrate_cm5_persistent_data_to_nvme.sh` — preflight.
6. `sudo ./tools/migrate_cm5_persistent_data_to_nvme.sh --apply` — kontrolowana migracja.
7. `sudo ./tools/validate_cm5_nvme_data.sh` — walidacja sprzętowo-systemowa.

Pliki źródłowe z eMMC nie są kasowane podczas pierwszej migracji. Pozostają jako nieaktywna kopia rollback do czasu zakończenia walidacji.

## Warunek merge

Merge do `main` dopiero po:

- pełnym CI na gałęzi,
- walidacji ext4/mount po restarcie CM5,
- potwierdzeniu zapisu telemetry/alertów na NVMe,
- potwierdzeniu braku undervoltage (`throttled=0x0`),
- potwierdzeniu działania core, SENSOR BUS, AERO, Zigbee i WebGUI na sprzęcie.
