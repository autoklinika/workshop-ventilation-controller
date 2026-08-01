# Integracja lokalnej AI

## 1. Cel

Lokalna AI jest opcjonalną warstwą analityczną systemu Workshop Ventilation Controller. Ma wspomagać użytkownika w interpretacji danych, wykrywaniu anomalii, przygotowywaniu raportów i proponowaniu zmian konfiguracji.

Warstwa AI nie jest częścią krytycznej automatyki i nie może być wymagana do prawidłowej pracy wentylacji.

## 2. Platforma wykonawcza

Usługa AI będzie uruchamiana na osobnym komputerze Minisforum z lokalnym środowiskiem Ollama. Raspberry Pi Compute Module 5 pozostaje jedynym sterownikiem centralnym instalacji.

Model używany przez CAN Research Tool może być współdzielony infrastrukturalnie, ale oba projekty zachowują:

- osobne konteksty i prompty systemowe,
- osobne dane i historię,
- osobne narzędzia,
- osobne uprawnienia,
- techniczną niezależność aplikacji.

Wspólna jest wyłącznie usługa uruchamiająca model na Minisforum.

## 3. Zasada bezkarnego wyłączenia

Wyłączenie, restart, aktualizacja, przeciążenie lub awaria Minisforum, Ollamy, modelu albo połączenia sieciowego nie może wpływać na:

- odczyt czujników,
- komunikację Modbus RTU i RS-485,
- sterowanie wentylatorami 0–10 V,
- harmonogramy,
- alarmy,
- tryby awaryjne,
- sterowanie rekuperatorem,
- lokalny zapis podstawowej historii,
- działanie interfejsu sterowania na CM5.

Po odłączeniu AI niedostępne mogą być wyłącznie funkcje analityczne, raportowe i konwersacyjne.

## 4. Podział odpowiedzialności

### Raspberry Pi Compute Module 5 / `ventilation-core`

CM5 odpowiada za całą deterministyczną automatykę:

- pobieranie i walidację pomiarów,
- wykonywanie reguł sterowania,
- obsługę progów, histerez i harmonogramów,
- sterowanie wentylatorami i rekuperatorem,
- funkcje bezpieczeństwa i stany bezpieczne,
- alarmy krytyczne,
- watchdogi,
- rejestrację zdarzeń,
- autorytatywny stan systemu.

### Minisforum / Ollama

AI może:

- analizować dane bieżące i historyczne,
- tworzyć raporty dzienne, tygodniowe i miesięczne,
- odpowiadać na pytania użytkownika w języku naturalnym,
- wykrywać nietypowe trendy i anomalie,
- porównywać skuteczność wentylacji między podobnymi zdarzeniami,
- oceniać czas oczyszczania pomieszczeń,
- wskazywać możliwe pogorszenie przepływu, zabrudzenie filtrów lub zmianę zachowania czujnika,
- proponować korekty ustawień,
- uzasadniać rekomendacje na podstawie danych.

AI nie może:

- bezpośrednio sterować wentylatorami,
- wysyłać poleceń RS-485 lub Modbus,
- bezpośrednio zapisywać wartości DAC,
- zmieniać progów bezpieczeństwa,
- kasować alarmów,
- omijać logiki domenowej,
- samodzielnie stosować rekomendowanych zmian.

Ograniczenia muszą wynikać z architektury API i przyznanych uprawnień, a nie wyłącznie z instrukcji tekstowej modelu.

## 5. Profil instalacji

AI będzie korzystać z ustrukturyzowanego profilu instalacji opisującego rzeczywisty obiekt. Profil powinien zawierać między innymi:

- geometrię i kubaturę pomieszczeń,
- przeznaczenie poszczególnych stref,
- rozmieszczenie czujników,
- lokalizację nawiewów i wyciągów,
- parametry wentylatorów i rekuperatora,
- charakterystykę źródeł zanieczyszczeń, w tym myjek i pieca,
- dostępne pomiary i ich jednostki,
- progi, cele sterowania i ograniczenia,
- harmonogramy pracy,
- znane stany normalne i awaryjne,
- historię eksploatacji i zmian konfiguracji.

Sam opis pomieszczenia nie gwarantuje precyzyjnych rekomendacji. Dokładność będzie wynikała z połączenia profilu instalacji, zweryfikowanych danych historycznych, bieżącej telemetrii i klasycznych obliczeń statystycznych.

## 6. Analiza w czasie rzeczywistym

Wykrywanie anomalii zostaje podzielone na dwa poziomy.

### Poziom deterministyczny — CM5

Natychmiastowo i niezależnie od AI wykrywane są:

- przekroczenia jawnych progów,
- utrata komunikacji,
- brak świeżych danych,
- awaria czujnika,
- niewłaściwy stan urządzenia,
- alarmy bezpieczeństwa,
- błędy wykonawcze i watchdogi.

### Poziom analityczny — AI

AI może wykrywać zjawiska wymagające kontekstu historycznego, na przykład:

- wydłużający się czas oczyszczania przy podobnych warunkach,
- nietypową dynamikę wzrostu VOC lub PM,
- niższą skuteczność wentylacji przy tych samych nastawach,
- stopniową zmianę charakterystyki czujnika,
- nietypowe zależności między obrotami, temperaturą, wilgotnością i jakością powietrza,
- zachowanie odbiegające od profilu normalnej pracy warsztatu.

Alarmy AI są komunikatami diagnostycznymi i rekomendacjami. Nie zastępują alarmów deterministycznych generowanych przez `ventilation-core`.

## 7. Rekomendacje ustawień

AI może proponować zmiany parametrów na podstawie historii i porównania podobnych zdarzeń, na przykład:

- zmianę minimalnych obrotów,
- zmianę czasu przewietrzania po zdarzeniu,
- korektę harmonogramu,
- wcześniejsze zwiększenie wydajności przy rozpoznanym trendzie,
- kontrolę filtra, przepustnicy lub wentylatora.

Każda rekomendacja powinna zawierać:

- proponowaną zmianę,
- zakres danych użytych do analizy,
- uzasadnienie,
- oczekiwany efekt,
- poziom pewności,
- możliwe ryzyko,
- możliwość odrzucenia przez użytkownika.

Pierwsza wersja integracji nie stosuje zmian automatycznie. Ewentualna przyszła funkcja zatwierdzania rekomendacji musi przekazywać wyłącznie intencję do warstwy aplikacyjnej CM5. Rdzeń ponownie sprawdza zakres, uprawnienia, stan instalacji i ograniczenia bezpieczeństwa.

## 8. Dane i komunikacja

Preferowany podział kanałów:

- MQTT — bieżąca telemetria, zdarzenia i potwierdzony stan domenowy,
- REST API — historia, statystyki, profil instalacji i zapytania analityczne,
- osobny interfejs AI Gateway — kontrolowane narzędzia udostępnione modelowi.

W pierwszym etapie AI ma dostęp wyłącznie do odczytu. Przykładowe operacje:

```text
get_current_state()
get_measurements(time_range)
get_events(time_range)
get_daily_statistics(date)
get_installation_profile()
create_recommendation()
```

Nie udostępnia się modelowi operacji takich jak:

```text
set_fan_speed()
write_modbus()
write_dac()
disable_alarm()
change_safety_threshold()
```

CM5 buforuje dane potrzebne do późniejszego uzupełnienia historii. Po ponownym uruchomieniu Minisforum warstwa analityczna może pobrać brakujący okres bez wpływu na bieżące sterowanie.

## 9. Obliczenia klasyczne i model językowy

Model językowy nie powinien samodzielnie obliczać podstawowych statystyk z dużych zbiorów surowych próbek. Oprogramowanie analityczne powinno deterministycznie wyliczać między innymi:

- wartości minimalne, maksymalne, średnie i mediany,
- przekroczenia progów,
- czas trwania zdarzeń,
- czas powrotu do normy,
- trendy i pochodne,
- korelacje,
- porównania z historyczną bazą odniesienia.

Model otrzymuje uporządkowane wyniki, interpretuje je, łączy z profilem instalacji i przygotowuje zrozumiały opis lub rekomendację. Ogranicza to ryzyko błędów obliczeniowych i halucynacji.

## 10. Etapy wdrożenia

1. Uruchomienie i walidacja kompletnej automatyki bez AI.
2. Stabilny zapis danych, zdarzeń i decyzji sterownika.
3. Uruchomienie Ollamy na Minisforum.
4. Implementacja `AI Gateway` w trybie tylko do odczytu.
5. Raporty i pytania o historię.
6. Budowa profilu normalnej pracy instalacji.
7. Wykrywanie anomalii w czasie zbliżonym do rzeczywistego.
8. Proponowanie optymalizacji ustawień bez automatycznego stosowania.
9. Ewentualne zatwierdzanie wybranych rekomendacji przez użytkownika i ponowna walidacja w `ventilation-core`.

## 11. Zasada końcowa

AI jest doradcą i warstwą analityczną. `ventilation-core` pozostaje jedynym źródłem prawdy i jedynym komponentem uprawnionym do wykonywania logiki sterowania. System musi zachować pełną funkcjonalność automatyki nawet po trwałym usunięciu całej warstwy AI.

## 12. Diagnostyka dwukanałowa węzłów

AI może korzystać z przygotowanych przez CM5 wyników diagnostyki krzyżowej RS-485 i prywatnego Wi-Fi węzłów KAmod.

Dane diagnostyczne mogą obejmować:

- stan komunikacji Modbus,
- heartbeat Wi-Fi,
- czas ostatniego zapytania Modbus widziany przez KAmod,
- stan SEN55,
- liczniki błędów I²C i RS-485,
- uptime i przyczynę restartu,
- RSSI,
- historię OTA i rollbacków,
- lokalny bufor zdarzeń węzła.

AI może na tej podstawie przygotować zrozumiałą diagnozę, na przykład odróżnić:

- prawdopodobną awarię przewodu lub magistrali RS-485,
- utratę kanału serwisowego Wi-Fi,
- brak zasilania węzła,
- awarię SEN55 przy działającym KAmod,
- niestabilność firmware lub powtarzające się restarty.

Wniosek o przyczynie awarii pozostaje rekomendacją diagnostyczną. Alarm komunikacyjny, reakcja na brak świeżych danych i strategia bezpieczna są zawsze wyznaczane deterministycznie przez CM5.

AI nie otrzymuje bezpośredniego dostępu do usług serwisowych KAmod. Korzysta wyłącznie z danych zebranych, zweryfikowanych i udostępnionych przez `ventilation-core` lub kontrolowany `AI Gateway`.

Szczegóły komunikacji i macierz stanów definiuje dokument `DUAL_CHANNEL_NODE_COMMUNICATION_PL.md`.