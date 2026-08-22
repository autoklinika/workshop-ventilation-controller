# Architektura POWER ON/OFF – notatka robocza

> Dokument żywy. Zapisujemy tu wszystkie ustalenia, testy i decyzje dotyczące uruchamiania, wyłączania i stanów zasilania całego systemu Workshop Ventilation Controller.

## 1. Cel

Zaprojektować spójny i bezpieczny mechanizm POWER ON/OFF obejmujący co najmniej:

- CM5,
- HMI iiyama ProLite TW1025LASC-B3PNR,
- urządzenia wykonawcze i peryferia,
- domenę zasilania 12 V,
- logikę NFC,
- kolejność bezpiecznego wyłączania i uruchamiania.

System nie musi pracować 24/7. Docelowo ma pracować głównie wtedy, gdy warsztat pracuje. Nie zakładamy utrzymywania całego CM5 i całej automatyki stale aktywnych tylko po to, aby czekały na polecenie uruchomienia.

## 2. Domeny zasilania, które trzeba traktować osobno

### 2.1. CM5 / 5 V

CM5 jest głównym sterownikiem systemu. Jego finalny stan OFF i sposób ponownego uruchamiania wymagają jeszcze decyzji architektonicznej.

### 2.2. HMI / PoE

HMI jest osobnym urządzeniem z Androidem, Ethernetem/PoE, NFC, paskiem RGB i sterowanym podświetleniem LCD.

HMI nie jest interlockiem bezpieczeństwa. Awaria lub brak HMI nie mogą blokować bezpiecznego zatrzymania CM5 i urządzeń wykonawczych.

### 2.3. Peryferia / 12 V

Planowane jest dodanie przekaźnika z cewką/sterowaniem 5 V, który będzie fizycznie załączał i odłączał zasilanie 12 V części układu/peryferiów.

Założenie:

- przed odcięciem 12 V urządzenia muszą zostać logicznie doprowadzone do stanu SAFE,
- dopiero po potwierdzeniu SAFE można wyłączyć domenę 12 V,
- przy starcie 12 V należy załączyć przed inicjalizacją urządzeń zależnych od tej domeny i odczekać wymagany czas stabilizacji.

Szczegóły elektryczne sterowania przekaźnikiem nie są jeszcze zamknięte. GPIO CM5 nie powinno bezpośrednio zasilać cewki przekaźnika; wymagany będzie odpowiedni driver lub gotowy moduł zgodny z poziomem 3,3 V.

## 3. HMI sleep/wake – POC wykonany 2026-08-22

### 3.1. Android SLEEP / WAKEUP

Użyte komendy:

```bash
adb shell input keyevent 223   # KEYCODE_SLEEP
adb shell input keyevent 224   # KEYCODE_WAKEUP
```

Potwierdzone zachowanie na fizycznym HMI:

- `KEYCODE_SLEEP` wygasza ekran i przełącza Android w stan sleep,
- przy połączeniu przez Wi-Fi HMI podczas sleep przestaje być osiągalne po Wi-Fi,
- po podłączeniu przewodowego Ethernetu `eth0` pozostaje aktywny po `KEYCODE_SLEEP`,
- po sleep HMI nadal odpowiada na ping po Ethernet,
- port TCP 5555 pozostaje dostępny,
- po celowym zerwaniu istniejącej sesji ADB można zestawić nową sesję ADB z uśpionym HMI po Ethernet,
- `adb get-state` po ponownym połączeniu zwraca `device`,
- `KEYCODE_WAKEUP` wysłany przez nową sesję ADB poprawnie wybudza ekran,
- pojedyncze tapnięcie palcem w uśpiony ekran również wybudza HMI.

Test Ethernet wykonano przy osobnym zasilaniu HMI, bez PoE. Po docelowym stałym podłączeniu Ethernet/PoE należy powtórzyć krótki test końcowy.

### 3.2. Sterowanie podświetleniem LCD

Potwierdzono bezpośrednie sterowanie:

```text
/sys/class/backlight/backlight/brightness
```

Parametry z testu:

- `max_brightness = 255`,
- typowa jasność robocza podczas testów: `220`,
- `brightness = 0` całkowicie wygasza podświetlenie,
- przy `brightness = 0` Android nadal działa,
- Wi-Fi i ADB pozostają aktywne,
- kiosk pozostaje uruchomiony,
- przywrócenie `brightness = 220` natychmiast zapala ekran.

Mechanizm `brightness=0/220` jest potwierdzonym mechanizmem programowego wygaszania bez usypiania Androida.

### 3.3. NFC przy prawdziwym Android SLEEP

Potwierdzono, że przy `KEYCODE_SLEEP` przyłożenie karty NFC nie wybudza HMI.

W stanie sleep:

- Android raportował `mScreenState=OFF_UNLOCKED`,
- `mAlwaysOnState=off`,
- kontroler NFC przechodził w stan oszczędzania/standby,
- sama karta nie powodowała wybudzenia ekranu.

Wniosek: w obecnej konfiguracji/firmware nie można zakładać NFC jako źródła wybudzenia HMI z prawdziwego Android SLEEP.

### 3.4. NFC przy `brightness = 0`

Potwierdzono, że gdy Android pozostaje aktywny, a wyłączone jest tylko podświetlenie:

- karta NFC jest normalnie wykrywana,
- HMI generuje dźwięk rozpoznania karty,
- logi NFC pokazują prawidłową aktywację i odczyt taga oraz późniejsze wykrycie jego usunięcia,
- sam odczyt karty nie zapala jeszcze ekranu ani paska RGB, ponieważ taka reakcja nie została zaprogramowana.

Wniosek: `brightness = 0` pozostawia NFC aktywne i może być użyte jako stan oczekiwania na kartę, jeśli taki wariant zostanie wybrany.

## 4. Wnioski z testów HMI

Mamy dwa technicznie różne stany „ciemnego HMI”:

### A. Prawdziwy Android SLEEP

Zalety:

- HMI faktycznie przechodzi w sleep,
- ekran wybudza się jednym tapnięciem,
- po przewodowym Ethernet HMI pozostaje zdalnie osiągalne i można je wybudzić przez ADB.

Ograniczenie:

- NFC nie wybudza HMI i nie może obecnie pełnić funkcji bezpośredniego triggera startu systemu z tego stanu.

### B. Android aktywny + `brightness = 0`

Zalety:

- ekran jest wizualnie wyłączony,
- Android, sieć, kiosk i NFC pozostają aktywne,
- karta NFC jest wykrywana.

Ograniczenie:

- HMI nie jest faktycznie uśpione i nadal pracuje w tle.

Finalny wybór między tymi stanami zależy od całej architektury POWER ON/OFF i wymaganego sposobu uruchamiania systemu.

## 5. NFC jako sterowanie systemem – koncepcja

Rozważany UX:

### Gdy system jest OFF

1. Użytkownik przykłada autoryzowaną kartę NFC.
2. System rozpoczyna procedurę uruchamiania.
3. HMI i CM5 przechodzą do stanu roboczego.
4. Ekran zostaje pokazany dopiero, gdy backend/core/WebGUI są gotowe.

### Gdy system jest ON

1. Użytkownik przykłada autoryzowaną kartę NFC.
2. HMI wysyła żądanie bezpiecznego wyłączenia.
3. CM5 wykonuje sekwencję SAFE.
4. Wyłączana jest domena 12 V.
5. HMI przechodzi do ustalonego stanu OFF/sleep/dark.
6. CM5 przechodzi do docelowego stanu OFF.

Mechanizm fizycznego uruchomienia CM5 z pełnego OFF nie został jeszcze ostatecznie wybrany.

## 6. Wstępna sekwencja wyłączania

Docelowa kolejność powinna zachować zasadę: najpierw bezpieczeństwo procesu, potem odcinanie zasilania i wygaszanie interfejsu.

1. Żądanie POWER OFF.
2. Zablokowanie nowych poleceń uruchamiających urządzenia.
3. CM5 doprowadza urządzenia wykonawcze do stanu SAFE.
4. EC → STOP / 0 V.
5. AERO → bezpieczny stan OFF / bieg 0 zgodnie z istniejącą procedurą.
6. Pozostałe urządzenia → odpowiednie stany bezpieczne.
7. Potwierdzenie zakończenia krytycznej procedury SAFE.
8. Fizyczne odłączenie domeny 12 V przez przekaźnik.
9. Doprowadzenie HMI do docelowego stanu OFF/sleep/dark.
10. CM5 przechodzi do docelowego stanu OFF.

Awaria HMI nie może zatrzymać krytycznej części shutdown.

## 7. Wstępna sekwencja uruchamiania

1. Trigger POWER ON.
2. Start/wybudzenie CM5 zgodnie z wybranym mechanizmem.
3. Start Linuxa i wymaganych usług.
4. Załączenie domeny 12 V.
5. Czas na stabilizację 12 V.
6. Inicjalizacja urządzeń/peryferiów.
7. Sprawdzenie stanu sprzętu i komunikacji.
8. Start/gotowość `ventilation-core` i WebGUI.
9. HMI zostaje doprowadzone do stanu aktywnego.
10. Sprawdzenie, czy kiosk `pl.autoklinika.workshopventilation.hmi` jest aktywny; w razie potrzeby przywrócenie go na pierwszy plan.
11. Ekran HMI jest prezentowany użytkownikowi dopiero po osiągnięciu gotowości systemu.

## 8. Zasady bezpieczeństwa architektury

- `ventilation-core` pozostaje autorytatywnym źródłem decyzji dotyczących bezpiecznego sterowania wyjściami.
- HMI jest interfejsem użytkownika, nie elementem bezpieczeństwa.
- Brak HMI nie może blokować zatrzymania wentylatorów ani bezpiecznego shutdown.
- Domeny zasilania należy odłączać dopiero po logicznym zatrzymaniu urządzeń.
- Restart, zanik sieci lub błąd pojedynczego peryferium nie mogą prowadzić do przypadkowego ponownego uruchomienia urządzeń wykonawczych.
- Normalny stan OFF ma ograniczać niepotrzebną wielogodzinną pracę elementów systemu poza godzinami pracy warsztatu.

## 9. Otwarte decyzje / następne testy

Do ustalenia:

- finalny stan CM5 po normalnym POWER OFF,
- mechanizm fizycznego POWER ON CM5,
- czy NFC będzie głównym sposobem START/STOP,
- czy HMI w stanie OFF ma używać prawdziwego `SLEEP`, czy `brightness=0`, czy kombinacji obu zależnie od scenariusza,
- finalna logika paska RGB podczas STARTING / ON / STOPPING / OFF,
- finalny sposób sterowania przekaźnikiem 12 V,
- które dokładnie urządzenia należą do odcinanej domeny 12 V,
- czas stabilizacji 12 V po załączeniu,
- reakcja na błąd przekaźnika lub brak 12 V,
- zachowanie po zaniku i powrocie zasilania sieciowego,
- test końcowy HMI na docelowym Ethernet/PoE,
- test zachowania Wi-Fi po wybudzeniu HMI dotykiem,
- sposób autoryzacji kart NFC i debounce/ochrona przed podwójnym odczytem.

## 10. Status

Architektura POWER ON/OFF nie jest jeszcze zamknięta. POC HMI potwierdził kilka możliwych mechanizmów, ale przed implementacją logiki produkcyjnej należy domknąć całe zachowanie CM5, HMI i domeny 12 V jako jednego systemu.
