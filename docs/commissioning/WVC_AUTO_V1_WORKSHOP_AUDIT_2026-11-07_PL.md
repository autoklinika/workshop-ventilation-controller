# WVC AUTO V1 — odbiór techniczny w warsztacie

Data: 7 listopada 2026 (Europe/Warsaw). Dwa pomieszczenia po 36 m³. EC: kanały Ø160 mm, SEN55 #1. Rekuperator AERO: kanały Ø120 mm, SEN55 #2.

**Decyzja: NO-GO dla bezobsługowej aktywacji AUTO do czasu zamknięcia braków poniżej.** Dotychczasowy ręczny WVC pozostaje działający.

## 1. Stan przed testem

- CM5: Core STOP, EC 0 V / 0 V, AERO 0% / 0%; SEN55 nr 1 i nr 2 online/usable; aktywne alarmy: 0.
- PM2.5: EC 29,7 µg/m³, AERO 31,5 µg/m³ — wskazania SEN55, nie wynik pomiarów narażenia zawodowego.
- Produkcyjny Control Engine: actuation_supported=false. Nowy, aktywny kod jest w PR #94 i nie został wdrożony do produkcji.

## 2. Weryfikacja fizyczna AERO — PASS

Wszystkie polecenia były wysyłane przez istniejącą ścieżkę Core, a po wykonaniu sprawdzano rzeczywistą telemetrię obu wentylatorów.

| Przejście | Potwierdzony stan | Czas komendy | Status |
|---|---|---:|---|
| 0 → bieg 1 | 30% / 30% | 14,85 s | PASS |
| 1 → bieg 2 | 60% / 60% | 7,75 s | PASS |
| 2 → bieg 3 | 90% / 90% | 7,75 s + stabilizacja | PASS |
| 3 → 0 | 0% / 0% | 34,43 s | PASS |
| 0 → bieg 3 (drugi test) | 90% / 90% | 21,9 s | PASS |
| Wietrzenie ON | 100% / 100% | 7,6 s | PASS |
| Wietrzenie OFF | 90% / 90% | 7,5 s | PASS |
| 3 → 0 (rollback) | 0% / 0% | 32,2 s | PASS |

Istotne: przy przejściu 2 → 3 pierwszy odczyt „potwierdzony” miał 60% / 90%, a dopiero po kolejnych sekundach oba kanały osiągnęły 90%. Oryginalny AERO executor potwierdza dowolną zmianę, nie docelowy stan dwóch wentylatorów. Kod AUTO uzupełniono o weryfikację pary wartości docelowych.

Dowody surowe:
- /home/wentylacja/commissioning/WVC_AERO_PHYSICAL_TEST_2026-11-07.jsonl
- /home/wentylacja/commissioning/WVC_AERO_MAX_PHYSICAL_TEST_2026-11-07.jsonl

Na końcu AERO 0% / 0%, EC STOP / 0 V / 0 V; alarmy 0. Nie wykonywano zmian trwałych.

## 3. Bilans strumieni — orientacyjny, jeszcze NIEZATWIERDZONY

Metoda: jednopunktowy pomiar prędkości skrzydełkowym anemometrem przy wylocie Ø160 mm (EC) i Ø120 mm (AERO). Przeliczenie prędkości punktowej na Q nie daje średniej po przekroju ani rzeczywistej wydajności.

| Profil EC | Szac. IN m³/h | Szac. OUT m³/h | Różnica OUT względem IN |
|---|---:|---:|---:|
| ECO 2/1 V | 101 | 109 | +7,1% |
| NORMAL 4/3 V | 174 | 188 | +8,3% |
| BOOST 7/5 V | 268 | 290 | +8,1% |
| HIGH 9/6 V | 304 | 326 | +7,1% |
| MAX 10/7 V | 340 | 362 | +6,4% |

AERO przy Ø120 mm, punktowo IN/OUT: bieg 1 — 85/73, bieg 2 — 216/175, bieg 3 — 322/265, MAX — 330/273 m³/h. Te wielkości nie dowodzą nadciśnienia lub podciśnienia w pomieszczeniach.

Do potwierdzenia bilansu potrzeba pomiaru uśrednionego po przekroju lub kaptura przepływowego, z kontrolą filtrów, drzwi/bram i działających odciągów miejscowych. Same średnice i kubatury 36 m³ nie przesądzają o wymaganym przepływie.

## 4. TACHO i awarie

- Wcześniej potwierdzono fizycznie rozruch i charakterystykę RPM EC 1–10 V. W Stage7D zweryfikowano w izolowanej konfiguracji czas potwierdzenia TACHO 4,0 s. Produkcyjny tuning nadal pozostaje niekompletny.
- Test syntetyczny nowej pętli AUTO sprawdza utratę TACHO SUPPLY, EXTRACT, BOTH oraz trwałe HOLD. Nie odłączano fizycznych przewodów.
- **BLOKER:** HOLD pozostawia ostatnie wyjścia, co nie gwarantuje bezpiecznego przepływu po zatrzymaniu jednego z wentylatorów. Potrzebna decyzja i walidacja osobno dla wszystkich trzech masek awarii.
- **KOD + TESTY SYNTETYCZNE:** wdrożono w gałęzi osobną pętlę watchdog TACHO EC (2 s), niezależną od trwającego nawet około 60 s polecenia AERO; test wielowątkowy wykazał HOLD pomimo zablokowanego wywołania AERO. **BLOKER:** nadal brakuje walidacji czasowej na realnym CM5 i potwierdzonej procedury awaryjnej dla zatrzymania fizycznego.
- Nie weryfikowano fizycznego odłączenia TACHO pod napięciem; byłoby to niewłaściwe bez zabezpieczonego stanowiska.

## 5. Bezpieczeństwo stanowisk

NIEZATWIERDZONE ZDALNIE: rodzaj i ilość emisji, analiza ryzyka oraz NDS/NDSCh/NDSP, skuteczność odciągów miejscowych przy lutowaniu, ewentualna niezależna ochrona przed CO przy pracach silnikowych, konieczność wentylacji awaryjnej, stan drzwi i czerpni, wyłącznik awaryjny, fizyczne zachowanie przy zaniku zasilania.

WVC nie może traktować SEN55 jako detektora CO, a indeksów VOC/NOx jako oznaczeń konkretnych toksyn. PM2.5 z SEN55 nie zastępuje pomiarów narażenia zawodowego. Nie istnieje jedna uniwersalna wartość ACH gwarantująca bezpieczeństwo dla wszystkich prac warsztatowych.

Źródła:
- Ogólne przepisy BHP §30–32: https://eli.gov.pl/api/acts/DU/2003/1650/text.html
- Warunki techniczne §147–149: https://eli.gov.pl/api/acts/DU/2022/1225/text.html
- NDS: https://eli.gov.pl/eli/DU/2018/1286/ogl
- Badania i pomiary czynników szkodliwych: https://eli.gov.pl/api/acts/DU/2023/419/text.html
- GIS: https://www.gov.pl/web/gis/czynniki-szkodliwe-wystepujace-w-miejscu-pracy2

## 6. Podsumowanie GO/NO-GO

| Kryterium | Ocena |
|---|---|
| SEN55, RS485 i podstawowy CoreState | PASS |
| Fizyczne przełączenia AERO 1/2/3/MAX i powrót | PASS |
| Fizyczna charakterystyka RPM/TACHO EC | PASS częściowy |
| Rzeczywisty bilans przepływów i wymagany Q | INCOMPLETE |
| Bezpieczna reakcja na fizyczną awarię jednego lub obu EC | INCOMPLETE |
| Nadzór TACHO podczas przejścia AERO | PASS symulacyjnie / fizycznie INCOMPLETE |
| BHP procesu, odciągi, ryzyko CO, wymagania NDS | INCOMPLETE |
| Aktywacja bezobsługowego AUTO | **NO-GO** |

Nie podpisywać fikcyjnej akceptacji commissioning ani nie omijać bramki aktywacji. Po uzyskaniu wymaganych dowodów należy powtórzyć kontrolowaną próbę z operatorem przy instalacji i dopiero wtedy rozważyć GO.
