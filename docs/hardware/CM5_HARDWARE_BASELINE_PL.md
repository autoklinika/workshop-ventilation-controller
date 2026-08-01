# Bazowa platforma sprzętowa CM5

## Status

Ten dokument opisuje rzeczywistą platformę uruchomieniową sterownika wentylacji. Jest punktem odniesienia dla konfiguracji systemu, testów peryferiów i późniejszego wdrożenia `ventilation-core`.

## Sterownik główny

- moduł: Raspberry Pi Compute Module 5 Wireless,
- pamięć RAM: 4 GB,
- pamięć wbudowana: 32 GB eMMC,
- płyta bazowa: oficjalna Raspberry Pi Compute Module 5 IO Board,
- łączność: Ethernet, Wi-Fi i Bluetooth,
- system podstawowy: Raspberry Pi OS Lite 64-bit / Debian 13 `trixie`,
- architektura: ARM64,
- hostname: `wentylacja`,
- system plików root: eMMC `/dev/mmcblk0p2`,
- partycja startowa: eMMC `/dev/mmcblk0p1`,
- dodatkowy magazyn danych: opcjonalny NVMe w przyszłości.

## Zweryfikowany stan uruchomieniowy

Podczas pierwszej walidacji potwierdzono:

- poprawny start systemu bezpośrednio z eMMC,
- około 23 GB wolnej przestrzeni po instalacji i aktualizacji systemu,
- prawidłową pracę Wi-Fi,
- temperaturę spoczynkową około 36°C,
- brak zdarzeń undervoltage i throttlingu (`throttled=0x0`).

Dynamiczny adres IP nie jest częścią konfiguracji projektu. Docelowo Ethernet będzie podstawowym łączem sterownika, a Wi-Fi pozostanie kanałem serwisowym lub zapasowym.

## Zasady wykorzystania pamięci

- system operacyjny, konfiguracja i `ventilation-core` pozostają na eMMC,
- krytyczna automatyka nie może zależeć od obecności dodatkowego dysku,
- opcjonalny NVMe może później przechowywać długą historię pomiarów, archiwa i kopie danych,
- odłączenie lub awaria NVMe nie może zatrzymać sterowania wentylacją.

## Pierwsze uruchamiane peryferium

Pierwszym elementem wykonawczym uruchamianym z CM5 będzie dwukanałowy DAC 0–10 V DFRobot Gravity DFR0971, komunikujący się przez I²C.

Kolejność walidacji:

1. wykrycie magistrali I²C i adresu DAC,
2. odczyt lub potwierdzenie konfiguracji urządzenia,
3. generowanie napięć testowych bez podłączonych wentylatorów,
4. pomiar multimetrem punktów 0 V, 2 V, 5 V, 8 V i 10 V,
5. sprawdzenie zachowania po restarcie i zaniku komunikacji,
6. dopiero potem podłączenie wejść sterujących wentylatorów EC,
7. pomiar minimalnego napięcia startu oraz zależności napięcie–prędkość.

## Zasada bezpieczeństwa wyjść 0–10 V

Do chwili zakończenia walidacji DAC nie podłączamy wentylatorów. Pierwsze testy wykonujemy multimetrem i — jeżeli będzie potrzebne — bezpiecznym obciążeniem testowym. Oprogramowanie uruchomieniowe musi rozpoczynać pracę od jawnie zdefiniowanego stanu bezpiecznego, a nie od przypadkowej wartości zachowanej przez urządzenie.

## Kolejne interfejsy

Po walidacji DAC kolejno uruchomimy:

1. dwa wentylatory EC 0–10 V,
2. wejścia Tacho po potwierdzeniu ich charakterystyki elektrycznej,
3. interfejs USB–RS-485,
4. moduły pomiarowe SEN55,
5. integrację Modbus RTU rekuperatora Compit.
