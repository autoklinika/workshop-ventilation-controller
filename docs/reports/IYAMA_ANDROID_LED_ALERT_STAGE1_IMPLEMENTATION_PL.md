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

## Potwierdzone komendy sprzętowe B3

Na docelowym panelu potwierdzono:

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

Potwierdzone tryby animowane producenta:

```text
0x0B = cykl kolorów
0x0F = biały fade/strobe
0x13 = wielokolorowy fade
0x17 = skokowa zmiana kolorów
```

Nie są one używane przez AlertV2, ponieważ przejmują prezentację koloru.

Próby uzyskania fade bieżącego koloru przez `0x00/0x01`, pełne ramki NEC i custom RGB nie dały użytecznej regulacji jasności na docelowym B3. Starszy interfejs `/dev/ledjni` z demo B1 nie istnieje w firmware B3. W `/sys/devices/platform/led_con_h` wystawiony jest tylko atrybut `zigbee_reset`.

## Zasada sterowania po OFF

Po `0x02 = OFF` przed następnym statycznym kolorem wysyłane jest `0x03 = ON`, a następnie właściwy kolor. Jeżeli pasek jest już włączony, zmiana pomiędzy statycznymi kolorami odbywa się bez ponownego `0x03`.

## Logika AlertV2

Priorytet najwyższego aktywnego alertu wygrywa. Kontroler obsługuje pole `weight` 0..4 oraz obecne `severity`.

| Stan | Kolor | Wzór |
|---|---|---|
| start przed pierwszym poprawnym snapshotem | biały | wolne miganie |
| utrata komunikacji po wcześniejszym poprawnym połączeniu > 6 s | czerwony | szybkie miganie |
| brak alertów | zielony | stały |
| lokalny tryb serwisowy / wyjście do Androida, bez alertów | niebieski | stały |
| INFO | niebieski | ACK stały / brak ACK wolne miganie |
| WARNING | żółty | ACK stały / brak ACK miganie |
| ALARM | pomarańczowy | ACK stały / brak ACK szybsze miganie |
| CRITICAL | czerwony | ACK stały / brak ACK szybkie miganie |

ACK nie obniża priorytetu i nie zmienia koloru danego stanu. Wpływa tylko na wzór migania.

## Zgodność z AlertV2

- CM5 / ventilation-core pozostaje źródłem prawdy.
- HMI nie tworzy alertów i nie wpływa na sterowanie wentylacją.
- przy wielu alertach wygrywa najwyższa waga;
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

## Deterministyczny tryb diagnostyczny

Ręczne wysyłanie komend bezpośrednio do `zigbee_reset` podczas działania APK może ścigać się z `HmiLedController`, który steruje tym samym interfejsem. Taki równoległy zapis może powodować pozornie losowe zmiany koloru/stanu.

Dlatego build debug `0.5.4-led-diagnostic` ma kontrolowany diagnostic override dostępny wyłącznie dla `BuildConfig.DEBUG` przez ADB broadcast. Polling CM5 nadal działa w tle, ale renderer LED jest wymuszony na jednym wskazanym stanie aż do `CLEAR`.

Pełny test sprzętowy:

```powershell
.\tools\test-led-alert-states-diagnostic.ps1
```

Skrypt:

1. uruchamia HMI i czyści logcat;
2. ustawia znany baseline `NORMAL`;
3. kolejno wymusza każdy stan LED;
4. przy każdym stanie użytkownik jawnie wybiera `P=PASS`, `F=FAIL` albo `Q`;
5. zapisuje wyniki i `WvcHmiLed` logcat do pliku;
6. na końcu wysyła `CLEAR`, aby oddać sterowanie aktualnej logice live.

Podczas tego testu nie należy uruchamiać żadnego drugiego skryptu zapisującego bezpośrednio do `zigbee_reset`.

## Status

Implementacja znajduje się na gałęzi `agent/iiyama-led-alert-stage1`. PR #70 pozostaje DRAFT i nie może być scalony do `main` bez pełnej fizycznej walidacji i wyraźnej zgody właściciela projektu.
