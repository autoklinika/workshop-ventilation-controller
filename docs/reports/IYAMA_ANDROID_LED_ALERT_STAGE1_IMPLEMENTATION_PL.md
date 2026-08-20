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

## Potwierdzone kody sprzętowe

Na docelowym panelu potwierdzono:

```text
0x02 = OFF
0x03 = LED ON
0x04 = RED
0x05 = GREEN
0x06 = BLUE
0x07 = WHITE
0x08 = ORANGE
0x0B = YELLOW
```

Sterownik wysyła `LED ON = 0x03` przed każdą komendą koloru.

## Logika Stage 1

Priorytet najwyższego aktywnego alertu wygrywa. Kontroler obsługuje zarówno przyszłe pole `weight` 0..4, jak i obecne pole `severity`.

Mapowanie logiczne:

| Stan | Kolor | Wzór |
|---|---|---|
| start przed pierwszym poprawnym snapshotem | biały | wolne miganie |
| utrata komunikacji po wcześniejszym poprawnym połączeniu > 6 s | czerwony | szybkie miganie |
| brak alertów | zielony | stały |
| lokalny tryb serwisowy / wyjście do Androida, bez alertów | niebieski | stały |
| INFO | niebieski | ACK stały / brak ACK wolne miganie |
| WARNING | żółty | ACK stały / brak ACK wolne miganie |
| ALARM | pomarańczowy | ACK stały / brak ACK średnie miganie |
| CRITICAL | czerwony | ACK stały / brak ACK szybkie miganie |

ACK nie obniża priorytetu i nie zmienia koloru. W Stage 1 wpływa tylko na wzór migania.

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

Aktywność `MainActivity` ustawia stan lokalny NORMAL, natomiast `ServiceModeActivity` i `ServiceAccessActivity` ustawiają lokalny tryb serwisowy. Po świadomym wyjściu do launchera Android ostatni lokalny stan serwisowy pozostaje niebieski, o ile żaden alert nie ma wyższego priorytetu.

## CI

Finalny HEAD Stage 1 po kalibracji palety:

```text
4f9c95f3c14155b219e1088ccb2b809cfdec077a
```

GitHub Actions:

```text
HMI Android            PASS
Ventilation Core Tests PASS
```

## Testy wymagające panelu

1. build i deploy APK 0.5.0-led-alert-stage1;
2. bez aktywnych alertów: zielony;
3. wejście NFC / PIN do menu serwisowego: niebieski, jeżeli brak alertu;
4. wyjście kafelkiem ANDROID: niebieski, jeżeli brak alertu;
5. powrót do HMI: zielony;
6. aktywny WARNING: żółty wolno migający; po ACK żółty stały;
7. aktywny ALARM: pomarańczowy średnio migający; po ACK pomarańczowy stały;
8. aktywny CRITICAL: czerwony szybko migający; po ACK czerwony stały;
9. odcięcie komunikacji HMI->CM5 na > 6 s: czerwony szybko migający;
10. ponowne połączenie: automatyczny powrót do aktualnego stanu alertów.

## Status

Implementacja software Stage 1 na gałęzi `agent/iiyama-led-alert-stage1`.

CI: PASS.

Paleta RGB: sprzętowo potwierdzona.

Wymagana pełna walidacja przepływu alertów na iiyamie przed jakimkolwiek merge do `main`.
