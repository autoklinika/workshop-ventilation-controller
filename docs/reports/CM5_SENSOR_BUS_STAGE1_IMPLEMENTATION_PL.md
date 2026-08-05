# CM5 SENSOR BUS Stage 1 — raport implementacji

Data: 2026-08-05  
Repozytorium: `autoklinika/workshop-ventilation-controller`  
Gałąź: `agent/cm5-sensor-bus-worker-stage1-refresh`  
Draft PR: `#8`  
Baza: `main` @ `40de40f84218d8e4b74ec7d57f5eb81700530746`

## 1. Punkt startowy

Zasilanie 3,3 V obu DFR0845 zostało wykonane. Moduły są uruchomione i podłączone do CM5 według zatwierdzonego pinoutu. Dwa węzły KAmod + SEN55 są połączone w jednej magistrali SENSOR BUS i zasilone napięciem 12 V.

```text
DFR0845 #1 -> /dev/ttyAMA0 -> SENSOR BUS
DFR0845 #2 -> /dev/ttyAMA4 -> AERO BUS
```

SENSOR BUS:

```text
/dev/ttyAMA0
19200 bit/s, 8N1
Modbus RTU, FC04
slave 1 i 2
mapa v1
19 Input Registers
10 ms przerwy między węzłami
```

AERO BUS pozostaje poza zakresem tego etapu:

```text
/dev/ttyAMA4
9600 bit/s, 8N1
slave 44
```

Wcześniejsza walidacja sprzętowa potwierdziła:

```text
UART0 <-> UART4:             20/20 w obu kierunkach
2× DFR0845 przy 19200 bit/s: 100/100 w obu kierunkach
2× DFR0845 przy 9600 bit/s:  100/100 w obu kierunkach
```

Szczegóły: `docs/reports/CM5_DFR0845_DUAL_UART_RS485_VALIDATION_PL.md`.

## 2. Architektura

Dodano niezależny proces SENSOR BUS:

```text
ventilation-core
├── proces główny — autorytatywny CoreState i Unix socket
├── hardware worker — wyłączny właściciel I²C / DFR0971
└── sensor_bus_worker — wyłączny właściciel /dev/ttyAMA0
    ├── KAmod + SEN55, slave 1
    └── KAmod + SEN55, slave 2
```

Worker:

- otwiera `/dev/ttyAMA0` w trybie wyłącznym,
- wysyła wyłącznie FC04,
- czyta 19 rejestrów mapy v1,
- zachowuje minimum 10 ms między kolejnymi slave,
- utrzymuje niezależny stan i statystyki obu węzłów,
- nie blokuje zdrowego węzła po timeoutcie drugiego,
- ponownie otwiera UART po błędzie portu,
- automatycznie wykrywa powrót węzła,
- jest nadzorowany i restartowany po nieoczekiwanym zakończeniu,
- usuwa zakończony obiekt procesu i stare wpisy kolejki przed restartem.

## 3. Model danych

Dla każdego slave publikowane są:

- `online`, `usable`, `measurement_valid`, `measurement_stale`, `sensor_present`,
- maska dostępności i statusu,
- PM1.0, PM2.5, PM4.0, PM10,
- wilgotność, temperatura, VOC Index i NOx Index,
- wiek pomiaru,
- liczniki błędów SEN55 i usługi Modbus,
- uptime, firmware, wersja mapy i sekwencja,
- czas ostatniego sukcesu i ostatni błąd,
- liczniki odpytań, sukcesów, błędów komunikacji, invalid, stale i błędów mapy.

Pole niedostępne według maski jest reprezentowane jako `None`, a nie jako pozornie prawidłowe zero.

`usable=true` wymaga:

```text
poprawnej odpowiedzi Modbus
map_version == 1
MEASUREMENT_VALID
braku MEASUREMENT_STALE
co najmniej jednego dostępnego pola
prawidłowego wieku pomiaru
```

Wersja mapy jest sprawdzana przed dekodowaniem wartości. Przy nieznanej wersji urządzenie pozostaje `online=true`, ale dane są wyczyszczone, `usable=false`, a licznik błędów mapy rośnie.

## 4. Separacja awarii

Obowiązuje rozdział:

```text
DAC / I²C != SENSOR BUS != pojedynczy slave
```

Awaria SENSOR BUS:

- nie ustawia alarmu DAC,
- nie zmienia napięć wentylatorów,
- nie przełącza trybu sterowania,
- nie zatrzymuje `ventilation-core`.

Awaria slave `1` nie zatrzymuje slave `2` i odwrotnie. Ostatnie wartości mogą pozostać w stanie diagnostycznym, ale `online=false` i `usable=false` zabraniają uznania ich za aktualny pomiar.

Ścieżki uruchamiania i zamykania zabezpieczono tak, aby procesy były sprzątane również po błędzie inicjalizacji SENSOR BUS, utworzenia Unix socketu lub zamknięcia procesu DAC.

## 5. Interfejs diagnostyczny

Pełny stan:

```bash
ventilationctl status
```

Tylko SENSOR BUS:

```bash
ventilationctl sensors
```

Polecenia zwracają JSON. GUI, MQTT i przyszłe API nie otwierają UART-u i nie znają numerów rejestrów Modbus.

## 6. Konfiguracja runtime

Dodane argumenty:

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

Konfiguracja `systemd`:

```text
port:                 /dev/ttyAMA0
addresses:            1,2
baud:                 19200
timeout:              0,5 s
poll interval:        1,0 s
inter-node delay:     0,010 s
reconnect delay:      1,0 s
SupplementaryGroups: i2c dialout
```

Dodano zależność `pyserial>=3.5`. Na docelowym Raspberry Pi OS preferowany jest pakiet systemowy:

```bash
sudo apt install python3-serial
```

## 7. Walidacja programowa

GitHub Actions dla kodowego checkpointu Draft PR `#8`:

```text
Commit:     416efae1bb3ff22e620208f962d3afb1b95cb2ae
Workflow:   Ventilation Core Tests
Run:        #290
Python:     3.11.15
compileall: PASS
unit tests: 31/31 PASS
conclusion: success
```

Testy obejmują między innymi:

- znany wektor CRC Modbus,
- budowę żądania FC04,
- pełną odpowiedź 19 rejestrów,
- błędne CRC,
- skalowanie mapy SEN55 v1,
- ujemną temperaturę `int16`,
- pola niedostępne jako `None`,
- stale i brak pierwszego pomiaru,
- odrzucenie nieznanej wersji mapy przed dekodowaniem,
- zachowanie `online=true` i wyczyszczenie danych przy nieznanej mapie,
- brak blokowania slave `2` po timeoutcie slave `1`,
- integrację SENSOR BUS z `CoreState`,
- niezależność błędu czujników od DAC,
- sprzątanie procesów po błędach startu i zamykania,
- wszystkie wcześniejsze testy DFR0971, polityki napięć i nadzoru procesu.

## 8. Walidacja na rzeczywistym CM5

### 8.1. Przygotowanie

```bash
cd /home/wentylacja/workshop-ventilation-controller
git fetch origin
git switch agent/cm5-sensor-bus-worker-stage1-refresh
git pull
sudo apt update
sudo apt install -y python3-serial
```

### 8.2. Port i uprawnienia

```bash
ls -l /dev/ttyAMA0
id wentylacja
sudo systemctl status serial-getty@ttyAMA0.service --no-pager
cat /proc/cmdline
```

`/dev/ttyAMA0` nie może być używany przez konsolę szeregową ani `serial-getty`.

### 8.3. Testy lokalne

```bash
cd /home/wentylacja/workshop-ventilation-controller
PYTHONPATH=src python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Oczekiwane zakończenie:

```text
Ran 31 tests
OK
```

### 8.4. Ręczne uruchomienie

```bash
sudo systemctl stop ventilation-core
sudo install -d -o wentylacja -g wentylacja -m 0770 /run/workshop-ventilation
cd /home/wentylacja/workshop-ventilation-controller
sudo -u wentylacja env PYTHONPATH=src python3 -m ventilation_core.main \
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

W drugim terminalu:

```bash
cd /home/wentylacja/workshop-ventilation-controller
PYTHONPATH=src python3 -m ventilation_core.ctl sensors
```

Pierwsze kryteria:

```text
ready=true
worker_alive=true
slave 1: online=true, usable=true, map_version=1
slave 2: online=true, usable=true, map_version=1
measurement_valid=true
measurement_stale=false
communication_errors=0
successful_polls rośnie
```

### 8.5. Degradacja i powrót

1. Odłączyć tylko slave `1` i potwierdzić dalszy wzrost statystyk slave `2`.
2. Podłączyć slave `1` i potwierdzić automatyczny powrót.
3. Powtórzyć dla slave `2`.
4. Odłączyć całą magistralę od DFR0845 i potwierdzić brak wpływu na DAC.
5. Podłączyć magistralę i potwierdzić odzyskanie bez restartu rdzenia.
6. Wykonać minimum 300 cykli obu węzłów bez błędów.
7. Sprawdzić restart usługi i pełny restart CM5.

### 8.6. Systemd dopiero po walidacji ręcznej

```bash
sudo cp deploy/systemd/ventilation-core.service /etc/systemd/system/ventilation-core.service
sudo systemctl daemon-reload
sudo systemctl restart ventilation-core
sudo systemctl status ventilation-core --no-pager
journalctl -u ventilation-core -n 100 --no-pager
ventilationctl sensors
```

## 9. Poza zakresem

Stage 1 nie dodaje:

- workera AERO BUS ani FC06 dla AERO,
- automatycznego sterowania na podstawie SEN55,
- progów PM/VOC,
- trybów AUTO i BOOST,
- GUI, MQTT, historii, bazy danych ani AI.

Nie wykonano merge i nie oznaczono PR jako Ready for Review.
