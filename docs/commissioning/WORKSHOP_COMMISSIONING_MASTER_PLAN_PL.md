# Workshop Ventilation Controller — master plan commissioningowy

Data przygotowania: 2026-08-29  
Środowisko docelowe: **WORKSHOP**  
Tryb Control Engine podczas całego pakietu: **SHADOW / non-actuating**  
WebGUI: **klient**, port docelowy `18091`  
Źródło prawdy: **`ventilation-core`**

## 1. Cel

Ten dokument definiuje kompletną procedurę pierwszego uruchomienia i strojenia Workshop Ventilation Controller po montażu w docelowym warsztacie. Celem commissioning jest zebranie wersjonowanych, powtarzalnych dowodów z rzeczywistej instalacji i wyznaczenie parametrów Control Engine bez improwizowania oraz bez automatycznego przyznawania fizycznego authority.

Commissioning **nie jest** etapem uruchamiania autonomicznego sterowania. Nawet po zakończeniu wszystkich pomiarów Control Engine pozostaje SHADOW, dopóki osobny przyszły etap actuation nie zostanie zaprojektowany, przetestowany i jawnie autoryzowany.

## 2. Stan wejściowy

Repozytorium definiuje dziewięć grup tuningowych:

1. `fan_outputs` — charakterystyka lokalnych wentylatorów EC i bilans pomieszczenia;
2. `aero_outputs` — mapowanie stanów logicznych na rzeczywiste biegi AERO;
3. `dynamics` — histerezy, potwierdzenia, minimum hold i decay;
4. `fan_sensor_fallback` — bezpieczna para nawiew/wyciąg przy utracie SEN55 strefy wentylatorowej;
5. `aero_sensor_fallback` — deterministyczny bieg AERO przy utracie SEN55 strefy rekuperatora;
6. `tacho_confirmation` — czas potwierdzenia braku TACHO;
7. `tacho_supply_fallback` — para awaryjna po potwierdzonej awarii TACHO nawiewu;
8. `tacho_extract_fallback` — para awaryjna po potwierdzonej awarii TACHO wyciągu;
9. `tacho_both_fallback` — polityka awaryjna przy jednoczesnej utracie obu kanałów TACHO.

Aktualny ledger repozytorium ma **1/9** grup spełniających wymagany poziom. `tacho_confirmation` jest `PHYSICAL_VALIDATED` z wartością `4.0 s`. Pozostałe osiem grup wymaga dowodów `WORKSHOP_VALIDATED`.

Wartość `4.0 s` zachowujemy, chyba że zmieni się wentylator, tor TACHO, kondycjonowanie sygnału, pinout albo sposób jego próbkowania.

## 3. Niezmienne zasady bezpieczeństwa

Podczas całego commissioning obowiązują następujące gate'y:

- `actuation_supported=false` dla Control Engine;
- `actuation_authorized=false`;
- `readiness=false`;
- WebGUI pozostaje klientem i nie jest źródłem logiki;
- AI może analizować dane, ale nie może wysyłać poleceń wykonawczych;
- narzędzia commissioningowe są read-only względem sterowania;
- żadna procedura nie może automatycznie wykonywać `set`, `stop`, `aero-speed`, `aero-airing`, restartu hosta, shutdown ani przełączenia zasilania;
- każde fizyczne wymuszenie jest osobną, jawną czynnością operatora przy urządzeniu;
- nie wywołujemy sztucznie niebezpiecznych stężeń PM/VOC/NOx tylko w celu testu — wykorzystujemy normalne procesy warsztatowe albo replay danych;
- przy niespodziewanym ruchu wentylatora, nieoczekiwanym napięciu, utracie kontroli, nieznanym stanie AERO albo błędnej telemetrii test jest natychmiast przerywany;
- nie odłączamy wtyczek RS-485 pod zasilaniem. Jeżeli test wymaga fizycznego rozłączenia, najpierw wyłączamy zasilanie danego węzła zgodnie z procedurą serwisową;
- nie zwieramy i nie odłączamy przewodów TACHO pod pozorem symulacji awarii. Awarię w pierwszej kolejności odtwarzamy przez bezpieczne sterowanie wentylatorem albo replay/symulację wejścia;
- każdy test awaryjny ma wcześniej zdefiniowany sposób powrotu do stanu bezpiecznego.

## 4. Dane identyfikacyjne każdej sesji

Każda sesja commissioningowa musi zapisać co najmniej:

- `session_id` i czas rozpoczęcia/zakończenia w `Europe/Warsaw`;
- operatora;
- miejsce/strefę;
- produkcyjny `main` SHA;
- rzeczywisty SHA runtime core/WebGUI;
- PID i CWD `ventilation-core.service` oraz `wvc-web-ui.service`;
- boot ID;
- stan RTC wakealarm i `wvc-host-power.service`;
- rewizję konfiguracji Calendar i Control Engine;
- stan `actuation_supported`, `actuation_authorized`, `readiness`;
- wersję hardware oraz informację, czy od ostatniej walidacji zmieniano wentylator/TACHO/RS-485/AERO;
- identyfikatory SEN55 i Zigbee używane w instalacji;
- referencję do surowej telemetrii i zakres czasu pomiarów;
- warunki otoczenia: temperatura wewnętrzna, nawiewu/wywiewu/zewnętrzna, stan bram/drzwi, aktywne procesy;
- wszystkie ręczne wymuszenia operatora wraz z czasem;
- anomalie i decyzję PASS/FAIL/INCOMPLETE.

Do tworzenia snapshotu początkowego i końcowego służy `tools/workshop_commissioning_snapshot.py`.

## 5. Gate wejściowy — instalacja jeszcze bez testów dynamicznych

Przed pierwszym uruchomieniem dynamicznym:

### 5.1 Kontrola mechaniczna

- wentylatory i AERO są zamontowane w finalnym układzie kanałów;
- kratki, czerpnie, wyrzutnie i filtry są zamontowane;
- kierunek przepływu jest potwierdzony;
- przewody nie mogą zostać wciągnięte przez wirniki;
- dostęp serwisowy jest zachowany;
- drzwi/bramy, które istotnie wpływają na przepływ, są zidentyfikowane.

### 5.2 Kontrola elektryczna

- PE, zasilania i zabezpieczenia są zweryfikowane;
- sygnały 0–10 V mają wspólną referencję zgodną z projektem;
- TACHO supply/extract jest zgodne z dokumentacją i przypisaniem GPIO;
- nie ma luźnych zacisków;
- 12 V peryferiów i jego odcięcie są sprawdzone serwisowo;
- po włączeniu CM5 żaden kanał EC nie może samoczynnie wystartować.

### 5.3 RS-485 / Zigbee / sensory

- RS-485 ma finalną topologię i zakończenia;
- żadna wtyczka RS-485 nie jest odłączana podczas pracy;
- oba SEN55 są osiągalne i stabilne;
- oba czujniki temperatury Zigbee są przypisane do prawidłowych ról nawiew/wywiew;
- AERO odpowiada stabilnie po swoim interfejsie;
- czasy systemowe CM5 i urządzeń pomocniczych są poprawne.

### 5.4 Preflight software

Wymagane przed kontynuacją:

- `/automation` działa na `http://<CM5>:18091/automation`;
- `ventilation-core.service` i `wvc-web-ui.service` są `active`;
- WebGUI odczytuje rzeczywisty core;
- fizyczne setpointy EC wynoszą `0.0 V`;
- nie ma obserwowanego ruchu lokalnych wentylatorów;
- operator Control Engine jest `AUTO`;
- Control Engine pozostaje SHADOW;
- tuning ledger ma dziewięć grup i nie jest runtime-bound;
- telemetria zapisuje się na docelowy storage;
- alerty są dostępne;
- snapshot PRE został zapisany.

Jeżeli którykolwiek punkt jest niespełniony, commissioning nie przechodzi do testów dynamicznych.

## 6. Faza A — pasywny baseline 48–72 h

Po instalacji najpierw zbieramy **48–72 godziny** danych bez strojenia progów na podstawie pojedynczej chwili. Okres powinien objąć co najmniej jeden normalny dzień pracy oraz okres nocny/nieaktywny.

Zbieramy:

- PM2.5, VOC, NOx, temperaturę i wilgotność z SEN55;
- temperatury kanałowe Zigbee;
- TACHO/RPM obu wentylatorów;
- rzeczywiste setpointy;
- decyzję SHADOW Control Engine i `decision_reason`;
- stan AERO;
- Calendar phase/profile;
- alerty;
- zdarzenia operatora;
- informacje o otwarciu bramy/drzwi i typowych procesach, jeśli można je wiarygodnie zanotować.

Minimalny wynik fazy A:

- brak niewyjaśnionych luk danych;
- brak samoczynnego sterowania z Control Engine;
- rozpoznane normalne zakresy noc/dzień/praca;
- wytypowane reprezentatywne zdarzenia do fazy `dynamics`;
- potwierdzone, które zmiany wynikają z procesu, a które z bramy/drzwi lub pogody.

Baseline nie promuje automatycznie żadnej grupy. Jest materiałem wejściowym.

## 7. Grupa `fan_outputs`

Cel: wyznaczyć rzeczywistą charakterystykę lokalnego nawiewu i wyciągu w finalnym pomieszczeniu.

### 7.1 Przebieg

1. Rozpocznij od 0% i potwierdź brak ruchu.
2. Fizyczne wymuszenie wykonuje operator w istniejącym, zatwierdzonym trybie ręcznym — nie narzędzie commissioningowe.
3. Zwiększaj żądanie małymi krokami, nie większymi niż 10 punktów procentowych na krok.
4. Po każdym kroku czekaj na stabilizację RPM; zapisuj co najmniej kilka minut stabilnego okna.
5. Dla każdego punktu zanotuj supply request, extract request, napięcie, RPM, temperatury, efekt przepływu/bilansu i hałas/wibracje.
6. Nie przechodź do kolejnego kroku, jeżeli pojawia się nadmierne pod-/nadciśnienie, niestabilność, nieprawidłowy TACHO lub anomalia mechaniczna.
7. Oddzielnie wyznacz potrzebny `extract_bias_pct`; nie kopiuj go z założenia LAB.
8. Powtórz reprezentatywne punkty przy innych warunkach termicznych, jeżeli pierwsza sesja nie obejmuje chłodnego nawiewu.

### 7.2 Wynik

Muszą być jawnie wybrane i uzasadnione:

- `normal_air_request_pct`;
- `boost_air_request_pct`;
- `high_air_request_pct`;
- `max_air_request_pct`;
- `thermal_normal_limit_pct`;
- `thermal_limiting_limit_pct`;
- `thermal_minimum_limit_pct`;
- `thermal_protection_limit_pct`;
- `extract_bias_pct`.

Przed promocją wartości są odtwarzane w testach scenario/matrix.

## 8. Grupa `aero_outputs`

Cel: przypisać NORMAL/BOOST/HIGH/MAX do realnych, stabilnych biegów AERO w finalnej instalacji.

Dla każdego dostępnego biegu:

- potwierdź osiągalność i stabilność;
- zapisz temperatury nawiewu/wywiewu, stan AERO i reakcję strefy;
- obserwuj normalne obciążenie procesu, nie generuj sztucznego zanieczyszczenia;
- zanotuj hałas, nietypowe alarmy, bypass/defrost jeśli wystąpią naturalnie;
- po zmianie biegu poczekaj na stabilizację przed oceną.

Wynik:

- `aero_normal_speed`;
- `aero_boost_speed`;
- `aero_high_speed`;
- `aero_max_speed`;

z monotoniczną i uzasadnioną polityką.

## 9. Grupa `dynamics`

Cel: ustawić histerezy i czasy na podstawie realnych trajektorii, nie pojedynczych pików.

Wykorzystaj co najmniej kilka reprezentatywnych zdarzeń z normalnej pracy. Dla każdego oznacz:

- początek procesu;
- początek wzrostu PM/VOC/NOx;
- osiągnięte maksimum;
- koniec procesu;
- czas naturalnego/spowodowanego wentylacją spadku;
- ewentualne ponowne wzrosty;
- zmianę temperatury.

Dobierane pola:

- `pm2_5_hysteresis_ug_m3`;
- `voc_hysteresis_index`;
- `nox_hysteresis_index`;
- `temperature_hysteresis_celsius`;
- `pm2_5_boost_confirmation_seconds`;
- `state_minimum_hold_seconds`;
- `boost_decay_seconds`.

Kryterium: replay zapisanych danych pokazuje eskalację, hold i recovery bez chatter oraz bez maskowania istotnego pogorszenia jakości powietrza.

## 10. Grupy utraty SEN55

### 10.1 `fan_sensor_fallback`

Najpierw ustal fizyczny efekt kilku kandydatów fallback w realnym pomieszczeniu przy działającym SEN55. Dopiero później przeprowadź kontrolowany test fault/recovery.

Wynik:

- `sensor_fallback_supply_pct`;
- `sensor_fallback_extract_pct`.

Fallback ma być konserwatywny, ale nie wolno go opisywać jako dowodu bezpieczeństwa BHP — brak pomiaru oznacza brak wiedzy o rzeczywistym stężeniu.

### 10.2 `aero_sensor_fallback`

W realnej strefie rekuperatora sprawdź kandydatów biegu fallback, następnie wykonaj kontrolowany fault/recovery.

Wynik:

- `aero_sensor_fallback_speed`.

### 10.3 Bezpieczne wywołanie utraty sensora

Preferencja kolejności:

1. replay/symulacja do sprawdzenia logiki;
2. kontrolowane programowe odcięcie źródła danych w oknie serwisowym, jeśli mamy do tego osobną zatwierdzoną procedurę;
3. fizyczne odłączenie tylko gdy jest konieczne i po bezpiecznym wyłączeniu zasilania właściwego węzła.

Nigdy nie wykonujemy hot-unplug RS-485 jako metody testowej.

## 11. `tacho_confirmation`

Aktualnie wartość `4.0 s` jest `PHYSICAL_VALIDATED` i nie wymaga ponownego strojenia w warsztacie, jeżeli hardware toru TACHO pozostał bez zmian.

W pierwszym uruchomieniu wykonujemy jedynie sanity-check:

- właściwy kanał odpowiada właściwemu wentylatorowi;
- RPM rośnie wraz z rzeczywistą prędkością;
- przy 0 V nie ma ruchu;
- nie ma fałszywych faultów w normalnej pracy.

Zmiana hardware unieważniająca wcześniejsze evidence otwiera tę grupę ponownie.

## 12. Grupy fallback TACHO

### 12.1 `tacho_supply_fallback`

Sprawdź finalny pokój w stanie, w którym nawiew jest rzeczywiście niedostępny albo utrzymany na 0, podczas gdy odpowiedź wyciągu jest obserwowana. Zwróć szczególną uwagę na podciśnienie i wpływ na transport zanieczyszczeń.

Wynik:

- `tacho_supply_fault_fallback_supply_pct`;
- `tacho_supply_fault_fallback_extract_pct`.

### 12.2 `tacho_extract_fallback`

Sprawdź stan, w którym wyciąg jest niedostępny albo utrzymany na 0. Zwróć szczególną uwagę na dodatnie ciśnienie i ryzyko migracji zanieczyszczeń do innych pomieszczeń.

Wynik:

- `tacho_extract_fault_fallback_supply_pct`;
- `tacho_extract_fault_fallback_extract_pct`.

### 12.3 `tacho_both_fallback`

Najpierw rozróżnij prawdziwą utratę obu wentylatorów od uszkodzenia wspólnego toru sygnałowego. Następnie oceń w realnym pomieszczeniu awaryjną strategię logiczną i procedurę operatora.

Wynik:

- `tacho_both_fault_fallback_supply_pct`;
- `tacho_both_fault_fallback_extract_pct`.

Dla wszystkich trzech masek wartości muszą mieć własne evidence. Nie wolno kopiować pary z innego fault mask bez osobnego testu.

## 13. Testy systemowe poza dziewięcioma grupami tuningowymi

Te testy nie zwiększają licznika 1/9, ale są wymagane przed przyszłym etapem authority.

### 13.1 Calendar

- czas lokalny `Europe/Warsaw`;
- przejście przez regułę tygodniową;
- wyjątek daty;
- PREVENTILATION/PURGE, jeśli są używane;
- zachowanie po restarcie core;
- brak wpływu WebGUI restart na stan Calendar.

### 13.2 Restart i recovery

W kontrolowanym oknie serwisowym:

- restart samego WebGUI — core nie zmienia stanu;
- restart core — WebGUI pozostaje klientem, operator volatile wraca do AUTO;
- persistence Calendar;
- po pełnym reboot CM5 runtime uruchamia się zgodnie z wdrożoną konfiguracją;
- brak niezamierzonego startu fizycznych wyjść podczas bootu/recovery.

### 13.3 Telemetryka

- zapis ciągły na docelowy storage;
- poprawne timestampy;
- identyfikowalne luki;
- brak wpływu logowania na stabilność core;
- kopia danych z sesji jest zachowana przed zmianą parametrów.

### 13.4 Alerty

Dla bezpiecznie możliwych przypadków potwierdź, że operator widzi fault, jego źródło, czas, acknowledge/clear zgodnie z aktualnym kontraktem alertów.

## 14. Kryteria natychmiastowego ABORT

Przerwij bieżący test i wróć do stanu bezpiecznego, jeżeli wystąpi którekolwiek z poniższych:

- nieoczekiwany niezerowy setpoint;
- wentylator porusza się mimo żądania 0;
- utrata możliwości zatrzymania ręcznego;
- `actuation_supported`, `actuation_authorized` albo `ready` przyjmuje wartość inną niż oczekiwana fail-closed;
- RPM jest sprzeczne z obserwacją fizyczną;
- AERO przechodzi w nieoczekiwany bieg lub alarm;
- silne nad-/podciśnienie, trzaskanie drzwiami, zasysanie spalin/zanieczyszczeń z niepożądanego kierunku;
- szybkie wychłodzenie lub temperatura nawiewu poza założonym zakresem testu;
- telemetria przestaje być wiarygodna;
- sensor lub czas systemowy jest stale/stary;
- RS-485 wykazuje błędy komunikacji podczas planowanego testu;
- operator nie potrafi jednoznacznie określić aktualnego stanu systemu.

FAIL/ABORT jest wynikiem wartościowym — zapisujemy snapshot i przyczynę, nie próbujemy „dokończyć za wszelką cenę”.

## 15. Pierwszy dzień, pierwszy tydzień, dalszy sezon

### Pierwszy dzień

- instalacja i preflight;
- sanity-check sensorów/TACHO/AERO;
- snapshot PRE;
- rozpoczęcie baseline;
- bez strojenia finalnych progów na podstawie pierwszych godzin.

### Pierwsze 48–72 h

- baseline noc/dzień/praca;
- oznaczanie realnych procesów;
- kontrola jakości danych;
- wybór sesji do dalszego replay.

### Pierwszy tydzień

Jeśli baseline jest stabilny:

- `fan_outputs`;
- `aero_outputs`;
- pierwsza iteracja `dynamics`;
- fallback SEN55;
- fallbacki TACHO w kontrolowanych oknach;
- testy Calendar/restart/recovery.

Nie wymuszamy zakończenia grupy, jeżeli tydzień nie przyniósł reprezentatywnych warunków.

### Sezonowo

Parametry termiczne i zachowanie wentylacji muszą zostać ponownie ocenione przy warunkach istotnie innych od tych, w których wykonano commissioning. Szczególnie ważna jest pierwsza realna zima i okres wysokich temperatur. Sezonowy review może skorygować profil, ale każda zmiana wymaga własnego evidence i replay przed promocją.

## 16. Promocja grupy do WORKSHOP_VALIDATED

Grupa może zostać promowana dopiero, gdy:

1. spełniono wszystkie `required_observations` z `config/control-engine-commissioning-plan-v1.json`;
2. wybrano wszystkie pola wymagane przez `config/control-engine-commissioning-candidate-template-v1.json`;
3. istnieje wersjonowany raport lub referencja do telemetrii;
4. wynik został sprawdzony na replay/scenario/matrix, jeśli dotyczy;
5. nie ma otwartego safety blocker związany z daną grupą;
6. wartości zostały zapisane do candidate profile, nie bezpośrednio jako nieudokumentowany runtime tweak.

Dopiero komplet wymaganych poziomów może sprawić, że `ready_for_actuation_preconditions` przestanie być blokowane. To nadal **nie przyznaje authority**.

## 17. Zamknięcie commissioning

Na końcu przygotowujemy jeden finalny pakiet evidence:

- snapshot PRE i POST;
- wypełniona karta sesji dla każdej grupy;
- candidate JSON;
- referencje do telemetryki;
- wykresy/analizy pomocnicze;
- lista wszystkich odchyleń i otwartych problemów;
- zaktualizowany tuning validation ledger na osobnej gałęzi;
- CI/replay dla wybranych wartości;
- osobny raport `WORKSHOP_COMMISSIONING_RESULT_<date>_PL.md`.

`default_runtime_binding` pozostaje `false`, a Control Engine pozostaje SHADOW. Przejście do fizycznego authority jest oddzielnym projektem/stage i nie jest częścią tego dokumentu.
