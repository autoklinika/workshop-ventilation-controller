# Workshop Ventilation Controller — checklista terenowa commissioning

Ta checklista jest skrótem operacyjnym. Szczegóły i kryteria znajdują się w `WORKSHOP_COMMISSIONING_MASTER_PLAN_PL.md`.

## A. Dane sesji

- [ ] `session_id`: ______________________________
- [ ] data / czas start: __________________________
- [ ] operator: __________________________________
- [ ] strefa / pomieszczenie: _____________________
- [ ] main SHA zapisany
- [ ] runtime core SHA zapisany
- [ ] runtime WebGUI SHA zapisany
- [ ] boot ID zapisany
- [ ] snapshot PRE zapisany
- [ ] zakres/referencja telemetryki przygotowana

## B. Gate bezpieczeństwa przed testem

Wszystkie muszą być TAK:

- [ ] `ventilation-core.service` active
- [ ] `wvc-web-ui.service` active
- [ ] WebGUI `:18091/automation` osiągalne
- [ ] WebGUI jest tylko klientem realnego core
- [ ] Control Engine SHADOW
- [ ] `actuation_supported=false`
- [ ] `actuation_authorized=false`
- [ ] `readiness=false`
- [ ] EC supply setpoint = `0.0 V`
- [ ] EC extract setpoint = `0.0 V`
- [ ] brak nieoczekiwanego ruchu wentylatorów
- [ ] operator Control Engine = AUTO
- [ ] tuning ledger zawiera 9 grup
- [ ] runtime binding evidence = false
- [ ] TACHO confirmation = `4.0 s`, jeśli hardware TACHO bez zmian
- [ ] telemetria zapisuje się poprawnie
- [ ] alerty są dostępne

Jeżeli choć jeden punkt jest NIE/UNKNOWN → **STOP**.

## C. Instalacja mechaniczna

- [ ] finalne wentylatory i kanały zamontowane
- [ ] kierunek nawiewu potwierdzony
- [ ] kierunek wyciągu potwierdzony
- [ ] czerpnia/wyrzutnia drożna
- [ ] filtry zamontowane
- [ ] brak luźnych elementów przy wirnikach
- [ ] bramy/drzwi wpływające na bilans zidentyfikowane
- [ ] dostęp serwisowy zachowany

## D. Instalacja elektryczna

- [ ] PE i zabezpieczenia sprawdzone
- [ ] zaciski zasilające sprawdzone
- [ ] 0–10 V i referencja sygnałowa zgodne z projektem
- [ ] supply TACHO przypisane do właściwego kanału
- [ ] extract TACHO przypisane do właściwego kanału
- [ ] 12 V peryferiów sprawdzone
- [ ] po boot CM5 brak samoczynnego startu EC

## E. Komunikacja i sensory

- [ ] SEN55 strefa EC stabilny
- [ ] SEN55 strefa AERO stabilny
- [ ] Zigbee temperatura nawiewu — właściwa rola
- [ ] Zigbee temperatura wywiewu — właściwa rola
- [ ] AERO odpowiada stabilnie
- [ ] RS-485 działa bez błędów
- [ ] nie wykonujemy hot-unplug RS-485
- [ ] zegar CM5 / Europe/Warsaw poprawny

## F. Baseline 48–72 h

- [ ] co najmniej jeden okres nocny
- [ ] co najmniej jeden normalny dzień pracy
- [ ] PM2.5 kompletne
- [ ] VOC kompletne
- [ ] NOx kompletne
- [ ] temperatury kompletne
- [ ] RPM/TACHO kompletne
- [ ] setpointy kompletne
- [ ] decyzje SHADOW kompletne
- [ ] Calendar context kompletny
- [ ] typowe procesy oznaczone
- [ ] otwarcia bram/drzwi zanotowane, jeśli istotne
- [ ] luki danych opisane

## G. 9 grup commissioningowych

### G1. `fan_outputs`

- [ ] małe kroki ręcznego żądania, max +10 pp/krok
- [ ] stabilne RPM dla reprezentatywnych punktów
- [ ] bilans pomieszczenia oceniony
- [ ] wpływ termiczny oceniony
- [ ] reakcja na realny proces oceniona
- [ ] `normal_air_request_pct`
- [ ] `boost_air_request_pct`
- [ ] `high_air_request_pct`
- [ ] `max_air_request_pct`
- [ ] 4 limity termiczne
- [ ] `extract_bias_pct`
- [ ] replay/scenario po wybraniu wartości

### G2. `aero_outputs`

- [ ] każdy używany bieg AERO osiągalny
- [ ] każdy używany bieg stabilny
- [ ] reakcja realnej strefy zapisana
- [ ] `aero_normal_speed`
- [ ] `aero_boost_speed`
- [ ] `aero_high_speed`
- [ ] `aero_max_speed`

### G3. `dynamics`

- [ ] kilka reprezentatywnych zdarzeń z normalnej pracy
- [ ] rise time zapisany
- [ ] peak zapisany
- [ ] decay/recovery zapisany
- [ ] PM hysteresis wybrana
- [ ] VOC hysteresis wybrana
- [ ] NOx hysteresis wybrana
- [ ] temp hysteresis wybrana
- [ ] boost confirmation wybrane
- [ ] minimum hold wybrane
- [ ] boost decay wybrane
- [ ] replay bez chatter

### G4. `fan_sensor_fallback`

- [ ] kandydaci fallback sprawdzeni najpierw przy sprawnym sensorze
- [ ] wpływ na temperaturę oceniony
- [ ] bilans pomieszczenia oceniony
- [ ] fault/recovery wykonany bez hot-unplug RS-485
- [ ] supply fallback wybrany
- [ ] extract fallback wybrany

### G5. `aero_sensor_fallback`

- [ ] kandydat biegu sprawdzony przy sprawnym sensorze
- [ ] fault/recovery wykonany bez hot-unplug RS-485
- [ ] `aero_sensor_fallback_speed` wybrany

### G6. `tacho_confirmation`

- [ ] hardware TACHO od wcześniejszej walidacji NIE zmienił się
- [ ] sanity-check kanał supply poprawny
- [ ] sanity-check kanał extract poprawny
- [ ] brak ruchu przy 0 V
- [ ] brak fałszywych faultów
- [ ] zachowane `4.0 s`

Jeżeli hardware się zmienił → wcześniejsze evidence nie obowiązuje i grupa wymaga ponownej walidacji.

### G7. `tacho_supply_fallback`

- [ ] kontrolowany test supply unavailable/0
- [ ] obserwacja podciśnienia/bilansu
- [ ] wpływ na usuwanie zanieczyszczeń
- [ ] wpływ termiczny
- [ ] jawna procedura recovery
- [ ] własna para supply/extract wybrana

### G8. `tacho_extract_fallback`

- [ ] kontrolowany test extract unavailable/0
- [ ] obserwacja nadciśnienia/bilansu
- [ ] ryzyko migracji zanieczyszczeń ocenione
- [ ] wpływ termiczny
- [ ] jawna procedura recovery
- [ ] własna para supply/extract wybrana

### G9. `tacho_both_fallback`

- [ ] rozróżniono dual fan loss od wspólnej awarii sygnału
- [ ] procedura alarm/recovery opisana
- [ ] real-room response oceniony
- [ ] własna para supply/extract wybrana
- [ ] wynik opisany jako degraded/emergency, nie dowód BHP

## H. Testy systemowe

- [ ] Calendar weekly rule
- [ ] Calendar date exception
- [ ] Calendar persistence po core restart
- [ ] restart WebGUI nie zmienia core state
- [ ] restart core nie restartuje WebGUI
- [ ] operator volatile po core restart wraca AUTO
- [ ] kontrolowany reboot CM5 bez niezamierzonego startu wyjść
- [ ] telemetryka po reboot wraca
- [ ] RTC/host-power zachowują oczekiwany stan
- [ ] alerty widoczne dla bezpiecznie przetestowanych faultów

## I. ABORT — natychmiast STOP, jeżeli

- [ ] pojawił się nieoczekiwany niezerowy setpoint
- [ ] wentylator ruszył mimo 0
- [ ] nie da się pewnie zatrzymać układu
- [ ] authority/readiness przestało być fail-closed
- [ ] TACHO/RPM jest sprzeczne z rzeczywistym ruchem
- [ ] AERO zachowuje się nieprzewidywalnie
- [ ] wystąpiło nieakceptowalne nad-/podciśnienie
- [ ] telemetria jest niewiarygodna
- [ ] RS-485 zaczęło generować błędy
- [ ] operator nie potrafi określić bieżącego stanu

## J. Zamknięcie sesji

- [ ] fizyczne wymuszenia zakończone
- [ ] system wrócił do uzgodnionego stanu bezpiecznego
- [ ] snapshot POST zapisany
- [ ] anomalie opisane
- [ ] zakres surowej telemetrii zapisany
- [ ] candidate values zapisane wyłącznie tam, gdzie są poparte evidence
- [ ] PASS / FAIL / INCOMPLETE nadany dla sesji
- [ ] nic nie nadało Control Engine physical authority
