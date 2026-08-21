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
0x02 = OFF latch
0x03 = wake / domyślnie WHITE
0x04 = RED
0x05 = GREEN
0x06 = BLUE
0x07 = WHITE
0x08 = ORANGE
0x10 = YELLOW
```

Najważniejszy potwierdzony kontrakt sprzętowy po `0x02 OFF`:

```text
0x02
...
0x03 + COLOR   # natychmiast, w tej samej sesji su
```

Po `0x02` sam kod koloru nie jest wystarczającym kontraktem do niezawodnego ponownego włączenia paska. `0x03` budzi pasek do stanu białego, a właściwy kolor musi zostać zapisany bezpośrednio po nim w tej samej sesji root shell.

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

Build debug ma kontrolowany diagnostic override dostępny przez ADB broadcast. Polling CM5 nadal działa w tle, ale fizyczny renderer LED może zostać przypięty do wskazanego stanu aż do `CLEAR`.

Dodatkowo dodano debugowy stan `PAUSE`:

```text
PAUSE = polling i proces HMI działają dalej, ale HmiLedController nie wykonuje żadnych fizycznych zapisów LED
CLEAR = przywrócenie normalnego renderera
```

`PAUSE` był konieczny, ponieważ `am force-stop` nie izoluje tego kiosku — proces HMI jest uruchamiany ponownie automatycznie i może ponownie stać się writerem LED.

## Ustalenia z wcześniejszych testów

Pierwszy deterministyczny log ujawnił rzeczywisty race pomiędzy zmianą diagnostic override a rendererem. Został on naprawiony przez wspólny `renderLock`; po zaakceptowaniu nowego stanu nie może już zostać wypisana komenda starego stanu.

W tym samym okresie błędnie uznano sekwencję `0x03 + COLOR` po OFF za zbędną i zbudowano wariant `0.5.5-led-single-command`. Późniejsza walidacja sprzętowa wykazała, że ten wniosek był niepoprawny: problemem nie było samo `0x03`, tylko brak prawdziwej izolacji writerów podczas części testów.

## Izolowana walidacja sprzętowa 2026-08-21

W buildzie `0.5.7-led-diagnostic-pause` renderer aplikacji został zatrzymany przez `PAUSE`, przy zachowaniu procesu HMI i pollingu. Ręczne ADB -> `su` było wtedy jedynym writerem paska.

Wynik:

```text
REARM_GREEN_03_PLUS_05        PASS
REARM_RED_STATIC_03_PLUS_04   PASS
REARM_RED_BLINK_1000MS        PASS
REARM_RED_BLINK_500MS         PASS
REARM_RED_BLINK_250MS         FAIL
```

Podsumowanie sprzętowe:

```text
greenRearm=True
redStatic=True
red1000=True
red500=True
red250=False
```

To potwierdza dwie rzeczy:

1. po `0x02 OFF` ponowne włączenie koloru ma używać atomowej sekwencji `0x03 + COLOR` w jednej sesji `su`;
2. czerwone miganie jest stabilne przy 500 ms ON / 500 ms OFF, natomiast wariant 250 ms nie jest akceptowany jako poprawny wizualnie na docelowym panelu.

## Korekta build 0.5.8

Build `0.5.8-led-rearm` implementuje potwierdzony kontrakt B3:

- `OFF` -> pojedynczy zapis `0x02`;
- każdy widoczny kolor -> atomowa sekwencja `0x03 + COLOR` w jednej sesji root shell;
- `renderLock` pozostaje i nadal serializuje zmianę stanu z fizycznym renderem;
- `CRITICAL_UNACK` i `COMMUNICATION_LOST` używają 500 ms ON / 500 ms OFF;
- `CRITICAL_ACK` pozostaje stałym czerwonym;
- debugowy `PAUSE` pozostaje dostępny do izolowanych testów sprzętowych.

Log drivera dla koloru ma teraz postać:

```text
RGB write PASS commands=0x03,0x04
```

a dla OFF:

```text
RGB write PASS commands=0x02
```

## Pełna walidacja aplikacji 0.5.8

Pełny test deterministyczny na docelowym panelu dał PASS dla wszystkich stanów poza `CRITICAL_ACK`:

```text
NORMAL             PASS
INFO_UNACK         PASS
INFO_ACK           PASS
WARNING_UNACK      PASS
WARNING_ACK        PASS
ALARM_UNACK        PASS
ALARM_ACK          PASS
CRITICAL_UNACK     PASS
CRITICAL_ACK       FAIL
COMMUNICATION_LOST PASS
STARTUP_UNKNOWN    PASS
SERVICE            PASS
```

Log dokładnie wyizolował krawędź przejścia. Ostatni `CRITICAL_UNACK` zapisał `0x02 OFF` z sukcesem o 09:48:47.836. `CRITICAL_ACK` został zaakceptowany już o 09:48:47.865, a próba `0x03+0x04` rozpoczęła się o 09:48:47.961, czyli około 125 ms po zakończeniu OFF. Driver raportował sukces zapisu, ale panel nie przeszedł wizualnie w stabilny czerwony stan.

To nie jest błąd mapowania koloru ani sekwencji `0x03+0x04`: statyczny czerwony po kontrolowanym re-armie był wcześniej PASS. Jest to krawędź czasowa OFF -> SOLID przy zbyt szybkim przejściu logicznym z migania UNACK do ACK.

## Korekta build 0.5.9

Build `0.5.9-led-solid-rearm-guard` dodaje wyłącznie ochronę przejścia do stanu stałego po ostatnim app-owned `0x02 OFF`:

- HmiLedController pamięta ostatnią skuteczną fizyczną komendę i czas jej zakończenia;
- jeśli nowy stan jest stały, a ostatnią komendą było `OFF`, renderer nie próbuje natychmiast re-armować koloru;
- stały kolor jest odroczony do czasu, aż od zakończenia `OFF` minie co najmniej 500 ms;
- zwykła kadencja stanów migających pozostaje bez zmian;
- każda właściwa komenda koloru nadal używa atomowego `0x03 + COLOR` w jednej sesji root shell.

W logu odroczenie jest jawne:

```text
LED solid re-arm deferred state=CRITICAL_ACK sinceOffMs=<...> guardMs=500
```

Po osiągnięciu guardu renderer zapisuje normalnie:

```text
LED render state=CRITICAL_ACK command=0x04
RGB write PASS commands=0x03,0x04
```

## Odporność transportu

Polling: 2 s.

Timeout connect/read: 1.5 s.

Po 6 s bez poprawnego snapshotu, po wcześniejszym poprawnym połączeniu, HMI przechodzi lokalnie w `COMMUNICATION_LOST`. Przed pierwszym poprawnym snapshotem używa `STARTUP_UNKNOWN`.

## Status

Gałąź: `agent/iiyama-led-alert-stage1`.

Aktualny test build:

```text
versionCode 16
versionName 0.5.9-led-solid-rearm-guard
```

PR #70 pozostaje DRAFT. Następny test sprzętowy powinien obejmować przede wszystkim przejście `CRITICAL_UNACK -> CRITICAL_ACK` (`-RedOnly`). Po jego PASS można powtórzyć pełny test końcowy i dopiero wtedy rozważać zakończenie Stage 1.
