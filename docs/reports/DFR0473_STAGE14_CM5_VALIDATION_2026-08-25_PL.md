# DFR0473 Stage14 – walidacja na fizycznym CM5 — 2026-08-25

## Zakres

Walidacja nieinwazyjna domeny zasilania 12 V sterowanej przez DFRobot DFR0473 na fizycznym Raspberry Pi Compute Module 5.

Gałąź:

```text
agent/power-domain-dfr0473-stage14
```

Zweryfikowany HEAD podczas testu:

```text
e5e1f95f79542cf8b9c1f0beff0e656899e46087
```

Użyty harness:

```text
tools/install_validate_dfr0473_power_domain_cm5.sh
```

Test nie wykonywał `poweroff` ani `reboot` hosta.

## Stan wejściowy

Przed testem obie usługi były aktywne:

```text
ventilation-core.service: active
wvc-host-power.service:   active
```

Polecenie lokalnego STOP nie mogło zostać potwierdzone z powodu istniejącej awarii DAC DFR0971 / GP8403:

```text
No response from GP8403 at 0x58: [Errno 121] Remote I/O error
```

Stan core:

```text
mode: FAULT
supply_voltage: 0.0
extract_voltage: 0.0
hardware_ready: false
output_state_known: false
```

Aktywny był alert:

```text
DAC_COMMUNICATION_LOST
severity: critical
```

Dodatkowo niedostępne były oba SEN55 oraz AERO. Te błędy nie były przyczyną awarii lokalnego STOP, ale stanowiły równoległą diagnostykę peryferiów.

## Zdegradowany warunek wejściowy

Harness rozpoznał wąski, jawnie dozwolony stan zdegradowany:

```text
requested EC setpoints: 0 V / 0 V
DAC_COMMUNICATION_LOST: present
physical EC output confirmation: UNAVAILABLE
DEGRADED ZERO-REQUEST PRECONDITION: ACCEPTED FOR POWER-DOMAIN TEST
```

Ten wynik NIE oznacza, że fizyczne wyjścia 0–10 V DFR0971 zostały potwierdzone jako 0 V.

## Instalacja i zależności systemd

Harness utworzył backup aktualnie zainstalowanych plików w:

```text
/var/tmp/wvc-dfr0473-stage14-backup-20260825-111326
```

Zainstalowano konfigurację Stage14 oraz sprawdzono graf zależności systemd.

Wynik:

```text
systemd dependency/config: PASS
```

## Test DFR0473 OFF

`wvc-host-power.service` został zatrzymany. Zależność `Requires/After` spowodowała także zatrzymanie `ventilation-core.service`.

Stan usług po zatrzymaniu:

```text
wvc-host-power: inactive
ventilation-core: inactive
```

Operator fizycznie potwierdził:

```text
DFR0473 OFF
relay released / LED OFF
```

## Test DFR0473 ON

Następnie uruchomiono `ventilation-core.service`.

Systemd najpierw uruchomił `wvc-host-power`, który przejął GPIO22, załączył domenę 12 V i odczekał czas stabilizacji, a następnie pozwolił wystartować core.

Log potwierdził:

```text
12 V power domain commanded ON via DFR0473 line=GPIO22
```

Operator fizycznie potwierdził:

```text
DFR0473 ON
relay energized / LED ON
```

Obie usługi wróciły do `active`.

## Stan po ponownym starcie core

Ze względu na nadal istniejącą awarię DFR0971 / GP8403 core wrócił do:

```text
mode: FAULT
supply_voltage: 0.0
extract_voltage: 0.0
output_state_known: false
```

Harness ponownie zaakceptował wyłącznie jawny stan zdegradowany z `DAC_COMMUNICATION_LOST` i żądanymi setpointami `0.0 / 0.0`.

## Wynik końcowy

```text
STAGE14 NON-DESTRUCTIVE POWER-DOMAIN VALIDATION: PASS (DAC FAULT DEGRADED)
```

Potwierdzono:

- GPIO22 steruje DFR0473 zgodnie z oczekiwaniem,
- DFR0473 fizycznie przechodzi OFF po zatrzymaniu warstwy host-power,
- DFR0473 fizycznie przechodzi ON przy starcie warstwy host-power,
- zależności systemd wymuszają właściwą kolejność `wvc-host-power -> ventilation-core`,
- znana awaria DAC nie blokuje walidacji domeny 12 V,
- test nie wykonał restartu ani wyłączenia CM5.

Nie potwierdzono:

- fizycznego stanu VOUT0/VOUT1 DFR0971 podczas obecnej awarii I²C,
- zachowania VOUT0/VOUT1 podczas prawdziwego `poweroff` CM5,
- pełnej sekwencji GUI shutdown -> DFR0473 OFF -> CM5 poweroff,
- ponownego startu przez fizyczny `PWR_BUT`.

## Następny bezpieczny krok

Przed pierwszym pełnym host `poweroff` należy zmierzyć multimetrem rzeczywiste napięcia:

```text
VOUT0 -> GND
VOUT1 -> GND
```

przy aktualnym stanie `FAULT / DAC_COMMUNICATION_LOST`.

Dopiero po zapisaniu rzeczywistych napięć można przejść do kontrolowanego testu pełnego POWER OFF i późniejszego startu przez `PWR_BUT`.
