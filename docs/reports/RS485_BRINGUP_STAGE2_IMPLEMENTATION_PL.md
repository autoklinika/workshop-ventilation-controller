# Stage 2 — RS-485 / Modbus RTU bring-up

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

Baza: `main`, commit `b4217586b521e06ad80933b6c30d62beb9713206`.

## Cel

Przygotować niezależną, testowalną warstwę komunikacji RS-485 / Modbus RTU dla CM5 przed podłączeniem logiki konkretnych urządzeń: węzłów SEN55 + KAmod oraz rekuperatora.

## Korekta sprzętowa

W projekcie nie używamy konwertera USB–RS-485. Dostępne są dwa moduły DFRobot DFR0845, które konwertują sprzętowy UART na izolowaną magistralę RS-485.

Stage 2 obsługuje od początku dwa niezależne UART-y:

- pierwszy DFR0845 na `uart0-pi5`, GPIO14/GPIO15,
- drugi DFR0845 na `uart2-pi5`, GPIO4/GPIO5.

Szczegółowe podłączenie znajduje się w:

`docs/reports/RS485_BRINGUP_STAGE2_DFR0845_DUAL_UART_CM5_WIRING_PL.md`

## Granice Stage 2

Stage 2 obejmuje:

- wykrywanie sprzętowych UART-ów Linux: `/dev/serial*`, `/dev/ttyAMA*`, `/dev/ttyS*`,
- zachowanie obsługi portów USB jako opcji pomocniczej,
- konfigurację portu: baudrate, parity, stopbits, bytesize i timeout,
- Modbus RTU CRC16,
- odczyt holding registers funkcją `0x03`,
- odczyt input registers funkcją `0x04`,
- walidację adresu slave, funkcji, długości i CRC odpowiedzi,
- obsługę odpowiedzi wyjątkowych Modbus,
- osobny proces workera jako jedyny właściciel każdego portu,
- możliwość równoczesnego uruchomienia wielu workerów,
- beztransmisyjny test otwarcia jednego albo dwóch UART-ów,
- narzędzie serwisowe `rs485ctl`.

Stage 2 nie obejmuje jeszcze:

- mapy rejestrów SEN55 / KAmod,
- mapy rejestrów rekuperatora,
- cyklicznego odpytywania urządzeń,
- wspólnych alarmów urządzeń RS-485,
- integracji danych RS-485 ze stanem głównego `ventilation-core`.

Te elementy zostaną dodane po potwierdzeniu rzeczywistych UART-ów i pierwszej poprawnej transakcji.

## Architektura

```text
                    +--> ProcessRS485Master #1 --> worker UART0 --> DFR0845 #1 --> BUS 1
rs485ctl / core ----|
                    +--> ProcessRS485Master #2 --> worker UART2 --> DFR0845 #2 --> BUS 2
```

Każdy port jest otwierany wyłącznie w swoim procesie workera. Instancje nie współdzielą deskryptorów, kolejek ani transportu szeregowego.

## Narzędzie `rs485ctl`

### Wykrycie portów

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl ports
```

### Otwarcie dwóch UART-ów bez transmisji

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl check-ports \
  --port /dev/ttyAMA0 \
  --port /dev/ttyAMA2
```

Nazwy są przykładowe. Należy użyć ścieżek zwróconych przez `ports`.

Wynik zawiera:

```json
{
  "ok": true,
  "count": 2,
  "transmitted": false
}
```

### Odczyt holding registers — funkcja `0x03`

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl read-holding \
  --port /dev/ttyAMA0 \
  --baudrate 9600 \
  --parity N \
  --stopbits 1 \
  --slave 1 \
  --address 0 \
  --count 1
```

### Odczyt input registers — funkcja `0x04`

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl read-input \
  --port /dev/ttyAMA0 \
  --baudrate 9600 \
  --parity N \
  --stopbits 1 \
  --slave 1 \
  --address 0 \
  --count 1
```

Odpowiedź zawiera ustawienia portu, surową ramkę TX, surową ramkę RX i zdekodowane rejestry.

## Zależność systemowa

Transport korzysta z `pyserial`. Na CM5 uruchamianym bez instalacji pakietu projektu należy zainstalować:

```bash
sudo apt update
sudo apt install -y python3-serial
```

Użytkownik wykonujący transakcje musi mieć dostęp do portów szeregowych, zwykle przez grupę `dialout`.

## Konfiguracja Device Tree

W `/boot/firmware/config.txt`:

```ini
enable_uart=1
dtoverlay=uart0-pi5
dtoverlay=uart2-pi5
```

Nie używamy trybu sterowania RTS/DE w jądrze, ponieważ DFR0845 udostępnia zwykłe linie UART TX/RX i realizuje konwersję po swojej stronie.

## Walidacja automatyczna

Pierwsza wersja Stage 2 została potwierdzona na CM5 wynikiem:

```text
Ran 29 tests
OK
```

Po korekcie pod DFR0845 dodano testy:

- klasyfikacji sprzętowych UART-ów,
- preferencji aliasu `/dev/serialN`,
- równoczesnego utworzenia dwóch niezależnych workerów,
- potwierdzenia, że `check-ports` nie wykonuje transmisji,
- odrzucenia dwukrotnego otwarcia tej samej ścieżki w jednym wywołaniu.

Pełny zestaw wymaga ponownej walidacji na CM5 po aktualizacji gałęzi.

## Kryterium zakończenia Stage 2

Stage 2 można zakończyć po potwierdzeniu na docelowym CM5:

1. aktywacji `uart0-pi5` i `uart2-pi5`,
2. wykrycia rzeczywistych urządzeń `/dev/ttyAMA*` lub aliasów `/dev/serial*`,
3. poprawnych uprawnień użytkownika,
4. równoczesnego otwarcia obu portów przez `check-ports`,
5. pierwszej prawidłowej odpowiedzi Modbus z rzeczywistego urządzenia,
6. braku wpływu testów RS-485 na działanie DAC i fanów.

## Następny etap

Stage 3 wykorzysta ten fundament do cyklicznego nadzoru urządzeń i alarmów utraty komunikacji dla każdego slave'a oraz każdej magistrali RS-485.
