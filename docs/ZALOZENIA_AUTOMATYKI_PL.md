# Założenia automatyki

## Status dokumentu

Dokument definiuje aktualne założenia projektowe automatyki Workshop Ventilation Controller uzgodnione podczas prac koncepcyjnych rozpoczętych 2026-08-12 i rozszerzone 2026-08-27.

Nie jest to jeszcze finalna specyfikacja progów ani dokument potwierdzający zgodność BHP. Wartości opisane jako **progi procesowe** są punktami startowymi do implementacji i późniejszego strojenia na podstawie pomiarów z rzeczywistych pomieszczeń.

---

## 1. Cel automatyki

Automatyka ma jednocześnie realizować trzy cele:

1. chronić ludzi przed niebezpiecznym pogorszeniem jakości powietrza,
2. zapewniać świeże powietrze i skuteczne usuwanie zanieczyszczeń,
3. ograniczać niepotrzebne straty ciepła, szczególnie zimą.

Priorytety są jednoznaczne:

**BEZPIECZEŃSTWO > JAKOŚĆ POWIETRZA > TEMPERATURA / ENERGOOSZCZĘDNOŚĆ**.

Temperatura może ograniczać wentylację tylko wtedy, kiedy jakość powietrza na to pozwala. Ochrona przed wychłodzeniem nie może zablokować wentylacji wymaganej ze względów bezpieczeństwa.

---

## 2. Dwa różne przypadki pomieszczeń

### 2.1. Pomieszczenie z lutowaniem i rekuperatorem

Pomieszczenie z procesem lutowania posiada rekuperator.

W tym przypadku bilans cieplny nie jest głównym problemem projektowym automatyki wentylatorów, ponieważ odzysk ciepła jest realizowany przez rekuperator. Sterowanie może koncentrować się przede wszystkim na:

- jakości powietrza,
- wykrywaniu pogorszenia warunków,
- zwiększaniu wymiany powietrza podczas procesu,
- diagnostyce działania układu.

Szczegółowa logika rekuperatora będzie rozwijana niezależnie.

### 2.2. Pomieszczenie z osobnym nawiewem i wyciągiem

Drugie pomieszczenie nie posiada rekuperatora. Ma dwa niezależnie sterowane wentylatory EC:

- nawiew,
- wyciąg.

Sterowanie odbywa się sygnałami 0–10 V, a rzeczywista praca wentylatorów może być weryfikowana przez TACHO.

To pomieszczenie wymaga regulatora wielokryterialnego, ponieważ intensywna wentylacja zimą może szybko wychładzać wnętrze.

Automatyka ma więc dostarczać tylko tak dużą wymianę powietrza, jaka jest w danej chwili potrzebna, ale bez obniżania wentylacji poniżej poziomu wymaganego dla jakości i bezpieczeństwa powietrza.

---

## 3. Pomiary wymagane przez automatykę

### 3.1. SEN55

SEN55 dostarcza co najmniej:

- PM1.0,
- PM2.5,
- PM4.0,
- PM10,
- VOC Index,
- NOx Index,
- temperaturę,
- wilgotność względną.

PM2.5 i PM10 mogą być używane jako bezpośrednie pomiary stężenia pyłu.

VOC Index i NOx Index są wskaźnikami względnymi algorytmu Sensiriona. Nie są pomiarem stężenia konkretnej substancji toksycznej w ppm ani mg/m³ i nie wolno ich interpretować jako formalnego pomiaru BHP.

### 3.2. Temperatura wewnętrzna

Temperatura pomieszczenia jest jednym z podstawowych sygnałów regulatora.

System powinien znać rzeczywistą temperaturę wewnętrzną i wykorzystywać ją do ograniczania niepotrzebnej wentylacji zimą.

### 3.3. Temperatura zewnętrzna / temperatura powietrza nawiewanego

Dla pomieszczenia bez rekuperatora wymagany jest dodatkowy pomiar temperatury zewnętrznej albo temperatury powietrza pobieranego przez nawiew.

Bez tego pomiaru sterownik widzi jedynie spadek temperatury wewnętrznej, ale nie zna aktualnego potencjału wychładzania pomieszczenia.

Przykład:

- `T_inside = 20°C`, `T_outside = +12°C` — można dopuścić większą wymianę powietrza,
- `T_inside = 20°C`, `T_outside = -15°C` — przy dobrej jakości powietrza wentylacja powinna być mocno ograniczona.

### 3.4. Dodatkowy pomiar CO

SEN55 nie mierzy tlenku węgla CO.

W środowisku warsztatowym, szczególnie tam, gdzie mogą pracować silniki spalinowe, osobny pomiar CO należy traktować jako ważny element przyszłej warstwy bezpieczeństwa.

Czujnik / detektor bezpieczeństwa CO nie powinien zależeć wyłącznie od CM5, Linuxa, sieci ani AI. Funkcja alarmowa powinna zachować działanie również przy awarii nadrzędnego systemu sterowania.

### 3.5. CO₂

SEN55 nie mierzy CO₂.

CO₂ może zostać dodany jako pomocniczy wskaźnik skuteczności wentylacji przy obecności ludzi. Nie zastępuje jednak pomiarów zanieczyszczeń procesowych, spalin ani CO.

---

## 4. Wartości referencyjne i wstępne progi procesowe

### 4.1. Pyły

Jako punkt odniesienia dla jakości powietrza przyjmujemy zalecenia WHO dla średniej 24-godzinnej:

- PM2.5: **15 µg/m³**,
- PM10: **45 µg/m³**.

Nie należy traktować średniej 24-godzinnej jako progu, po którego osiągnięciu dopiero uruchamia się wentylację. Automatyka powinna reagować wcześniej na wzrost chwilowy i trend.

Wstępna propozycja dla PM2.5:

| PM2.5 | Reakcja procesowa |
|---:|---|
| 0–15 µg/m³ | normalna praca |
| >15 µg/m³ przez określony czas | BOOST / zwiększenie wymiany |
| >25 µg/m³ | silna wentylacja |
| >50 µg/m³ | MAX + zdarzenie alarmowe procesu |

Poziomy 25 i 50 µg/m³ są obecnie założeniami procesowymi do strojenia, a nie progami WHO.

### 4.2. VOC Index

VOC Index nie jest stężeniem toksycznego gazu.

Wstępne progi sterowania:

| VOC Index | Interpretacja procesowa |
|---:|---|
| <100 | poniżej lokalnej średniej / dobrze |
| 100–150 | normalna praca |
| 150–200 | BOOST |
| 200–300 | silna wentylacja |
| >300 | MAX + zapis alarmu procesu |

Progi te są przeznaczone wyłącznie do sterowania i diagnostyki. Nie mogą być używane jako deklaracja, że atmosfera jest bezpieczna toksykologicznie.

### 4.3. NOx Index

NOx Index Sensiriona również nie jest bezpośrednim stężeniem NO₂.

Wstępne progi procesowe:

| NOx Index | Reakcja procesowa |
|---:|---|
| 1–10 | normalna praca |
| >10 | BOOST |
| >50 | silna wentylacja |
| >100 | MAX + alarm procesu |

Progi wymagają strojenia na rzeczywistych danych.

### 4.4. Wilgotność

Jako zakres preferowany przyjmujemy orientacyjnie:

- 30–50% RH — zakres korzystny,
- 50–60% RH — akceptowalnie,
- >60% RH — możliwe zwiększenie wentylacji, jeśli warunki zewnętrzne na to pozwalają,
- >70% RH przez dłuższy czas — zdarzenie wymagające reakcji / diagnostyki.

Samo zwiększenie wentylacji nie zawsze obniża wilgotność. Docelowo decyzja powinna uwzględniać warunki zewnętrzne.

---

## 5. Sterowanie temperaturą w pomieszczeniu bez rekuperatora

Temperatura nie jest niezależnym celem sterowania wentylacją. Jest ograniczeniem energetycznym nakładanym na normalną wymianę powietrza.

Wstępny model stref temperaturowych:

| Temperatura wewnętrzna | Zachowanie przy dobrej jakości powietrza |
|---:|---|
| >20°C | normalna wentylacja |
| 18–20°C | stopniowe ograniczanie wydajności |
| 16–18°C | minimalna wymiana powietrza |
| <16°C | tylko konieczne minimum / tryb ochrony cieplnej |

Wartości te nie są jeszcze finalnymi nastawami. Muszą zostać zweryfikowane po poznaniu rzeczywistej wydajności wentylatorów, kubatury pomieszczenia, strat cieplnych i charakterystyki ogrzewania.

### Zasada nadrzędna

Jeżeli temperatura jest niska, ale jakość powietrza wymaga zwiększenia wymiany, sterownik ma zwiększyć wentylację mimo ryzyka wychłodzenia.

W takim stanie system powinien raportować przyczynę, np.:

`LOW_TEMPERATURE + AIR_QUALITY_OVERRIDE`

czyli: niska temperatura, ale wentylacja została wymuszona przez jakość powietrza.

---

## 6. Priorytety i stany regulatora

### 6.1. SAFETY / EMERGENCY

Warstwa najwyższego priorytetu.

Przykłady:

- alarm CO,
- przyszły alarm innego dedykowanego czujnika bezpieczeństwa,
- inny warunek jednoznacznie sklasyfikowany jako zagrożenie.

Reakcja docelowa:

- wentylacja wymuszona na poziomie bezpieczeństwa lub MAX,
- ograniczenia temperaturowe są ignorowane,
- generowany jest alarm,
- decyzja nie zależy od AI.

### 6.2. AIR QUALITY HIGH

PM / VOC / NOx wskazują wyraźne pogorszenie jakości powietrza.

Reakcja:

- zwiększenie nawiewu i wyciągu,
- temperatura może wpływać na strategię tylko wtedy, jeśli nie ogranicza wymiany wymaganej przez jakość powietrza,
- przy silnym pogorszeniu jakości powietrza przejście do BOOST / MAX.

### 6.3. AIR QUALITY NORMAL

Powietrze jest dobre.

Dopiero w tym stanie regulator temperatury może ograniczać wentylację w celu zmniejszenia strat ciepła.

### 6.4. THERMAL PROTECTION

Przy niskiej temperaturze wewnętrznej i dobrej jakości powietrza:

- ograniczana jest wymiana,
- zachowywane jest niezbędne minimum świeżego powietrza,
- możliwa jest w przyszłości praca okresowa.

### 6.5. UNOCCUPIED / FROST — funkcja przyszła

Jeżeli pomieszczenie jest nieużywane, powietrze jest czyste, a temperatura zewnętrzna jest bardzo niska, można rozważyć okresową wymianę zamiast pracy ciągłej, np. krótkie cykle wentylacji rozdzielone przerwami.

Ten tryb nie powinien być wdrażany bez wcześniejszego zebrania danych z rzeczywistego obiektu.

---

## 7. Sposób wyznaczania wydajności

Sterownik powinien rozdzielać co najmniej dwa pojęcia:

- **AIR_REQUEST** — wymagana wydajność wynikająca z jakości powietrza,
- **TEMP_LIMIT** — ograniczenie wydajności wynikające z bilansu cieplnego.

Przy dobrej jakości powietrza temperatura może ograniczać normalne żądanie wentylacji.

Przy pogorszonej jakości powietrza żądanie wynikające z jakości powietrza ma pierwszeństwo.

W stanie bezpieczeństwa ograniczenie temperaturowe jest ignorowane.

Docelowo logika powinna być implementowana w sposób jawny, z zapisem źródła decyzji, a nie jako nieprzejrzysta suma wielu korekt.

Przykładowe pola diagnostyczne:

- `air_request_pct`,
- `temperature_limit_pct`,
- `safety_override`,
- `final_supply_pct`,
- `final_extract_pct`,
- `control_reason`.

---

## 8. Nawiew i wyciąg

Nawiew i wyciąg nie muszą pracować z identycznym zadaniem.

W pomieszczeniu generującym zanieczyszczenia można rozważyć lekkie podciśnienie, czyli wyciąg pracujący nieco mocniej od nawiewu.

Przykładowo koncepcyjnie:

- nawiew 45%,
- wyciąg 50%.

Nie jest to finalna nastawa. Różnica pomiędzy nawiewem i wyciągiem musi być parametrem konfiguracyjnym i zostać zweryfikowana w rzeczywistym pomieszczeniu. Zbyt duże podciśnienie może powodować niekontrolowany napływ powietrza przez nieszczelności budynku.

---

## 9. TACHO i diagnostyka wentylatorów

TACHO należy wykorzystać jako niezależne potwierdzenie rzeczywistej pracy wentylatora.

Sterownik nie powinien zakładać, że zadane 0–10 V oznacza poprawną pracę urządzenia.

Należy wykrywać co najmniej:

- brak obrotów mimo aktywnego zadania,
- zbyt małą prędkość względem oczekiwanej,
- niespójność nawiew / wyciąg,
- zatrzymanie wentylatora,
- utratę sygnału TACHO.

W dalszym etapie TACHO może zostać użyte także do regulacji bazującej na rzeczywistej prędkości, ale nie jest to wymagane dla pierwszej wersji automatyki.

---

## 10. Rola AI

AI nie podejmuje decyzji, czy atmosfera jest bezpieczna.

Twarde progi, warunki awaryjne i decyzje bezpieczeństwa mają być realizowane deterministycznie lokalnie w `ventilation-core` na CM5.

AI może działać ponad tą warstwą i realizować zadania takie jak:

- analiza trendów,
- wykrywanie anomalii,
- porównywanie zachowania pomieszczenia w różnych warunkach,
- proponowanie korekt nastaw,
- wykrywanie długoterminowego pogorszenia sprawności,
- przygotowywanie raportów i rekomendacji.

Awaria AI, serwera AI, LAN albo Internetu nie może pozbawić systemu podstawowej automatyki i funkcji bezpieczeństwa.

---

## 11. Strojenie na danych z rzeczywistego obiektu

Pierwsza wersja regulatora powinna mieć konserwatywne, łatwo edytowalne parametry.

Po uruchomieniu należy gromadzić dane potrzebne do strojenia:

- temperatura wewnętrzna,
- temperatura zewnętrzna / nawiewu,
- wilgotność,
- PM1.0 / PM2.5 / PM4.0 / PM10,
- VOC Index,
- NOx Index,
- zadanie 0–10 V dla obu kanałów,
- TACHO obu wentylatorów,
- tryb regulatora,
- przyczyna każdej zmiany wydajności,
- alarmy i override'y,
- czas potrzebny na oczyszczenie pomieszczenia po zdarzeniu,
- tempo wychładzania pomieszczenia przy różnych temperaturach zewnętrznych.

Na podstawie tych danych będzie można ustalić rzeczywiste zależności pomiędzy:

- jakością powietrza,
- wydajnością wentylacji,
- temperaturą zewnętrzną,
- szybkością wychładzania pomieszczenia.

Dopiero wtedy należy optymalizować progi i krzywe regulacji.

---

## 12. Parametry, które mają być konfigurowalne

Co najmniej:

- minimalna wydajność nawiewu,
- minimalna wydajność wyciągu,
- maksymalna wydajność,
- różnica zadania nawiew / wyciąg,
- progi PM,
- progi VOC Index,
- progi NOx Index,
- progi temperatury wewnętrznej,
- wpływ temperatury zewnętrznej,
- histerezy,
- minimalne czasy utrzymania stanu,
- czasy potwierdzenia przekroczeń,
- czasy wygaszania BOOST,
- zachowanie po utracie SEN55,
- zachowanie po utracie czujnika temperatury,
- zachowanie po awarii TACHO,
- warunki SAFETY override.

---

## 13. Otwarte decyzje projektowe

Do ustalenia w kolejnych etapach:

1. Docelowy sprzętowy czujnik temperatury zewnętrznej / nawiewu.
2. Sposób pomiaru temperatury wewnętrznej używanej przez regulator — SEN55 czy osobny punkt pomiarowy.
3. Dobór niezależnego czujnika / detektora CO.
4. Ewentualne dodanie pomiaru CO₂.
5. Minimalna stabilna prędkość obu wentylatorów EC.
6. Rzeczywisty przepływ powietrza dla kolejnych poziomów sterowania 0–10 V.
7. Kubatura pomieszczenia i docelowa minimalna wymiana powietrza.
8. Docelowe histerezy i czasy filtracji pomiarów.
9. Czy potrzebny jest sygnał obecności ludzi / stanu pracy procesu.
10. Finalna strategia lekkiego podciśnienia.

---

## 14. Źródła referencyjne użyte do założeń

Przed implementacją finalnej warstwy bezpieczeństwa należy ponownie zweryfikować obowiązujące wymagania i dokumentację urządzeń.

- WHO Global Air Quality Guidelines — PM2.5 / PM10.
- Sensirion SEN55 — zakres pomiarowy i charakter mierzonych parametrów.
- Sensirion Gas Index Algorithm / SGP41 — interpretacja VOC Index i NOx Index.
- Aktualne polskie przepisy dotyczące najwyższych dopuszczalnych stężeń czynników szkodliwych w środowisku pracy.

---

## 15. Zasada projektowa do zachowania

System nie ma maksymalizować wentylacji. Ma zapewniać **minimalną wystarczającą wentylację dla aktualnych warunków**, zwiększać ją natychmiast wtedy, gdy wymaga tego jakość powietrza, oraz ignorować oszczędzanie ciepła wtedy, gdy pojawia się zagrożenie.

W pomieszczeniu bez rekuperatora głównym problemem regulacyjnym jest więc równowaga:

**świeże i bezpieczne powietrze ↔ minimalizacja wychładzania pomieszczenia**.

---

## 16. Automatyka V1 — harmonogram, maszyna stanów i shadow mode

Poniższe założenia definiują pierwszą, konserwatywną warstwę automatyki przeznaczoną do wdrożenia przed bardziej zaawansowanym regulatorem.

### 16.1. Podział odpowiedzialności

`ventilation-core` pozostaje jedynym miejscem podejmującym decyzje sterujące. GUI jest klientem prezentującym stan i umożliwiającym operatorowi zmianę dozwolonych nastaw. Home Assistant pozostaje integracją wyłącznie read-only. AI może analizować dane i proponować zmiany, ale nie znajduje się w bezpośredniej pętli sterowania.

Pierwsza wersja automatyki ma być:

- deterministyczna,
- przewidywalna,
- łatwa do przetestowania,
- łatwa do diagnostyki,
- bezpieczna przy utracie części pomiarów.

### 16.2. Trzy warstwy decyzji

Sterowanie należy rozdzielić na trzy logiczne warstwy:

1. **HARMONOGRAM** — wyznacza bazowy lub minimalny poziom wentylacji wynikający z pory dnia i trybu pracy obiektu.
2. **JAKOŚĆ POWIETRZA** — może zwiększyć zapotrzebowanie ponad poziom harmonogramu.
3. **TEMPERATURA / BEZPIECZEŃSTWO** — ogranicza straty ciepła przy dobrym powietrzu, ale nie może zablokować wentylacji wymaganej przez bezpieczeństwo.

Koncepcyjnie:

`final_request = max(schedule_request, air_quality_request, safety_request)`

z osobną logiką `temperature_limit`, stosowaną wyłącznie tam, gdzie nie narusza priorytetu jakości powietrza i bezpieczeństwa.

### 16.3. Stany automatyki V1

Pierwsza maszyna stanów powinna przewidywać co najmniej:

| Stan | Znaczenie |
|---|---|
| `OFF` | system świadomie wyłączony |
| `STANDBY` | poza godzinami pracy; pomiary i zabezpieczenia pozostają aktywne |
| `PREVENTILATION` | przewietrzenie przed rozpoczęciem pracy |
| `NORMAL` | standardowa praca według harmonogramu |
| `BOOST` | zwiększona wentylacja z powodu pogorszenia jakości powietrza |
| `PURGE` | przewietrzanie po zakończeniu pracy |
| `TEMP_LIMIT` | ograniczenie bazowej wentylacji z powodu niskiej temperatury przy dobrej jakości powietrza |
| `EMERGENCY_VENT` | wymuszone intensywne przewietrzanie z priorytetem bezpieczeństwa |
| `MANUAL` | ręczne zadanie operatora, nadal podlegające nadrzędnym zabezpieczeniom |
| `FAULT` | stan awaryjny wymagający zdefiniowanego bezpiecznego fallbacku |

Nazwy stanów są robocze i mogą zostać skorygowane podczas implementacji, ale ich znaczenie ma pozostać jawne.

### 16.4. Harmonogram bazowy

Dla dnia roboczego przyjmujemy koncepcyjnie:

- przed rozpoczęciem pracy: `PREVENTILATION`, np. przez około 30 min,
- w godzinach pracy: `NORMAL`, z minimalnym poziomem wynikającym z konfiguracji,
- po zakończeniu pracy: `PURGE`, np. przez 30–60 min,
- poza godzinami pracy: `STANDBY`.

Wartości procentowe i czasy są parametrami konfiguracyjnymi i nie są jeszcze finalnymi nastawami.

W weekendy i dni wolne system może pozostawać w `STANDBY`, ale nadal musi:

- mierzyć parametry,
- obsługiwać AlertV2,
- reagować na pogorszenie jakości powietrza,
- realizować diagnostykę urządzeń.

Na tym etapie nie zakładamy cyklicznego przewietrzania „co godzinę” przy dobrych pomiarach, ponieważ zimą może to powodować niepotrzebne straty ciepła.

### 16.5. Poziomy jakości powietrza

Pierwsza implementacja powinna używać dyskretnych poziomów zamiast ciągłego regulatora.

Koncepcyjny model:

| Poziom | Znaczenie | Reakcja |
|---:|---|---|
| 0 | powietrze dobre | poziom wynikający z harmonogramu |
| 1 | lekkie pogorszenie | niewielkie zwiększenie minimum |
| 2 | wyraźne pogorszenie | `BOOST` |
| 3 | złe warunki | silny `BOOST` |
| 4 | stan krytyczny | `EMERGENCY_VENT` / maksymalna wymiana |

Mapowanie PM/VOC/NOx na poziomy będzie korzystać z osobnych konfigurowalnych progów procesowych opisanych wcześniej w tym dokumencie.

### 16.6. Histereza i potwierdzanie stanów

Automatyka nie może reagować na pojedynczą próbkę.

Dla wejścia w stan o wyższym poziomie należy stosować czas potwierdzenia przekroczenia, przykładowo 60–120 s zależnie od parametru.

Powrót do niższego poziomu powinien następować dopiero po:

- spadku poniżej niższego progu histerezy,
- utrzymaniu poprawnych wartości przez określony czas, przykładowo kilka minut.

Celem jest uniknięcie ciągłego przełączania stanów i zmian prędkości wentylatorów wokół jednego progu.

### 16.7. Temperatura w V1

Temperatura ma wpływać przede wszystkim na bazową wentylację przy dobrej jakości powietrza.

Koncepcyjnie:

- temperatura komfortowa — normalna praca,
- lekko obniżona — redukcja minimum,
- niska — `TEMP_LIMIT`,
- bardzo niska — minimalizacja wentylacji niewymaganej przez jakość powietrza.

Jeżeli równocześnie występuje warunek `BOOST` lub `EMERGENCY_VENT`, priorytet jakości powietrza / bezpieczeństwa ma pierwszeństwo nad ochroną cieplną.

### 16.8. Temperatura zewnętrzna / nawiewu

Po dostępności wiarygodnego pomiaru temperatury powietrza pobieranego z zewnątrz należy rozszerzyć regulator o różnicę temperatur, np.:

`delta_t = T_inside - T_supply`

Pozwoli to rozróżniać sytuacje, w których takie samo `T_inside` występuje przy łagodnych i bardzo mroźnych warunkach zewnętrznych.

W V1 parametr ten może być przygotowany w modelu danych, ale jego wpływ na sterowanie powinien być wdrażany etapowo i po walidacji pomiarów.

### 16.9. Sterowanie ręczne

Operator powinien mieć tryby `AUTO` i `MANUAL`.

W `MANUAL` operator może ustawić zadanie wentylatorów, ale ręczne sterowanie nie może wyłączyć nadrzędnych zabezpieczeń.

Przykład:

`MANUAL 20% + warunek krytyczny -> EMERGENCY_VENT`

Core powinien wtedy jawnie raportować, że ręczne zadanie zostało nadpisane przez warstwę bezpieczeństwa.

### 16.10. Zachowanie po utracie pomiarów

Utrata czujnika nie może prowadzić automatycznie do zatrzymania wentylacji.

Przykładowa polityka V1:

- utrata SEN55 podczas aktywnych godzin pracy -> bezpieczny, konfigurowalny poziom fallback + AlertV2,
- utrata zewnętrznego czujnika temperatury -> wyłączenie optymalizacji temperaturowej, ale zachowanie normalnej automatyki jakości powietrza,
- utrata TACHO -> AlertV2 i przejście do zdefiniowanej polityki awaryjnej zależnej od kanału i zadanego sterowania.

Dokładne wartości fallback są parametrami konfiguracyjnymi i wymagają walidacji sprzętowej.

### 16.11. Jawna diagnostyka decyzji

`ventilation-core` powinien zawsze publikować nie tylko wynik sterowania, ale także źródło decyzji.

Przykładowy stan diagnostyczny:

```text
mode: AUTO
automation_state: BOOST
schedule_state: NORMAL
schedule_minimum_pct: 30
air_quality_request_pct: 60
temperature_limit_pct: 40
safety_request_pct: 0
final_request_pct: 60
control_reason: VOC_HIGH
```

Należy unikać sytuacji, w której końcowe zadanie jest wynikiem niejawnej sumy wielu korekt i nie da się jednoznacznie ustalić przyczyny działania systemu.

### 16.12. Shadow mode jako pierwszy etap uruchomienia

Pierwsze wdrożenie automatyki powinno zostać uruchomione w trybie **shadow mode**.

W tym trybie core:

- oblicza harmonogram,
- przełącza logiczne stany automatyki,
- wylicza `requested_output`,
- zapisuje przyczyny decyzji,
- udostępnia wynik w API / GUI / telemetrii,
- ale nie zmienia rzeczywistych wyjść 0–10 V na podstawie tej nowej logiki.

Rzeczywiste sterowanie pozostaje na dotychczasowej bezpiecznej ścieżce.

Celem shadow mode jest obserwacja przez kilka dni, czy decyzje odpowiadają rzeczywistym warunkom, np. czy system prawidłowo proponuje `BOOST` po wzroście VOC i wraca do `NORMAL` po oczyszczeniu powietrza.

Dopiero po walidacji zachowania na rzeczywistym CM5 należy dopuścić przejście z `requested_output` do fizycznego sterowania.

### 16.13. Zakres pierwszego etapu implementacyjnego

Pierwszy etap kodowania powinien obejmować:

1. scheduler dzień roboczy / weekend,
2. stany `PREVENTILATION`, `NORMAL`, `PURGE`, `STANDBY`,
3. poziomy jakości powietrza co najmniej `NORMAL`, `BOOST`, `EMERGENCY`,
4. histerezę,
5. czasy potwierdzenia przekroczeń i wygaszania,
6. `AUTO` / `MANUAL`,
7. fallback po utracie SEN55,
8. jawny model przyczyny decyzji,
9. telemetrię stanu automatyki,
10. shadow mode bez wpływu nowej logiki na fizyczne wyjścia.

Po poprawnej walidacji tego etapu będzie można rozpocząć strojenie rzeczywistych poziomów oraz bezpiecznie włączać sterowanie automatyczne na fizycznych wentylatorach.

### 16.14. Harmonogram wielopoziomowy — rok, miesiące, tygodnie i dni

Harmonogram nie może być ograniczony wyłącznie do dni tygodnia. Powinien umożliwiać opis normalnego cyklu pracy obiektu w skali całego roku.

Model harmonogramu powinien obejmować:

1. **bazowy harmonogram tygodniowy** — typowe godziny pracy dla poszczególnych dni tygodnia,
2. **zakresy dat** — czasowe profile obowiązujące od konkretnej daty do konkretnej daty,
3. **miesiące / sezony** — wybór profilu sezonowego, np. ZIMA / WIOSNA / LATO / JESIEŃ,
4. **tygodnie roku** — jako wygodny sposób edycji lub wyboru zakresu, ale nie jako jedyny mechanizm adresowania czasu,
5. **wyjątki roczne i konkretne daty** — święta, dni zamknięcia, urlopy zakładowe, dni serwisowe i inne odstępstwa.

Technicznie podstawowym mechanizmem powinny być daty i zakresy dat. Numery tygodni mogą być prezentowane w GUI jako wygodna forma wyboru, ponieważ tygodnie na przełomie roku mogą być niejednoznaczne.

### 16.15. Bazowy harmonogram tygodniowy

Każdy dzień powinien umożliwiać zdefiniowanie co najmniej godziny rozpoczęcia i zakończenia pracy oraz wybranego trybu harmonogramowego.

Przykład:

| Dzień | Start | Koniec | Tryb |
|---|---:|---:|---|
| Poniedziałek–Piątek | 06:30 | 18:00 | `AUTO` |
| Sobota | 08:00 | 14:00 | `AUTO` |
| Niedziela | — | — | `STANDBY` |

Model danych powinien umożliwiać więcej niż jeden przedział czasu w ciągu jednego dnia, np. `06:30–12:00` oraz `13:00–18:00`.

### 16.16. Znaczenie trybów harmonogramowych

Harmonogram nie powinien ustawiać stanu `MANUAL`, ponieważ `MANUAL` ma jednoznacznie oznaczać świadome przejęcie sterowania przez operatora.

Do harmonogramu należy przewidzieć co najmniej:

- `AUTO` — harmonogram określa aktywność obiektu i poziom bazowy, a rzeczywistą wydajność ustala automatyka na podstawie pomiarów,
- `FIXED` / `SCHEDULED_FIXED` — harmonogram narzuca skonfigurowany poziom bazowy lub zadany poziom pracy,
- `STANDBY` — obiekt jest poza normalnymi godzinami pracy, ale pomiary, AlertV2 i nadrzędne reakcje bezpieczeństwa pozostają aktywne,
- `OFF` — świadome wyłączenie funkcji wentylacji w zakresie dozwolonym przez politykę bezpieczeństwa; nie oznacza zatrzymania pomiarów ani warstwy bezpieczeństwa,
- `MANUAL` — wyłącznie ręczne przejęcie przez operatora, niezależne od harmonogramu.

Ta separacja ma być zachowana w modelu danych, API, GUI i logach diagnostycznych.

### 16.17. Semantyka godzin ON / OFF

Godziny `ON` i `OFF` nie powinny oznaczać fizycznego włączenia i wyłączenia całego systemu.

`ON` oznacza początek aktywnego okresu pracy obiektu, a `OFF` oznacza koniec tego okresu. Na tej podstawie core może automatycznie wyznaczać `PREVENTILATION` i `PURGE`.

Przykład:

```text
start_pracy: 07:00
koniec_pracy: 17:00
preventilation: 30 min
purge: 30 min
```

Core interpretuje to jako:

```text
06:30 PREVENTILATION
07:00 AUTO/NORMAL
17:00 PURGE
17:30 STANDBY
```

Dzięki temu operator nie musi osobno wpisywać czterech godzin dla jednego dnia pracy.

### 16.18. Profile sezonowe i miesięczne

Rok powinien umożliwiać przypisanie profili sezonowych, np. `ZIMA`, `WIOSNA`, `LATO`, `JESIEŃ`.

Profil sezonowy nie powinien bezpośrednio sterować wentylatorami. Powinien wybierać zestaw parametrów automatyki, np.:

- minimalne poziomy wentylacji,
- wpływ temperatury na ograniczenie bazowego przepływu,
- czasy `PREVENTILATION` i `PURGE`,
- progi lub parametry strategii oszczędzania ciepła.

Przykładowo profil `ZIMA` może stosować niższe minimum i silniejszą ochronę cieplną przy dobrym powietrzu, natomiast `LATO` może pozwalać na większą wymianę bez ograniczeń temperaturowych.

### 16.19. Wyjątki, święta i okresy specjalne

System musi umożliwiać definiowanie wyjątków o wyższym priorytecie niż standardowy harmonogram tygodniowy.

Przykłady:

- święto ustawowo wolne,
- pojedynczy dzień zamknięcia,
- urlop zakładowy,
- dzień serwisowy,
- niestandardowe godziny pracy,
- czasowy profil wakacyjny.

Przykładowo zakres `2026-08-10`–`2026-08-23` może wymusić profil `STANDBY` niezależnie od tego, że bazowo są to dni robocze.

### 16.20. Hierarchia rozstrzygania harmonogramu

Przy nakładaniu się reguł scheduler powinien stosować jednoznaczną hierarchię:

1. wyjątek dla konkretnej daty,
2. specjalny zakres dat / profil okresowy,
3. profil sezonowy / miesięczny,
4. bazowy harmonogram tygodniowy,
5. profil domyślny.

Ponad harmonogramem znajduje się ręczny override operatora `MANUAL`, natomiast ponad nim pozostaje warstwa `SAFETY / EMERGENCY`.

Koncepcyjnie:

`SAFETY > MANUAL_OVERRIDE > DATE_EXCEPTION > PERIOD_PROFILE > SEASON_PROFILE > WEEKLY_SCHEDULE > DEFAULT`

Przy czym warstwa bezpieczeństwa może nadpisać nawet ręczne ustawienie operatora.

### 16.21. Czasowy override operatora

Ręczne przejęcie sterowania powinno mieć możliwość ustawienia czasu wygaśnięcia.

Przykład:

`MANUAL: nawiew 60%, wyciąg 65%, przez 2 godziny`

Po upływie czasu system automatycznie wraca do aktualnie obowiązującego harmonogramu.

Core powinien jednocześnie raportować aktywny override oraz to, co wynikałoby z harmonogramu bez override'u, np.:

```text
control_mode: MANUAL
manual_supply_pct: 60
manual_extract_pct: 65
manual_until: 2026-08-27T15:30:00+02:00
scheduled_mode: AUTO
scheduled_profile: NORMAL_WORKDAY
```

Override bez czasu wygaśnięcia może być dopuszczony wyłącznie jako świadoma opcja operatorska i powinien być wyraźnie sygnalizowany w GUI.

### 16.22. Przykładowe profile harmonogramowe

Przykład typowego dnia roboczego:

```text
profile: NORMAL_WORKDAY
applies_to: MON-FRI
start_work: 07:00
end_work: 17:00
preventilation: 30 min
purge: 30 min
control_mode: AUTO
minimum_supply_pct: 25
minimum_extract_pct: 30
```

Przykład dnia specjalnego:

```text
profile: SERVICE_DAY
date: 2026-09-12
start_work: 08:00
end_work: 13:00
control_mode: FIXED
supply_pct: 35
extract_pct: 40
```

### 16.23. Wymagania diagnostyczne schedulera

Core powinien publikować co najmniej:

- aktualny czas lokalny i strefę czasową,
- aktywny profil harmonogramowy,
- źródło wybranej reguły (`weekly`, `season`, `date_range`, `date_exception`, `manual_override`),
- aktualny tryb (`AUTO`, `FIXED`, `STANDBY`, `OFF`, `MANUAL`),
- czas rozpoczęcia i zakończenia aktywnego przedziału,
- czas następnego przejścia harmonogramu,
- aktywny profil sezonowy,
- informację o aktywnym wyjątku,
- stan i czas wygaśnięcia ręcznego override'u.

Scheduler powinien korzystać z lokalnej strefy czasowej systemu i poprawnie obsługiwać zmianę czasu letniego/zimowego.

### 16.24. Zasada projektowa schedulera

Harmonogram nie jest jedynie zegarem ON/OFF. Jest warstwą opisującą **kiedy i w jakim profilu obiekt ma pracować**, natomiast `ventilation-core` nadal podejmuje końcową decyzję o wydajności na podstawie harmonogramu, jakości powietrza, temperatury, stanu urządzeń i warstwy bezpieczeństwa.

### 16.25. Noc, weekendy i dni wolne — pełny kontrolowany shutdown

Założenie docelowe dla WVC jest następujące: w nocy, w weekendy oraz w zadeklarowane dni wolne CM5 nie pozostaje przez wiele godzin w normalnie działającym stanie `STANDBY`. Po zakończeniu wymaganych czynności system wykonuje **pełny, kontrolowany shutdown Linuxa**, a następnie pozostaje w stanie niskiego poboru do czasu następnego wybudzenia.

`STANDBY` pozostaje stanem logicznym przydatnym dla krótkich przerw, chwilowego oczekiwania, serwisu lub konfiguracji, ale nie jest podstawowym stanem nocnym WVC.

Docelowa sekwencja końca dnia:

```text
NORMAL / AUTO
    -> PURGE
    -> bezpieczne zatrzymanie funkcji peryferyjnych
    -> wyłączenie domeny 12 V
    -> wyznaczenie następnego aktywnego okresu przez scheduler
    -> zaprogramowanie alarmu RTC
    -> odczyt i weryfikacja alarmu RTC
    -> kontrolowany shutdown CM5
    -> stan niskiego poboru
```

### 16.26. Zasada zasilania CM5 podczas oczekiwania na RTC

Automatyczne wybudzenie RTC zakłada, że główne zasilanie 5 V CM5 pozostaje dostępne. Nie wolno traktować baterii RTC jako źródła energii do ponownego uruchomienia całego modułu.

W docelowej architekturze nocnej:

- zasilacz / domena 5 V CM5 pozostaje zasilona,
- CM5 jest poprawnie zatrzymany i pozostaje w stanie niskiego poboru,
- bateria RTC podtrzymuje zegar w warunkach wymagających podtrzymania czasu,
- domena 12 V urządzeń wykonawczych i peryferiów może być odłączona przez DFR0473 zgodnie z architekturą zasilania,
- fizyczne odcięcie 5 V CM5 nie jest normalnym mechanizmem nocnego wyłączania, ponieważ uniemożliwiłoby automatyczny start wywołany przez RTC.

Fizyczny przycisk uruchamiający CM5 pozostaje niezależną ścieżką ręcznego startu systemu.

### 16.27. RTC przechowuje tylko najbliższe wybudzenie

Cały kalendarz roczny pozostaje w schedulerze `ventilation-core`. RTC nie ma przechowywać kompletnego harmonogramu dni, tygodni i miesięcy.

Przed każdym planowanym shutdownem scheduler oblicza wyłącznie **najbliższy moment, w którym WVC musi ponownie się uruchomić**.

Przykład:

```text
piątek: koniec pracy 18:00
sobota: dzień wolny
niedziela: dzień wolny
poniedziałek: start pracy 07:00
PREVENTILATION: 30 min
```

Następny alarm RTC powinien zostać ustawiony na:

```text
poniedziałek 06:30
```

Jeżeli poniedziałek jest wyjątkiem `HOLIDAY/OFF`, scheduler przechodzi do następnego aktywnego dnia. Analogicznie urlop zakładowy może spowodować ustawienie następnego wybudzenia dopiero po wielu dniach.

Najbliższe wybudzenie powinno odpowiadać początkowi `PREVENTILATION`, a nie dopiero godzinie `start_work`.

### 16.28. Fail-safe przed shutdownem

Planowany shutdown nie może zostać wykonany, jeśli system nie ma wiarygodnie uzbrojonego następnego wybudzenia.

Minimalna sekwencja bezpieczeństwa:

1. scheduler wyznacza `next_wake`,
2. czas jest walidowany względem aktualnego czasu i aktywnego kalendarza,
3. alarm jest zapisywany do RTC,
4. alarm RTC jest ponownie odczytywany,
5. odczytana wartość jest porównywana z oczekiwanym `next_wake`,
6. dopiero po poprawnej weryfikacji można przejść do shutdownu.

Jeżeli którykolwiek etap zawiedzie:

```text
RTC_WAKE_ARM_FAILED
    -> AlertV2
    -> scheduled shutdown ABORT
    -> CM5 pozostaje uruchomiony
```

Zasada bezpieczeństwa brzmi: **lepiej pozostawić WVC uruchomiony przez noc lub dzień wolny niż dopuścić do sytuacji, w której nie uruchomi się przed następnym okresem pracy**.

Dla świadomego ręcznego shutdownu operatora można przewidzieć osobną politykę, ale nie może ona być mylona z automatycznym shutdownem harmonogramowym.

### 16.29. Czas lokalny, UTC i zmiana czasu

Harmonogram operatorski jest definiowany w lokalnej strefie czasu obiektu, docelowo `Europe/Warsaw`.

Scheduler powinien:

1. rozstrzygnąć następny aktywny termin w czasie lokalnym,
2. uwzględnić zmianę czasu letniego / zimowego,
3. przeliczyć moment wybudzenia do reprezentacji używanej przez RTC / kernel,
4. zapisać jednoznaczny timestamp następnego wybudzenia,
5. po restarcie ponownie obliczyć przyszłe zdarzenia na podstawie pełnego kalendarza.

Nie należy przechowywać logiki DST w samym RTC. Odpowiedzialność za interpretację kalendarza pozostaje w schedulerze.

### 16.30. Start po wybudzeniu RTC

Po uruchomieniu CM5 przez RTC system powinien przejść przez normalną, deterministyczną sekwencję startową.

Koncepcyjnie:

```text
RTC WAKE
    -> boot CM5
    -> start ventilation-core
    -> walidacja czasu, konfiguracji i wymaganych usług
    -> uruchomienie domeny 12 V
    -> inicjalizacja i diagnostyka urządzeń
    -> PREVENTILATION
    -> AUTO / NORMAL
```

Awaria pojedynczego urządzenia przy starcie nie może powodować niejawnego pominięcia diagnostyki. Core powinien jawnie publikować stan startu, brakujące urządzenia i aktywne fallbacki / AlertV2.

### 16.31. Diagnostyka planowanego shutdownu i wybudzenia

Core powinien publikować co najmniej:

- `scheduled_shutdown_enabled`,
- `next_shutdown_at`,
- `next_wake_at_local`,
- `next_wake_at_utc` lub równoważny jednoznaczny timestamp,
- `next_wake_reason`,
- `rtc_alarm_armed`,
- `rtc_alarm_verified`,
- `rtc_alarm_value`,
- `shutdown_inhibited_reason`,
- źródło wybudzenia po starcie, jeśli platforma umożliwia jego wiarygodne ustalenie.

Dzięki temu GUI i logi mogą jednoznacznie pokazać np.:

```text
Następne wyłączenie: piątek 18:30
Następne uruchomienie: poniedziałek 06:30
Powód: NORMAL_WORKDAY / PREVENTILATION
RTC: ARMED + VERIFIED
```

### 16.32. Aktualizacja zasady `STANDBY`

Wcześniejsze założenie, że weekendy i dni wolne są realizowane jako wielogodzinny `STANDBY` z aktywnym Linuxem, należy traktować jako założenie przejściowe.

Docelowo:

- krótka przerwa / oczekiwanie -> `STANDBY`,
- noc -> `SCHEDULED_SHUTDOWN`,
- weekend / dzień wolny -> `SCHEDULED_SHUTDOWN`,
- urlop / długi okres zamknięcia -> `SCHEDULED_SHUTDOWN`,
- ręczne uruchomienie przez fizyczny przycisk pozostaje możliwe niezależnie od zaplanowanego alarmu RTC.

Funkcja `SCHEDULED_SHUTDOWN -> RTC WAKE` musi przed włączeniem produkcyjnym przejść osobną walidację na fizycznym CM5, obejmującą co najmniej poprawny shutdown, skuteczne wybudzenie RTC, zachowanie po długim okresie wyłączenia, restart po utracie zasilania oraz zmianę czasu letniego / zimowego.

### 16.33. Kalendarz jako niezależna warstwa domenowa

Przy rozbudowanym harmonogramie obejmującym cały rok kalendarz należy wydzielić jako **niezależną warstwę logiczną**. Nie jest to drugi sterownik wentylacji ani alternatywny „mózg” systemu. Jego jedyną odpowiedzialnością jest deterministyczne rozstrzyganie czasu, profili i przyszłych zdarzeń kalendarzowych.

Warstwa ta powinna być nazywana roboczo `Calendar Engine`.

Koncepcyjny przepływ:

```text
CALENDAR ENGINE
      |
      | schedule_intent / calendar_state
      v
VENTILATION-CORE
      |
      +-- jakość powietrza
      +-- temperatura
      +-- stan urządzeń
      +-- operator override
      +-- SAFETY / EMERGENCY
      |
      v
WYJŚCIA / URZĄDZENIA
```

`ventilation-core` pozostaje jedyną warstwą podejmującą końcowe decyzje sterujące.

### 16.34. Odpowiedzialność `Calendar Engine`

`Calendar Engine` powinien odpowiadać za:

- rozstrzyganie bazowego harmonogramu tygodniowego,
- miesiące i profile sezonowe,
- zakresy dat,
- konkretne daty i wyjątki,
- święta i dni wolne,
- wiele przedziałów w jednym dniu,
- hierarchię reguł kalendarzowych,
- strefę czasu i DST,
- obowiązujący profil harmonogramowy,
- obowiązujący tryb harmonogramowy (`AUTO`, `FIXED`, `STANDBY`, `OFF`),
- bieżący okres kalendarzowy,
- następne przejście harmonogramu,
- następny aktywny okres,
- następny wymagany start systemu,
- moment `PREVENTILATION`,
- dane potrzebne do wyznaczenia `next_wake`.

Warstwa kalendarza ma odpowiadać na pytanie:

**„Jaki profil pracy wynika teraz z kalendarza i kiedy kalendarz zmieni ten stan?”**

### 16.35. Czego `Calendar Engine` nie robi

Kalendarz nie może:

- analizować danych SEN55,
- wyznaczać `BOOST` na podstawie PM/VOC/NOx,
- wykonywać regulatora temperatury,
- interpretować TACHO jako decyzji sterującej,
- generować końcowego zadania 0–10 V,
- bezpośrednio sterować wentylatorami,
- nadpisywać warstwy `SAFETY / EMERGENCY`,
- wykonywać ręcznego `MANUAL` operatora,
- samodzielnie wyłączać CM5.

Calendar Engine dostarcza **intencję czasową**, a nie decyzję wykonawczą.

### 16.36. Kontrakt pomiędzy kalendarzem a core

`ventilation-core` nie powinien samodzielnie przeszukiwać wszystkich reguł rocznych. Powinien korzystać z jednego jawnego interfejsu, koncepcyjnie:

```python
calendar.resolve(now)
```

Wynik powinien zawierać co najmniej:

```text
effective_profile
effective_mode
current_period
rule_source
next_transition
next_active_period
next_wake
```

Rozszerzony wynik może zawierać również:

```text
preventilation_start
work_start
work_end
purge_end
season_profile
active_exception
```

Dzięki temu logika kalendarza jest testowalna niezależnie od czujników i sprzętu.

### 16.37. `MANUAL` pozostaje poza kalendarzem

Ręczny override operatora nie jest regułą kalendarzową. Calendar Engine powinien nadal raportować, co wynikałoby z harmonogramu, nawet gdy operator przejął sterowanie.

Przykład:

```text
calendar_mode: AUTO
calendar_profile: NORMAL_WORKDAY
operator_mode: MANUAL
manual_until: 14:00
```

Dopiero `ventilation-core` rozstrzyga końcową hierarchię:

`SAFETY > MANUAL_OVERRIDE > CALENDAR_INTENT`

Pozwala to zawsze stwierdzić, czy aktualne zachowanie wynika z kalendarza, operatora czy warstwy bezpieczeństwa.

### 16.38. Relacja `Calendar Engine` -> `Power Scheduler` -> RTC

Obsługę wyłączenia i RTC należy rozdzielić od samego kalendarza:

```text
Calendar Engine
      |
      | next_active_period / next_wake
      v
Power Scheduler
      |
      | arm + verify
      v
RTC / shutdown
```

`Calendar Engine` wyznacza czas następnego wymaganego uruchomienia. `Power Scheduler` odpowiada za politykę `SCHEDULED_SHUTDOWN`, zaprogramowanie RTC, jego weryfikację i bezpieczne uruchomienie procedury shutdownu.

RTC jest więc mechanizmem wykonawczym warstwy zasilania, a nie częścią modelu kalendarza.

Wcześniejsze określenia „scheduler” w sekcjach dotyczących kalendarza należy interpretować jako funkcjonalność docelowo realizowaną przez `Calendar Engine`; funkcje bezpiecznego shutdownu i RTC należą do `Power Scheduler`.

### 16.39. Implementacja — osobny moduł, nie osobny demon

W pierwszej implementacji `Calendar Engine` powinien być niezależną warstwą architektoniczną, ale nie osobnym procesem Linux. Pozostaje uruchamiany wewnątrz `ventilation-core` jako wydzielony moduł domenowy.

Koncepcyjna struktura kodu:

```text
src/ventilation_core/
    calendar/
        model.py
        resolver.py
        profiles.py
        exceptions.py
        timezone.py

    power_schedule/
        rtc.py
        shutdown.py
        wake_plan.py
```

Taki podział zapewnia separację odpowiedzialności bez dokładania kolejnego demona, IPC i dodatkowego punktu awarii. Jeżeli w przyszłości pojawi się realna potrzeba, granica modułu pozwoli Calendar Engine wydzielić bez przebudowy logiki automatyki.

### 16.40. GUI kalendarza

GUI powinno traktować kalendarz jako osobną funkcjonalność użytkową, np. z widokami:

- tydzień,
- miesiąc,
- rok,
- profile,
- wyjątki / święta / urlopy,
- następne przejście,
- następne wyłączenie,
- następne uruchomienie RTC.

GUI pozostaje klientem. Może edytować dozwoloną konfigurację Calendar Engine i prezentować jej wynik, ale nie rozstrzyga reguł czasu lokalnie.

### 16.41. Fail-safe warstwy kalendarza

Błąd konfiguracji, niespójna reguła albo brak możliwości jednoznacznego wyznaczenia przyszłego aktywnego okresu nie może prowadzić do niekontrolowanego shutdownu.

W takim przypadku:

```text
CALENDAR_RESOLUTION_FAILED
    -> AlertV2
    -> scheduled shutdown INHIBITED
    -> CM5 pozostaje uruchomiony
```

`ventilation-core` powinien nadal działać zgodnie ze swoją bezpieczną polityką fallback. Błąd Calendar Engine nie może wyłączyć warstwy bezpieczeństwa ani bezpośrednio zmienić fizycznych wyjść.

### 16.42. Zasada architektoniczna

Docelowa separacja odpowiedzialności jest następująca:

```text
Calendar Engine  = KIEDY i JAKI PROFIL
Power Scheduler  = KIEDY UŚPIĆ/WYŁĄCZYĆ I JAK UZBROIĆ RTC
ventilation-core = CO W DANEJ CHWILI ZROBIĆ Z WENTYLACJĄ
GUI              = KONFIGURACJA I PREZENTACJA
```

Ta granica ma być zachowana w modelu danych, testach, API i dalszej implementacji automatyki.