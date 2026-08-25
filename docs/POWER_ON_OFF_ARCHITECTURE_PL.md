# Architektura POWER ON/OFF – notatka robocza

> Dokument żywy. Zapisujemy tu wszystkie ustalenia, testy i decyzje dotyczące uruchamiania, wyłączania i stanów zasilania całego systemu Workshop Ventilation Controller.

## 1. Cel

Zaprojektować spójny i bezpieczny mechanizm POWER ON/OFF obejmujący:

- CM5,
- HMI iiyama ProLite TW1025LASC-B3PNR,
- urządzenia wykonawcze i peryferia,
- fizycznie odcinaną domenę 12 V,
- kolejność bezpiecznego wyłączania, restartu i uruchamiania.

System nie ma pracować 24/7. Normalny stan OFF ma ograniczać niepotrzebną wielogodzinną pracę CM5, peryferiów i urządzeń wykonawczych poza godzinami pracy warsztatu.

## 2. Aktualnie przyjęta filozofia docelowa

### 2.1. POWER ON CM5

CM5 będzie uruchamiany fizycznym chwilowym przyciskiem podłączonym do dedykowanego wejścia `PWR_BUT` CM5/CM5 IO Board.

Nie planujemy dodatkowego sterownika USB, przekaźnika USB ani NFC do fizycznego uruchamiania CM5.

Normalny POWER ON:

1. System jest wyłączony.
2. Użytkownik naciska fizyczny przycisk POWER.
3. `PWR_BUT` uruchamia CM5.
4. Linux startuje.
5. Uprzywilejowana warstwa `wvc-host-power` przejmuje GPIO DFR0473 w stanie LOW, a następnie świadomie załącza domenę 12 V.
6. Po stabilizacji 12 V uruchamiany jest `ventilation-core` i oceniana jest rzeczywista gotowość sprzętu.
7. HMI zostaje doprowadzone do stanu roboczego po osiągnięciu gotowości systemu.

### 2.2. POWER OFF CM5

Normalne wyłączenie ma być zawsze kontrolowane programowo przez istniejący mechanizm host-power.

Fizyczny przycisk służy do uruchamiania CM5. Krótkie naciśnięcie przy działającym Linuxie ma być ignorowane i nie może tworzyć alternatywnej drogi shutdown omijającej `host_power_agent`.

Długie przytrzymanie sprzętowego `PWR_BUT` pozostaje awaryjnym hard-off i nie jest normalną procedurą użytkową.

Kluczowa zasada po walidacji 2026-08-25:

```text
AWARIA KOMUNIKACJI / BRAK POTWIERDZENIA SAFE
!=
ZAKAZ WYŁĄCZENIA CM5
```

Program zawsze próbuje zatrzymać układ możliwie bezpiecznie, ale uszkodzony DAC, AERO, SEN55, Zigbee lub inne peryferium nie może pozostawić systemu w stanie „nie da się wyłączyć”.

### 2.3. Zachowanie po zaniku i powrocie zasilania sieciowego

Jeżeli finalnie wymagamy, aby po powrocie zasilania CM5 nie uruchamiał się sam, lecz czekał na fizyczny przycisk, bootloader CM5 należy skonfigurować z:

```text
POWER_OFF_ON_HALT=1
WAIT_FOR_POWER_BUTTON=1
```

To ustawienie należy zwalidować na fizycznym CM5 przed uznaniem za produkcyjne.

## 3. Domeny zasilania

### 3.1. CM5 / 5 V

CM5 pozostaje głównym sterownikiem procesu. Po normalnym POWER OFF ma przechodzić do pełnego shutdown/power-off, a ponowny start odbywa się przez fizyczny `PWR_BUT`.

### 3.2. HMI / PoE

HMI jest osobnym urządzeniem z Androidem, Ethernetem/PoE, NFC, paskiem RGB i sterowanym podświetleniem LCD.

HMI nie jest interlockiem bezpieczeństwa. Awaria lub brak HMI nie mogą blokować zatrzymania CM5 i urządzeń wykonawczych.

Docelowy stan HMI podczas OFF nie jest jeszcze całkowicie zamknięty, ale prawdziwy Android SLEEP jest technicznie potwierdzony i wybudza się pojedynczym tapnięciem.

### 3.3. Peryferia / 12 V – DFR0473

Do fizycznego załączania i odłączania domeny 12 V zastosowano:

```text
DFRobot DFR0473
Gravity: Digital 10A Relay Module
```

Stan fizyczny na 2026-08-25:

- moduł jest już zamontowany i podłączony do CM5,
- zasilanie strony sterującej: **3,3 V z CM5**,
- sterowanie: **GPIO22 / pin fizyczny 15**,
- masa: wspólna GND CM5,
- styki mocy: `COM + NO`, przełączany jest `+12 V`, nie masa,
- aktualnie zmierzony prąd całej domeny 12 V nie przekroczył około 1,5 A,
- wejście modułu ma sprzętowy pull-down, więc brak aktywnego sygnału pozostawia przekaźnik wyłączony.

Potwierdzone fizycznie na CM5:

```text
GPIO22 LOW  -> DFR0473 OFF
GPIO22 HIGH -> DFR0473 ON
GPIO22 LOW  -> DFR0473 OFF
```

Sterowanie jest fail-safe:

```text
GPIO LOW / Hi-Z -> relay OFF -> 12 V OFF
GPIO HIGH 3,3 V -> relay ON  -> 12 V ON
```

### 3.4. DAC DFR0971 nie należy do domeny 12 V

DFRobot DFR0971 / GP8403 jest zasilany bezpośrednio z szyny **3,3 V CM5**. DFR0473 nie odcina jego zasilania.

To rozróżnienie jest krytyczne:

```text
DFR0473 OFF
=> fizycznie odcina domenę +12 V

DFR0473 OFF
!= gwarancja 0 V na VOUT0/VOUT1 DFR0971
```

Dlatego status `12V commanded OFF` nie może być przedstawiany jako dowód bezpiecznego stanu analogowych wyjść 0–10 V. Sprzętowy fail-safe toru 0–10 V pozostaje osobnym zadaniem projektowym/walidacyjnym.

## 4. HMI sleep/wake – POC 2026-08-22

### 4.1. Android SLEEP / WAKEUP

Użyte komendy:

```bash
adb shell input keyevent 223   # KEYCODE_SLEEP
adb shell input keyevent 224   # KEYCODE_WAKEUP
```

Potwierdzone na fizycznym HMI:

- `KEYCODE_SLEEP` wygasza ekran i przełącza Android w stan sleep,
- przy połączeniu przez Wi-Fi HMI podczas sleep przestaje być osiągalne po Wi-Fi,
- po przewodowym Ethernet `eth0` pozostaje aktywny podczas sleep,
- po sleep HMI odpowiada na ping po Ethernet,
- TCP 5555 pozostaje dostępny,
- po zerwaniu starej sesji ADB można zestawić nową sesję ADB z uśpionym HMI po Ethernet,
- `KEYCODE_WAKEUP` wybudza ekran,
- pojedyncze tapnięcie palcem w uśpiony ekran również wybudza HMI.

Test Ethernet wykonano przy osobnym zasilaniu HMI, bez docelowego PoE. Po stałym montażu Ethernet/PoE należy wykonać test końcowy.

### 4.2. Sterowanie samym podświetleniem LCD

Potwierdzono:

```text
/sys/class/backlight/backlight/brightness
max_brightness = 255
brightness = 0   -> ekran całkowicie ciemny
brightness = 220 -> typowa jasność testowa
```

Przy `brightness=0` Android, kiosk, sieć i ADB pozostają aktywne.

### 4.3. NFC przy prawdziwym Android SLEEP

Potwierdzono, że karta NFC nie wybudza HMI z prawdziwego Android SLEEP. W tym stanie czytnik nie może być traktowany jako trigger startu systemu.

### 4.4. NFC przy `brightness=0`

Potwierdzono, że przy aktywnym Androidzie i `brightness=0` karta NFC jest normalnie wykrywana. HMI generuje dźwięk odczytu, a logi pokazują prawidłową aktywację i odczyt taga. Sam odczyt nie zapala ekranu ani RGB, ponieważ taka reakcja nie została zaprogramowana.

Po decyzji o fizycznym przycisku POWER NFC nie jest potrzebne do uruchamiania CM5. Może pozostać przeznaczone do autoryzacji/trybu serwisowego lub innych przyszłych funkcji.

## 5. Program – wymagany model działania

### 5.1. Zasada nadrzędna

Kolejność normalnego wyłączenia:

```text
próba SAFE
-> odcięcie 12 V
-> shutdown hosta
```

`ventilation-core` pozostaje źródłem prawdy dla sterowania procesem. GUI/HMI jest klientem.

Jednocześnie host-power jest ostatnią drogą wyjścia z awarii. Żaden błąd komunikacji ani brak potwierdzenia stanu wykonawczego nie może powodować nieskończonego oczekiwania lub całkowicie uniemożliwiać wyłączenia systemu.

### 5.2. POWER ON / boot

Stan początkowy po wyłączeniu:

```text
CM5 OFF
DFR0473 OFF
12 V OFF
```

Po naciśnięciu fizycznego przycisku:

1. CM5 startuje.
2. GPIO22 pozostaje początkowo LOW/Hi-Z.
3. `wvc-host-power` przejmuje linię GPIO jako OUTPUT/LOW.
4. `wvc-host-power` ustawia GPIO22 HIGH i załącza 12 V.
5. Program odczekuje zdefiniowany czas stabilizacji domeny 12 V.
6. Dopiero potem `wvc-host-power` zgłasza gotowość do systemd.
7. `ventilation-core` jest zależny od gotowego `wvc-host-power` i startuje po nim.
8. Core ocenia rzeczywistą gotowość DAC, magistral i peryferiów; awaria urządzenia nie jest maskowana.
9. System pozostaje bez aktywnego żądania pracy do czasu normalnego polecenia/operatora/automatyki.

### 5.3. Normalny POWER OFF

Docelowa i zaimplementowana na gałęzi Stage14 sekwencja:

1. Żądanie POWER OFF.
2. Zablokowanie równoległych nowych akcji power.
3. Próba `ventilation-core -> STOP` dla lokalnych wyjść EC.
4. Jeżeli STOP zostanie potwierdzony jako `mode=STOP`, `0.0/0.0 V`, `output_state_known=true`, zapisujemy potwierdzony stan SAFE.
5. Jeżeli STOP nie powiedzie się, DAC nie odpowiada, stan wyjścia jest nieznany albo nie można potwierdzić 0 V, zapisujemy **CRITICAL diagnostykę shutdown**, ale **nie blokujemy POWER OFF**.
6. Dla AERO i innych peryferiów posiadających funkcję bezpiecznego zatrzymania wykonujemy próbę SAFE z ograniczonym timeoutem.
7. Brak odpowiedzi, timeout, CRC/Modbus error, utrata magistrali lub wcześniejszy stan offline peryferium nie blokują kolejnych kroków.
8. `GPIO22 -> LOW` i DFR0473 odcina domenę 12 V.
9. Brak możliwości przełączenia DFR0473 na OFF pozostaje na tym etapie interlockiem normalnej ścieżki software POWER OFF, ponieważ świadomie pozostawilibyśmy całą domenę 12 V zasiloną.
10. Program może potwierdzić `12V commanded OFF`; bez dodatkowego sprzężenia zwrotnego nie nazywamy tego fizycznym pomiarem napięcia 12 V.
11. HMI może zostać uśpione jako krok niekrytyczny; brak komunikacji z HMI nie może zatrzymać shutdown.
12. `systemctl poweroff`.

Zasada jest jednoznaczna:

```text
DAC / AERO / SEN55 / ZIGBEE / INNE PERYFERIUM NIE ODPOWIADA
-> zapisz diagnostykę
-> nie czekaj bez końca
-> DFR0473 OFF
-> CM5 poweroff
```

Awaria DAC nie jest więc ignorowana: nadal powoduje FAULT/CRITICAL i blokuje normalne sterowanie wentylatorami. Nie ma jednak prawa odebrać operatorowi możliwości kontrolowanego wyłączenia całego systemu.

### 5.3.1. Realna walidacja awarii DAC – 2026-08-25

Podczas pierwszego harnessu DFR0473 produkcyjny core nie przyjął `STOP` i zwrócił:

```text
No response from GP8403 at 0x58: [Errno 121] Remote I/O error
```

Stan core w tym momencie:

```text
mode = FAULT
supply_voltage = 0.0
extract_voltage = 0.0
hardware_ready = false
output_state_known = false
DAC_COMMUNICATION_LOST = active
```

Równocześnie SEN55 i AERO były offline. Harness zatrzymał się przed zmianą konfiguracji usług i przed zmianą stanu DFR0473, co potwierdziło działanie jego pierwotnego zabezpieczenia.

Ten przypadek ujawnił błąd w pierwotnym założeniu architektury: wymaganie potwierdzonego lokalnego 0 V jako bezwzględnego warunku host shutdown mogłoby permanentnie uwięzić system w stanie FAULT. Politykę zmieniono tak, aby niepotwierdzony STOP był krytyczną diagnostyką, ale nie veto dla host shutdown.

Jednocześnie `setpoints=0/0` przy `output_state_known=false` oznacza wyłącznie **żądany/zapamiętany stan**, a nie pomiar fizycznego napięcia VOUT0/VOUT1.

### 5.4. RESTART

Restart używa tej samej filozofii co shutdown:

1. próba STOP / lokalne EC 0 V,
2. jeżeli brak potwierdzenia: CRITICAL diagnostyka, ale restart pozostaje dostępny,
3. próba AERO OFF i innych poleceń SAFE z ograniczonym timeoutem,
4. brak komunikacji z peryferiami nie blokuje restartu,
5. DFR0473 -> 12 V OFF,
6. `systemctl reboot`,
7. po ponownym boot: GPIO22 LOW -> kontrolowane 12 V ON -> stabilizacja -> start core.

Restart nie może pozostawiać domeny 12 V aktywnej bez kontroli podczas restartu systemu operacyjnego.

### 5.5. Nieoczekiwane zatrzymanie usługi / OS

Warstwa sterująca DFR0473 ma próbować wymusić LOW podczas zamykania procesu/usługi. Dodatkowo właściwości elektryczne modułu zapewniają OFF przy utracie aktywnego sygnału GPIO.

Przy zaniku zasilania CM5 przekaźnik ma opaść i odłączyć 12 V.

Nie jest to jednak zabezpieczenie analogowego wyjścia DFR0971, ponieważ DAC jest zasilany z 3,3 V CM5. Zachowanie VOUT0/VOUT1 przy awarii, halt i zaniku 3,3 V wymaga osobnej walidacji sprzętowej.

## 6. Architektura software Stage14

Nie tworzymy drugiej niezależnej logiki shutdown. `wvc-host-power` jest jedynym właścicielem GPIO DFR0473 i rozszerza istniejącą ścieżkę host-power.

Zaimplementowane wymagania:

- jeden właściciel GPIO DFR0473,
- GPIO konfigurowalne parametrem, produkcyjnie `GPIO22`,
- GPIO przejmowane najpierw jako OUTPUT/LOW,
- brak bezpośredniego dostępu GUI do GPIO,
- dependency injection/fake backend dla testów bez sprzętu,
- `Type=notify`: gotowość systemd dopiero po załączeniu i stabilizacji 12 V,
- `ventilation-core Requires/After wvc-host-power`,
- test kolejności `attempt local EC SAFE -> best-effort peripheral SAFE -> relay OFF -> host power action`,
- test, że awaria DAC STOP nie blokuje shutdown,
- test, że niepotwierdzone/niezerowe lokalne wyjście nie odbiera możliwości host shutdown,
- test, że offline/timeout AERO nie blokuje shutdown,
- test, że restart również odcina 12 V,
- test, że błąd przełączenia DFR0473 OFF blokuje normalny host power action,
- bezpieczny harness sprzętowy, który sam nie wykonuje `poweroff` ani `reboot`.

## 7. Obsługa fizycznego PWR_BUT przy działającym Linuxie

CM5 traktuje krótki `PWR_BUT` jako przycisk power także podczas pracy systemu. Nie możemy dopuścić, aby systemowy handler wykonał zwykłe `poweroff` z pominięciem naszej procedury host-power.

Przyjęta polityka:

- krótki przycisk podczas pracy Linuxa: ignorowany przez standardowy handler OS,
- fizyczny przycisk służy do normalnego POWER ON,
- normalny POWER OFF: wyłącznie aplikacja -> `host_power_agent`,
- długie >5 s: sprzętowy emergency hard-off, wyłącznie sytuacja awaryjna.

Na Stage14 dodano drop-in `systemd-logind` z polityką ignorowania krótkiego POWER. Zachowanie musi zostać jeszcze zwalidowane na fizycznym CM5 po kontrolowanym cyklu reboot/boot.

## 8. Zasady bezpieczeństwa

- `ventilation-core` pozostaje autorytatywnym źródłem decyzji dotyczących normalnego sterowania lokalnymi wyjściami.
- HMI jest interfejsem użytkownika, nie elementem bezpieczeństwa.
- Brak HMI nie może blokować shutdown.
- Brak komunikacji z DAC, AERO, SEN55, Zigbee lub innym peryferium nie może blokować shutdown/restart.
- Polecenia SAFE są wykonywane best-effort z ograniczonym timeoutem; brak potwierdzenia jest diagnostyką, nie veto dla POWER OFF.
- `DAC_COMMUNICATION_LOST` nadal jest krytycznym FAULT i blokuje normalne sterowanie, ale nie host poweroff.
- DFR0473 ma odłączyć domenę 12 V także wtedy, gdy urządzenia w tej domenie nie odpowiadają.
- Awaria komunikacji nie może prowadzić do nieskończonego oczekiwania podczas wyłączania.
- `DFR0473 OFF` nie dowodzi 0 V na DFR0971, ponieważ DAC jest na 3,3 V CM5.
- Fizyczny fail-safe toru 0–10 V pozostaje osobnym zadaniem hardware.
- GUI nie steruje bezpośrednio przekaźnikiem ani GPIO.

## 9. Następne kroki

1. Dokończyć nieinwazyjny harness Stage14 na fizycznym CM5 także w obecnym stanie `DAC_COMMUNICATION_LOST`.
2. Potwierdzić fizycznie checkpoint `DFR0473 OFF` oraz `DFR0473 ON` przy sterowaniu przez usługi systemd.
3. Po PASS wykonać pierwszy pełny kontrolowany POWER OFF z GUI: próba SAFE -> 12 V OFF -> CM5 poweroff.
4. Uruchomić CM5 fizycznym `PWR_BUT` i zwalidować: boot -> 12 V ON -> core.
5. Zweryfikować, że krótki `PWR_BUT` podczas RUNNING jest ignorowany.
6. Zweryfikować `POWER_OFF_ON_HALT=1` + `WAIT_FOR_POWER_BUTTON=1`, jeśli wymagamy ręcznego startu także po powrocie zasilania sieciowego.
7. Osobno zdiagnozować bieżącą awarię GP8403/DFR0971 na I²C.
8. Osobno zaprojektować/zwalidować sprzętowy fail-safe wyjść 0–10 V przy awarii DAC i zaniku CM5.
9. Po stałym podłączeniu HMI przez Ethernet/PoE wykonać końcowy test HMI SLEEP/WAKE.

## 10. Status

Aktualna filozofia POWER ON/OFF:

```text
POWER ON CM5: fizyczny PWR_BUT
krótki PWR_BUT podczas RUNNING: ignorowany
awaryjny hard-off: długie >5 s

12 V: DFR0473, GPIO22 / pin 15, sterowanie z 3.3 V CM5
DFR0473 LOW -> OFF
DFR0473 HIGH -> ON
fizyczny test LOW -> HIGH -> LOW: PASS

POWER OFF:
próba EC STOP
-> brak potwierdzenia? CRITICAL, ale kontynuuj
-> best-effort peripheral SAFE
-> DFR0473 OFF
-> CM5 poweroff

BRAK KOMUNIKACJI Z DAC/PERYFERIAMI: nie blokuje POWER OFF
BŁĄD DFR0473 OFF: na obecnym etapie blokuje normalną ścieżkę POWER OFF

RESTART:
ta sama sekwencja -> 12 V OFF -> reboot -> 12 V ON po boot

DFR0971:
zasilany z 3.3 V CM5, poza domeną DFR0473
DFR0473 OFF != potwierdzone 0 V na VOUT0/VOUT1
```

Do domknięcia pozostają przede wszystkim pełna walidacja fizycznego cyklu OFF/ON, konfiguracja PWR_BUT po bootloaderze, diagnostyka aktualnej awarii GP8403 oraz osobny hardware fail-safe toru 0–10 V.
