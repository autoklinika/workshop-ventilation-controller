# Prompt startowy — SEN55 Modbus Stage 2B

Skopiuj poniższy tekst do nowej rozmowy.

---

Kontynuujemy rozwój Workshop Ventilation Controller po zakończeniu checkpointu integracyjnego z 2026-08-03.

Repozytorium:

`autoklinika/workshop-ventilation-controller`

Obowiązująca gałąź bazowa:

`main`

Najpierw sprawdź rzeczywisty aktualny HEAD `main`, stan repozytorium oraz wszystkie otwarte PR-y. Nie zakładaj, że numery commitów podane w raportach są nadal aktualnym końcem gałęzi.

Przeczytaj dokładnie:

- `docs/reports/VENTILATION_CONTROLLER_CHECKPOINT_2026-08-03_PL.md`
- `docs/MODBUS_MAP_PL.md`
- `docs/reports/KAMOD_MODBUS_STAGE2_IMPLEMENTATION_PL.md`
- `docs/DECISIONS_PL.md`
- `docs/COMPIT_AERO4A2_INTEGRATION_PL.md`
- `docs/reports/COMPIT_NANO_V630_CONTROL_VALIDATION_PL.md`

Najważniejsza decyzja architektoniczna:

Rekuperator NANO COLOR 2 / AERO 4A2 ma osobną magistralę RS-485 i nie może zostać dołączony do magistrali czujników SEN55.

Docelowy podział:

```text
RS-485 SENSOR BUS
CM5 ↔ KAmod + SEN55 #1 ↔ KAmod + SEN55 #2
19200 bit/s, 8N1, FC04
```

```text
RS-485 AERO BUS
CM5 ↔ NANO COLOR 2 v6.30 / AERO 4A2
9600 bit/s, 8N1, slave 44, FC03/FC06
```

Celem nowego etapu jest:

**SEN55 Modbus Stage 2B — dwa węzły KAmod + SEN55 na jednej, oddzielnej magistrali czujników.**

Utwórz nową gałąź roboczą, np.:

`agent/kamod-modbus-stage2b-multinode`

Nie wykonuj merge ani nie oznaczaj PR jako Ready for Review bez mojego wyraźnego polecenia.

## Stan bazowy Stage 2A

Firmware:

`0.2.0-stage2`

Potwierdzony kontrakt pojedynczego węzła:

```text
Modbus RTU slave
19200 bit/s
8N1
slave 1
FC04 Read Input Registers
mapa wersja 1
adresy 0..18
brak funkcji zapisu
```

Stage 2A został zwalidowany programowo i fizycznie. Nie przebudowuj istniejącej mapy bez rzeczywistej potrzeby.

Zachowaj:

- funkcję `FC04`,
- 19 Input Registers,
- kolejność i kodowanie danych,
- wersjonowanie mapy,
- status `MEASUREMENT_VALID`,
- maskę dostępności,
- wiek pomiaru,
- liczniki błędów,
- kolejność high word / low word,
- odrzucanie funkcji zapisu,
- odzyskiwanie po utracie SEN55,
- istniejące zabezpieczenia OTA i platform readiness.

## Zakres Stage 2B

1. Zaprojektuj minimalny i bezpieczny sposób nadania dwóm urządzeniom trwałych adresów Modbus `1` i `2`.

2. Przed implementacją krótko porównaj możliwe rozwiązania:

- osobne warianty builda / konfiguracja Kconfig,
- lokalny provisioning przez USB/UART i zapis w NVS,
- inne proste rozwiązanie odpowiednie dla jednego lokalnego wdrożenia.

Preferuj rozwiązanie proste, serwisowalne i odporne na przypadkową zmianę. Nie dodawaj zdalnej zmiany adresu przez Modbus w tym etapie.

3. Baudrate pozostaje stały:

```text
19200 bit/s, 8N1
```

4. Oba węzły muszą używać tego samego kodu firmware i tej samej mapy danych.

5. Nie dodawaj do zakresu:

- rekuperatora AERO,
- drugiej prędkości na tej magistrali,
- Wi-Fi jako kanału produkcyjnych pomiarów,
- MQTT,
- Home Assistant,
- AI,
- GUI,
- Modbus mastera produkcyjnego na CM5,
- zapisywalnych Holding Registers,
- zdalnej konfiguracji przez Modbus.

6. Przygotuj lub rozbuduj narzędzie PC do jednoczesnego odpytywania slave `1` i `2`.

Narzędzie powinno:

- odczytywać pełną mapę FC04 każdego węzła,
- sprawdzać CRC,
- sprawdzać wersję mapy,
- sprawdzać `MEASUREMENT_VALID`, maskę i wiek,
- jednoznacznie oznaczać dane z węzła 1 i 2,
- raportować brak odpowiedzi jednego węzła bez przerywania odczytu drugiego,
- mieć tryb cykliczny i podsumowanie błędów,
- nie wykonywać zapisów.

7. Dodaj testy hostowe i walidację CI dla:

- poprawnego zastosowania adresu urządzenia,
- odrzucenia adresu spoza zakresu 1..247,
- zachowania istniejącej mapy rejestrów,
- braku regresji kodowania danych,
- konfiguracji dwóch wariantów urządzenia,
- składni narzędzia PC,
- pełnego builda ESP-IDF.

## Wymagana walidacja fizyczna

Walidację wykonamy etapami z użytkownikiem. Przygotuj precyzyjne komendy, ale nie twierdź, że sprzęt został przetestowany bez otrzymania wyników.

Docelowe stanowisko:

- KAmod ESP32 POW RS485 + SEN55, slave 1,
- KAmod ESP32 POW RS485 + SEN55, slave 2,
- jedna liniowa magistrala RS-485 SENSOR BUS,
- izolowany konwerter USB–RS485,
- 19200 bit/s, 8N1.

Minimalne testy fizyczne:

1. osobny odczyt slave 1,
2. osobny odczyt slave 2,
3. odczyt obu urządzeń na jednej magistrali,
4. brak odpowiedzi dla nieistniejącego adresu,
5. odłączenie slave 1 — slave 2 nadal działa,
6. ponowne podłączenie slave 1 — automatyczny powrót,
7. odłączenie slave 2 — slave 1 nadal działa,
8. zimny start obu urządzeń i mastera,
9. dłuższy test cykliczny bez timeoutów i błędów CRC,
10. kontrola `modbus_errors` obu węzłów,
11. próba nieobsługiwanej funkcji zapisu nadal odrzucana,
12. potwierdzenie topologii liniowej i terminacji tylko na końcach magistrali.

## Kryteria jakości

- żadna awaria jednego węzła nie blokuje odczytu drugiego,
- master nie interpretuje danych bez `MEASUREMENT_VALID`,
- brak odpowiedzi jest rozróżniany od nieaktualnego pomiaru,
- nie ma konfliktu adresów,
- nie ma zmian formatu sesji ani istniejącej mapy bez wersjonowania,
- nie ma bezpośrednich zależności GUI od RS-485,
- nie mieszamy magistrali SENSOR i AERO.

## Dokumentacja końcowa etapu

Po implementacji i walidacji przygotuj:

- raport implementacyjny Stage 2B,
- raport walidacji CI,
- raport fizycznej walidacji dwóch węzłów,
- aktualizację `docs/MODBUS_MAP_PL.md`, jeżeli wymaga jej sposób konfiguracji adresu,
- aktualizację `docs/DECISIONS_PL.md`,
- końcowy raport i handoff do następnego etapu,
- opis PR z zakresem, testami, ograniczeniami i następnymi krokami.

Na początku pracy przedstaw krótki plan Stage 2B oraz rekomendowany sposób trwałego nadania adresów `1` i `2`. Następnie realizuj etap małymi, kontrolowanymi krokami z checkpointem przed walidacją sprzętową.

---
