# CM5 SENSOR BUS Stage 1 — raport implementacji

Data rozpoczęcia: 2026-08-05

Repozytorium:

```text
autoklinika/workshop-ventilation-controller
```

Gałąź implementacyjna:

```text
agent/cm5-sensor-bus-worker-stage1-refresh
```

Punkt bazowy:

```text
main
40de40f84218d8e4b74ec7d57f5eb81700530746
```

## 1. Powód użycia odświeżonej gałęzi

W repozytorium istniała już gałąź:

```text
agent/cm5-sensor-bus-worker-stage1
```

Zawierała ona raport i narzędzie wcześniejszej walidacji dwóch UART-ów CM5 oraz dwóch DFR0845, ale rozeszła się z aktualnym `main` i nie zawierała czterech najnowszych commitów dokumentujących docelowy pinout.

Nie nadpisano ani nie usunięto tej gałęzi. Utworzono świeżą gałąź z aktualnego `main`, a wartościowe materiały walidacyjne zostały zachowane również w nowej gałęzi.

## 2. Potwierdzony punkt startowy sprzętu

Zasilanie 3,3 V obu DFR0845 zostało wykonane. Moduły są uruchomione i podłączone do CM5 według zatwierdzonego pinoutu. Dwa węzły KAmod + SEN55 są połączone w jednej magistrali SENSOR BUS i zasilone napięciem 12 V.

Autorytatywna konfiguracja SENSOR BUS:

```text
port:                 /dev/ttyAMA0
parametry:            19200 bit/s, 8N1
protokół:             Modbus RTU
funkcja:              FC04 Read Input Registers
slave:                1, 2
mapa:                 v1
liczba rejestrów:     19
inter-node delay:     10 ms
```

AERO BUS pozostaje niezależny:

```text
/dev/ttyAMA4
9600 bit/s, 8N1
slave 44
```

Stage 1 nie otwiera ani nie obsługuje AERO BUS.

## 3. Zakres implementacji

Dodano produkcyjny tor odczytu SENSOR BUS do `ventilation-core`:

```text
ventilation-core
    ├── proces główny i autorytatywny CoreState
    ├── osobny proces DAC / I²C
    └── osobny proces sensor_bus_worker
            └── wyłączny właściciel /dev/ttyAMA0
                    ├── KAmod + SEN55 slave 1
                    └── KAmod + SEN55 slave 2
```

Worker:

- jest jedynym właścicielem UART SENSOR BUS,
- otwiera `/dev/ttyAMA0` w trybie wyłącznym,
- odpytuje slave `1` i `2` przez FC04,
- czyta 19 Input Registers mapy v1,
- zachowuje 10 ms ciszy między kolejnymi węzłami,
- utrzymuje osobny stan i liczniki diagnostyczne dla każdego slave,
- nie blokuje drugiego węzła po timeoutcie pierwszego,
- ponownie otwiera port po błędzie UART,
- pozwala wykryć powrót węzła bez restartu całego rdzenia,
- przekazuje do rdzenia model domenowy niezależny od numerów rejestrów.

## 4. Normalizowany model danych

Dla każdego węzła publikowane są między innymi:

- `online` — poprawna odpowiedź bieżącego odpytywania,
- `usable` — poprawna wersja mapy i ważny, nieprzeterminowany pomiar,
- `measurement_valid`,
- `measurement_stale`,
- `sensor_present`,
- maska dostępności i maska statusu,
- PM1.0, PM2.5, PM4.0, PM10 w µg/m³,
- wilgotność w %RH,
- temperatura w °C,
- VOC Index,
- NOx Index,
- wiek pomiaru,
- liczniki błędów SEN55 i usługi Modbus węzła,
- uptime, wersja firmware, wersja mapy i numer sekwencji,
- czas ostatniego poprawnego odczytu,
- ostatni błąd,
- liczniki odpytań, sukcesów, błędów komunikacji, stale, invalid i błędów mapy.

Pole niedostępne według maski nie jest przedstawiane jako zero. W modelu domenowym otrzymuje wartość `None`.

## 5. Separacja błędów

Zachowano niezależne domeny awarii:

```text
DAC / I²C != SENSOR BUS != pojedynczy slave
```

Konsekwencje:

- awaria SENSOR BUS nie ustawia alarmu utraty DAC,
- awaria SENSOR BUS nie przełącza wentylatorów ani nie zmienia ich zadanych napięć,
- awaria slave `1` nie zatrzymuje odczytu slave `2`,
- niepoprawna wersja mapy oznacza `usable=false`, mimo że urządzenie odpowiada,
- worker jest nadzorowany i automatycznie odtwarzany po nieoczekiwanym zakończeniu procesu,
- obiekt zakończonego procesu oraz stare stany kolejki są usuwane przed restartem workera.

## 6. Integracja z autorytatywnym stanem

`CoreState` zawiera teraz opcjonalny `sensor_bus`.

Pełny stan:

```bash
ventilationctl status
```

Widok tylko SENSOR BUS:

```bash
ventilationctl sensors
```

Polecenia zwracają JSON. GUI, MQTT ani przyszłe API nie muszą znać numerów rejestrów Modbus i nie otwierają portu szeregowego.

## 7. Konfiguracja runtime

Dodano parametry uruchomieniowe:

```text
--sensor-port
--sensor-addresses
--sensor-baud
--sensor-timeout
--sensor-poll-interval
--sensor-inter-node-delay
--sensor-reconnect-delay
--disable-sensor-bus
```

W pliku `systemd` przyjęto jawnie:

```text
/dev/ttyAMA0
slave 1,2
19200 bit/s
timeout 0,5 s
poll interval 1,0 s
inter-node delay 0,010 s
reconnect delay 1,0 s
```

Użytkownik usługi `wentylacja` otrzymuje grupy uzupełniające:

```text
i2c
dialout
```

Uruchomienie przez `systemd` pozostaje odłożone do zakończenia walidacji ręcznej.

## 8. Zależności

Do zależności projektu dodano:

```text
pyserial>=3.5
```

Na docelowym Raspberry Pi OS / Debian preferowana jest instalacja pakietu systemowego:

```bash
sudo apt install python3-serial
```

Pozwala to uniknąć konfliktu z mechanizmem externally-managed Python środowiska systemowego.

## 9. Testy programowe

Dodano testy:

- znanego wektora CRC Modbus,
- budowy żądania FC04,
- odbioru i dekodowania rejestrów,
- odrzucenia niepoprawnego CRC,
- skalowania i konwersji mapy SEN55 v1,
- ujemnej temperatury `int16`,
- pól niedostępnych jako `None`,
- odrzucenia pomiaru stale,
- odrzucenia braku pierwszego pomiaru,
- obecności SENSOR BUS w `CoreState`,
- niezależności awarii monitora czujników od stanu DAC.

Lokalny model implementacji przeszedł `compileall` i testy nowej ścieżki. Pełny wynik workflow gałęzi zostanie wpisany po uruchomieniu GitHub Actions dla Draft PR.

## 10. Plan walidacji na rzeczywistym CM5

### 10.1. Przygotowanie

```bash
cd /home/wentylacja/workshop-ventilation-controller
git fetch origin
git switch agent/cm5-sensor-bus-worker-stage1-refresh
git pull
sudo apt update
sudo apt install -y python3-serial
```

### 10.2. Sprawdzenie portu i uprawnień

```bash
ls -l /dev/ttyAMA0
id wentylacja
sudo systemctl status serial-getty@ttyAMA0.service --no-pager
cat /proc/cmdline
```

Port nie może być zajęty przez konsolę szeregową ani `serial-getty`.

### 10.3. Testy bez uruchamiania usługi

```bash
cd /home/wentylacja/workshop-ventilation-controller
PYTHONPATH=src python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

### 10.4. Ręczne uruchomienie rdzenia

Najpierw zatrzymać istniejącą usługę, aby nie otwierała DAC ani portów równolegle:

```bash
sudo systemctl stop ventilation-core
```

Uruchomić rdzeń w pierwszym terminalu:

```bash
cd /home/wentylacja/workshop-ventilation-controller
sudo -u wentylacja PYTHONPATH=src python3 -m ventilation_core.main \
  --socket /run/workshop-ventilation/ventilation-core.sock \
  --sensor-port /dev/ttyAMA0 \
  --sensor-addresses 1,2 \
  --sensor-baud 19200 \
  --sensor-timeout 0.5 \
  --sensor-poll-interval 1.0 \
  --sensor-inter-node-delay 0.010 \
  --sensor-reconnect-delay 1.0 \
  --log-level INFO
```

Jeżeli katalog runtime nie istnieje po zatrzymaniu usługi, utworzyć go przed startem ręcznym:

```bash
sudo install -d -o wentylacja -g wentylacja -m 0770 /run/workshop-ventilation
```

### 10.5. Pierwszy odczyt

W drugim terminalu:

```bash
cd /home/wentylacja/workshop-ventilation-controller
PYTHONPATH=src python3 -m ventilation_core.ctl sensors
```

Kryteria:

- `ready=true`,
- `worker_alive=true`,
- dwa wpisy w `nodes`,
- slave `1` i `2` mają `online=true`,
- `map_version=1`,
- `measurement_valid=true`,
- `measurement_stale=false`,
- `usable=true`,
- `successful_polls` rośnie,
- `communication_errors=0`,
- wartości PM/VOC/temperatury/wilgotności są wiarygodne.

### 10.6. Test degradacji i powrotu

1. Odłączyć wyłącznie slave `1`.
2. Potwierdzić, że slave `1` przechodzi na `online=false`, ale statystyki slave `2` nadal rosną.
3. Ponownie podłączyć slave `1` i potwierdzić automatyczny powrót `online=true` oraz `usable=true`.
4. Powtórzyć test dla slave `2`.
5. Odłączyć całą magistralę od DFR0845 i potwierdzić raportowanie błędów bez wpływu na DAC.
6. Ponownie podłączyć magistralę i potwierdzić odzyskanie komunikacji bez restartu rdzenia.

### 10.7. Dopiero po zaliczeniu testu ręcznego

```bash
sudo cp deploy/systemd/ventilation-core.service /etc/systemd/system/ventilation-core.service
sudo systemctl daemon-reload
sudo systemctl restart ventilation-core
sudo systemctl status ventilation-core --no-pager
journalctl -u ventilation-core -n 100 --no-pager
ventilationctl sensors
```

## 11. Kryteria zaliczenia Stage 1

Stage 1 może zostać uznany za zwalidowany sprzętowo dopiero po potwierdzeniu:

- obu slave działających jednocześnie na `/dev/ttyAMA0`,
- poprawnej mapy v1 i wszystkich skal,
- minimum 300 kolejnych cykli bez błędów dla obu węzłów,
- zachowania co najmniej 10 ms między węzłami,
- braku blokowania zdrowego slave przez uszkodzony lub odłączony slave,
- automatycznego powrotu obu węzłów,
- automatycznego odtworzenia procesu worker po jego kontrolowanym zakończeniu,
- braku wpływu błędów SENSOR BUS na sterowanie DAC,
- poprawnej pracy po restarcie usługi,
- poprawnej pracy po pełnym restarcie CM5.

## 12. Poza zakresem

Stage 1 nie dodaje:

- workera AERO BUS,
- komend FC06 dla AERO,
- automatycznego sterowania wentylatorami na podstawie SEN55,
- progów PM/VOC,
- trybów AUTO i BOOST,
- GUI,
- MQTT,
- historii pomiarów,
- bazy danych,
- AI.

Nie wykonano merge i nie oznaczono PR jako Ready for Review.
