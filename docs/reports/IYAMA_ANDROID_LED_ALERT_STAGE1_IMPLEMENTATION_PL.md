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

## Potwierdzone komendy sprzętowe

W początkowych testach HMI i w działających taskach VS Code potwierdzono następujące komendy:

```text
0x00 = zwiększenie jasności
0x01 = zmniejszenie jasności
0x02 = OFF
0x03 = ON
0x04 = RED
0x05 = GREEN
0x06 = BLUE
0x07 = WHITE
```

To są komendy/funkcje vendorowego sterownika — nie liniowa paleta RGB.

Dodatkowo wcześniej zaobserwowano, że część wyższych wartości uruchamia efekty, a nie statyczne kolory:

```text
0x0B = cykl zmieniających się kolorów
0x0F = biały efekt przyciemniania/rozjaśniania
0x13 = przyciemnianie/rozjaśnianie ze zmianą koloru
0x17 = pętla zielony/niebieski/czerwony
```

Dlatego wartości `0x08..0x17` nie mogą być automatycznie interpretowane jako statyczna paleta. W szczególności wcześniejsze przypisanie `0x08 = orange` i `0x0B = yellow` było błędne i zostało usunięte z implementacji alertów.

## Zasada sterowania po OFF

Po `0x02 = OFF` przed następnym statycznym kolorem należy najpierw wysłać `0x03 = ON`. Jeżeli pasek jest już włączony, zmiana pomiędzy potwierdzonymi statycznymi kolorami odbywa się bez ponownego `0x03`.

Implementacja Stage 1 śledzi lokalny stan `ON/OFF` i nie wysyła `0x03` przed każdą zmianą koloru.

## Logika Stage 1

Priorytet najwyższego aktywnego alertu wygrywa. Kontroler obsługuje pole `weight` 0..4 oraz obecne `severity`.

Do czasu znalezienia prawdziwych statycznych komend żółtego i pomarańczowego alerty używają wyłącznie potwierdzonych statycznych kolorów. Żaden efekt `0x08..0x17` nie jest używany przez alert LED.

| Stan | Kolor | Wzór |
|---|---|---|
| start przed pierwszym poprawnym snapshotem | biały | wolne miganie |
| utrata komunikacji po wcześniejszym poprawnym połączeniu > 6 s | czerwony | szybkie miganie |
| brak alertów | zielony | stały |
| lokalny tryb serwisowy / wyjście do Androida, bez alertów | niebieski | stały |
| INFO | niebieski | ACK stały / brak ACK wolne miganie |
| WARNING | czerwony fallback | ACK stały / brak ACK wolne miganie |
| ALARM | czerwony fallback | ACK stały / brak ACK średnie miganie |
| CRITICAL | czerwony | ACK stały / brak ACK szybkie miganie |

ACK nie obniża priorytetu i nie zmienia statycznego koloru danego stanu. Wpływa tylko na wzór migania.

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

## Testy wymagające panelu

1. build i deploy APK `0.5.2-led-static-commands`;
2. bez aktywnych alertów: zielony;
3. wejście NFC / PIN do menu serwisowego: niebieski, jeżeli brak alertu;
4. aktywny alert niepotwierdzony: czerwony zgodnie z odpowiednim wzorem migania;
5. ACK tego samego aktywnego alertu: ten sam czerwony, ale stały;
6. po fizycznym ustąpieniu przyczyny i `CLEARED`: zielony lub następny aktywny stan;
7. odcięcie komunikacji HMI->CM5 na > 6 s: czerwony szybko migający;
8. ponowne połączenie: automatyczny powrót do aktualnego stanu alertów.

## Status

Implementacja software Stage 1 na gałęzi `agent/iiyama-led-alert-stage1`.

Wymagana pełna walidacja przepływu alertów na iiyamie przed jakimkolwiek merge do `main`.
