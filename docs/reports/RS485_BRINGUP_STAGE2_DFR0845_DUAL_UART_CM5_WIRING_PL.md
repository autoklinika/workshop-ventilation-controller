# Stage 2 — podłączenie dwóch DFR0845 do UART CM5

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Decyzja architektoniczna

W projekcie są dostępne dwa moduły DFRobot DFR0845. Stage 2 nie zakłada już konwertera USB–RS-485. Każdy DFR0845 jest izolowanym konwerterem UART ↔ RS-485 i otrzymuje własny sprzętowy UART CM5.

Dzięki temu możliwe są dwie niezależne magistrale RS-485:

- `RS485_BUS_1` — pierwszy DFR0845,
- `RS485_BUS_2` — drugi DFR0845.

Każdy port jest otwierany przez osobny proces `rs485-worker`. Nie ma współdzielenia deskryptora portu ani kolejek pomiędzy magistralami.

## Zasilanie DFR0845 — zweryfikowana decyzja

DFR0845 zasilamy z szyny **5 V**, nie z 3,3 V CM5IO.

Podczas próby zasilania DFR0845 z pinu 3,3 V użytkownik potwierdził, że obciążenie uniemożliwiało prawidłowy start CM5. Po przełączeniu zasilania modułu na 5 V CM5 uruchomił się poprawnie.

Jest to zgodne z charakterem modułu: DFR0845 zawiera izolowany transceiver i izolowaną przetwornicę. Producent dopuszcza zasilanie modułu 3,3–5 V oraz deklaruje zgodność strony UART z logiką 3,3 V i 5 V. W naszym wdrożeniu 5 V jest więc obowiązującym źródłem zasilania modułów, natomiast same linie UART CM5 pozostają liniami logicznymi 3,3 V.

Nie należy ponownie zasilać DFR0845 z pinu 3,3 V CM5IO.

## Warunek elektryczny CM5IO

Napięcie logiki GPIO na Compute Module 5 IO Board musi być ustawione na **3,3 V**, nie 1,8 V.

To ustawienie dotyczy poziomów sygnałów UART, a nie zasilania DFR0845. DFR0845 otrzymuje zasilanie 5 V z dedykowanych pinów zasilających 40-pinowego złącza.

## Złącze Gravity DFR0845 — poprawne oznaczenia

Dla przewodu widocznego na module:

| Kolor | Oznaczenie DFR0845 | Funkcja modułu |
|---|---|---|
| czerwony | `+` | zasilanie VCC |
| czarny | `-` | masa UART |
| niebieski | `T` | wyjście TX modułu |
| zielony | `R` | wejście RX modułu |

Sygnały UART należy skrzyżować funkcjonalnie:

- TX CM5 → `R` DFR0845 — przewód zielony,
- RX CM5 ← `T` DFR0845 — przewód niebieski.

## DFR0845 nr 1 — UART0

Overlay: `uart0-pi5`

| DFR0845 | Kolor | CM5 GPIO / zasilanie | Pin fizyczny 40-pin |
|---|---|---|---:|
| `+` | czerwony | 5 V | 2 |
| `-` | czarny | GND | 6 |
| `R` | zielony | GPIO14 / TXD0 | 8 |
| `T` | niebieski | GPIO15 / RXD0 | 10 |

## DFR0845 nr 2 — UART2

Overlay: `uart2-pi5`

| DFR0845 | Kolor | CM5 GPIO / zasilanie | Pin fizyczny 40-pin |
|---|---|---|---:|
| `+` | czerwony | 5 V | 4 |
| `-` | czarny | GND | 14 |
| `R` | zielony | GPIO4 / TXD2 | 7 |
| `T` | niebieski | GPIO5 / RXD2 | 29 |

Piny GND można zastąpić innymi pinami masy. Piny 2 i 4 są wspólną szyną 5 V; rozdzielenie ich pomiędzy dwa moduły ułatwia jednoznaczne prowadzenie przewodów.

## Konfiguracja Raspberry Pi OS

W `/boot/firmware/config.txt` należy dodać:

```ini
enable_uart=1
dtoverlay=uart0-pi5
dtoverlay=uart2-pi5
```

Nie używamy parametrów `rs485` ani linii RTS/DE. DFR0845 udostępnia zwykłe TX/RX po stronie UART i sam realizuje automatyczną konwersję na dwuprzewodową magistralę RS-485.

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

Narzędzie wykrywa:

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

1. Wyłączyć CM5 przed podłączaniem przewodów Gravity — DFR0845 nie obsługuje hot-plug.
2. Podłączyć tylko DFR0845 nr 1, zasilany z 5 V.
3. Włączyć CM5 i potwierdzić UART nr 1.
4. Wyłączyć CM5.
5. Podłączyć DFR0845 nr 2, również zasilany z 5 V.
6. Potwierdzić oba UART-y poleceniem `check-ports`.
7. Dopiero później podłączyć zaciski `A/B` pierwszego urządzenia RS-485.

Testy wykonujemy pojedynczo, mimo że kod od początku obsługuje dwie niezależne magistrale.
