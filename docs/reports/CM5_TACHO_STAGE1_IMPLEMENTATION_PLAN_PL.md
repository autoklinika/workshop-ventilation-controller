# CM5 TACHO Stage 1 — plan implementacji dwóch wejść prędkości wentylatorów

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Gałąź:** `agent/cm5-tacho-stage1`  
**Bazowy `main`:** `e689a991f9e71bf77f1771ca2cec31cd9b5716f6`

## 1. Cel etapu

Celem Stage 1 jest wprowadzenie do `ventilation-core` niezależnego, diagnostycznego pomiaru rzeczywistej prędkości dwóch wentylatorów EC na podstawie ich sygnałów TACHO.

Etap ma dostarczyć:

- odczyt dwóch wejść GPIO,
- pomiar częstotliwości z detekcji zboczy,
- przeliczenie `Hz -> RPM`,
- podstawowe wygładzenie pomiaru,
- detekcję utraty impulsów,
- publikację danych w `CoreState` i przez istniejące polecenie `status`,
- testy jednostkowe warstwy domenowej i integracji z `VentilationService`,
- narzędzie/tryb diagnostyczny do walidacji na rzeczywistym CM5.

Stage 1 **nie ma jeszcze wpływać na sterowanie wentylatorami ani wymuszać FAULT**. Najpierw należy potwierdzić poprawność obu kanałów na urządzeniu.

## 2. Stan bazowy repozytorium

Na początku etapu potwierdzono, że `main` wskazuje na:

```text
e689a991f9e71bf77f1771ca2cec31cd9b5716f6
CM5 AERO BUS Stage 3B: guarded production control (#19)
```

Aktualne `ventilation-core` posiada:

- DAC DFR0971 jako `VentilationActuator`,
- SENSOR BUS jako osobny monitor/worker,
- AERO BUS jako osobny monitor/worker,
- `CoreState` jako centralny model stanu,
- Unix socket API w `runtime/server.py`, którego `status` serializuje `CoreState.to_dict()`.

TACHO powinno zostać dodane jako **kolejny niezależny monitor wejściowy**, a nie jako część sterownika DAC.

## 3. Aktualny przydział GPIO CM5 wynikający z repozytorium

Aktualnie zajęte linie 40-pin header:

| Funkcja | GPIO | Pin fizyczny |
|---|---:|---:|
| DAC DFR0971 SDA1 | GPIO2 | 3 |
| DAC DFR0971 SCL1 | GPIO3 | 5 |
| SENSOR BUS TXD0 | GPIO14 | 8 |
| SENSOR BUS RXD0 | GPIO15 | 10 |
| AERO BUS TXD4 | GPIO12 | 32 |
| AERO BUS RXD4 | GPIO13 | 33 |

Repozytorium nie przydziela obecnie po stronie CM5 linii `GPIO17` ani `GPIO27`.

## 4. Proponowany pinout TACHO

Dla Stage 1 proponuje się:

| Kanał | GPIO BCM | Pin fizyczny | Status |
|---|---:|---:|---|
| TACHO FAN SUPPLY | **GPIO17** | **11** | proponowany, wymaga walidacji pinmux na CM5 |
| TACHO FAN EXTRACT | **GPIO27** | **13** | proponowany, wymaga walidacji pinmux na CM5 |

Powody wyboru:

- brak konfliktu z przydziałem zapisanym w `docs/PINOUT.md`,
- oba piny są dostępne na standardowym 40-pin header CM5 IO Board,
- nie kolidują z używanym I²C1 ani UART0/UART4,
- są wygodne do prowadzenia jako dwa sąsiednie wejścia cyfrowe.

### Ważne

To jest **przydział projektowy**, jeszcze nie walidacja aktywnego pinmux na uruchomionym CM5.

Przed fizycznym podłączeniem wejść należy na docelowym CM5 potwierdzić co najmniej:

```bash
pinctrl get 17 27
```

oraz stan kontrolerów/linie widziane przez libgpiod, np.:

```bash
gpioinfo
```

Nie należy hardkodować `/dev/gpiochipN`, dopóki rzeczywiste mapowanie na CM5 nie zostanie potwierdzone.

## 5. Zwalidowany tor elektryczny

Dla każdego wentylatora niezależnie:

```text
                      +3.3 V
                         │
                       10 kΩ
                         │
TACHO FAN ───────────────●
                         │
                        1 kΩ
                         │
                         ●──────── GPIO CM5
                         │
                        1 nF
                         │
                        GND

GND FAN ───────────────────────── GND SYSTEM
```

Właściwości zwalidowane oscyloskopowo:

- wyjście TACHO zachowuje się jak open-collector,
- podciągnięcie do 3,3 V działa poprawnie,
- `10 kΩ + 1 kΩ + 1 nF` ogranicza overshoot,
- poziom na przyszłym GPIO wynosi około `0–3,2 V`,
- duty około 50%,
- zakres zmierzony około `19,933–113,28 Hz`,
- **3 impulsy na obrót**,
- `RPM = TACHO_HZ × 20`.

## 6. Architektura software

### 6.1. Warstwa domenowa

Nowy moduł:

```text
src/ventilation_core/domain/tacho.py
```

Proponowane modele:

```text
FanTachoState
- frequency_hz: float | None
- rpm: float | None
- last_edge_monotonic: float | None
- signal_present: bool
- sample_count: int

TachoState
- supply: FanTachoState
- extract: FanTachoState
- ready: bool
- worker_alive: bool
- last_error: str | None
```

Model domenowy nie powinien znać libgpiod ani numeru `/dev/gpiochipN`.

### 6.2. Port aplikacyjny

Do `application/ports.py` należy dodać interfejs:

```text
TachoMonitor
- state() -> TachoState
- health_check() -> None
- close() -> None
```

`VentilationService` otrzyma opcjonalny `tacho_monitor`, analogicznie do SENSOR BUS i AERO BUS.

### 6.3. Infrastruktura GPIO

Nowy moduł:

```text
src/ventilation_core/infrastructure/tacho_monitor.py
```

Odpowiedzialność:

- otwarcie dwóch linii GPIO przez libgpiod,
- konfiguracja obu jako input,
- odbiór zdarzeń jednego typu zbocza dla każdego kanału,
- timestamp zdarzeń zegarem monotonicznym,
- obliczenie okresu między kolejnymi zboczami tego samego kanału,
- wyliczenie częstotliwości,
- wyliczenie RPM,
- timeout braku impulsów,
- przechowywanie ostatniego stabilnego stanu do odczytu przez `VentilationService`.

Preferowane jest mierzenie **jednego typu zbocza** (np. falling edge), żeby zachować bezpośrednio potwierdzone `3 impulsy/obrót` i nie wprowadzać przypadkowego mnożnika ×2.

### 6.4. Model wykonania

Dla Stage 1 nie ma potrzeby osobnego procesu dla każdego kanału.

Wystarczy jeden niezależny monitor obsługujący dwie linie GPIO w jednym wątku roboczym, ponieważ:

- maksymalna zmierzona częstotliwość to tylko około 113 Hz na kanał,
- zdarzenia GPIO są lekkie,
- monitor nie wykonuje operacji sterujących,
- awaria TACHO nie może blokować DAC, SENSOR BUS ani AERO BUS.

Jeżeli praktyczna walidacja libgpiod na CM5 pokaże problem z blokowaniem lub stabilnością, monitor można później przenieść do procesu bez zmiany portu aplikacyjnego.

## 7. Algorytm pomiaru

Dla każdego kanału osobno:

```text
edge[n-1] timestamp
        ↓
edge[n] timestamp
        ↓
period = t[n] - t[n-1]
        ↓
frequency_hz = 1 / period
        ↓
rpm = frequency_hz × 20
```

### 7.1. Wygładzanie

Nie należy uśredniać GPIO przez próbkowanie w pętli.

Proponowany Stage 1:

- przechowywać ostatnie 5–8 poprawnych okresów,
- odrzucać okresy <= 0,
- wyznaczać stabilną wartość z mediany okresów albo odpornej średniej,
- dopiero z wygładzonego okresu wyliczać Hz i RPM.

Mediana jest preferowana na początku, ponieważ pojedynczy fałszywy impuls nie przesuwa wyniku tak silnie jak zwykła średnia.

### 7.2. Timeout sygnału

Przy najniższym zwalidowanym punkcie 1 V otrzymano około 19,933 Hz, czyli poprawne zbocze tego samego typu pojawia się co około 50 ms.

Początkowy timeout Stage 1 może wynosić np. **0,5 s**, czyli około dziesięć okresów przy najniższej zmierzonej prędkości.

Po przekroczeniu timeoutu:

```text
signal_present = false
frequency_hz = 0.0
rpm = 0.0
```

Timeout musi być konfigurowalny, aby później można go dobrać na podstawie testów zatrzymania i rozbiegu.

## 8. Integracja z CoreState

`CoreState` powinien otrzymać:

```text
tacho: TachoState | None
```

`CoreState.to_dict()` powinien publikować nową sekcję bez zmiany istniejących pól:

```json
{
  "tacho": {
    "ready": true,
    "worker_alive": true,
    "last_error": null,
    "supply": {
      "frequency_hz": 71.94,
      "rpm": 1439,
      "signal_present": true,
      "sample_count": 123
    },
    "extract": {
      "frequency_hz": 82.12,
      "rpm": 1642,
      "signal_present": true,
      "sample_count": 126
    }
  }
}
```

Dzięki istniejącemu `status -> CoreState.to_dict()` dane automatycznie staną się dostępne dla klientów Unix socket.

## 9. Integracja z VentilationService

`VentilationService` powinien:

- przyjmować `tacho_monitor: TachoMonitor | None`,
- dołączać `tacho_monitor.state()` do `CoreState`,
- wywoływać `tacho_monitor.health_check()` w istniejącym cyklu health-check,
- zamykać monitor w `close()`.

### Kluczowa zasada Stage 1

Błąd TACHO **nie może**:

- ustawiać `VentilationMode.FAULT`,
- blokować `set_manual()`,
- zerować DAC,
- wpływać na SENSOR BUS,
- wpływać na AERO BUS.

Na tym etapie TACHO jest obserwacją/diagnostyką. Sprzężenie z bezpieczeństwem zostanie zaprojektowane dopiero po walidacji obu kanałów na realnym układzie.

## 10. Konfiguracja CLI

Do `ventilation_core.main` należy docelowo dodać parametry w rodzaju:

```text
--tacho-chip <zwalidowany gpiochip>
--tacho-supply-line 17
--tacho-extract-line 27
--tacho-pulses-per-revolution 3
--tacho-signal-timeout 0.5
--disable-tacho
```

Wartość `3 pulses/revolution` powinna być konfigurowalna, mimo że dla obecnie zbadanego wentylatora została potwierdzona sprzętowo.

## 11. systemd i uprawnienia

Aktualna jednostka:

```text
deploy/systemd/ventilation-core.service
```

ma:

```text
SupplementaryGroups=i2c dialout
```

Przed uruchomieniem libgpiod przez użytkownika `wentylacja` należy zweryfikować właściciela i grupę właściwego `/dev/gpiochipN`.

Jeżeli urządzenie korzysta ze standardowej grupy `gpio`, jednostkę należy rozszerzyć do:

```text
SupplementaryGroups=i2c dialout gpio
```

Zmianę należy wykonać dopiero po sprawdzeniu uprawnień na docelowym CM5.

## 12. Telemetria i Web GUI

Stage 1 powinien najpierw opublikować TACHO w `CoreState`.

Dopiero po walidacji należy rozszerzyć:

1. Web GUI — pokazanie `actual RPM` obok wartości zadanej,
2. CM5 -> AI telemetry — wysyłanie `command_voltage`, `tacho_hz`, `rpm`,
3. diagnostykę — porównanie `expected RPM` z `actual RPM`.

Nie należy mieszać tych zmian z pierwszym uruchomieniem GPIO. Ułatwi to znalezienie ewentualnych problemów sprzętowych i zachowa mały zakres pierwszego PR z kodem.

## 13. Charakterystyka referencyjna

Zwalidowana tabela pierwszego badanego wentylatora:

| Sterowanie | TACHO | RPM |
|---:|---:|---:|
| 1,0 V | 19,933 Hz | 399 |
| 1,5 V | 27,040 Hz | 541 |
| 2,0 V | 33,370 Hz | 667 |
| 3,0 V | 44,921 Hz | 898 |
| 4,0 V | 61,321 Hz | 1226 |
| 5,0 V | 71,937 Hz | 1439 |
| 6,0 V | 82,123 Hz | 1642 |
| 7,0 V | 90,734 Hz | 1815 |
| 8,0 V | 101,090 Hz | 2022 |
| 9,0 V | 109,100 Hz | 2182 |
| 10,0 V | 113,280 Hz | 2266 |

Tabela ma charakter referencyjny. Nie wolno w Stage 1 używać jej jako sztywnej zależności sterującej ani alarmowej.

## 14. Plan walidacji na CM5

### Krok A — pinmux i dostęp

Bez podłączonych linii TACHO:

```bash
pinctrl get 17 27
gpioinfo
id wentylacja
ls -l /dev/gpiochip*
```

Potwierdzić:

- brak funkcji alternatywnej kolidującej z TACHO,
- prawidłowy gpiochip i line offsets,
- uprawnienia użytkownika usługi.

### Krok B — jeden kanał

Podłączyć tylko FAN SUPPLY przez zwalidowany tor `10 kΩ + 1 kΩ + 1 nF`.

Sprawdzić:

- 1 V,
- 5 V,
- 10 V,
- brak fałszywych impulsów przy stałej prędkości,
- zgodność z oscyloskopem w granicach rozsądnej tolerancji.

### Krok C — drugi kanał

Powtórzyć dla FAN EXTRACT.

### Krok D — oba kanały jednocześnie

Uruchomić różne prędkości na obu wentylatorach i potwierdzić brak zamiany kanałów oraz brak utraty zdarzeń.

### Krok E — zatrzymanie i utrata przewodu

Sprawdzić:

- sterowanie 0 V,
- naturalny wybieg wentylatora,
- timeout po zatrzymaniu,
- odłączenie przewodu TACHO przy aktywnym wentylatorze,
- ponowne podłączenie sygnału.

Na tym etapie zdarzenia mają być tylko raportowane; nie wolno automatycznie zatrzymywać systemu.

## 15. Testy software przed uruchomieniem sprzętu

Minimalny zestaw:

- `RPM = Hz × 20`,
- poprawny okres dla kolejnych timestampów,
- filtr medianowy,
- timeout sygnału,
- niezależność kanałów supply/extract,
- serializacja `TachoState.to_dict()`,
- `VentilationService.state()` z TACHO i bez TACHO,
- awaria monitora nie blokuje DAC,
- `close()` zamyka monitor,
- kompatybilność istniejących testów `ventilation-core`.

Po implementacji należy uruchomić pełny zestaw:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

## 16. Kolejność implementacji

1. Zatwierdzić/zwalidować `GPIO17` i `GPIO27` na działającym CM5.
2. Dodać domenę `tacho.py`.
3. Dodać `TachoMonitor` do portów aplikacyjnych.
4. Dodać monitor libgpiod i testowalny algorytm pomiarowy.
5. Wpiąć monitor do `VentilationService` i `CoreState`.
6. Dodać konfigurację CLI.
7. Dostosować systemd po sprawdzeniu rzeczywistych uprawnień `/dev/gpiochip*`.
8. Uruchomić testy jednostkowe.
9. Wykonać walidację jednego kanału na CM5.
10. Wykonać walidację drugiego kanału.
11. Wykonać test obu kanałów równocześnie.
12. Dopiero potem projektować alarmy `command vs actual RPM`, telemetrię i Web GUI.

## 17. Granica Stage 1

Stage 1 jest zakończony dopiero, gdy:

- oba wejścia GPIO są zwalidowane na realnym CM5,
- oba wentylatory raportują stabilne Hz i RPM,
- odczyt nie zakłóca DAC/SENSOR BUS/AERO BUS,
- zatrzymanie i odłączenie sygnału są poprawnie wykrywane,
- `status` zwraca dane obu wentylatorów,
- pełne testy repozytorium przechodzą,
- istniejące sterowanie pozostaje niezmienione.

Dopiero następny etap powinien wykorzystać TACHO do aktywnej diagnostyki i alarmów.
