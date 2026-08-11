# Walidacja sygnału TACHO wentylatora EC i przygotowanie wejścia dla CM5

**Projekt:** Workshop Ventilation Controller  
**Data pomiarów:** 2026-08-11  
**Zakres:** sprzętowa identyfikacja sygnału TACHO wentylatora EC, dobór podciągania i filtracji oraz pomiary TACHO dla sterowania 0–10 V.  
**Cel następnego etapu:** implementacja pomiaru prędkości dwóch wentylatorów przez Raspberry Pi Compute Module 5.

## 1. Cel przeprowadzonych testów

Celem było ustalenie rzeczywistych właściwości wyjścia TACHO wentylatora przed podłączeniem go do CM5.

Do ustalenia były przede wszystkim:

- rodzaj elektryczny wyjścia TACHO,
- wymagane podciągnięcie,
- poziomy napięć,
- częstotliwość sygnału,
- liczba impulsów przypadających na obrót,
- zależność częstotliwości od sterowania wentylatora 0–10 V,
- sposób bezpiecznego doprowadzenia sygnału do GPIO CM5,
- konieczność zastosowania filtracji przeciwzakłóceniowej.

Pomiary wykonano oscyloskopem **Rigol MSO5104, 4 kanały, 100 MHz, 8 GSa/s**.

## 2. Identyfikacja wyjścia TACHO

Pierwsze próby bez właściwego podciągnięcia dawały nieczytelny przebieg. Po zastosowaniu zewnętrznego rezystora podciągającego uzyskano stabilny sygnał prostokątny.

Zachowanie wyjścia wskazuje na wyjście typu:

**open-collector / otwarty kolektor**.

Elektronika wentylatora realizuje stan LOW przez zwieranie linii TACHO do masy, natomiast stan HIGH jest tworzony przez zewnętrzny rezystor pull-up.

Dzięki temu poziom logiczny dla CM5 można ustalić przez podciągnięcie TACHO bezpośrednio do **3,3 V**, zamiast konwertować sygnał 10 V na 3,3 V.

## 3. Pierwszy test — pull-up 22 kΩ do +10 V

Początkowo zastosowano:

```text
+10 V
  │
 22 kΩ
  │
  ├──── TACHO FAN
  │
oscyloskop
```

Przy pełnej prędkości uzyskano stabilny przebieg prostokątny.

Po prawidłowym ustawieniu sondy i zakresu oscyloskopu zmierzono m.in.:

- `Vtop ≈ 9,799 V`,
- `Vbase ≈ 0 V`,
- `Vmax ≈ 10,655 V`,
- `Vmin ≈ -0,476 V`,
- `Vpp ≈ 11,131 V`,
- częstotliwość około **113 Hz**,
- duty około **50%**.

Potwierdziło to, że rezystor pull-up rzeczywiście określa poziom HIGH.

**TACHO podciągniętego do 10 V nie wolno bezpośrednio podłączać do GPIO CM5.**

### Uwaga dotycząca pomiaru

Podczas pierwszych pomiarów pojawił się pozorny poziom około 1 V. Wynikało to z ustawienia sondy **×10** i niespójności konfiguracji pomiaru. Po przejściu na właściwe ustawienia potwierdzono rzeczywisty przebieg około **0–10 V**.

## 4. Zasilanie 3,3 V do prób

Do przygotowania napięcia **3,3 V** wykorzystano moduł:

**DFRobot DFR0570**.

Moduł został wykorzystany jako źródło 3,3 V dla rezystora pull-up podczas prób laboratoryjnych.

Istotne było zastosowanie wspólnej masy pomiędzy:

- wentylatorem,
- źródłem 3,3 V,
- układem pomiarowym.

DFR0570 był tutaj jedynie wygodnym laboratoryjnym źródłem 3,3 V. Nie przesądza to, że musi znaleźć się w finalnym torze TACHO. Docelowe źródło 3,3 V należy ustalić przy finalnym okablowaniu CM5.

## 5. Test pull-up 22 kΩ do 3,3 V

Zastosowano:

```text
3.3 V
  │
 22 kΩ
  │
  └──── TACHO
```

Uzyskano prawidłowy sygnał logiczny około **0–3,3 V**.

Przykładowy pomiar:

- częstotliwość: **117,23 Hz**,
- `Vtop = 3,0444 V`,
- `Vmax = 3,7103 V`,
- `Vmin = -0,3806 V`,
- duty ≈ **49/51%**,
- Rise Time ≈ **162 µs**,
- Fall Time ≈ **1,42 µs**.

### Wniosek

Eksperyment potwierdził, że wyjście TACHO poprawnie współpracuje z pull-up do **3,3 V**.

Nie jest potrzebny klasyczny konwerter poziomów 10 V → 3,3 V.

22 kΩ działał, ale stosunkowo duża rezystancja powodowała wolniejsze zbocze narastające.

## 6. Zmiana pull-up z 22 kΩ na 10 kΩ

Następnie zastosowano **10 kΩ do 3,3 V**.

Przykładowy wynik:

- `Vtop = 3,1395 V`,
- `Vbase = 0 V`,
- `Vmax = 3,8055 V`,
- `Vmin = -190 mV`,
- częstotliwość = **109,70 Hz**,
- Rise Time = **88,84 µs**,
- Fall Time = **1,52 µs**,
- duty ≈ **49/51%**.

Zmiana z 22 kΩ na 10 kΩ skróciła czas narastania mniej więcej z:

**162 µs → 89 µs**.

Prąd pull-up w stanie LOW wynosi około:

```text
I = 3,3 V / 10 kΩ ≈ 0,33 mA
```

### Decyzja

**10 kΩ przyjęto jako preferowaną wartość rezystora pull-up.**

## 7. Dodanie ochrony i filtracji wejścia

Przy samym pull-up 10 kΩ zaobserwowano krótkotrwały overshoot sięgający około **3,8 V**.

Przetestowano więc tor wejściowy:

- pull-up: **10 kΩ**,
- rezystor szeregowy do przyszłego GPIO: **1 kΩ**,
- kondensator do GND: **1 nF ceramiczny**.

Kondensator:

- **1 nF**,
- ceramiczny,
- niepolaryzowany,
- typowe oznaczenie: **102**.

Schemat zwalidowanego układu:

```text
                     +3.3 V
                        │
                      10 kΩ
                        │
TACHO FAN ──────────────●
                        │
                       1 kΩ
                        │
                        ●──────── przyszłe GPIO CM5
                        │
                       1 nF
                        │
                       GND

GND FAN ─────────────────────── wspólna GND
```

Oscyloskop podczas walidacji był podłączony **za rezystorem 1 kΩ**, czyli w punkcie odpowiadającym przyszłemu wejściu GPIO CM5.

## 8. Wynik działania filtra 1 kΩ + 1 nF

Po dodaniu filtra otrzymano:

- częstotliwość: **115,12 Hz**,
- `Vtop = 3,0444 V`,
- `Vbase = 0 V`,
- `Vmax = 3,2346 V`,
- `Vmin = -95,1 mV`,
- `Vpp = 3,3298 V`,
- Rise Time = **93,76 µs**,
- Fall Time = **3,44 µs**,
- overshoot = **6,25%**,
- duty ≈ **49,4/50,6%**.

Porównanie:

| Parametr | 10 kΩ bez filtra | 10 kΩ + 1 kΩ + 1 nF |
|---|---:|---:|
| Vtop | 3,1395 V | 3,0444 V |
| Vmax | 3,8055 V | **3,2346 V** |
| Vmin | −190 mV | **−95 mV** |
| Overshoot | 21,2% | **6,25%** |
| Rise Time | 88,84 µs | 93,76 µs |
| Fall Time | 1,52 µs | 3,44 µs |

Filtr bardzo skutecznie ograniczył szpilki napięciowe, praktycznie nie wpływając na możliwość pomiaru częstotliwości.

### Decyzja sprzętowa

Jako aktualny zwalidowany punkt wyjścia dla wejścia TACHO przyjmujemy:

**10 kΩ pull-up do 3,3 V + 1 kΩ szeregowo + 1 nF ceramiczny do GND.**

Nie ma obecnie przesłanek do dalszej zmiany tych wartości.

## 9. Pomiary całego zakresu sterowania 0–10 V

Po przygotowaniu toru wejściowego przeprowadzono serię pomiarów częstotliwości TACHO przy kolejnych napięciach sterujących wentylatorem.

Zmierzono punkty:

**1,0; 1,5; 2; 3; 4; 5; 6; 7; 8; 9; 10 V.**

Ważna korekta: pierwsze zdjęcie opisane początkowo jako 1 V było w rzeczywistości wykonane przy **1,5 V**. Następnie wykonano osobny, właściwy pomiar dla **1,0 V**.

| Sterowanie 0–10 V | TACHO | Okres | Duty HIGH |
|---:|---:|---:|---:|
| **1,0 V** | **19,933 Hz** | 50,167 ms | 49,905% |
| **1,5 V** | **27,040 Hz** | 36,983 ms | 49,882% |
| **2,0 V** | **33,370 Hz** | 29,967 ms | 49,851% |
| **3,0 V** | **44,921 Hz** | 22,261 ms | 49,777% |
| **4,0 V** | **61,321 Hz** | 16,307 ms | 49,705% |
| **5,0 V** | **71,937 Hz** | 13,900 ms | 49,657% |
| **6,0 V** | **82,123 Hz** | 12,176 ms | 49,557% |
| **7,0 V** | **90,734 Hz** | 11,021 ms | 49,503% |
| **8,0 V** | **101,09 Hz** | 9,8916 ms | 49,463% |
| **9,0 V** | **109,10 Hz** | 9,1652 ms | 49,443% |
| **10,0 V** | **113,28 Hz** | 8,8273 ms | 49,513% |

## 10. Stabilność elektryczna TACHO w całym zakresie

W całej serii zmienia się częstotliwość, natomiast elektryczne parametry sygnału pozostają praktycznie niezmienne.

Typowe wartości:

- `Vtop ≈ 3,17–3,19 V`,
- `Vbase ≈ 0,095 V`,
- `Vmax ≈ 3,29–3,31 V`,
- `Vmin ≈ 0,024 V`,
- Rise Time ≈ **105–116 µs**,
- Fall Time ≈ **3,7–3,9 µs**,
- duty ≈ **50%**.

CM5 nie będzie musiał dostosowywać sposobu odczytu TACHO zależnie od prędkości wentylatora. W całym zmierzonym zakresie otrzymujemy zasadniczo ten sam sygnał logiczny 3,3 V, a informacja o prędkości jest zakodowana w jego **częstotliwości**.

## 11. Liczba impulsów na obrót

Ustalono, że wentylator generuje:

**3 impulsy TACHO na jeden pełny obrót.**

W związku z tym:

```text
RPM = frequency_Hz × 60 / 3
RPM = frequency_Hz × 20
```

Jest to kluczowy przelicznik dla przyszłego oprogramowania CM5.

## 12. Charakterystyka sterowanie → RPM

| Sterowanie | TACHO | Obliczone RPM |
|---:|---:|---:|
| **1,0 V** | 19,933 Hz | **399 RPM** |
| **1,5 V** | 27,040 Hz | **541 RPM** |
| **2,0 V** | 33,370 Hz | **667 RPM** |
| **3,0 V** | 44,921 Hz | **898 RPM** |
| **4,0 V** | 61,321 Hz | **1226 RPM** |
| **5,0 V** | 71,937 Hz | **1439 RPM** |
| **6,0 V** | 82,123 Hz | **1642 RPM** |
| **7,0 V** | 90,734 Hz | **1815 RPM** |
| **8,0 V** | 101,09 Hz | **2022 RPM** |
| **9,0 V** | 109,10 Hz | **2182 RPM** |
| **10,0 V** | 113,28 Hz | **2266 RPM** |

Wzór dla CM5:

```text
RPM = frequency_Hz × 20
```

Przykład:

```text
113.28 Hz × 20 = 2265.6 RPM
```

## 13. Charakterystyka wentylatora

Pomiar pokazuje wyraźną i monotoniczną zależność:

**większe napięcie sterujące → większa częstotliwość TACHO → większe RPM.**

Nie należy jednak zakładać idealnej liniowości funkcji `0–10 V → RPM`.

Szczególnie w górnym zakresie widać stopniowe dochodzenie do maksymalnej prędkości:

- 7 V → ~1815 RPM,
- 8 V → ~2022 RPM,
- 9 V → ~2182 RPM,
- 10 V → ~2266 RPM.

Zmierzona tabela powinna stanowić początkową charakterystykę referencyjną.

## 14. Co CM5 będzie faktycznie mierzył

GPIO będzie otrzymywało przebieg prostokątny około:

```text
LOW  ≈ 0 V
HIGH ≈ 3.1–3.2 V
```

Oprogramowanie ma mierzyć:

- zbocza,
- częstotliwość lub okres,
- poprawność występowania impulsów.

Następnie:

```text
TACHO GPIO
    ↓
liczenie impulsów / pomiar okresu
    ↓
częstotliwość [Hz]
    ↓
RPM = Hz × 20
    ↓
rzeczywista prędkość wentylatora
```

## 15. Rekomendowany sposób pomiaru w oprogramowaniu

Przy częstotliwościach około **20–115 Hz** nie ma potrzeby szybkiego odpytywania GPIO w pętli użytkownika.

Preferowane jest wykorzystanie mechanizmu detekcji zboczy / zdarzeń GPIO.

Jeżeli zmierzony zostanie okres `T` w sekundach:

```text
frequency_Hz = 1 / T
RPM = 20 / T
```

W praktycznej implementacji należy uśredniać kilka kolejnych okresów lub używać odpowiednio dobranego okna czasowego, aby prezentowane RPM nie oscylowało od pojedynczego pomiaru.

## 16. Diagnostyka, którą umożliwia TACHO

CM5 będzie znał jednocześnie wartość zadaną i rzeczywistą:

```text
fan_command
fan_rpm
```

Pozwala to wykrywać m.in.:

- wentylator zatrzymany mimo aktywnego sterowania,
- brak TACHO,
- zerwany przewód TACHO,
- wentylator obracający się zbyt wolno,
- wentylator zablokowany mechanicznie,
- problemy z zasilaniem wentylatora,
- narastające opory mechaniczne,
- pogarszanie się stanu łożysk,
- odchylenie rzeczywistych RPM od oczekiwanej charakterystyki,
- niestabilność prędkości,
- nieoczekiwane zatrzymanie podczas pracy.

Powinno to zostać wykorzystane przez `ventilation-core` i warstwę diagnostyczną.

## 17. Ważne rozróżnienie dla software'u

Nie należy traktować napięcia 0–10 V jako rzeczywistej prędkości wentylatora.

Przykładowo:

```text
command = 50%
```

oznacza jedynie polecenie sterujące.

Natomiast:

```text
RPM = 1439
```

jest rzeczywistą informacją zwrotną.

Docelowy model danych powinien przechowywać obie wartości niezależnie, np.:

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

## 18. Charakterystyka referencyjna jako punkt startowy diagnostyki

Tabela zmierzona podczas testu może zostać wykorzystana jako **pierwsza charakterystyka referencyjna wentylatora**.

Nie należy jednak kodować jej jako sztywnego wymogu typu:

```text
5 V = dokładnie 1439 RPM
```

Rzeczywiste RPM mogą zależeć od:

- warunków przepływu,
- oporów kanałów,
- temperatury,
- napięcia zasilania,
- konkretnego egzemplarza wentylatora,
- warunków pracy instalacji.

Lepszym rozwiązaniem będzie późniejsze zdefiniowanie:

```text
expected_rpm
tolerance
```

i diagnostyki na podstawie dopuszczalnego przedziału.

## 19. Elementy użyte podczas walidacji

### Wentylator EC

- sterowanie analogowe 0–10 V,
- wyjście TACHO,
- ustalone **3 impulsy na obrót**.

### Oscyloskop

- Rigol MSO5104,
- 4 kanały,
- 100 MHz,
- 8 GSa/s.

### Źródło 3,3 V podczas prób

- DFRobot **DFR0570**.

### Tor TACHO

- rezystor pull-up: **10 kΩ**,
- rezystor szeregowy przed GPIO: **1 kΩ**,
- kondensator filtrujący: **1 nF ceramiczny, niepolaryzowany**.

Wcześniej testowano również:

- **22 kΩ do 10 V**,
- **22 kΩ do 3,3 V**.

Na podstawie pomiarów wybrano **10 kΩ do 3,3 V**.

## 20. Aktualny schemat referencyjny TACHO

Dla jednego wentylatora:

```text
                      +3.3 V
                         │
                       10 kΩ
                         │
TACHO FAN ───────────────●
                         │
                        1 kΩ
                         │
                         ●──────────── GPIO_TACHO CM5
                         │
                        1 nF
                         │
                        GND

GND FAN ────────────────────────────── GND SYSTEM
```

Dla dwóch wentylatorów należy zastosować **dwa niezależne takie tory**, po jednym na każde TACHO.

## 21. Status walidacji sprzętowej

### Potwierdzone

- TACHO generuje stabilny przebieg prostokątny.
- Wyjście współpracuje z zewnętrznym pull-up.
- Pull-up może być wykonany do 3,3 V.
- Pull-up 10 kΩ działa poprawnie.
- Filtr `1 kΩ + 1 nF` działa poprawnie.
- Filtr znacząco ogranicza overshoot.
- Amplituda pozostaje stabilna w całym zmierzonym zakresie prędkości.
- Duty pozostaje około 50%.
- Częstotliwość zmienia się wraz z rzeczywistą prędkością.
- Wentylator generuje **3 impulsy/obrót**.
- Obowiązuje przelicznik `RPM = frequency_Hz × 20`.
- Zmierzono charakterystykę dla sterowania **1–10 V**, dodatkowo punkt **1,5 V**.

## 22. Czego jeszcze nie należy uznawać za zakończone

Przed implementacją produkcyjną na CM5 trzeba jeszcze ustalić lub zwalidować:

- konkretne GPIO dla TACHO FAN 1,
- konkretne GPIO dla TACHO FAN 2,
- aktualny pinmux tych GPIO na działającym CM5,
- sposób wykorzystania GPIO w Linuxie,
- warstwę abstrakcji w `ventilation-core`,
- sposób filtrowania/uśredniania RPM w software,
- timeout braku impulsów,
- progi diagnostyczne,
- zachowanie systemu przy `command > 0`, ale `RPM = 0`,
- tolerancję różnicy `expected RPM ↔ actual RPM`,
- zachowanie przy bardzo małych prędkościach,
- zachowanie po zatrzymaniu wentylatora,
- sposób publikacji RPM do Web GUI/API/telemetrii.

Nie należy zgadywać pinoutu. Kolejny etap musi oprzeć się na rzeczywistym przydziale GPIO w aktualnym repozytorium oraz walidacji pinmux na docelowym CM5.

## 23. Rekomendacja dla implementacji CM5

Pierwszy etap software'u powinien być możliwie prosty i diagnostyczny:

```text
GPIO edge
   ↓
timestamp
   ↓
period
   ↓
frequency
   ↓
RPM = frequency × 20
```

Dopiero po potwierdzeniu rzeczywistych odczytów obu wentylatorów na CM5 należy dodawać:

```text
uśrednianie
↓
expected RPM
↓
tolerancje
↓
alarmy
↓
diagnostyka
↓
Web GUI / telemetry
```

Dzięki temu warstwa sprzętowa i pomiarowa zostanie oddzielona od późniejszej logiki diagnostycznej.

## 24. Handoff

Aktualny zwalidowany interfejs TACHO:

```text
FAN TACHO
   │
   ├── open-collector
   │
   ├── 3 pulses / revolution
   │
   ▼
10 kΩ pull-up → 3.3 V
   │
   ▼
1 kΩ series
   │
   ├──── GPIO CM5
   │
  1 nF ceramic
   │
  GND
```

Konwersja:

```text
RPM = TACHO_HZ × 20
```

Zmierzony zakres:

```text
1.0 V  →  19.933 Hz  →   ~399 RPM
1.5 V  →  27.040 Hz  →   ~541 RPM
2.0 V  →  33.370 Hz  →   ~667 RPM
3.0 V  →  44.921 Hz  →   ~898 RPM
4.0 V  →  61.321 Hz  →  ~1226 RPM
5.0 V  →  71.937 Hz  →  ~1439 RPM
6.0 V  →  82.123 Hz  →  ~1642 RPM
7.0 V  →  90.734 Hz  →  ~1815 RPM
8.0 V  → 101.090 Hz  →  ~2022 RPM
9.0 V  → 109.100 Hz  →  ~2182 RPM
10.0 V → 113.280 Hz  →  ~2266 RPM
```

Po filtracji poziom logiczny w punkcie przyszłego GPIO został zwalidowany oscyloskopowo jako stabilny sygnał około **0–3,2 V**, z duty około **50%** i bez wcześniejszych dużych przepięć.

**Sprzętową walidację TACHO uznaje się za zakończoną na potrzeby rozpoczęcia implementacji po stronie CM5.**
