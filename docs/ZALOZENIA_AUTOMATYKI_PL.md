# Założenia automatyki

## Status dokumentu

Dokument definiuje aktualne założenia projektowe automatyki Workshop Ventilation Controller uzgodnione podczas prac koncepcyjnych 2026-08-12.

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
