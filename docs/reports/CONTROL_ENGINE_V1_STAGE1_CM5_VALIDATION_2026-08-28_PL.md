# Control Engine V1 Stage1 — walidacja CM5

Data: 2026-08-28
Repozytorium: `autoklinika/workshop-ventilation-controller`
Gałąź: `agent/automation-v1-control-engine`
Walidowany SHA: `859df1b3e4dfbf58ec7efc8e45cfdf9f34a7a2eb`
Produkcyjny `main`: `7628c407cfc9c0ea72d262566759ea2d4598fec8`
Tryb: LAB / non-actuating

## Wynik

**PASS** — Control Engine V1 Stage1 persistent SHADOW runtime został zwalidowany fizycznie na CM5.

## Potwierdzone własności

- produkcyjny `main` przed testem był czysty i zgodny z oczekiwanym SHA,
- logiczne wyjścia EC pozostawały `0.0 V`,
- nie zaobserwowano ruchu wentylatorów,
- branch core uruchomił się z przypiętego worktree,
- początkowa konfiguracja persistent miała `revision=1`,
- początkowa wersja polityki: `shadow-policy-v1-2026-08-12`,
- cały tuning pozostał `null`,
- `actuation_supported=false`,
- hot reload konfiguracji zmienił wyłącznie wersję polityki i podbił rewizję do `2`,
- hot reload zgłosił `dynamics_reset=true`,
- po restarcie branch core utrzymał `revision=2`,
- persistence konfiguracji przez restart została potwierdzona,
- `proposed_supply_voltage` i `proposed_extract_voltage` pozostały `null`,
- RTC wakealarm nie został zmieniony,
- `wvc-host-power` nie został wywołany ani zrestartowany,
- domena 12 V pozostała ON,
- CM5 nie wykonał reboot ani poweroff,
- `boot_id` nie uległ zmianie,
- po zakończeniu testu produkcyjny `main` został poprawnie przywrócony.

## Obserwowane identyfikatory runtime

- `main before PID`: `1223`
- `branch PID #1`: `2083`
- `branch PID #2`: `2201`
- `main after PID`: `2414`
- `host-power PID`: `709`
- `boot_id`: `2af4e8dd-65e8-402b-8ddc-e3cab2a1cf71`

## Kluczowe linie PASS

```text
PASS: Control Engine V1 Stage1 persistent SHADOW runtime validated on CM5
PASS: hot reload + restart persistence verified; all tuning stayed null
PASS: RTC unchanged; host-power untouched; CM5 never rebooted/powered off
```

## Wniosek

Stage1 można uznać za zakończony fizycznie. Następny etap powinien walidować realne dane wejściowe SEN55 + Zigbee w trybie SHADOW, nadal bez fizycznej aktuacji DAC/AERO.
