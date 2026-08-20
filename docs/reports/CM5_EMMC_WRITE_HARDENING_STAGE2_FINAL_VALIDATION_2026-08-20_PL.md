# CM5 eMMC write hardening Stage 2 — final validation — 2026-08-20

## Wynik

**HARDWARE VALIDATION: PASS**

Walidacja została wykonana na docelowym CM5 po pełnym restarcie, po migracji wysokozapisowych danych WVC na SN770 oraz po przeniesieniu DHCP leases i VS Code Remote poza eMMC.

## Wynik walidatora po restarcie

Potwierdzono:

- `/srv/wvc-data` jest zamontowane,
- warstwa danych jest na `/dev/nvme0n1p1`,
- root systemu pozostaje na `/dev/mmcblk0p2`,
- `dnsmasq` przechowuje lease DHCP w RAM,
- `wvc-sensor-dhcp.service` posiada `RuntimeDirectory` dla volatile lease table,
- stara ścieżka lease na eMMC jest wyłącznie symlinkiem kompatybilności do `/run`,
- `/run` jest tmpfs,
- `wvc-sensor-dhcp.service` jest active,
- `wvc-service-agent.service` jest active,
- `ventilation-core.service` jest active,
- `.vscode-server` wskazuje na target na NVMe,
- dane VS Code Server są faktycznie na `/dev/nvme0n1p1`,
- po restarcie żaden aktywny deskryptor VS Code nie wskazuje na rollback copy na eMMC,
- persistent journald churn jest wyłączony,
- swap używa zram, nie eMMC.

Końcowy komunikat walidatora:

`EMMC WRITE HARDENING STAGE 2: PASS`

## Low-write configuration świadomie pozostawiona na eMMC

- `/var/lib/workshop-ventilation/automation.sqlite3`
- `/var/lib/workshop-ventilation/zigbee-roles.json`

Te dane są częścią niezależnej od NVMe konfiguracji podstawowego core i nie wykazują cyklicznego wysokiego zapisu.

## RTC / time safety

Osobna walidacja potwierdziła poprawne działanie sprzętowego RTC CM5 (`rpi-rtc`) oraz ustawianie czasu systemowego z RTC podczas bootu. NTP działa poprawnie. `/var/lib/systemd/timesync/clock` pozostaje świadomie jako mały, akceptowalny systemowy write-path bezpieczeństwa czasu.

## Cleanup rollbacków

Po finalnym PASS można usunąć niepotrzebny rollback VS Code z eMMC. Legacy dane Stage 1 WVC nie są kasowane bez kopii: narzędzie `tools/cleanup_cm5_emmc_rollback_stage2.sh` najpierw archiwizuje je na NVMe, weryfikuje kopię, a dopiero potem usuwa źródło z eMMC. `automation.sqlite3` i `zigbee-roles.json` są chronione guard railami i nie są usuwane.

## Status Git

Zmiany pozostają na gałęzi `agent/emmc-write-hardening-stage2`. `main` nie jest modyfikowany bez osobnej, jednoznacznej zgody użytkownika.
