# CM5 TACHO Stage 1 — walidacja EXTRACT na GPIO27

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Host:** `wentylacja` / Raspberry Pi Compute Module 5  
**Gałąź:** `agent/cm5-tacho-stage1`  
**Status:** kanał EXTRACT / GPIO27 zwalidowany sprzętowo; runtime `CoreState.tacho.extract` działa poprawnie w STOP i RUN; pozostaje końcowy test runtime timeout oraz izolacji po odłączeniu przewodu TACHO.

## 1. Konfiguracja stanowiska

W laboratorium dostępny jest obecnie jeden fizyczny wentylator EC. Dla walidacji przyjęto jednoznaczne mapowanie:

```text
sterowanie: EXTRACT / DAC CH1 / VOUT1 / DB9 pin 5
TACHO:      GPIO27 / physical pin 13 / gpiochip0 offset 27
```

Przewód TACHO tego samego wentylatora został fizycznie przepięty z GPIO17 na GPIO27. GPIO17 pozostaje zarezerwowany dla przyszłego drugiego wentylatora i nie jest częścią bieżącego testu.

Tor wejściowy:

```text
TACHO FAN -> węzeł z pull-up 10 kΩ do 3,3 V -> 1 kΩ szeregowo -> GPIO27
                                                |
                                               1 nF
                                                |
                                               GND
```

Potwierdzone: wyjście open-collector/open-drain, 3 impulsy/obrót, `RPM = Hz * 20`.

## 2. Dynamiczny pomiar diagnostyczny przy 5,0 V

Sterowanie:

```text
supply=0.0 V
extract=5.0 V
```

Narzędzie diagnostyczne:

```bash
PYTHONPATH=src python3 tools/hardware/tacho_cli.py \
  --chip /dev/gpiochip0 \
  --only extract \
  --duration 15
```

Po odrzuceniu pierwszej próbki przejściowej średnia z kolejnych 14 próbek wyniosła:

```text
frequency ~= 70.575 Hz
RPM       ~= 1411.5
```

Zakres kolejnych 14 próbek:

```text
69.798 .. 70.978 Hz
1396.0 .. 1419.6 RPM
```

Odchylenie standardowe częstotliwości wyniosło około `0.330 Hz`.

Punkt referencyjny z wcześniejszej charakterystyki oscyloskopowej dla 5 V:

```text
71.937 Hz
1438.7 RPM
```

Odchyłka średniego pomiaru CM5 wyniosła około `-1.89 %`.

Wniosek: GPIO27, libgpiod, kernelowe timestampy i estimator pracują prawidłowo; nie ma oznak błędu skali ani podwójnego liczenia zboczy.

## 3. Sprzętowy test RUN -> STOP / timeout

Na finalnym GPIO27 wentylator uruchomiono na 5 V, rozpoczęto capture, a następnie wykonano `stop`.

Bezpośrednio przed STOP rejestrowano około:

```text
70.086 .. 70.296 Hz
1401.7 .. 1405.9 RPM
```

Pierwszy wydruk po zaniku zboczy:

```text
EXTRACT  NO VALID TACHO  age=0.295s
```

Następnie `NO VALID TACHO` utrzymywało się bez fałszywych powrotów do valid aż do:

```text
age=7.795s
```

Estimator używa timeoutu `0.25 s`; wynik jest z nim zgodny.

Wniosek: sprzętowy kanał `EXTRACT / CH1 / VOUT1 + GPIO27` jest **HARDWARE PASS**.

## 4. Integracja runtime z ventilation-core

Dodano opcjonalny read-only monitor `ExtractTachoMonitor` uruchamiany przez:

```text
--enable-extract-tacho
```

Monitor:

- używa tylko GPIO27,
- żąda tylko zboczy narastających,
- używa `bias=disabled`, ponieważ istnieje zewnętrzny pull-up 10 kΩ,
- korzysta z monotonicznych timestampów zdarzeń,
- publikuje wynik w `CoreState.tacho.extract`,
- nie wpływa na DAC, setpointy, SENSOR BUS, AERO BUS ani `VentilationMode`,
- nie generuje jeszcze alarmu TACHO.

`CoreState.tacho.supply` pozostaje `null`, ponieważ drugi fizyczny wentylator nie jest dostępny do walidacji.

## 5. Runtime TACHO przy STOP — PASS

Po kontrolowanym restarcie `ventilation-core` z tymczasowym drop-inem systemd w `/run` potwierdzono:

```text
mode=STOP
setpoints=0.0/0.0 V
hardware_ready=true
active_alarms=[]
```

Stan TACHO:

```text
ready=true
worker_alive=true
last_error=null
supply=null
extract.line_name=GPIO27
extract.line_offset=27
extract.frequency_hz=0.0
extract.rpm=0.0
extract.sample_count=0
extract.age_seconds=null
extract.valid=false
```

`gpioinfo GPIO27`:

```text
input bias=disabled edges=rising consumer="ventilation-core-extract-tacho"
```

Wniosek: runtime poprawnie przejmuje GPIO27 i publikuje stan zatrzymanego wentylatora bez naruszania sterowania.

## 6. Runtime TACHO przy 5 V — PASS ścieżki end-to-end

Przez normalny interfejs `ventilation_core.ctl` zadano:

```text
supply=0.0 V
extract=5.0 V
```

Po nominalnych 5 s stabilizacji `CoreState.tacho.extract` raportował kolejno:

```text
56.244 Hz -> 1124.9 RPM
65.423 Hz -> 1308.5 RPM
67.149 Hz -> 1343.0 RPM
67.721 Hz -> 1354.4 RPM
67.640 Hz -> 1352.8 RPM
```

Każda próbka miała:

```text
mode=MANUAL
cmd=5.0V
ready=true
valid=true
sample_count=6
```

Po komendzie STOP, po około 0,4 s od polecenia, odczyt wynosił:

```text
mode=STOP
cmd=0.0V
valid=true
71.716 Hz
1434.3 RPM
age=0.2025s
```

Ten wynik jest **prawidłowy**, ponieważ `age=0.2025 s` jest mniejsze od timeoutu `0.25 s`. Odczyt nie powinien zostać uznany za nieważny przed przekroczeniem timeoutu od ostatniego rzeczywistego zbocza.

Wartość `71.716 Hz / 1434.3 RPM` tuż po STOP jest bardzo bliska wcześniejszemu punktowi oscyloskopowemu `71.937 Hz / 1438.7 RPM` i wskazuje, że wentylator nadal rozpędzał się po pierwszych 5 s. Na tym stanowisku 5 s nie należy więc traktować jako gwarantowanego czasu osiągnięcia prędkości ustalonej.

To jest ważne dla przyszłej diagnostyki `command vs actual`: ewentualny alarm under-speed musi mieć osobny czas rozruchu/stabilizacji i nie może oceniać odchyłki RPM natychmiast po zmianie setpointu.

Ścieżka end-to-end została potwierdzona:

```text
ctl set -> DAC CH1/VOUT1 -> fizyczny wentylator -> TACHO -> GPIO27 -> libgpiod -> estimator -> CoreState.tacho.extract
```

## 7. Korekta estimatora dla stałego runtime

Po przejściu z narzędzia jednorazowego do stałego monitora dodano reset historii okresów po przerwie dłuższej niż timeout. Dzięki temu pierwszy impuls po długim postoju nie zaniża RPM przez potraktowanie czasu postoju jako jednego okresu obrotu.

## 8. Pozostałe checkpointy Stage 1

Przed trwałym włączeniem TACHO w jednostce systemd pozostaje:

1. uruchomić EXTRACT 5 V i dać mu dłuższy czas stabilizacji,
2. po STOP obserwować `CoreState.tacho.extract` do rzeczywistego przejścia `valid=true -> false`, zamiast sprawdzać po stałym czasie od komendy,
3. fizycznie odłączyć przewód TACHO przy pracującym wentylatorze,
4. potwierdzić, że tylko stan TACHO staje się nieważny, natomiast DAC, SENSOR BUS, tryb i setpointy pozostają bez zmian,
5. dopiero po PASS włączyć monitor w trwałym pliku systemd.

Drugi kanał TACHO zostanie zwalidowany dopiero po dostępności drugiego fizycznego wentylatora.
