# HMI Sleep/Wake Stage15 – walidacja na fizycznym CM5/HMI — 2026-08-25

## Zakres

Walidacja automatycznego usypiania i wybudzania lokalnego HMI iiyama ProLite TW1025LASC-B3PNR z Raspberry Pi Compute Module 5 przez ADB/TCP po przewodowym Ethernet.

Gałąź:

```text
agent/hmi-sleep-wake-stage15
```

Zweryfikowany HEAD podczas pierwszego testu:

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

## Pełny POWER OFF / POWER ON — pierwsza obserwacja

Przy pierwszym pełnym cyklu produkcyjnym HMI poprawnie zasnęło podczas POWER OFF oraz automatycznie wybudziło się po starcie CM5.

Po boot wszystkie kluczowe usługi były aktywne:

```text
wvc-hmi-power.service: active
wvc-host-power.service: active
ventilation-core.service: active
```

Pierwszy boot ujawnił jednak drobny problem UX: HMI budziło się szybciej niż WebGUI było gotowe, przez co przez chwilę wyświetlało komunikat braku komunikacji, po czym samo przechodziło do poprawnej pracy.

Log HMI z tego bootu:

```text
16:45:00 Starting wvc-hmi-power.service
16:45:01 adb daemon uruchomiony, połączenie do 192.168.1.39:5555 zestawione
16:45:03 HMI WAKE commanded via ADB target=192.168.1.39:5555 attempt=2/6
16:45:03 Finished wvc-hmi-power.service
```

Dodatkowo parser pierwszej próby ADB traktował poprawne połączenie jako failure, gdy `adb` poprzedzał linię `connected to ...` komunikatem o starcie własnego demona. To był false warning, nie realny problem transportu.

## Korekta kolejności WAKE

Na tej samej gałęzi Stage15 poprawiono kolejność uruchamiania HMI:

```text
network-online.target
+ wvc-web-ui.service
+ 4 s stabilizacji
-> HMI WAKE
```

Zainstalowany unit po aktualizacji został fizycznie sprawdzony na CM5:

```text
Wants=network-online.target wvc-web-ui.service
After=network-online.target wvc-web-ui.service
ExecStartPre=/usr/bin/sleep 4
TimeoutStartSec=30
```

Równolegle parser ADB został poprawiony tak, aby akceptował wieloliniowy wynik pierwszego `adb connect`, w którym przed `connected to ...` pojawia się start lokalnego demona ADB.

Ta zmiana pozostaje wyłącznie warstwą UX/startup i nie tworzy zależności safety. `wvc-hmi-power` nadal jest non-blocking wobec `wvc-host-power` i `ventilation-core`.

## Pełny boot po korekcie kolejności

Po aktualizacji unitu wykonano kolejny pełny POWER OFF / POWER ON. Logi bieżącego bootu potwierdziły oczekiwaną kolejność:

```text
17:09:39 wvc-web-ui.service active/running
17:09:39 Starting wvc-hmi-power.service
17:09:43 HMI WAKE commanded via ADB target=192.168.1.39:5555 attempt=1/6
17:09:43 Finished wvc-hmi-power.service
```

Czyli HMI zostało obudzone około 4 s po starcie WebGUI, zgodnie z `ExecStartPre=/usr/bin/sleep 4`.

Parser ADB nie zgłosił już fałszywego błędu pierwszej próby: WAKE został wykonany od razu jako `attempt=1/6`.

Po wybudzeniu WebGUI obsługiwało żądania HMI z `192.168.1.39`, m.in.:

```text
GET /api/v1/alerts 200
GET /api/v1/state 200
GET /api/v1/zigbee 200
GET /api/v1/zigbee/removal-confirmation 200
```

Wynik techniczny pełnego bootu po korekcie:

```text
WEB GUI BEFORE HMI WAKE: PASS
4 S STARTUP STABILIZATION: PASS
ADB WAKE FIRST ATTEMPT: PASS
HMI -> WEB API AFTER WAKE: PASS
```

Logi nie mogą samodzielnie potwierdzić elementu czysto wizualnego: czy po wybudzeniu ekran od razu pokazał poprawne GUI bez chwilowego komunikatu „brak komunikacji”. Ten punkt wymaga obserwacji operatora.

## Izolacja od safety/control plane

Podczas testów:

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

## Wynik aktualny

```text
STAGE15 HMI SLEEP/WAKE VALIDATION: PASS — TECHNICAL
```

Potwierdzono fizycznie i z logów:

- CM5 -> HMI ADB/TCP po Ethernet działa,
- bezpośredni WAKE działa,
- bezpośredni SLEEP działa,
- WAKE działa z prawdziwego Android SLEEP,
- systemd `ExecStop` usypia HMI,
- systemd `ExecStart` wybudza HMI,
- pełny POWER OFF usypia HMI,
- pełny POWER ON automatycznie wybudza HMI,
- HMI power layer jest niezależny od safety/control plane,
- target HMI jest zapisany w osobnym pliku środowiskowym,
- poprawiona kolejność startu HMI czeka na WebGUI i 4 s stabilizacji,
- po korekcie ADB WAKE przechodzi w pierwszej próbie,
- po WAKE HMI poprawnie komunikuje się z WebGUI.

## Pozostałe kryterium UX

Do pełnego finalnego zamknięcia Stage15 pozostaje tylko obserwacja operatora:

```text
Po automatycznym WAKE HMI od razu pokazuje działające WebGUI
bez chwilowego komunikatu o braku komunikacji.
```

Jeżeli ten punkt jest spełniony, Stage15 można oznaczyć jako finalny PASS sprzętowy/UX.
