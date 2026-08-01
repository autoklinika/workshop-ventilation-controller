# Stage 2 — korekta sprzętowa z USB-RS485 na dwa DFR0845 UART

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Powód korekty

Pierwsza wersja Stage 2 zakładała konwerter USB–RS-485. Użytkownik potwierdził, że rzeczywistym sprzętem są dwa moduły DFRobot DFR0845.

DFR0845 jest izolowanym konwerterem UART ↔ RS-485 i wymaga sprzętowych linii TX/RX CM5 zamiast portu USB.

## Zakres wykonanej zmiany

- rozszerzono wykrywanie portów o `/dev/serial*`, `/dev/ttyAMA*` i `/dev/ttyS*`,
- zachowano obsługę USB jako opcję pomocniczą,
- dodano klasyfikację `onboard-uart`,
- dodano możliwość równoczesnego uruchomienia wielu niezależnych workerów,
- nazwa procesu workera zawiera nazwę jego portu,
- dodano `rs485ctl check-ports`,
- `check-ports` może otworzyć jeden lub dwa UART-y bez wysyłania danych,
- wynik jawnie zawiera `transmitted: false`,
- dodano ochronę przed dwukrotnym podaniem tej samej ścieżki,
- dodano testy wieloportowe,
- przygotowano pełny schemat podłączenia dwóch DFR0845 do CM5IO.

## Przyjęte UART-y

- `uart0-pi5`: GPIO14 TX / GPIO15 RX,
- `uart2-pi5`: GPIO4 TX / GPIO5 RX.

## Elastyczność architektury

Obsługa dwóch UART-ów nie oznacza jeszcze obowiązkowego użycia dwóch magistral w instalacji.

Możliwe warianty:

1. jedna wspólna magistrala dla wszystkich slave'ów, jeśli urządzenia mają zgodne parametry transmisji,
2. osobna magistrala czujników i osobna magistrala rekuperatora,
3. drugi DFR0845 jako interfejs rezerwowy lub serwisowy.

Kod Stage 2 nie narzuca żadnego z tych wariantów.

## Następny checkpoint

1. ponowna walidacja pełnego zestawu testów na CM5,
2. konfiguracja overlayów UART,
3. identyfikacja rzeczywistych nazw urządzeń Linux,
4. uruchomienie pierwszego DFR0845,
5. uruchomienie drugiego DFR0845,
6. jednoczesny `check-ports` bez transmisji.
