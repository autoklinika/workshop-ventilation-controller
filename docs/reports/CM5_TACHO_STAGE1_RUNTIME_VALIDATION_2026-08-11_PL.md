# CM5 TACHO Stage 1 — walidacja runtime CoreState

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Host:** `wentylacja` / Raspberry Pi Compute Module 5  
**Gałąź:** `agent/cm5-tacho-stage1`  
**Status:** Stage 1 kanału EXTRACT / GPIO27 — HARDWARE + RUNTIME + PERMANENT DEPLOY PASS.

## 1. Konfiguracja stanowiska

```text
sterowanie: EXTRACT / DAC CH1 / VOUT1 / DB9 pin 5
TACHO:      GPIO27 / physical pin 13 / gpiochip0 offset 27
```

W laboratorium dostępny był jeden fizyczny wentylator EC. GPIO17 / pin 11 pozostaje zarezerwowany dla przyszłego drugiego wentylatora i nie był częścią finalnej walidacji runtime.

`ventilation-core` podczas testów był początkowo uruchomiony z tymczasowym drop-inem systemd w `/run/systemd/system/ventilation-core.service.d/90-tacho-validation.conf` i argumentem `--enable-extract-tacho`. Po zakończeniu walidacji ta konfiguracja została zastąpiona trwałą jednostką z repo.

## 2. Runtime przy STOP — PASS

Po restarcie z monitorem TACHO potwierdzono:

```text
mode=STOP
extract_voltage=0.0
hardware_ready=true
active_alarms=[]
tacho.ready=true
tacho.worker_alive=true
tacho.last_error=null
tacho.extract.valid=false
tacho.extract.frequency_hz=0.0
tacho.extract.rpm=0.0
```

`gpioinfo GPIO27`:

```text
input bias=disabled edges=rising consumer="ventilation-core-extract-tacho"
```

Stały runtime poprawnie przejął GPIO27 i publikował stan STOP bez wpływu na DAC ani alarmy.

## 3. Runtime przy 5 V — PASS end-to-end

Po normalnej komendzie:

```text
supply=0.0 V
extract=5.0 V
```

potwierdzono pełną ścieżkę:

```text
ctl set -> DAC CH1/VOUT1 -> fizyczny wentylator -> TACHO -> GPIO27 -> libgpiod -> estimator -> CoreState.tacho.extract
```

Pierwszy przebieg po nominalnych 5 s stabilizacji dał poprawne `valid=true`, przy czym wentylator nadal dochodził do prędkości ustalonej. Tuż po późniejszym STOP estimator zarejestrował:

```text
71.716 Hz / 1434.3 RPM
```

co jest bardzo bliskie wcześniejszej referencji oscyloskopowej:

```text
71.937 Hz / 1438.7 RPM
```

## 4. Dłuższy przebieg 12 s

Po 12 s stabilizacji i kolejnych pięciu odczytach 1 s otrzymano:

```text
67.895 Hz -> 1357.9 RPM
67.617 Hz -> 1352.3 RPM
67.803 Hz -> 1356.1 RPM
67.979 Hz -> 1359.6 RPM
68.122 Hz -> 1362.4 RPM
```

Średnio około:

```text
67.883 Hz
1357.7 RPM
```

Wszystkie odczyty były `valid=true`, `sample_count=6` i miały małe `age_seconds`. Różnice pomiędzy przebiegami nie wskazują na błąd zliczania impulsów. Kalibracja `command voltage -> expected RPM` nie jest częścią Stage 1.

## 5. Runtime timeout po STOP — PASS

Po komendzie STOP:

```text
mode=STOP cmd=0.0V valid=True  Hz=68.145 RPM=1362.9 age=0.006s
mode=STOP cmd=0.0V valid=True  Hz=69.395 RPM=1387.9 age=0.058s
mode=STOP cmd=0.0V valid=False Hz=0.000  RPM=0.0    age=0.314s
```

Następnie `valid=false`, `0 Hz / 0 RPM` utrzymywało się do końca obserwacji, a `age_seconds` wzrosło do około `5.966 s`.

Timeout `0.25 s` działa zgodnie z projektem:

- przy `age=0.058 s` odczyt pozostaje ważny,
- przy `age=0.314 s` jest już nieważny,
- brak fałszywego powrotu do `valid=true` po zaniku impulsów.

## 6. Odłączenie sygnału TACHO przy zachowaniu sterowania — PASS

Odłączono fizycznie wyłącznie przewód sygnałowy TACHO. Zasilanie wentylatora, wspólna masa i sterowanie 0–10 V pozostały bez zmian.

Przed startem:

```text
mode=STOP
extract_voltage=0.0
tacho_valid=false
tacho_rpm=0.0
hardware_ready=true
active_alarms=[]
```

Następnie wydano `extract=5.0 V`. Użytkownik potwierdził fizycznie, że wentylator normalnie pracował.

Po około 8 s runtime raportował:

```text
mode=MANUAL
extract_voltage=5.0
hardware_ready=true
output_state_known=true
active_alarms=[]
sensor_bus_ready=true
tacho_ready=true
tacho_worker_alive=true
tacho_last_error=null
tacho_valid=false
tacho_hz=0.0
tacho_rpm=0.0
```

Długi `tacho_age` był oczekiwany — pole oznacza wiek ostatniego rzeczywistego zbocza.

Wniosek: utrata TACHO jest poprawnie odseparowana od sterowania. Brak sygnału nie zatrzymuje wentylatora, nie generuje `FAULT` i nie wpływa na SENSOR BUS.

## 7. Odzyskanie sygnału bez restartu core — PASS

Po zatrzymaniu wentylatora przewód TACHO został ponownie podłączony do GPIO27. `ventilation-core` nie był restartowany.

Stan przed ponownym uruchomieniem:

```text
worker_alive: True
last_error: None
valid: False
Hz: 0.0
RPM: 0.0
age: 817.683 s
```

Po `extract=5.0 V` ten sam worker automatycznie odzyskał sygnał i raportował kolejno:

```text
53.650 Hz -> 1073.0 RPM
62.562 Hz -> 1251.2 RPM
64.387 Hz -> 1287.7 RPM
64.873 Hz -> 1297.5 RPM
65.246 Hz -> 1304.9 RPM
```

W każdej próbce:

```text
valid=true
sample_count=6
worker_alive=true
last_error=null
```

Potwierdza to automatyczne przejście `valid=false -> valid=true` po przywróceniu fizycznego sygnału, bez restartu procesu i bez ręcznej rekonfiguracji GPIO.

## 8. Zbiorczy wynik Stage 1 dla EXTRACT

Zwalidowano na rzeczywistym CM5:

- tor wejściowy `10 kΩ pull-up do 3,3 V + 1 kΩ + 1 nF`,
- GPIO27 / pin 13 / gpiochip0 offset 27,
- wejście z `bias=disabled`, zbocza narastające,
- 3 impulsy/obrót,
- `RPM = Hz * 20`,
- brak fałszywych zboczy przy STOP,
- realny pomiar Hz/RPM,
- timeout `0.25 s`,
- publikację `CoreState.tacho.extract`,
- pełną ścieżkę end-to-end od komendy DAC do feedbacku RPM,
- brak wpływu utraty TACHO na DAC, tryb sterowania, SENSOR BUS i alarmy,
- automatyczne odzyskanie sygnału po ponownym podłączeniu,
- `159/159` testów jednostkowych na CM5.

## 9. Trwałe wdrożenie systemd — PASS

Na branchu `agent/cm5-tacho-stage1` zwalidowano commit:

```text
7186d2dd69509e6d2a104857bbb1260b32bc07f4
```

Przed wdrożeniem pełny zestaw testów ponownie zakończył się wynikiem:

```text
Ran 159 tests
OK
```

Następnie:

1. wykonano bezpieczny `ventilation_core.ctl stop`,
2. wykonano backup dotychczasowej jednostki do `/tmp/ventilation-core.service.before-tacho`,
3. zainstalowano `deploy/systemd/ventilation-core.service` do `/etc/systemd/system/ventilation-core.service`,
4. usunięto tymczasowy drop-in `/run/systemd/system/ventilation-core.service.d/90-tacho-validation.conf`,
5. wykonano `systemctl daemon-reload`,
6. zrestartowano `ventilation-core.service`.

Efektywna trwała jednostka zawiera:

```text
--enable-extract-tacho
--tacho-chip /dev/gpiochip0
--extract-tacho-line GPIO27
--tacho-timeout 0.25
--tacho-averaging-periods 6
```

Po trwałym restarcie przy STOP:

```text
service=active
mode=STOP
hardware_ready=true
active_alarms=[]
tacho_ready=true
worker_alive=true
last_error=null
valid=false
Hz=0.0
RPM=0.0
```

`gpioinfo GPIO27` potwierdziło:

```text
input bias=disabled edges=rising consumer="ventilation-core-extract-tacho"
```

Końcowy smoke test po trwałym deployu, przy `extract=5.0 V`, dał:

```text
mode=MANUAL
extract_voltage=5.0
hardware_ready=true
active_alarms=[]
tacho_valid=true
tacho_hz=65.121
tacho_rpm=1302.4
worker_alive=true
last_error=null
```

Po końcowym STOP sterowanie wróciło do `0.0 V`, `hardware_ready=true`, `output_state_known=true`, brak aktywnych alarmów, SENSOR BUS pozostał gotowy. W bezpośredniej odpowiedzi po STOP TACHO nadal było chwilowo `valid=true` z małym `age_seconds`, co jest oczekiwanym skutkiem timeoutu `0.25 s` i zostało wcześniej zwalidowane osobnym testem zaniku.

Log po restarcie nie wykazał błędów startu core; SENSOR BUS i AERO BUS workery zostały uruchomione, a socket runtime został poprawnie wystawiony.

**Kanał EXTRACT / GPIO27 jest trwale uruchomiony jako read-only TACHO feedback w `ventilation-core.service`. Stage 1 jest zakończony wynikiem PASS.**

## 10. Granice Stage 1

W tym etapie TACHO pozostaje wyłącznie feedbackiem. Nie wdrażamy jeszcze:

- alarmu braku obrotów przy aktywnej komendzie,
- diagnostyki under-speed / over-speed,
- charakterystyki `0–10 V -> expected RPM`,
- diagnostyki trendu łożysk / tarcia,
- sterowania zamkniętego po RPM,
- drugiego kanału TACHO.

Drugi kanał będzie zwalidowany po dostępności drugiego fizycznego wentylatora.