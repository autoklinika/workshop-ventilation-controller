# CM5 Web GUI + Manual Control — Stage 1

Data rozpoczęcia: 2026-08-11  
Status: **IMPLEMENTATION / przed walidacją na docelowym CM5**  
Baza: `main` @ `e689a991f9e71bf77f1771ca2cec31cd9b5716f6`

## 1. Cel

Dodać pierwszy widoczny interfejs operatorski systemu Workshop Ventilation Controller bez uruchamiania automatyki jakości powietrza.

GUI ma być jednym responsywnym interfejsem webowym przeznaczonym równocześnie dla przeglądarki na komputerze, telefonu/tabletu i przyszłego lokalnego panelu dotykowego działającego w trybie kiosk. Stage 1 jest świadomie **manual-only**.

## 2. Granica architektoniczna

```text
browser / kiosk
      ↓ HTTP
wvc-web-ui.service
      ↓ Unix socket JSON
ventilation-core
      ↓
DAC / SENSOR BUS / AERO BUS
```

`wvc-web-ui` nie otwiera `/dev/ttyAMA0`, `/dev/ttyAMA4`, I²C ani DFR0971, nie implementuje Modbus RTU i nie posiada własnego autorytatywnego stanu. GUI wysyła tylko intencje użytkownika, a stan wykonany pochodzi z `ventilation-core`.

## 3. Wąski kontrakt HTTP

Dozwolone endpointy wykonawcze:

```text
POST /api/v1/manual/fans
POST /api/v1/manual/stop
POST /api/v1/manual/aero/speed
POST /api/v1/manual/aero/airing
```

Odczyt:

```text
GET /api/v1/state
GET /api/v1/config
GET /api/v1/health
```

Nie istnieje endpoint przekazujący dowolne pole `command` do core. Web nie wystawia `shutdown` ani surowego interfejsu serwisowego.

Walidacja na granicy web:

- DAC: `0.0 V` albo `1.0..10.0 V`,
- AERO speed: integer `0..3`,
- AERO airing: boolean.

Ostateczna walidacja i wykonanie nadal należą do `ventilation-core`.

## 4. Dashboard operatorski

### Strefa 1 — Mycie i wygrzewanie ECU

Widoczne są PM2.5, PM10, VOC Index, NOx Index, temperatura i wilgotność. Sterowanie obejmuje osobno nawiew i wyciąg 0–10 V oraz wyraźny wspólny STOP `0.0 V / 0.0 V`. Aktualne setpointy są pobierane z `CoreState`.

### Strefa 2 — Pomieszczenie lutowania

Widoczne są dane SEN55 oraz AERO: fan 1, fan 2, temperatura nawiewu, wywiewu, zewnętrzna i wilgotność. Sterowanie obejmuje speed `0/1/2/3` oraz airing ON/OFF. GUI uwzględnia `control_busy` i pokazuje `last_control_result`, w tym wynik fizycznego potwierdzenia.

## 5. Panel dotykowy

Frontend jest touch-first:

- duże pola dotykowe,
- brak funkcji wymagających hover,
- dwie kolumny na dużym ekranie i jedna na mniejszym,
- zwiększone cele dotykowe dla `pointer: coarse`,
- brak zależności od natywnej aplikacji panelu.

Docelowy panel może uruchamiać zwykłą przeglądarkę w trybie kiosk i otwierać lokalny URL CM5.

## 6. Konfiguracja mapowania stref

Usługa obsługuje:

```text
WVC_WEB_ZONE1_NAME
WVC_WEB_ZONE1_SENSOR_ADDRESS
WVC_WEB_ZONE2_NAME
WVC_WEB_ZONE2_SENSOR_ADDRESS
```

Domyślnie:

```text
zone 1 -> slave 1 -> Mycie i wygrzewanie ECU
zone 2 -> slave 2 -> Pomieszczenie lutowania
```

Przed produkcyjną walidacją należy potwierdzić fizyczne przypisanie obu obudów. W razie potrzeby wystarczy zmiana konfiguracji web, bez firmware.

## 7. Proces i systemd

Jednostka:

```text
deploy/systemd/wvc-web-ui.service
```

Proces pracuje jako `wentylacja:wentylacja`, korzysta tylko z Unix socketu core i nie posiada `Requires=ventilation-core.service`. Brak core ma być widoczny w GUI, ale nie powoduje awarii samej usługi web.

Implementacja używa wyłącznie biblioteki standardowej Pythona. Nie dodaje frameworka webowego do zależności runtime.

Domyślny port: `8088/tcp`.

## 8. Bezpieczeństwo sieciowe Stage 1

Stage 1 jest przeznaczony do kontrolowanej walidacji w zaufanej sieci warsztatowej. Nie należy wystawiać portu do Internetu ani wykonywać port-forwardingu z WAN.

Pierwsza wersja nie implementuje jeszcze kont użytkowników ani TLS. Przed udostępnieniem interfejsu w niezaufanej sieci należy dodać uwierzytelnianie i HTTPS/reverse proxy. Granica sprzętowa pozostaje jednak zachowana: klient HTTP nigdy nie otrzymuje bezpośredniego dostępu do Modbus, UART ani DAC.

## 9. Walidacja programowa przed publikacją

Nowe testy obejmują:

- `status` jako jedyne źródło stanu,
- ręczne DAC przez istniejący `set`,
- odrzucenie dead-band i wartości poza zakresem,
- STOP bez wystawienia `shutdown`,
- AERO speed tylko `0..3`,
- airing tylko boolean,
- brak generic command proxy,
- poprawne raportowanie odrzucenia przez core,
- web health przy niedostępnym core,
- publiczną konfigurację stref z `automation_enabled=false` i `ai_control_enabled=false`,
- kontrakt systemd i konfiguracji CM5.

Lokalna walidacja nowych testów przed publikacją: `13/13 PASS`.

Dodatkowo wykonano `node --check static/app.js` oraz test HTTP z fake core dla HTML/CSS/JS, `/api/v1/config`, `/api/v1/state` i manual fans — PASS.

Pełny istniejący zestaw testów repozytorium musi zostać wykonany przez GitHub Actions i następnie na CM5 przed instalacją produkcyjnej jednostki.

## 10. Poza zakresem

Stage 1 nie dodaje AUTO, ECO, BOOST, progów PM/VOC/NOx, histerez, harmonogramów, automatycznych sekwencji AERO, sterowania z AI, MQTT control, historii ani wykresów. AI pozostaje advisory-only.

## 11. Następna walidacja na CM5

Po przejściu CI należy:

1. przełączyć checkout na gałąź Stage 1 bez restartu `ventilation-core`,
2. wykonać pełne testy lokalne,
3. uruchomić web UI ręcznie na porcie testowym,
4. sprawdzić dashboard z rzeczywistymi slave 1 i 2,
5. potwierdzić przypisanie czujników do stref,
6. wykonać kontrolowane ustawienie DAC z GUI i powrót do STOP,
7. wykonać AERO `0→1→0`,
8. wykonać airing `ON→OFF`,
9. potwierdzić obsługę `control_busy`,
10. potwierdzić brak regresji SENSOR BUS, AERO BUS i DAC,
11. dopiero potem zainstalować i włączyć `wvc-web-ui.service`.

Nie restartować `ventilation-core` tylko po to, aby uruchomić GUI. Web UI jest osobnym klientem istniejącego Unix socketu.
