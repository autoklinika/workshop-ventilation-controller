# Lista elementów sprzętowych

## Status konfiguracji

Projekt jest pojedynczym lokalnym wdrożeniem. Priorytetem są gotowe moduły i proste, serwisowalne połączenia. Nie optymalizujemy obecnie sprzętu pod produkcję seryjną ani własną płytkę główną.

## Elementy potwierdzone

| Obszar | Element | Status / uwagi |
|---|---|---|
| Sterownik główny | Raspberry Pi Compute Module 5 Wireless, 4 GB RAM, 32 GB eMMC | Sprzęt uruchomiony i zweryfikowany |
| Płyta bazowa | Oficjalna Raspberry Pi Compute Module 5 IO Board | Platforma prototypowa i docelowa dla pierwszego wdrożenia |
| System | Raspberry Pi OS Lite 64-bit, Debian 13 `trixie`, ARM64 | Zainstalowany bezpośrednio na eMMC |
| Sieć | Ethernet + Wi-Fi | Ethernet docelowo podstawowy, Wi-Fi serwisowe lub zapasowe |
| Magazyn danych | 32 GB eMMC | System, konfiguracja i krytyczne dane; NVMe opcjonalnie później |
| Sterowanie analogowe | DFRobot Gravity DFR0971, 2-kanałowy I²C DAC 0–10 V | Pierwsze uruchamiane peryferium |
| Wyciąg strefy 1 | Harmann ML EC.A 125/300 lub posiadany docelowy odpowiednik | Wejście 0–10 V / PWM, Tacho 3 impulsy/obrót |
| Interfejsy przewodowe modułów | RJ45 Keystone w dedykowanych uchwytach | Złącza serwisowalne; nie oznaczają transmisji Ethernet |

## Aktualnie przyjęty kierunek

| Obszar | Element | Status / uwagi |
|---|---|---|
| Węzły pomiarowe | SEN55 + KAmod ESP32 POW RS485 | Gotowy moduł zamiast projektowania własnej płytki STM32; firmware i mapa Modbus do przygotowania |
| Komunikacja | Izolowany interfejs RS-485 dla Raspberry Pi / CM5 | Dokładny model i topologia magistrali zostaną potwierdzone podczas testów |
| Rekuperator | Prodmax PRO MINI 300 H/V CLASSIC, COMPIT AERO 4A2, NANO COLOR 2 | Preferowana integracja przez oficjalny Modbus RTU panelu |
| Nawiew strefy 1 | Wentylator EC 0–10 V | Dokładny model i charakterystyka do potwierdzenia |
| Diagnostyka obrotów | Wejścia Tacho obu wentylatorów | Wymagają ustalenia poziomów elektrycznych i układu zabezpieczającego |
| Zasilanie docelowe | Zasilacz 5 V na szynę DIN oraz pozostałe zasilacze wykonawcze | Dobór po pomiarach poboru prądu kompletnego zestawu |

## Kolejność uruchamiania sprzętu

1. DFR0971 na magistrali I²C bez podłączonych wentylatorów.
2. Pomiar wyjść 0–10 V multimetrem w kilku punktach zadanych.
3. Test stanu wyjść po restarcie CM5, restarcie procesu i utracie komunikacji I²C.
4. Podłączenie jednego wentylatora EC i wyznaczenie minimalnego napięcia startu.
5. Podłączenie drugiego wentylatora oraz pomiar bilansu nawiew–wyciąg.
6. Walidacja wejść Tacho przez układ dopasowujący i zabezpieczający.
7. Uruchomienie interfejsu RS-485 i pojedynczego węzła SEN55.
8. Test wielu urządzeń na wspólnej magistrali RS-485.
9. Integracja rekuperatora Compit — najpierw wyłącznie odczyt.

## Elementy instalacyjne i zabezpieczenia

- terminatory 120 Ω na fizycznych końcach magistrali RS-485,
- rezystory bias/failsafe, jeżeli nie zapewnia ich interfejs,
- ekranowana skrętka dla RS-485,
- jednoznaczne oznaczenie RJ45 jako złączy nie-Ethernetowych,
- osobne prowadzenie przewodów sygnałowych i przewodów mocy wentylatorów,
- zabezpieczenie przepięciowe wejść RS-485,
- bezpieczniki dla poszczególnych gałęzi zasilania,
- układ ochronny i dopasowujący dla Tacho,
- bezpieczny stan wyjść 0–10 V po uruchomieniu i awarii oprogramowania,
- chłodzenie CM5 odpowiednie do zamkniętej rozdzielni.

## Elementy niewymagane na obecnym etapie

- dodatkowy dysk NVMe,
- własna płyta nośna CM5,
- własna płytka węzła czujnika,
- detektor LEL,
- rozbudowane analizatory gazów,
- bezpośrednie prowadzenie I²C z SEN55 do CM5.

## Informacje wymagające potwierdzenia

1. Dokładny model wentylatora nawiewnego.
2. Rzeczywiste napięcia, prądy i zachowanie wejść 0–10 V obu wentylatorów.
3. Charakterystyka elektryczna obu wyjść Tacho.
4. Docelowy zasilacz 5 V DIN i budżet mocy dla CM5 oraz peryferiów.
5. Dokładny model izolowanego interfejsu RS-485.
6. Pinout przewodów prowadzonych przez RJ45 Keystone.
7. Zachowanie DFR0971 po zaniku zasilania i resecie magistrali I²C.

Szczegóły platformy CM5 znajdują się w [bazowej konfiguracji sprzętowej](hardware/CM5_HARDWARE_BASELINE_PL.md).
