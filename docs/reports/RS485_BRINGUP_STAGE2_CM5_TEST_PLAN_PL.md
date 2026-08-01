# Stage 2 — plan pierwszej walidacji RS-485 na CM5

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Zasada bezpieczeństwa

Test RS-485 jest niezależny od sterowania DAC. Przed rozpoczęciem należy pozostawić `ventilation-core` w stanie `STOP / 0 V / 0 V`. Nie zmieniamy przewodów DFR0971 ani sterowania fanów.

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

Oczekiwany wynik po dodaniu Stage 2: dotychczasowe testy + 11 nowych testów RS-485, wszystkie `OK`.

## Test B — identyfikacja użytkownika i grup

```bash
whoami
id
```

Użytkownik powinien należeć do grupy `dialout`. Jeżeli nie należy:

```bash
sudo usermod -aG dialout wentylacja
```

Zmiana grupy wymaga ponownego zalogowania albo restartu CM5.

## Test C — identyfikacja konwertera

Najpierw bez konwertera:

```bash
lsusb
PYTHONPATH=src python3 -m ventilation_core.rs485ctl ports
```

Następnie podłączyć konwerter USB–RS485 i powtórzyć:

```bash
lsusb
PYTHONPATH=src python3 -m ventilation_core.rs485ctl ports
ls -l /dev/serial/by-id/ 2>/dev/null || true
```

Oczekiwane:

- pojawia się nowy interfejs USB,
- `rs485ctl ports` zwraca co najmniej jeden port,
- preferowana jest ścieżka `stable_path: true`,
- ścieżka wskazuje na `/dev/ttyUSB*` albo `/dev/ttyACM*`.

## Test D — otwarcie portu bez urządzenia

Samo poprawne wykrycie portu nie potwierdza komunikacji z urządzeniem. Próba odczytu bez podłączonego slave'a powinna zakończyć się kontrolowanym timeoutem, a nie awarią procesu Python.

Polecenie zostanie dobrane po ustaleniu stabilnej ścieżki portu. Oczekiwany błąd:

```text
RS-485 response timed out
```

## Test E — pierwsza rzeczywista transakcja

Przed wysłaniem zapytania muszą być znane:

- urządzenie podłączone do magistrali,
- adres Modbus slave,
- baudrate,
- parity,
- liczba bitów stopu,
- funkcja `0x03` albo `0x04`,
- bezpieczny adres rejestru tylko do odczytu.

Nie wykonujemy skanowania wszystkich adresów ani zapisu rejestrów w ciemno.

## Okablowanie minimalne

- A konwertera do A urządzenia,
- B konwertera do B urządzenia,
- wspólna masa odniesienia, jeżeli wymaga jej zastosowany sprzęt,
- terminacja 120 Ω tylko zgodnie z topologią i długością magistrali,
- brak rozgałęzień gwiazdowych podczas pierwszej próby.

Jeżeli brak odpowiedzi, pierwszym testem jest zamiana A/B, ponieważ oznaczenia producentów nie zawsze są spójne.

## Kryterium PASS pierwszego kroku

Pierwszy krok Stage 2 jest zaliczony, gdy CM5 pokaże jednoznaczną, stabilną ścieżkę konwertera i użytkownik ma prawo otworzyć port. Pierwsza odpowiedź Modbus będzie kolejnym checkpointem.
