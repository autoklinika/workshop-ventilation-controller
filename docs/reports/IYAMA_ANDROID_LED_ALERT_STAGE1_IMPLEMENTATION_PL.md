# iiyama Android HMI — RGB alert LED — Stage 1

Data: 2026-08-20

## Cel

Dodać lokalną wizualizację stanu systemu na pasku RGB panelu iiyama TW1025LASC-B3PNR bez zmian w ventilation-core i bez przenoszenia logiki bezpieczeństwa do GUI.

Android HMI pozostaje klientem. Źródłem prawdy o alertach jest istniejący endpoint:

```text
http://192.168.1.64:18091/api/v1/alerts
```

Android odpytuje endpoint bezpośrednio, niezależnie od WebView / JavaScript.

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
/sys/devices/platform/led_con_h/zigbee_reset
```

Sterownik paska używa lokalnego `su` i vendorowego sysfs. Nie wykonuje żadnych operacji na CM5 poza odczytem istniejącego API.

## Wynik walidacji sprzętowej sterowania RGB

Na docelowym TW1025LASC-B3PNR potwierdzono statyczne komendy używane przez AlertV2:

```text
0x02 = OFF
0x03 = ON
0x04 = RED
0x05 = GREEN
0x06 = BLUE
0x07 = WHITE
0x08 = ORANGE
0x10 = YELLOW
```

Wartości są komendami/funkcjami vendorowego sterownika, a nie liniową paletą RGB.

Potwierdzone tryby animowane:

```text
0x0B = sekwencyjna zmiana kolorów
0x0F = biały fade in/out
0x13 = wielokolorowy fade in/out
0x17 = skokowa zmiana kolorów
```

Te tryby nie są używane przez AlertV2, ponieważ przejmują własną prezentację koloru i nie pozwalają zachować semantyki WARNING/ALARM/CRITICAL.

Komendy `0x00` i `0x01`, mimo opisu w materiałach producenta jako brightness +/-, nie dały widocznej zmiany jasności na docelowym B3. Próby pełnych ramek NEC również zmieniały tylko stan/kolor i nie dały użytecznej regulacji jasności.

Dokumentacja producenta dla starszego B1 zawiera również `/dev/ledjni` z regulacją poziomu 0..15 przez `ioctl()`, ale na docelowym B3 urządzenie `/dev/ledjni` nie istnieje. W `/sys/devices/platform/led_con_h/` dostępny jest tylko atrybut `zigbee_reset`; brak osobnego PWM/brightness dla paska.

Wniosek: AlertV2 używa wyłącznie statycznych kolorów i programowego blink ON/OFF. Nie implementujemy sztucznego fade przez szybkie wywołania `su`/sysfs.

## Zasada sterowania po OFF

Po `0x02 = OFF` przed następnym statycznym kolorem wysyłane jest `0x03 = ON`, a następnie właściwy kolor. Jeżeli pasek jest już włączony, zmiana między statycznymi kolorami odbywa się bez ponownego `0x03`.

`IiyamaLedDriver` śledzi lokalny stan ON/OFF i odrzuca komendy animowane.

## Finalne mapowanie AlertV2

Priorytet najwyższego aktywnego alertu wygrywa. Kontroler obsługuje pole `weight` 0..4 oraz obecne `severity`.

| Stan | Kolor | Wzór |
|---|---|---|
| start przed pierwszym poprawnym snapshotem | biały | wolne miganie |
| utrata komunikacji po wcześniejszym poprawnym połączeniu > 6 s | czerwony | szybkie miganie |
| NORMAL / brak alertów | zielony | stały |
| SERVICE / Android, bez alertów | niebieski | stały |
| INFO | niebieski | ACK stały / brak ACK wolne miganie |
| WARNING | żółty | ACK stały / brak ACK wolne miganie |
| ALARM | pomarańczowy | ACK stały / brak ACK średnie miganie |
| CRITICAL | czerwony | ACK stały / brak ACK szybkie miganie |

Kody produkcyjne:

```text
NORMAL   GREEN   0x05
INFO     BLUE    0x06
WARNING  YELLOW  0x10
ALARM    ORANGE  0x08
CRITICAL RED     0x04
STARTUP  WHITE   0x07
```

ACK nie obniża priorytetu i nie zmienia koloru aktywnego alertu. Zmienia wyłącznie wzór z migania na światło stałe.

## Zgodność z AlertV2

- CM5 / ventilation-core pozostaje źródłem prawdy.
- HMI nie tworzy alertów i nie wpływa na sterowanie wentylacją.
- przy wielu alertach wygrywa najwyższa waga;
- jeżeli na najwyższym poziomie jest co najmniej jeden alert bez ACK, LED pozostaje w trybie migania;
- aktywny alert ma priorytet nad lokalnym niebieskim trybem serwisowym;
- brak danych nie jest interpretowany jako zielony;
- po utracie wcześniej działającej komunikacji HMI sygnalizuje lokalny stan krytyczny czerwonym szybkim miganiem.

## Odporność transportu

Polling: 2 s.

Timeout connect/read: 1.5 s.

Krótka pojedyncza utrata pakietu nie zmienia od razu LED. Po 6 s bez poprawnego snapshotu od wcześniej działającego core ustawiany jest lokalny `COMMUNICATION_LOST`.

Przed pierwszym poprawnym połączeniem pokazywany jest `STARTUP_UNKNOWN` — biały wolno migający.

## Niezależność od WebView

`HmiApplication` uruchamia `HmiLedController` przy starcie procesu Android. Sterownik nie korzysta z `alerts.js`, DOM ani eventów WebView. Przeładowanie GUI nie resetuje logiki paska.

## Wersja do walidacji

APK:

```text
versionCode 10
versionName 0.5.3-led-alert-palette
```

## Testy wymagające panelu

1. build i deploy APK `0.5.3-led-alert-palette`;
2. bez aktywnych alertów: zielony stały;
3. tryb serwisowy bez alertów: niebieski stały;
4. INFO bez ACK: niebieski migający; po ACK niebieski stały;
5. WARNING bez ACK: żółty migający; po ACK żółty stały;
6. ALARM bez ACK: pomarańczowy migający; po ACK pomarańczowy stały;
7. CRITICAL bez ACK: czerwony szybko migający; po ACK czerwony stały;
8. przy wielu alertach wygrywa najwyższy poziom;
9. po `CLEARED` następuje przejście do następnego aktywnego poziomu albo NORMAL;
10. odcięcie komunikacji HMI->CM5 na > 6 s: czerwony szybki blink;
11. ponowne połączenie: automatyczny powrót do aktualnego stanu alertów;
12. zimny start: biały wolny blink do pierwszego poprawnego snapshotu.

## Status

Implementacja znajduje się na gałęzi `agent/iiyama-led-alert-stage1` i w draft PR #70.

Nie wykonywać merge do `main` przed pełną walidacją sprzętową i wyraźną zgodą właściciela projektu.
