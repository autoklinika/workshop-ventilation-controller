# Uruchomienie DAC DFRobot DFR0971 na CM5

## Cel etapu

Uruchomić dwukanałowy DAC GP8403 / DFR0971 przez I²C, potwierdzić oba wyjścia multimetrem i poznać zachowanie modułu przed podłączeniem wejść sterujących wentylatorów EC.

## Zasady bezpieczeństwa

- podczas całego pierwszego etapu oba wejścia 0–10 V wentylatorów pozostają odłączone,
- moduł DFR0971 zasilamy z 3,3 V, aby poziomy i podciągnięcia I²C były bezpieczne dla GPIO CM5,
- połączenia wykonujemy przy wyłączonym zasilaniu CM5,
- mierzymy napięcie wyłącznie pomiędzy `VOUT0` lub `VOUT1` i zaciskiem `GND` wyjść DAC,
- nie używamy funkcji zapisu nieulotnego `store`,
- po każdym teście oba kanały są jawnie sprowadzane do 0 V,
- sam restart programu lub CM5 nie stanowi jeszcze sprzętowego zabezpieczenia wyjść; do testów z wentylatorami przechodzimy dopiero po pełnej walidacji.

## Połączenie DFR0971 z 40-pinowym złączem CM5 IO Board

Połączenia wykonujemy według nazw sygnałów nadrukowanych na module, a nie wyłącznie według kolorów przewodu Gravity.

| DFR0971 | CM5 IO Board | Numer fizyczny pinu |
|---|---|---:|
| `VCC` | 3,3 V | 1 |
| `GND` | GND | 6 |
| `SDA` | GPIO2 / SDA1 | 3 |
| `SCL` | GPIO3 / SCL1 | 5 |

Przełączniki adresowe `A0`, `A1`, `A2` pozostawiamy w pozycji `0`, co daje domyślny adres `0x58`.

## Włączenie I²C i pakiety

```bash
sudo raspi-config nonint do_i2c 0
sudo apt update
sudo apt install -y i2c-tools python3-smbus
sudo reboot
```

Po ponownym zalogowaniu:

```bash
ls -l /dev/i2c-1
i2cdetect -y 1
```

Oczekiwany adres modułu:

```text
58
```

Jeżeli zamiast `0x58` pojawi się adres `0x59`–`0x5F`, należy zanotować ustawienie przełączników i przekazać adres do narzędzia przez `--address`.

## Pobranie narzędzia

```bash
cd ~/workshop-ventilation-controller
git pull --ff-only
```

## Próba komunikacji

```bash
python3 tools/hardware/dac_cli.py probe
```

## Ustawienie obu kanałów na 0 V

```bash
python3 tools/hardware/dac_cli.py zero
```

Po tym poleceniu mierzymy osobno:

- `VOUT0` względem `GND`,
- `VOUT1` względem `GND`.

Oba wyniki powinny być bliskie 0 V.

## Sekwencja pomiarowa kanału 0

```bash
python3 tools/hardware/dac_cli.py sequence \
  --channel 0 \
  --confirm-no-fans
```

Program kolejno ustawi 0 V, 2 V, 5 V, 8 V i 10 V. Po każdym kroku czeka na pomiar multimetrem i naciśnięcie Enter. Na końcu oraz po `Ctrl+C` próbuje sprowadzić oba kanały do 0 V.

## Sekwencja pomiarowa kanału 1

```bash
python3 tools/hardware/dac_cli.py sequence \
  --channel 1 \
  --confirm-no-fans
```

## Pojedynczy punkt pomiarowy

Przykład 5 V na kanale 0:

```bash
python3 tools/hardware/dac_cli.py measure \
  --channel 0 \
  --voltage 5 \
  --confirm-no-fans
```

## Tabela wyników

| Kanał | Zadane napięcie | Zmierzone napięcie | Błąd | Wynik |
|---:|---:|---:|---:|---|
| 0 | 0 V |  |  |  |
| 0 | 2 V |  |  |  |
| 0 | 5 V |  |  |  |
| 0 | 8 V |  |  |  |
| 0 | 10 V |  |  |  |
| 1 | 0 V |  |  |  |
| 1 | 2 V |  |  |  |
| 1 | 5 V |  |  |  |
| 1 | 8 V |  |  |  |
| 1 | 10 V |  |  |  |

## Następny punkt kontrolny

Po potwierdzeniu obu kanałów:

1. zapisujemy rzeczywiste wyniki pomiarów,
2. sprawdzamy stan wyjść podczas restartu systemu i zatrzymania procesu,
3. ustalamy bezpieczne zachowanie przy starcie `ventilation-core`,
4. dopiero potem podłączamy jeden wentylator i wyznaczamy minimalne napięcie startu.
