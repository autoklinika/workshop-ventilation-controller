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
5. Program załącza domenę 12 V.
6. Po stabilizacji 12 V uruchamiane/oceniane są peryferia i `ventilation-core`.
7. HMI zostaje doprowadzone do stanu roboczego po osiągnięciu gotowości systemu.

### 2.2. POWER OFF CM5

Normalne wyłączenie ma być zawsze kontrolowane programowo przez istniejący mechanizm host-power i procedurę SAFE.

Fizyczny przycisk służy do uruchamiania CM5. Krótkie naciśnięcie przy działającym Linuxie ma być ignorowane i nie może tworzyć alternatywnej drogi shutdown omijającej `host_power_agent` i procedurę SAFE.

Długie przytrzymanie sprzętowego `PWR_BUT` pozostaje awaryjnym hard-off i nie jest normalną procedurą użytkową.

### 2.3. Zachowanie po zaniku i powrocie zasilania sieciowego

Jeżeli finalnie wymagamy, aby po powrocie zasilania CM5 nie uruchamiał się sam, lecz czekał na fizyczny przycisk, bootloader CM5 należy skonfigurować z:

```text
POWER_OFF_ON_HALT=1
WAIT_FOR_POWER_BUTTON=1
```

To ustawienie należy zwalidować na fizycznym CM5 przed uznaniem za produkcyjne.

## 3. Domeny zasilania

### 3.1. CM5 / 5 V

CM5 pozostaje głównym sterownikiem bezpieczeństwa procesu. Po normalnym POWER OFF ma przechodzić do pełnego shutdown/power-off, a ponowny start odbywa się przez fizyczny `PWR_BUT`.

### 3.2. HMI / PoE

HMI jest osobnym urządzeniem z Androidem, Ethernetem/PoE, NFC, paskiem RGB i sterowanym podświetleniem LCD.

HMI nie jest interlockiem bezpieczeństwa. Awaria lub brak HMI nie mogą blokować bezpiecznego zatrzymania CM5 i urządzeń wykonawczych.

Docelowy stan HMI podczas OFF nie jest jeszcze całkowicie zamknięty, ale prawdziwy Android SLEEP jest technicznie potwierdzony i wybudza się pojedynczym tapnięciem.

### 3.3. Peryferia / 12 V – decyzja sprzętowa

Do fizycznego załączania i odłączania domeny 12 V wybrano i zamówiono:

```text
DFRobot DFR0473
Gravity: Digital 10A Relay Module
```

Założenia elektryczne:

- moduł zasilany z 5 V,
- wejście sterujące zgodne z sygnałem 3,3 V z GPIO CM5,
- przekaźnik mechaniczny 10 A,
- aktualnie zmierzony prąd całej domeny 12 V nie przekroczył około 1,5 A,
- używamy styków `COM` + `NO`, aby brak sterowania oznaczał 12 V OFF,
- wejście modułu ma sprzętowy pull-down, więc brak aktywnego sygnału sterującego ma pozostawiać przekaźnik wyłączony.

Sterowanie ma być fail-safe:

```text
GPIO LOW / Hi-Z -> relay OFF -> 12 V OFF
GPIO HIGH 3,3 V -> relay ON  -> 12 V ON
```

Dokładny GPIO CM5 należy wpisać po finalnym przypisaniu i walidacji fizycznej. Aktualny pinout wykorzystuje GPIO2/3, GPIO12/13, GPIO14/15, GPIO17 i GPIO27; nowa linia przekaźnika nie może z nimi kolidować.

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

Najpierw bezpieczeństwo procesu, potem odcięcie zasilania, a na końcu shutdown hosta.

`ventilation-core` pozostaje źródłem prawdy dla bezpiecznych stanów wykonawczych. GUI/HMI jest klientem.

Brak komunikacji z peryferium nie może uniemożliwić wyłączenia systemu. Shutdown musi mieć skończony czas wykonania i zawsze prowadzić w stronę stanu bezpiecznego.

### 5.2. POWER ON / boot

Stan początkowy po wyłączeniu:

```text
CM5 OFF
DFR0473 OFF
12 V OFF
```

Po naciśnięciu fizycznego przycisku:

1. CM5 startuje.
2. GPIO sterujące DFR0473 pozostaje początkowo LOW/Hi-Z.
3. Uprzywilejowana warstwa power-management przejmuje linię GPIO w bezpiecznym stanie LOW.
4. Warstwa power-management ustawia GPIO HIGH i załącza 12 V.
5. Program odczekuje zdefiniowany czas stabilizacji domeny 12 V.
6. Dopiero potem urządzenia zależne od 12 V są traktowane jako gotowe do inicjalizacji/komunikacji.
7. `ventilation-core` startuje lub przechodzi do pełnej oceny `hardware_ready`.
8. System pozostaje w bezpiecznym STOP do czasu normalnego polecenia pracy/automatyki.
9. Po gotowości systemu HMI może zostać wybudzone/pokazane użytkownikowi.

Wymagane jest uporządkowanie systemd tak, aby warstwa 12 V była gotowa przed procesami wymagającymi zasilonych peryferiów.

### 5.3. Normalny POWER OFF

Obecny `host_power_agent` już wykonuje część wymaganej sekwencji:

- żądanie `STOP` do core,
- potwierdzenie trybu STOP,
- potwierdzenie `supply_voltage=0.0`,
- potwierdzenie `extract_voltage=0.0`,
- potwierdzenie `output_state_known=true`,
- dla dostępnego AERO: airing OFF i speed 0 z fizycznym potwierdzeniem,
- dla AERO już zgłoszonego jako offline/unusable: brak blokowania host shutdown po pozytywnym STOP/0 V lokalnych wyjść.

Ta logika wymaga zmiany: błąd komunikacji z peryferium w trakcie shutdown nie może zatrzymać całego POWER OFF.

Docelowa sekwencja:

1. Żądanie POWER OFF.
2. Zablokowanie równoległych nowych akcji power.
3. `ventilation-core` -> STOP dla lokalnych wyjść EC.
4. Wymuszenie lokalnych wyjść EC na 0 V oraz potwierdzenie ich stanu, o ile lokalna warstwa wykonawcza działa.
5. Dla peryferiów komunikacyjnych (AERO, SEN55, Zigbee i przyszłe urządzenia) wykonać próbę logicznego przejścia do SAFE tylko wtedy, gdy dane urządzenie ma taką funkcję.
6. Każda próba komunikacji podczas shutdown ma mieć ograniczony timeout i ograniczoną liczbę prób.
7. Brak odpowiedzi, timeout, CRC/Modbus error, utrata magistrali lub wcześniejszy stan offline peryferium są rejestrowane jako diagnostyka shutdown, ale NIE blokują kolejnych kroków.
8. GPIO DFR0473 -> LOW.
9. Domena 12 V zostaje fizycznie odłączona niezależnie od tego, czy peryferia odpowiedziały na polecenia SAFE.
10. Program potwierdza co najmniej stan zadany/stan GPIO `12V commanded OFF`. Bez dodatkowego sprzężenia zwrotnego nie wolno nazywać tego pomiarem fizycznego napięcia 12 V.
11. HMI może zostać uśpione jako krok niekrytyczny; brak komunikacji z HMI nie może zatrzymać shutdown.
12. `systemctl poweroff`.

Zasada dla peryferiów jest więc jednoznaczna:

```text
PERIPHERAL ONLINE
-> spróbuj SAFE
-> 12 V OFF
-> CM5 poweroff

PERIPHERAL OFFLINE / TIMEOUT / BRAK KOMUNIKACJI
-> zapisz diagnostykę
-> NIE CZEKAJ bez końca
-> 12 V OFF
-> CM5 poweroff
```

Nie należy mylić braku komunikacji z peryferiami z awarią lokalnego toru 0–10 V EC. Dla lokalnego DAC/EC zachowujemy wymóg bezpiecznego 0 V do czasu osobnej walidacji sprzętowej zachowania DAC podczas zaniku/poweroff CM5.

### 5.4. RESTART

Restart ma używać tej samej filozofii bezpieczeństwa co shutdown:

1. STOP / lokalne EC 0 V.
2. Próba AERO OFF i innych poleceń SAFE z ograniczonym timeoutem.
3. Brak komunikacji z peryferiami nie blokuje restartu.
4. DFR0473 -> 12 V OFF.
5. `systemctl reboot`.
6. Po ponownym boot: bezpieczny start linii GPIO, 12 V ON, stabilizacja, inicjalizacja core/peryferiów.

Restart nie może pozostawiać domeny 12 V aktywnej bez kontroli podczas restartu systemu operacyjnego.

### 5.5. Nieoczekiwane zatrzymanie usługi / OS

Warstwa sterująca DFR0473 musi próbować wymusić LOW podczas zamykania procesu/usługi. Dodatkowo właściwości elektryczne modułu mają zapewniać OFF przy utracie sygnału GPIO.

Przy zaniku zasilania CM5 przekaźnik ma opaść i odłączyć 12 V.

## 6. Zalecana architektura software

Nie tworzymy drugiej niezależnej logiki shutdown. Rozszerzamy istniejącą uprzywilejowaną warstwę `wvc-host-power` o kontrolę domeny 12 V albo dokładamy bardzo wąski lokalny power-domain agent wywoływany przez `host_power_agent`.

Wymagania implementacyjne:

- jeden właściciel GPIO DFR0473,
- brak bezpośredniego dostępu GUI do GPIO,
- konfiguracja linii GPIO przez parametr/konfigurację, nie hard-code w logice domenowej,
- dependency injection/fake backend dla testów bez sprzętu,
- test kolejności `local EC SAFE -> best-effort peripheral SAFE -> relay OFF -> host power action`,
- test, że offline/timeout AERO nie blokuje shutdown,
- test, że offline/timeout SEN55 nie blokuje shutdown,
- test, że brak HMI nie blokuje shutdown,
- test, że komunikacja z peryferium nigdy nie powoduje nieskończonego oczekiwania podczas shutdown,
- test, że restart również odcina 12 V mimo braku komunikacji z peryferiami,
- test zachowania przy awarii lokalnego toru 0–10 V zgodnie z osobno zatwierdzoną polityką,
- test fail-safe przy zamknięciu procesu,
- osobny test fizyczny DFR0473 na CM5 przed aktywacją produkcyjną.

## 7. Obsługa fizycznego PWR_BUT przy działającym Linuxie

CM5 traktuje krótki `PWR_BUT` jako przycisk power także podczas pracy systemu. Nie możemy dopuścić, aby systemowy handler wykonał zwykłe `poweroff` z pominięciem naszej procedury SAFE.

Przyjęta polityka:

- krótki przycisk podczas pracy Linuxa: ignorowany przez standardowy handler OS,
- fizyczny przycisk służy do normalnego POWER ON,
- normalny POWER OFF: wyłącznie aplikacja -> `host_power_agent`,
- długie >5 s: sprzętowy emergency hard-off, wyłącznie sytuacja awaryjna.

Przed wdrożeniem trzeba zwalidować dokładne zachowanie systemd-logind i wejścia `KEY_POWER` na docelowym obrazie CM5.

## 8. Zasady bezpieczeństwa

- `ventilation-core` pozostaje autorytatywnym źródłem decyzji dotyczących sterowania lokalnymi wyjściami.
- HMI jest interfejsem użytkownika, nie elementem bezpieczeństwa.
- Brak HMI nie może blokować shutdown.
- Brak komunikacji z AERO, SEN55, Zigbee lub innym peryferium nie może blokować shutdown/restart.
- Polecenia SAFE do peryferiów są wykonywane best-effort z ograniczonym timeoutem; ich brak potwierdzenia jest diagnostyką, nie interlockiem POWER OFF.
- DFR0473 ma odłączyć domenę 12 V także wtedy, gdy urządzenia w tej domenie nie odpowiadają.
- Awaria komunikacji nie może prowadzić do nieskończonego oczekiwania podczas wyłączania.
- Lokalny tor sterowania EC 0–10 V pozostaje osobnym krytycznym zagadnieniem; jego zachowanie przy awarii/poweroff wymaga zachowania obecnego zabezpieczenia do czasu fizycznej walidacji.
- Przy awaryjnym/niekontrolowanym zaniku CM5 priorytetem jest fail-safe elektryczny DFR0473 -> OFF.
- GUI nie steruje bezpośrednio przekaźnikiem ani GPIO.

## 9. Następne kroki

1. Wybrać wolny GPIO dla DFR0473 i dopisać go do `docs/PINOUT.md`.
2. Przygotować software GPIO/power-domain z backendem testowym.
3. Rozszerzyć `host_power_agent` o `local EC SAFE -> best-effort peripheral SAFE -> 12 V OFF -> shutdown/restart`.
4. Zmienić obecną logikę AERO tak, aby timeout/błąd komunikacji podczas shutdown nie blokował host power action.
5. Uporządkować kolejność usług systemd dla boot i shutdown.
6. Dodać testy jednostkowe/regresyjne bez sprzętu.
7. Po dostawie DFR0473 wykonać test fizyczny LOW/HIGH, boot, shutdown i restart.
8. Dopiero po PASS aktywować przekaźnik w konfiguracji produkcyjnej.
9. Skonfigurować i zwalidować ignorowanie krótkiego PWR_BUT podczas pracy Linuxa.
10. Zweryfikować `POWER_OFF_ON_HALT=1` + `WAIT_FOR_POWER_BUTTON=1` na docelowym CM5, jeśli wymagamy ręcznego startu także po powrocie zasilania sieciowego.
11. Po stałym podłączeniu HMI przez Ethernet/PoE wykonać końcowy test HMI SLEEP/WAKE.

## 10. Status

Aktualna filozofia POWER ON/OFF jest w dużej części zamknięta:

```text
POWER ON CM5: fizyczny PWR_BUT
krótki PWR_BUT podczas RUNNING: ignorowany
awaryjny hard-off: długie >5 s
12 V: DFR0473 sterowany GPIO CM5
POWER OFF: aplikacja -> local EC SAFE -> best-effort peripheral SAFE -> 12 V OFF -> CM5 poweroff
BRAK KOMUNIKACJI Z PERYFERIAMI: nie blokuje POWER OFF
RESTART: local EC SAFE -> best-effort peripheral SAFE -> 12 V OFF -> reboot -> 12 V ON po boot
HMI: niezależne od safety; finalna automatyzacja sleep/wake po docelowym Ethernet/PoE
```

Do domknięcia pozostają głównie implementacja software, wybór GPIO, konfiguracja zachowania przycisku podczas pracy oraz testy na fizycznym DFR0473 i docelowym PoE HMI.
