# Stage 2 — plan pierwszej walidacji RS-485 na CM5 z DFR0845

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Zasada bezpieczeństwa

Test RS-485 jest niezależny od sterowania DAC. Przed rozpoczęciem należy pozostawić `ventilation-core` w stanie `STOP / 0 V / 0 V`. Nie zmieniamy przewodów DFR0971 ani sterowania fanów.

DFR0845 podłączamy wyłącznie przy wyłączonym CM5. Zaciski `A`, `B`, `RS485 GND`, `12V` i `12V-IN` pozostają na tym etapie wolne.

## Test A — aktualizacja i testy

```bash
cd ~/workshop-ventilation-controller

git fetch origin
git switch agent/rs485-bringup-stage2
git pull --ff-only origin agent/rs485-bringup-stage2

sudo apt update
sudo apt install -y python3-serial

PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Oczekiwany wynik: wszystkie testy zakończone `OK`. Poprzedni checkpoint przed korektą UART wynosił 29 testów; po korekcie liczba jest większa.

## Test B — konfiguracja UART

Sprawdzić końcówkę konfiguracji:

```bash
tail -n 30 /boot/firmware/config.txt
```

W pliku muszą znaleźć się:

```ini
enable_uart=1
dtoverlay=uart0-pi5
dtoverlay=uart2-pi5
```

Po zapisaniu konfiguracji:

```bash
sudo reboot
```

## Test C — kontrola funkcji pinów po restarcie

```bash
pinctrl get 4 5 14 15
```

Oczekiwane jest przypisanie funkcji UART do:

- GPIO14 — TX pierwszego UART-u,
- GPIO15 — RX pierwszego UART-u,
- GPIO4 — TX drugiego UART-u,
- GPIO5 — RX drugiego UART-u.

Jeżeli któryś pin jest zajęty przez inny overlay, nie podłączamy modułu do tego UART-u do czasu usunięcia konfliktu.

## Test D — identyfikacja urządzeń Linux

```bash
ls -l /dev/serial* /dev/ttyAMA* /dev/ttyS* 2>/dev/null

cd ~/workshop-ventilation-controller
PYTHONPATH=src python3 -m ventilation_core.rs485ctl ports
```

Oczekiwane:

- wykryte zostają dwa niezależne urządzenia UART,
- `interface_type` ma wartość `onboard-uart`,
- aliasy wskazujące na to samo urządzenie są deduplikowane,
- rzeczywiste ścieżki zostają zapisane do kolejnych testów.

Nie zakładamy z góry, że będą to dokładnie `/dev/ttyAMA0` i `/dev/ttyAMA2`.

## Test E — podłączenie DFR0845 nr 1

Przy wyłączonym CM5:

- czerwony `+` → pin 1, 3,3 V,
- czarny `-` → pin 6, GND,
- niebieski `R` → pin 8, GPIO14 / TX,
- zielony `T` → pin 10, GPIO15 / RX.

Po włączeniu CM5 ponownie wykonać testy C i D.

## Test F — otwarcie pierwszego UART-u bez transmisji

Podstawić ścieżkę pierwszego UART-u:

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl check-ports \
  --port /dev/SCIEZKA_UART_1
```

Oczekiwane:

```json
{
  "ok": true,
  "count": 1,
  "transmitted": false
}
```

## Test G — podłączenie DFR0845 nr 2

Wyłączyć CM5. Następnie podłączyć:

- czerwony `+` → pin 17, 3,3 V,
- czarny `-` → pin 14, GND,
- niebieski `R` → pin 7, GPIO4 / TX,
- zielony `T` → pin 29, GPIO5 / RX.

Po włączeniu ponownie wykonać testy C i D.

## Test H — równoczesne otwarcie dwóch UART-ów bez transmisji

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl check-ports \
  --port /dev/SCIEZKA_UART_1 \
  --port /dev/SCIEZKA_UART_2
```

Oczekiwane:

- `ok: true`,
- `count: 2`,
- oba porty mają `ready: true`,
- `transmitted: false`,
- sterowanie DAC i stan fana nie zmieniają się.

## Test I — uprawnienia

Jeżeli otwarcie portu kończy się błędem `Permission denied`:

```bash
id
sudo usermod -aG dialout wentylacja
sudo reboot
```

Nazwa użytkownika musi odpowiadać rzeczywistemu użytkownikowi usługi/terminala.

## Test J — pierwsza rzeczywista transakcja

Przed wysłaniem zapytania muszą być znane:

- wybrana magistrala i DFR0845,
- urządzenie podłączone do zacisków `A/B`,
- adres Modbus slave,
- baudrate,
- parity,
- liczba bitów stopu,
- funkcja `0x03` albo `0x04`,
- bezpieczny adres rejestru tylko do odczytu.

Nie wykonujemy skanowania wszystkich adresów ani zapisu rejestrów w ciemno.

## Kryterium PASS pierwszego kroku

Pierwszy krok Stage 2 jest zaliczony, gdy:

1. oba UART-y są aktywne na właściwych GPIO,
2. Linux udostępnia dwa różne urządzenia szeregowe,
3. oba DFR0845 można równocześnie otworzyć w osobnych workerach,
4. test nie wysyła danych i nie wpływa na DAC ani fany.

Pierwsza odpowiedź Modbus będzie kolejnym checkpointem.
