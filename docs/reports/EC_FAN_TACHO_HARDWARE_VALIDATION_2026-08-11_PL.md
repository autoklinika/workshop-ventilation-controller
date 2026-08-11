# Walidacja sprzętowa sygnału TACHO wentylatorów EC

**Projekt:** Workshop Ventilation Controller  
**Data pomiarów:** 2026-08-11  
**Status:** walidacja sprzętowa zakończona; gotowe do walidacji wejść na CM5.

## 1. Cel

Celem było ustalenie właściwości elektrycznych wyjścia TACHO wentylatora EC oraz przygotowanie bezpiecznego toru wejściowego dla Raspberry Pi Compute Module 5.

## 2. Wynik identyfikacji wyjścia

Wyjście TACHO zachowuje się jak **open-collector / otwarty kolektor**. Stan LOW jest realizowany przez zwarcie linii do masy, a stan HIGH powstaje przez zewnętrzny rezystor pull-up.

Potwierdzono poprawną pracę przy podciągnięciu do **3,3 V**, dzięki czemu nie jest potrzebny konwerter poziomów 10 V -> 3,3 V.

## 3. Zwalidowany tor wejściowy

Dla każdego wentylatora należy zastosować osobny tor:

```text
                      +3.3 V
                         |
                       10 kΩ
                         |
TACHO FAN --------------+
                         |
                        1 kΩ
                         |
                         +---------- GPIO_TACHO CM5
                         |
                        1 nF
                         |
                        GND

GND FAN ----------------------------- GND SYSTEM
```

Elementy:

- pull-up: **10 kΩ do 3,3 V**,
- rezystor szeregowy przed GPIO: **1 kΩ**,
- kondensator: **1 nF ceramiczny, niepolaryzowany**,
- wspólna masa wentylatora i CM5.

Podczas prób źródłem 3,3 V był **DFRobot DFR0570**. Nie oznacza to konieczności użycia DFR0570 w finalnym torze TACHO; finalne źródło 3,3 V należy traktować jako element projektu połączeń CM5.

## 4. Porównanie wariantów pull-up i filtracji

### 22 kΩ do 3,3 V

Przykładowo:

- częstotliwość: 117,23 Hz,
- Vtop: 3,0444 V,
- Vmax: 3,7103 V,
- Vmin: -0,3806 V,
- rise time: około 162 µs,
- fall time: około 1,42 µs.

### 10 kΩ do 3,3 V

Przykładowo:

- Vtop: 3,1395 V,
- Vmax: 3,8055 V,
- Vmin: -190 mV,
- częstotliwość: 109,70 Hz,
- rise time: 88,84 µs,
- fall time: 1,52 µs.

Zmiana 22 kΩ -> 10 kΩ skróciła zbocze narastające bez pogorszenia podstawowych parametrów. Prąd pull-up w stanie LOW wynosi około 0,33 mA.

### 10 kΩ + 1 kΩ + 1 nF

Po dodaniu filtra:

- częstotliwość: 115,12 Hz,
- Vtop: 3,0444 V,
- Vmax: 3,2346 V,
- Vmin: -95,1 mV,
- Vpp: 3,3298 V,
- rise time: 93,76 µs,
- fall time: 3,44 µs,
- overshoot: 6,25%,
- duty: około 50%.

Filtr ograniczył Vmax z około 3,81 V do około 3,23 V i zmniejszył ujemną szpilkę około dwukrotnie.

## 5. Liczba impulsów na obrót

Potwierdzono:

**3 impulsy TACHO na jeden obrót.**

Wobec tego:

```text
RPM = frequency_Hz * 60 / 3
RPM = frequency_Hz * 20
```

## 6. Zmierzona charakterystyka

| Sterowanie | TACHO | Obliczone RPM |
|---:|---:|---:|
| 1,0 V | 19,933 Hz | 399 RPM |
| 1,5 V | 27,040 Hz | 541 RPM |
| 2,0 V | 33,370 Hz | 667 RPM |
| 3,0 V | 44,921 Hz | 898 RPM |
| 4,0 V | 61,321 Hz | 1226 RPM |
| 5,0 V | 71,937 Hz | 1439 RPM |
| 6,0 V | 82,123 Hz | 1642 RPM |
| 7,0 V | 90,734 Hz | 1815 RPM |
| 8,0 V | 101,090 Hz | 2022 RPM |
| 9,0 V | 109,100 Hz | 2182 RPM |
| 10,0 V | 113,280 Hz | 2266 RPM |

Pierwszy pomiar pierwotnie opisany jako 1,0 V był faktycznie wykonany przy 1,5 V. Punkt 1,0 V został następnie zmierzony osobno.

## 7. Właściwości sygnału w całym zakresie

W całym zakresie sterowania zmienia się głównie częstotliwość. Parametry elektryczne pozostają stabilne:

- HIGH około 3,1-3,2 V,
- LOW około 0 V,
- duty około 50%,
- rise time około 105-116 µs w serii pomiarowej,
- fall time około 3,7-3,9 µs w serii pomiarowej.

CM5 ma więc mierzyć częstotliwość/okres impulsów, a nie amplitudę sygnału.

## 8. Znaczenie dla oprogramowania

Dla każdego wentylatora należy przechowywać niezależnie wartość zadaną i sprzężenie zwrotne, np.:

```text
fan_1.command_percent
fan_1.command_voltage
fan_1.tacho_hz
fan_1.rpm

fan_2.command_percent
fan_2.command_voltage
fan_2.tacho_hz
fan_2.rpm
```

Początkowa implementacja ma realizować:

```text
GPIO edge
  -> timestamp
  -> period/frequency
  -> RPM = frequency * 20
```

Dopiero po walidacji rzeczywistych odczytów na CM5 należy dodawać expected RPM, tolerancje i alarmy.

## 9. Charakterystyka referencyjna

Zmierzona tabela 1-10 V jest punktem startowym diagnostyki, ale nie należy kodować jej jako ścisłego wymagania. RPM może zależeć m.in. od oporów instalacji, napięcia zasilania, temperatury i konkretnego egzemplarza wentylatora.

Docelowa diagnostyka powinna pracować na `expected_rpm` i tolerancji.

## 10. Elementy pomiarowe

- wentylator EC ze sterowaniem 0-10 V i wyjściem TACHO,
- oscyloskop Rigol MSO5104, 4 kanały, 100 MHz, 8 GSa/s,
- DFRobot DFR0570 jako laboratoryjne źródło 3,3 V,
- rezystory 22 kΩ, 10 kΩ, 1 kΩ,
- kondensator 1 nF ceramiczny.

## 11. Handoff

Walidacja sprzętowa potwierdziła, że tor `10 kΩ pull-up do 3,3 V + 1 kΩ + 1 nF` daje stabilny sygnał logiczny odpowiedni do dalszej walidacji na GPIO CM5. Software powinien przyjąć **3 impulsy/obrót** oraz przelicznik **RPM = Hz × 20**.
