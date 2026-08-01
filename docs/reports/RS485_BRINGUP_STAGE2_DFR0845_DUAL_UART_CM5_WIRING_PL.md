# Stage 2 — podłączenie dwóch DFR0845 do UART CM5

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Decyzja architektoniczna

W projekcie są dostępne dwa moduły DFRobot DFR0845. Stage 2 nie zakłada już konwertera USB–RS-485. Każdy DFR0845 jest izolowanym konwerterem UART ↔ RS-485 i otrzymuje własny sprzętowy UART CM5.

Dzięki temu możliwe są dwie niezależne magistrale RS-485:

- `RS485_BUS_1` — pierwszy DFR0845,
- `RS485_BUS_2` — drugi DFR0845.

Każdy port jest otwierany przez osobny proces `rs485-worker`. Nie ma współdzielenia deskryptora portu ani kolejek pomiędzy magistralami.

## Warunek elektryczny CM5IO

Napięcie GPIO na Compute Module 5 IO Board musi być ustawione na **3,3 V**, nie 1,8 V.

DFR0845 może być zasilany napięciem 3,3–5 V, ale po stronie CM5 używamy 3,3 V, aby poziomy UART były zgodne z GPIO.

## Złącze Gravity DFR0845

Dla przewodu widocznego na module:

| Kolor | Oznaczenie DFR0845 | Funkcja modułu |
|---|---|---|
| czerwony | `+` | zasilanie VCC |
| czarny | `-` | masa UART |
| niebieski | `R` | wejście RX modułu |
| zielony | `T` | wyjście TX modułu |

Sygnały UART należy skrzyżować funkcjonalnie:

- TX CM5 → `R` DFR0845,
- RX CM5 ← `T` DFR0845.

## DFR0845 nr 1 — UART0

Overlay: `uart0-pi5`

| DFR0845 | Kolor | CM5 GPIO | Pin fizyczny 40-pin |
|---|---|---|---:|
| `+` | czerwony | 3,3 V | 1 |
| `-` | czarny | GND | 6 |
| `R` | niebieski | GPIO14 / TXD0 | 8 |
| `T` | zielony | GPIO15 / RXD0 | 10 |

## DFR0845 nr 2 — UART2

Overlay: `uart2-pi5`

| DFR0845 | Kolor | CM5 GPIO | Pin fizyczny 40-pin |
|---|---|---|---:|
| `+` | czerwony | 3,3 V | 17 |
| `-` | czarny | GND | 14 |
| `R` | niebieski | GPIO4 / TXD2 | 7 |
| `T` | zielony | GPIO5 / RXD2 | 29 |

Piny zasilania można zastąpić innymi pinami 3,3 V i GND, ale powyższy układ ułatwia jednoznaczne prowadzenie przewodów.

## Konfiguracja Raspberry Pi OS

W `/boot/firmware/config.txt` należy dodać:

```ini
enable_uart=1
dtoverlay=uart0-pi5
dtoverlay=uart2-pi5
```

Nie używamy parametrów `rs485` ani linii RTS/DE. DFR0845 udostępnia zwykłe TX/RX po stronie UART i sam realizuje konwersję na dwuprzewodową magistralę RS-485.

Po zmianie wymagany jest restart:

```bash
sudo reboot
```

## Identyfikacja urządzeń Linux

Nazwy typu `/dev/ttyAMA0` i `/dev/ttyAMA2` są prawdopodobne, ale nie należy zakładać ich bez sprawdzenia. Po restarcie wykonać:

```bash
ls -l /dev/serial* /dev/ttyAMA* /dev/ttyS* 2>/dev/null
pinctrl get 4 5 14 15

cd ~/workshop-ventilation-controller
PYTHONPATH=src python3 -m ventilation_core.rs485ctl ports
```

Narzędzie wykrywa teraz:

- `/dev/serial0`, `/dev/serial1`,
- `/dev/ttyAMA*`,
- `/dev/ttyS*`,
- porty USB jako opcję pomocniczą.

## Sprawdzenie dwóch portów bez transmisji

Po ustaleniu rzeczywistych nazw portów można otworzyć oba jednocześnie bez wysyłania ramek:

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl check-ports \
  --port /dev/ttyAMA0 \
  --port /dev/ttyAMA2
```

Polecenie:

- uruchamia osobny worker dla każdego UART-u,
- otwiera oba porty,
- sprawdza procesy lokalnym `ping`,
- nie zapisuje żadnych bajtów na UART,
- zwraca `transmitted: false`.

Rzeczywiste ścieżki należy podstawić zgodnie z wynikiem `rs485ctl ports`.

## Zaciski RS-485

Na początku zaciski `A`, `B`, `RS485 GND`, `12V` oraz `12V-IN` pozostają niepodłączone.

Przełącznik terminacji `120Ω` na obu DFR0845 ustawiamy początkowo na `OFF`. Terminację włączymy dopiero po zaprojektowaniu rzeczywistego odcinka magistrali i ustaleniu, który moduł znajduje się na jej końcu.

## Kolejność uruchomienia

1. Wyłączyć CM5 przed podłączaniem przewodów Gravity.
2. Podłączyć tylko DFR0845 nr 1.
3. Włączyć CM5 i potwierdzić UART nr 1.
4. Wyłączyć CM5.
5. Podłączyć DFR0845 nr 2.
6. Potwierdzić oba UART-y poleceniem `check-ports`.
7. Dopiero później podłączyć zaciski `A/B` pierwszego urządzenia RS-485.

Testy wykonujemy pojedynczo, mimo że kod od początku obsługuje dwie niezależne magistrale.
