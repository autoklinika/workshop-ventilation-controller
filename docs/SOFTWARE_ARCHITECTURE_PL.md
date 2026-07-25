# Architektura oprogramowania

## 1. Decyzja nadrzędna

Oprogramowanie musi być rozwijane warstwowo. Interfejs użytkownika nie może zawierać logiki sterowania ani komunikować się bezpośrednio ze sprzętem.

GUI, panel webowy, HMI, lokalny wyświetlacz, aplikacja mobilna oraz narzędzia serwisowe są niezależnymi klientami wspólnego rdzenia systemu.

Podstawowy kierunek zależności:

```text
Interfejs użytkownika
        ↓
API aplikacyjne
        ↓
Warstwa aplikacyjna
        ↓
Warstwa domenowa
        ↓
Abstrakcja sprzętu
        ↓
Modbus / RS-485 / DAC / Tacho / czujniki
```

Niedozwolony kierunek:

```text
GUI → Modbus → urządzenie
```

## 2. Cele architektury

Architektura ma zapewniać:

- działanie automatyki bez uruchomionego interfejsu użytkownika,
- możliwość restartu lub aktualizacji GUI bez zatrzymywania wentylacji,
- obsługę wielu typów interfejsów jednocześnie,
- identyczne zasady sterowania niezależnie od używanego klienta,
- możliwość podmiany urządzeń bez przebudowy logiki domenowej,
- testowanie rdzenia bez fizycznego sprzętu,
- możliwość użycia symulatorów i atrap urządzeń,
- kontrolę dostępu do operacji serwisowych i wykonawczych,
- stabilny model danych dla przyszłych klientów systemu.

## 3. Warstwy systemu

### 3.1. Warstwa sprzętowa i sterowniki urządzeń

Odpowiada wyłącznie za komunikację z konkretnym sprzętem:

- interfejsy RS-485,
- Modbus RTU,
- DAC 0–10 V,
- wejścia Tacho,
- węzły STM32 + SEN55,
- NANO COLOR 2 / AERO 4A2,
- przyszłe urządzenia wykonawcze i pomiarowe.

Każdy konkretny sterownik powinien implementować interfejs abstrakcyjny, np.:

```text
IAirQualitySensor
IVentilationActuator
IHeatRecoveryUnit
ITachoInput
IDeviceDiagnostics
```

Kod wyższych warstw nie może zależeć od konkretnego modelu czujnika, producenta rekuperatora ani biblioteki Modbus.

### 3.2. Warstwa abstrakcji sprzętu

Normalizuje różne urządzenia do wspólnego modelu funkcjonalnego.

Przykłady:

- odczytaj aktualną jakość powietrza,
- ustaw zadany poziom nawiewu,
- ustaw zadany poziom wyciągu,
- zażądaj czasowego przewietrzania,
- odczytaj stan rekuperatora,
- odczytaj diagnostykę urządzenia.

Warstwa ta odpowiada również za:

- timeouty,
- ponawianie bezpiecznych odczytów,
- walidację zakresów,
- normalizację jednostek,
- raportowanie jakości komunikacji,
- wykrywanie utraty urządzenia.

### 3.3. Warstwa domenowa

Jest właściwym mózgiem systemu. Nie zna szczegółów transportu ani interfejsu użytkownika.

Przewidywane komponenty:

```text
WorkshopController
ZoneController
AirQualityEvaluator
VentilationPolicy
BoostSessionManager
AlarmManager
OverrideManager
DeviceHealthEvaluator
```

Odpowiedzialności domeny:

- stan każdej strefy,
- ocena jakości powietrza,
- tryby AUTO / MANUAL / BOOST,
- histerezy i opóźnienia,
- zasady przewietrzania,
- koordynacja nawiewu i wyciągu,
- alarmy i degradacja działania,
- czasowe wymuszenia,
- automatyczny powrót do poprzedniego trybu,
- generowanie wyjaśnialnych decyzji sterujących.

Warstwa domenowa powinna działać identycznie z prawdziwym sprzętem, symulatorem oraz w testach jednostkowych.

### 3.4. Warstwa aplikacyjna

Koordynuje przypadki użycia systemu i udostępnia operacje klientom.

Przykładowe operacje:

- pobierz stan całego warsztatu,
- pobierz szczegóły strefy,
- uruchom czasowe przewietrzanie,
- anuluj ręczne wymuszenie,
- przełącz tryb strefy,
- pobierz historię,
- potwierdź alarm,
- zmień ustawienia,
- wykonaj dozwolony test serwisowy.

Warstwa aplikacyjna odpowiada za autoryzację operacji, walidację komend, kolejność wykonania i zapis zdarzeń.

### 3.5. Warstwa API

Udostępnia jeden spójny kontrakt wszystkim klientom.

Preferowane kanały:

- HTTP/REST do komend i odczytów,
- WebSocket lub Server-Sent Events do aktualizacji na żywo,
- opcjonalnie MQTT dla integracji automatyki budynkowej,
- lokalne IPC tylko wtedy, gdy będzie rzeczywiście potrzebne.

API musi operować na modelach domenowych, a nie na surowych rejestrach Modbus.

Przykładowe modele:

```text
WorkshopState
ZoneState
AirQualityState
VentilationState
HeatRecoveryState
AlarmState
DeviceHealth
ControlOverride
DecisionEvent
```

Surowe dane techniczne są dostępne jedynie przez kontrolowany interfejs serwisowy.

### 3.6. Warstwa prezentacji

Każdy klient może mieć inny zakres funkcji i sposób prezentacji, ale nie może posiadać własnej logiki sterowania.

Przewidywane klienty:

- pełny interfejs webowy,
- lokalny wyświetlacz HDMI/DSI,
- przemysłowy panel HMI,
- uproszczony ekran ścienny,
- aplikacja mobilna,
- narzędzie serwisowe,
- przyszłe integracje z innymi systemami.

Wszystkie klienty korzystają z tego samego API i widzą ten sam autorytatywny stan systemu.

## 4. Podział procesów

Preferowana architektura wykonawcza na Raspberry Pi:

```text
ventilation-core
├── logika domenowa
├── obsługa urządzeń
├── harmonogramy
├── historia i baza danych
├── alarmy
├── REST API
└── kanał aktualizacji na żywo

web-ui
└── niezależny klient przeglądarkowy

local-ui
└── klient kioskowy lub natywny

service-tools
└── diagnostyka i konfiguracja serwisowa
```

`ventilation-core` musi działać jako usługa systemowa niezależna od obecności wyświetlacza.

## 5. Jedno źródło prawdy

Autorytatywny stan systemu znajduje się w rdzeniu. Klient nie może samodzielnie zakładać, że polecenie zostało wykonane.

Prawidłowy przepływ:

1. klient wysyła komendę,
2. warstwa aplikacyjna ją waliduje,
3. domena podejmuje decyzję,
4. sterownik urządzenia wykonuje operację,
5. rdzeń aktualizuje stan,
6. wszyscy klienci otrzymują potwierdzony stan.

Dzięki temu panel webowy, HMI i lokalny wyświetlacz nie rozjeżdżają się funkcjonalnie.

## 6. Rozszerzalność sprzętowa

Dodanie nowego urządzenia powinno wymagać:

1. implementacji odpowiedniego adaptera sprzętowego,
2. konfiguracji mapowania jego możliwości,
3. ewentualnego rozszerzenia modelu domenowego tylko wtedy, gdy urządzenie wnosi nową funkcję.

Nie należy dodawać warunków typu `if producent == ...` w GUI ani w głównej logice strefy.

Przykładowo inny rekuperator powinien implementować `IHeatRecoveryUnit`, a nie wymuszać przebudowę interfejsu użytkownika.

## 7. Testowalność

Od początku należy zapewnić:

- atrapę każdego urządzenia,
- symulator obu stref,
- testy jednostkowe logiki domenowej,
- testy kontraktowe API,
- testy integracyjne adapterów Modbus,
- scenariusze utraty komunikacji,
- testy powrotu po restarcie,
- testy równoczesnych komend z kilku klientów,
- testy automatycznego wygaśnięcia ręcznych wymuszeń.

GUI nie może być wymagane do walidacji poprawności sterowania.

## 8. Bezpieczeństwo operacyjne

- Awaria klienta nie wpływa na działanie automatyki.
- Utrata sieci nie zatrzymuje lokalnego sterowania.
- Operacje serwisowe wymagają osobnego poziomu uprawnień.
- API nie udostępnia dowolnego zapisu rejestrów Modbus zwykłym klientom.
- Każde wymuszenie ma właściciela, czas rozpoczęcia i termin wygaśnięcia.
- Rdzeń rozstrzyga konflikty pomiędzy automatyką, harmonogramem i sterowaniem ręcznym.
- Po restarcie system odtwarza bezpieczny stan, a nie ostatnią niezweryfikowaną komendę UI.

## 9. Zasada dla interfejsów użytkownika

Interfejs odpowiada za:

- prezentację,
- nawigację,
- zebranie intencji użytkownika,
- lokalne formatowanie danych,
- dostępność i ergonomię.

Interfejs nie odpowiada za:

- obliczanie wydajności wentylacji,
- interpretację progów jakości powietrza,
- kontrolę timeoutów urządzeń,
- utrzymywanie trybu BOOST,
- podejmowanie decyzji awaryjnych,
- bezpośredni zapis Modbus lub DAC.

## 10. Konsekwencja projektowa

Każdy nowy ekran, panel, aplikacja lub integracja musi najpierw korzystać z istniejącego kontraktu aplikacyjnego. Jeżeli potrzebnej funkcji brakuje, rozszerzamy rdzeń i API, a nie omijamy warstw przez bezpośrednie połączenie klienta ze sprzętem.
