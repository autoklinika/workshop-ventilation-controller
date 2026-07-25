# Koncepcja interfejsu użytkownika

## 1. Główna idea

Interfejs nie powinien być prezentowany jako techniczny panel sterowania wentylatorami ani rekuperatorem. Ma być pulpitem jakości powietrza i środowiska pracy warsztatu.

Użytkownik powinien po jednym spojrzeniu rozumieć:

- czy w obu pomieszczeniach można bezpiecznie i komfortowo pracować,
- w której strefie pogorszyła się jakość powietrza,
- czy system już reaguje,
- czy wystąpił alarm, problem z filtrem albo brak komunikacji,
- dlaczego automatyka zmieniła sposób działania wentylacji.

Domyślny ekran ma używać nazw pomieszczeń i funkcji użytkowych, a nie nazw urządzeń, magistral ani rejestrów.

Przykłady:

- `Mycie i wygrzewanie ECU`, zamiast `SEN55 nr 1`,
- `Pomieszczenie lutowania`, zamiast `AERO 4A2`,
- `Przewietrzanie`, zamiast `rejestr 1081 = 1`,
- `Wentylacja 65%`, zamiast `AO1 = 6,5 V`.

## 2. Ekran główny — żywy plan warsztatu

Preferowany ekran główny przedstawia uproszczony plan warsztatu z dwiema strefami.

```text
┌──────────────────────────────────────────────────────────┐
│ AUTOKLINIKA — JAKOŚĆ POWIETRZA                  14:32    │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────────┐  ┌──────────────────────────┐  │
│  │ MYCIE / WYGRZEWANIE  │  │ LUTOWANIE                │  │
│  │                      │  │                          │  │
│  │ 🟡 Jakość średnia    │  │ 🟢 Powietrze dobre      │  │
│  │ VOC rośnie           │  │ Rekuperator: AUTO       │  │
│  │ Wentylacja 82%       │  │ Bieg 2                   │  │
│  └──────────────────────┘  └──────────────────────────┘  │
│                                                          │
│  Stan całego warsztatu: 🟡 System reaguje                │
│                                                          │
│  Ostatnie zdarzenie:                                     │
│  14:29 — zwiększono wyciąg w strefie mycia z 45% do 82%. │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  Strefy       Historia       Zdarzenia       Ustawienia  │
└──────────────────────────────────────────────────────────┘
```

Ekran główny nie powinien zawierać rozbudowanych tabel. Priorytetem są:

- aktualny stan każdej strefy,
- kierunek zmian jakości powietrza,
- aktualna reakcja systemu,
- alarmy i komunikaty wymagające działania,
- ostatnia ważna decyzja automatyki.

## 3. Model statusów

Każda strefa otrzymuje jeden dominujący status:

- **zielony — dobrze:** parametry stabilne, brak alarmów,
- **żółty — uwaga:** pogorszenie jakości powietrza lub aktywne zwiększanie wentylacji,
- **czerwony — alarm:** błąd urządzenia, brak skutecznej wentylacji, alarm rekuperatora lub utrzymujące się złe parametry,
- **szary — brak danych:** brak komunikacji, uruchamianie systemu lub nieważne pomiary.

Kolor nie może być jedynym nośnikiem informacji. Zawsze towarzyszy mu tekst i ikona.

## 4. Widok strefy 1 — mycie i wygrzewanie ECU

Widok szczegółowy powinien pokazywać:

- ocenę jakości powietrza,
- VOC Index i kierunek zmian,
- PM1.0, PM2.5, PM4 i PM10,
- temperaturę i wilgotność,
- zadaną wydajność nawiewu,
- zadaną wydajność wyciągu,
- opcjonalne obroty z Tacho,
- aktywny tryb: automatyczny, przewietrzanie, ręczny, awaryjny,
- stan komunikacji z modułem SEN55 + STM32,
- wykresy z ostatniej godziny, doby i tygodnia.

Najważniejsze akcje użytkownika:

- `Przewietrz teraz`,
- `Tryb automatyczny`,
- `Tryb ręczny` — dostępny po świadomym wejściu do ustawień zaawansowanych,
- podgląd przyczyny ostatniej zmiany wydajności.

## 5. Widok strefy 2 — pomieszczenie lutowania

Widok szczegółowy powinien pokazywać:

- ocenę jakości powietrza z lokalnego SEN55,
- stan miejscowego odciągu, jeżeli w przyszłości zostanie podłączony,
- tryb rekuperatora: OFF, AUTO, bieg 1–3, harmonogram, wietrzenie,
- rzeczywistą wydajność nawiewu i wywiewu,
- temperaturę zewnętrzną, nawiewu, wywiewu i wyrzutni,
- stan bypassu,
- aktywne rozmrażanie,
- stan filtra,
- alarmy AERO,
- stan komunikacji Modbus z NANO COLOR 2.

Najważniejsze akcje użytkownika:

- `Przewietrz teraz`,
- `Powrót do AUTO`,
- podgląd bieżącego alarmu,
- potwierdzenie wykonania obsługi filtra.

Interfejs nie powinien eksponować technicznych nazw `AERO 4A2`, `C14`, `Modbus` ani numerów rejestrów poza ekranem diagnostycznym.

## 6. Historia i wyjaśnialność automatyki

System ma nie tylko rysować wykresy, lecz także tłumaczyć swoje decyzje.

Przykład zdarzenia:

```text
11:42 — VOC w strefie mycia wzrósł z 92 do 188.
11:43 — nawiew zwiększono z 40% do 70%.
11:43 — wyciąg zwiększono z 45% do 80%.
11:55 — VOC zaczął spadać.
12:04 — przywrócono normalną wentylację.
```

Każda automatyczna zmiana powinna zapisywać:

- czas,
- strefę,
- powód,
- stan przed zmianą,
- podjętą akcję,
- stan po zmianie,
- wynik lub czas zakończenia reakcji.

Dzięki temu użytkownik widzi nie tylko co się wydarzyło, ale również dlaczego.

## 7. Nawigacja

Podstawowe sekcje aplikacji:

1. **Warsztat** — ekran główny z planem obu stref.
2. **Historia** — wykresy i porównania parametrów.
3. **Zdarzenia** — chronologiczny dziennik decyzji, alarmów i zmian trybów.
4. **Ustawienia** — konfiguracja stref, progów i urządzeń.
5. **Serwis** — ekran techniczny przeznaczony do uruchomienia i diagnostyki.

Najczęściej używane funkcje nie powinny wymagać wchodzenia do menu serwisowego.

## 8. Tryb serwisowy

Dane techniczne pozostają dostępne, ale są oddzielone od codziennego interfejsu.

Tryb serwisowy może zawierać:

- surowe wartości rejestrów Modbus,
- adresy urządzeń,
- stan magistrali RS-485,
- czasy odpowiedzi i liczniki błędów,
- wartości napięć DAC,
- liczniki impulsów Tacho,
- wersje firmware,
- test odczytu i test elementów wykonawczych,
- log diagnostyczny.

Zmiany mogące wpływać na bezpieczeństwo lub pracę urządzeń powinny wymagać dodatkowego potwierdzenia.

## 9. Tryby ręczne i bezpieczeństwo UI

Ręczne sterowanie nie może przypadkowo wyłączyć automatyki na stałe.

Zasady:

- ręczne przewietrzanie jest czasowe,
- po zakończeniu czasu system wraca do AUTO,
- ekran zawsze pokazuje, kto steruje: automatyka, użytkownik czy sterownik AERO,
- aktywne wymuszenie pokazuje pozostały czas,
- alarmy mają pierwszeństwo przed estetyką i innymi komunikatami,
- interfejs nie może sugerować, że SEN55 jest certyfikowanym detektorem zagrożeń chemicznych.

## 10. Styl wizualny

Kierunek wizualny:

- czytelny interfejs dotykowy,
- duże kafle stref,
- ograniczona liczba przycisków,
- jasna hierarchia informacji,
- łagodne tła w stanie normalnym,
- wyraźne, lecz nie agresywne komunikaty ostrzegawcze,
- tryb dzienny i nocny,
- pełne polskie nazewnictwo użytkowe,
- ikony wspierające tekst, nigdy zastępujące go całkowicie.

Interfejs powinien być spójny stylistycznie z ECU Platform, ale pozostawać niezależną aplikacją i nie kopiować jej struktury technicznej.

## 11. Architektura UI przygotowana na rozwój

Model interfejsu powinien opierać się na niezależnych strefach i modułach, aby w przyszłości można było dodać bez przebudowy całej aplikacji:

- kolejne pomieszczenia,
- zużycie energii,
- licznik godzin pracy wentylatorów,
- przypomnienia serwisowe,
- filtrację i stan filtrów,
- kompresor,
- piec do wygrzewania,
- czujniki temperatury i wilgotności,
- powiadomienia zdalne,
- ogólny pulpit stanu warsztatu.

Rozszerzenia nie oznaczają łączenia kodu z ECU Platform ani CRT. System może w przyszłości prezentować wspólny stan warsztatu, ale projekty pozostają technicznie rozdzielone.

## 12. Zakres pierwszej wersji UI

Pierwszy etap powinien obejmować:

- ekran główny z dwiema strefami,
- widok szczegółowy każdej strefy,
- czytelne statusy zielony/żółty/czerwony/szary,
- bieżące parametry SEN55,
- stan wentylatorów strefy 1,
- stan AERO strefy 2,
- przycisk czasowego przewietrzania,
- prostą historię 24 h,
- dziennik zdarzeń,
- ekran diagnostyczny komunikacji.

Zaawansowane raporty, powiadomienia mobilne, zużycie energii i kolejne moduły należy traktować jako późniejsze etapy.