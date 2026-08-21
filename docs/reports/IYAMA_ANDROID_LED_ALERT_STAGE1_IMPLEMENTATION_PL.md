# iiyama Android HMI — RGB alert LED — Stage 1

Data: 2026-08-21

## Cel

Dodać lokalną wizualizację stanu systemu na pasku RGB panelu iiyama TW1025LASC-B3PNR bez zmian w ventilation-core i bez przenoszenia logiki bezpieczeństwa do GUI.

Android HMI pozostaje klientem. Źródłem prawdy o alertach jest istniejący endpoint:

```text
http://192.168.1.64:18091/api/v1/alerts
```

## Architektura

```text
ventilation-core /api/v1/alerts
          |
          v
HmiLedController (Android)
          |
          v
IiyamaLedDriver
          |
          v
vendor sysfs LED attribute
```

HMI nie tworzy, nie kasuje i nie potwierdza alertów w core.

## Potwierdzone komendy B3

```text
0x02 = OFF
0x03 = ON (znana komenda producenta, ale nieużywana już przez renderer AlertV2)
0x04 = RED
0x05 = GREEN
0x06 = BLUE
0x07 = WHITE
0x08 = ORANGE
0x10 = YELLOW
```

Potwierdzone tryby animowane producenta:

```text
0x0B = cykl kolorów
0x0F = biały fade/strobe
0x13 = wielokolorowy fade
0x17 = skokowa zmiana kolorów
```

Nie są one używane przez AlertV2, ponieważ przejmują prezentację koloru.

Próby uzyskania fade bieżącego koloru przez `0x00/0x01`, pełne ramki NEC i custom RGB nie dały użytecznej regulacji jasności na docelowym B3. Starszy interfejs `/dev/ledjni` z demo B1 nie istnieje w firmware B3.

## Logika AlertV2

| Stan | Kolor | Wzór |
|---|---|---|
| STARTUP_UNKNOWN | biały | wolne miganie |
| COMMUNICATION_LOST | czerwony | szybkie miganie |
| NORMAL | zielony | stały |
| SERVICE | niebieski | stały |
| INFO | niebieski | ACK stały / UNACK miganie |
| WARNING | żółty | ACK stały / UNACK miganie |
| ALARM | pomarańczowy | ACK stały / UNACK szybsze miganie |
| CRITICAL | czerwony | ACK stały / UNACK szybkie miganie |

ACK nie obniża priorytetu i nie zmienia koloru.

## Deterministyczny tryb diagnostyczny

Build debug ma kontrolowany diagnostic override dostępny przez ADB broadcast. Polling CM5 nadal działa w tle, ale fizyczny renderer LED jest przypięty do jednego wskazanego stanu aż do `CLEAR`.

Skrypt:

```powershell
.\tools\test-led-alert-states-diagnostic.ps1
```

Test nie używa ręcznych zapisów sysfs równolegle z aplikacją.

## Wyniki pierwszej walidacji deterministycznej

Log z 2026-08-21 potwierdził, że resolver nie generował losowych kodów. Dla INFO/WARNING/ALARM/CRITICAL aplikacja wysyłała oczekiwane komendy kolorów i `0x02 OFF` z zadanymi okresami.

Jednocześnie log ujawnił dwa konkretne problemy implementacyjne:

1. Po każdym `0x02 OFF` driver wysyłał następnie `0x03 ON` i dopiero kolor, np. `0x03,0x10`, `0x03,0x08`, `0x03,0x04`. Oryginalne, wcześniej sprzętowo potwierdzone taski VS Code wykonywały pojedynczy zapis koloru bez poprzedzania go `0x03`. Dodatkowe `0x03` nie było więc częścią znanego dobrego kontraktu sprzętowego.
2. Przy przełączeniu diagnostic override renderer mógł mieć już rozpoczęty tick poprzedniego stanu. W logu po zaakceptowaniu `STARTUP_UNKNOWN` pojawił się jeszcze jeden zapis starego czerwonego stanu, a dopiero potem biały. To był wyścig pomiędzy zmianą stanu a renderem.

## Korekta build 0.5.5

Build `0.5.5-led-single-command` wprowadza dwie zmiany:

- każdy fizyczny stan LED jest teraz jednym atomowym zapisem: `0x02` albo bezpośrednia komenda koloru; renderer nie używa `0x03`;
- zmiana stanu, diagnostic override i fizyczny render są serializowane jednym `renderLock`, więc po zaakceptowaniu nowego stanu nie może zostać wypisana komenda starego stanu.

Dodatkowo log zawiera teraz jawne wpisy:

```text
LED render state=<STATE> command=0xNN
RGB write PASS command=0xNN
```

Pozwala to jednoznacznie porównać stan logiczny z dokładnie jednym poleceniem wysłanym do sterownika.

## Odporność transportu

Polling: 2 s.

Timeout connect/read: 1.5 s.

Po 6 s bez poprawnego snapshotu, po wcześniejszym poprawnym połączeniu, HMI przechodzi lokalnie w `COMMUNICATION_LOST`. Przed pierwszym poprawnym snapshotem używa `STARTUP_UNKNOWN`.

## Status

Gałąź: `agent/iiyama-led-alert-stage1`.

Aktualny test build:

```text
versionCode 12
versionName 0.5.5-led-single-command
```

PR #70 pozostaje DRAFT. Wymagana ponowna fizyczna walidacja diagnostyczna na docelowym TW1025LASC-B3PNR przed jakimkolwiek merge do `main`.
