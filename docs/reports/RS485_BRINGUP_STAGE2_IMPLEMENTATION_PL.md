# Stage 2 — RS-485 / Modbus RTU bring-up

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

Baza: `main`, commit `b4217586b521e06ad80933b6c30d62beb9713206`.

## Cel

Przygotować niezależną, testowalną warstwę komunikacji RS-485 / Modbus RTU dla CM5 przed podłączeniem logiki konkretnych urządzeń: węzłów SEN55 + KAmod oraz rekuperatora.

## Granice Stage 2

Stage 2 obejmuje:

- wykrywanie interfejsów szeregowych Linux,
- preferowanie stabilnych ścieżek `/dev/serial/by-id`,
- konfigurację portu: baudrate, parity, stopbits, bytesize i timeout,
- Modbus RTU CRC16,
- odczyt holding registers funkcją `0x03`,
- odczyt input registers funkcją `0x04`,
- walidację adresu slave, funkcji, długości i CRC odpowiedzi,
- obsługę odpowiedzi wyjątkowych Modbus,
- osobny proces `ventilation-rs485-worker` jako jedyny właściciel portu,
- narzędzie serwisowe `rs485ctl`.

Stage 2 nie obejmuje jeszcze:

- mapy rejestrów SEN55 / KAmod,
- mapy rejestrów rekuperatora,
- cyklicznego odpytywania urządzeń,
- wspólnych alarmów urządzeń RS-485,
- integracji danych RS-485 ze stanem głównego `ventilation-core`.

Te elementy zostaną dodane po potwierdzeniu rzeczywistego interfejsu i pierwszej poprawnej transakcji.

## Architektura

```text
rs485ctl / przyszły ventilation-core
              |
              v
      ProcessRS485Master
              |
              v
   ventilation-rs485-worker
              |
              v
 PySerialModbusTransport
              |
              v
 /dev/serial/by-id/... -> USB-RS485 -> magistrala
```

Port szeregowy jest otwierany wyłącznie w procesie workera. Proces nadrzędny przesyła kompletne ramki Modbus przez kolejki multiprocessing i koreluje odpowiedzi identyfikatorem żądania.

## Narzędzie `rs485ctl`

### Wykrycie portów

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl ports
```

### Odczyt holding registers — funkcja `0x03`

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl read-holding \
  --port /dev/serial/by-id/PRZYKLADOWY_PORT \
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
  --port /dev/serial/by-id/PRZYKLADOWY_PORT \
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

Użytkownik wykonujący transakcje musi mieć dostęp do portu szeregowego, zwykle przez grupę `dialout`.

## Walidacja automatyczna

Nowe testy lokalne:

```text
Ran 11 tests
OK
```

Obejmują:

- referencyjny CRC Modbus,
- ramki funkcji `0x03` i `0x04`,
- dekodowanie rejestrów,
- błędny CRC,
- odpowiedź wyjątkową Modbus,
- timeout transportu,
- odczyt ramki o zmiennej długości,
- deduplikację wykrytych portów.

## Kryterium zakończenia Stage 2

Stage 2 można zakończyć po potwierdzeniu na docelowym CM5:

1. wykrycia konkretnego konwertera RS-485,
2. stabilnej ścieżki `/dev/serial/by-id`,
3. poprawnych uprawnień użytkownika,
4. poprawnego otwarcia portu w osobnym workerze,
5. pierwszej prawidłowej odpowiedzi Modbus z rzeczywistego urządzenia,
6. braku wpływu testów RS-485 na działanie DAC i fanów.

## Następny etap

Stage 3 wykorzysta ten fundament do cyklicznego nadzoru urządzeń i alarmów utraty komunikacji dla każdego slave'a RS-485.
