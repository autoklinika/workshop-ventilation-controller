# HMI Sleep/Wake Stage15 – walidacja na fizycznym CM5/HMI — 2026-08-25

## Zakres

Walidacja automatycznego usypiania i wybudzania lokalnego HMI iiyama ProLite TW1025LASC-B3PNR z Raspberry Pi Compute Module 5 przez ADB/TCP po przewodowym Ethernet.

Gałąź:

```text
agent/hmi-sleep-wake-stage15
```

Zweryfikowany HEAD podczas testu:

```text
93f9bfc9ad2617938ae9fadaba1685b7a047ac29
```

Target HMI:

```text
192.168.1.39:5555
```

Użyty harness:

```text
tools/install_validate_hmi_sleep_wake_cm5.sh
```

Harness nie wykonywał `poweroff` ani `reboot` CM5.

## ADB na CM5

Pakiet `adb` nie był wcześniej zainstalowany. Zainstalowano Debian/Raspberry Pi package `adb` wraz z zależnościami.

Wersja:

```text
Android Debug Bridge version 1.0.41
```

Połączenie CM5 -> HMI przez Ethernet:

```text
connected to 192.168.1.39:5555
192.168.1.39:5555 device
```

Połączenie zostało zestawione poprawnie i HMI zaakceptowało klucz ADB CM5.

Klucz/state ADB dla usługi jest przechowywany w:

```text
/var/lib/wvc-hmi-power
```

## Test bezpośredniego WAKE

Polecenie Stage15 wysłało Android keyevent 224 przez ADB.

Wynik:

```text
HMI WAKE commanded via ADB target=192.168.1.39:5555 attempt=1/3
HMI WAKE command: PASS
```

## Test bezpośredniego SLEEP

Polecenie Stage15 wysłało Android keyevent 223 przez ADB.

Wynik:

```text
HMI SLEEP commanded via ADB target=192.168.1.39:5555 attempt=1/2
```

Operator fizycznie potwierdził prawdziwy Android SLEEP HMI.

## WAKE z prawdziwego Android SLEEP

Po uśpieniu panel nadal był osiągalny po przewodowym Ethernet/ADB i został wybudzony:

```text
HMI WAKE commanded via ADB target=192.168.1.39:5555 attempt=1/4
```

Operator fizycznie potwierdził wybudzenie HMI.

## Instalacja usługi systemd

Zainstalowano i włączono:

```text
wvc-hmi-power.service
```

Adres HMI został zapisany poza unitem w:

```text
/etc/workshop-ventilation/hmi-power.env
```

z wartością:

```text
WVC_HMI_ADB_TARGET=192.168.1.39:5555
```

Backup testu:

```text
/var/tmp/wvc-hmi-stage15-backup-20260825-163618
```

## Test systemd ExecStop -> SLEEP

Po uruchomieniu i następnie zatrzymaniu `wvc-hmi-power.service` wykonano:

```text
ExecStop -> HMI SLEEP
```

Log:

```text
16:36:40 HMI SLEEP commanded via ADB target=192.168.1.39:5555 attempt=1/2
```

Operator fizycznie potwierdził, że HMI zasnęło.

Wynik:

```text
SYSTEMD EXECSTOP SLEEP: PASS
```

## Test systemd ExecStart -> WAKE

Po ponownym uruchomieniu `wvc-hmi-power.service` wykonano:

```text
ExecStart -> HMI WAKE
```

Log:

```text
16:36:46 HMI WAKE commanded via ADB target=192.168.1.39:5555 attempt=1/6
```

Operator fizycznie potwierdził wybudzenie HMI.

Wynik:

```text
SYSTEMD EXECSTART WAKE: PASS
```

## Izolacja od safety/control plane

Podczas całego testu:

```text
wvc-host-power.service: active
ventilation-core.service: active
```

Usługa HMI nie wymagała restartu ani zatrzymania safety/control services.

Architektura pozostaje zgodna z zasadą:

```text
HMI = non-safety / best-effort
```

Brak HMI, brak Ethernet, timeout ADB lub błąd ADB nie mogą blokować `wvc-host-power`, `ventilation-core`, shutdown ani reboot CM5.

## Wynik końcowy

```text
STAGE15 HMI SLEEP/WAKE VALIDATION: PASS
```

Potwierdzono fizycznie:

- CM5 -> HMI ADB/TCP po Ethernet działa,
- bezpośredni WAKE działa,
- bezpośredni SLEEP działa,
- WAKE działa z prawdziwego Android SLEEP,
- systemd `ExecStop` usypia HMI,
- systemd `ExecStart` wybudza HMI,
- HMI power layer jest niezależny od safety/control plane,
- target HMI jest zapisany w osobnym pliku środowiskowym,
- harness nie wykonał restartu ani wyłączenia CM5.

## Następny krok

Wykonać pełny test produkcyjnej kolejności:

```text
GUI POWER OFF
-> host-power SAFE + DFR0473 OFF
-> systemd zatrzymuje wvc-hmi-power
-> HMI SLEEP
-> CM5 OFF

PWR_BUT
-> CM5 boot
-> network online
-> wvc-hmi-power ExecStart
-> HMI WAKE
```

W pełnym teście należy fizycznie potwierdzić, że HMI zasypia podczas shutdown i automatycznie wybudza się po ponownym starcie CM5.
