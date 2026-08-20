# CM5 eMMC write audit — Stage 2 — 2026-08-20

## Cel

Po wdrożeniu warstwy danych SN770 sprawdzić, czy normalna praca CM5 nadal generuje częste zapisy na systemowym eMMC, i usunąć write-pathy, które nie wymagają trwałości na eMMC.

## Punkt wejścia

- system root: `/dev/mmcblk0p2`, ext4, `noatime`
- data tier: `/dev/nvme0n1p1` -> `/srv/wvc-data`, ext4, `noatime`
- telemetry, alert history, AI/weather cache, service-agent state i Zigbee2MQTT: SN770
- journald: `Storage=volatile`
- swap: `/dev/zram0`

## Pomiar bazowy przed Stage 2

Czas pomiaru: 180 s.

Fizyczne zapisy na `mmcblk0`:

- 1784 sektory
- 913408 B
- 0.871 MiB / 180 s
- krótkookresowy równoważnik ~418 MiB/dobę przy utrzymaniu identycznego profilu aktywności 24/7

Zmodyfikowane regularne pliki na eMMC w czasie pomiaru:

1. `~/.vscode-server/.../vscode.lock`
2. `~/.vscode-server/data/logs/...agent-host....jsonl`

Nie powstały i nie zostały usunięte żadne inne pliki na root filesystemie w czasie pomiaru.

## Interpretacja `write_bytes`

Największe wartości procesowe nie oznaczały zapisów na eMMC:

- `ventilation_core.telemetry.main`: zapisuje bazę w `/srv/wvc-data/...` na NVMe
- `jbd2/nvme0n1p1-8`: journal ext4 SN770
- `ventilation_core.service_agent_ota`: state dir na SN770
- `ventilation_core.web.main`: historia/cache na SN770

Rzeczywistym aktywnym źródłem plików zmienianych na eMMC był VS Code Remote Server.

## Pozostawione świadomie na eMMC

### `automation.sqlite3`

Konfiguracja harmonogramu, nie dane historyczne. Zapis tylko przy zmianie konfiguracji. W czasie audytu główna baza miała mtime z 2026-08-17; brak cyklicznego zapisu.

### `zigbee-roles.json`

Konfiguracja przypisania ról Zigbee. Zapis przy zmianie przypisania/upgrade registry. Mtime z 2026-08-18; brak cyklicznego zapisu.

Obie ścieżki pozostają na eMMC, ponieważ są niskozapisową konfiguracją potrzebną podstawowemu core. Przeniesienie zwiększałoby zależność sterowania od NVMe bez istotnej korzyści wear.

## Stage 2 — usunięte write-pathy

### DHCP leases

`dnsmasq` przechowywał lease DHCP w:

`/var/lib/misc/dnsmasq-wvc.leases`

Stage 2 przeniósł lease do:

`/run/wvc-sensor-service/dnsmasq-wvc.leases`

`wvc-sensor-dhcp.service` tworzy katalog przez `RuntimeDirectory=wvc-sensor-service`. Dla zgodności dawny path pozostaje wyłącznie symlinkiem do `/run`; zawartość nie jest zapisywana na eMMC.

OTA Service Agent od Stage 2 odczytuje runtime lease table bezpośrednio z `/run`.

### VS Code Remote Server

Stage 2 przeniósł:

`/home/wentylacja/.vscode-server`

na:

`/srv/wvc-data/development/vscode-server`

Ścieżka w home jest symlinkiem do NVMe. Dotychczasowy katalog eMMC został zachowany jako rollback snapshot:

`/home/wentylacja/.vscode-server.emmc-rollback-20260820-172805`

Po pełnym restarcie stare deskryptory zostały zamknięte, a aktywny proces VS Code Remote uruchomił się z `/srv/wvc-data/development/vscode-server/...`.

## Końcowy audyt po Stage 2

Czas pomiaru: 180 s.

Zmodyfikowane pliki na eMMC:

1. `/var/lib/systemd/timesync/clock`

Nie utworzono i nie usunięto żadnych plików na eMMC w czasie pomiaru.

Aktywny VS Code Remote pracował z:

`/srv/wvc-data/development/vscode-server/...`

Fizyczne zapisy do `mmcblk0`:

- 3128 sektorów
- 1601536 B
- 1.527 MiB / 180 s
- krótkookresowy równoważnik 733.1 MiB/dobę

Ten równoważnik nie jest estymacją wear. Pomiar był krótki i wykonany niedługo po restarcie, więc obejmuje journal ext4 oraz aktywność startową systemu. W szczególności `jbd2/mmcblk0p2-8` raportował 868352 B operacji zapisu w tym oknie.

## Pozostały plik `systemd-timesyncd`

`/var/lib/systemd/timesync/clock` jest zerobajtowym plikiem, którego mtime systemd-timesyncd aktualizuje w celu zachowania przybliżonej monotoniczności czasu pomiędzy rebootami. Nie jest to historia aplikacyjna WVC.

Nie przenosimy ani nie wyłączamy tego mechanizmu bez osobnej walidacji RTC. CM5 posiada sprzętowy RTC, ale przed zmianą polityki czasu należy potwierdzić runtime RTC oraz zachowanie po utracie zasilania/baterii. Stabilność znaczników czasu telemetrycznych i harmonogramów ma wyższy priorytet niż eliminacja tego pojedynczego zapisu metadanych.

## Narzędzia Stage 2

- `tools/apply_cm5_emmc_write_hardening_stage2.sh`
- `tools/validate_cm5_emmc_write_hardening_stage2.sh`
- `tools/audit_cm5_emmc_runtime.py`

Audyt runtime raportuje teraz uptime i ostrzega, że ekstrapolacja z okna krótszego niż 1 h ma znaczenie diagnostyczne, a nie endurance/wear.

## Wniosek

Stage 2 osiągnął cel aplikacyjny:

1. historyczne i wysokozapisowe dane WVC pozostają na SN770,
2. DHCP lease jest w RAM,
3. VS Code Remote Server działa z NVMe,
4. brak regularnych zapisów aplikacyjnych WVC na eMMC podczas pomiaru,
5. `automation.sqlite3` i `zigbee-roles.json` pozostają świadomie jako low-write configuration,
6. jedyną wykrytą zmianą pliku na eMMC po Stage 2 był systemowy `/var/lib/systemd/timesync/clock`,
7. `main` pozostaje bez zmian do czasu osobnej, jednoznacznej zgody na merge.
