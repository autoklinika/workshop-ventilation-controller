# Integracja MQTT

## 1. Rola MQTT w systemie

MQTT jest opcjonalnym kanałem integracyjnym i magistralą zdarzeń dla warsztatu. Nie stanowi podstawowego mechanizmu sterowania wentylacją i nie zastępuje Modbus RTU, REST ani kanału aktualizacji na żywo.

Podstawowy podział odpowiedzialności:

```text
Modbus RTU / RS-485  → komunikacja ze sprzętem
REST                 → komendy i odczyty klientów
WebSocket / SSE      → aktualizacje interfejsów na żywo
MQTT                 → telemetria, zdarzenia i integracje zewnętrzne
```

Awaria brokera MQTT, utrata sieci lub wyłączenie modułu MQTT nie może zatrzymywać automatyki ani wpływać na lokalne działanie `ventilation-core`.

## 2. Architektura

```text
                    Web UI / HMI / lokalny ekran
                               │
                         REST / WebSocket
                               │
                       ventilation-core
                    ┌──────────┼──────────┐
                    │          │          │
               Modbus/DAC   Historia   MQTT adapter
                    │                     │
                urządzenia          broker MQTT
                                          │
                           Home Assistant / Node-RED /
                           telefon / inne systemy
```

MQTT jest adapterem wyjściowym rdzenia. Rdzeń publikuje potwierdzony stan domenowy i zdarzenia, a nie surowe ramki RS-485 ani bezpośrednie wartości rejestrów Modbus.

## 3. Główne zastosowania

### 3.1. Telemetria

Publikowanie aktualnego stanu, np.:

- VOC Index,
- PM1.0, PM2.5, PM4 i PM10,
- temperatura i wilgotność,
- ocena jakości powietrza,
- wydajność nawiewu i wyciągu,
- stan rekuperatora,
- bypass,
- alarmy,
- stan filtrów,
- jakość komunikacji urządzeń.

### 3.2. Zdarzenia

Publikowanie ważnych zmian, np.:

- przekroczenie poziomu jakości powietrza,
- automatyczne zwiększenie wentylacji,
- rozpoczęcie i zakończenie BOOST,
- utrata komunikacji z węzłem,
- alarm rekuperatora,
- przypomnienie o filtrze,
- powrót systemu do trybu AUTO.

### 3.3. Integracje zewnętrzne

MQTT może zasilać:

- Home Assistant,
- Node-RED,
- system powiadomień,
- zewnętrzny dashboard,
- archiwizację telemetrii,
- przyszły nadrzędny pulpit całego warsztatu.

## 4. Przykładowa przestrzeń tematów

Przestrzeń tematów powinna być wersjonowana i niezależna od nazw konkretnych urządzeń.

```text
workshop/v1/system/state
workshop/v1/system/health
workshop/v1/system/events

workshop/v1/zones/washing/state
workshop/v1/zones/washing/air-quality
workshop/v1/zones/washing/ventilation
workshop/v1/zones/washing/events

workshop/v1/zones/soldering/state
workshop/v1/zones/soldering/air-quality
workshop/v1/zones/soldering/heat-recovery
workshop/v1/zones/soldering/events
```

Nazwy tematów opisują funkcję i strefę, a nie model SEN55, AERO 4A2, numer rejestru czy kanał DAC.

## 5. Format danych

Preferowany format payloadu to UTF-8 JSON z jednoznacznym znaczeniem pól i jednostek.

Przykład stanu jakości powietrza:

```json
{
  "schema_version": 1,
  "zone": "washing",
  "timestamp": "2026-07-25T19:42:00+02:00",
  "quality": "degraded",
  "voc_index": 210,
  "pm25_ug_m3": 12.0,
  "temperature_c": 22.4,
  "humidity_percent": 48.0,
  "source_health": "ok"
}
```

Przykład zdarzenia domenowego:

```json
{
  "schema_version": 1,
  "event_id": "generated-unique-id",
  "timestamp": "2026-07-25T19:42:05+02:00",
  "zone": "washing",
  "type": "ventilation_boost_started",
  "reason": "voc_index_high",
  "previous_mode": "auto",
  "requested_percent": 80,
  "duration_seconds": 900
}
```

## 6. Retained messages i częstotliwość

- Aktualny stan stref i zdrowie systemu mogą być publikowane jako retained.
- Zdarzenia historyczne nie powinny być retained.
- Telemetrii nie publikujemy szybciej, niż jest to użyteczne.
- Preferowana jest publikacja po istotnej zmianie oraz okresowy heartbeat.
- Ograniczamy duplikaty i nie zalewamy brokera każdą próbką czujnika.

Dokładna częstotliwość zostanie dobrana podczas implementacji i testów.

## 7. Sterowanie przez MQTT

W pierwszym etapie MQTT działa wyłącznie jako kanał publikacji.

Nie wdrażamy schematu:

```text
GUI → MQTT → urządzenie
```

Ewentualne komendy MQTT w przyszłości mogą zostać dopuszczone tylko jako osobny, opcjonalny adapter wejściowy do warstwy aplikacyjnej. Muszą wtedy podlegać tym samym zasadom co REST:

- uwierzytelnienie i autoryzacja,
- walidacja komendy,
- kontrola zakresów,
- rozstrzyganie priorytetów w rdzeniu,
- czasowe wygasanie wymuszeń,
- potwierdzenie wykonania,
- zapis audytowy.

MQTT nigdy nie może omijać domeny ani pisać bezpośrednio do Modbus, DAC lub urządzenia.

## 8. Bezpieczeństwo

Docelowo wymagane są:

- osobne konto brokera dla systemu,
- minimalne uprawnienia ACL,
- brak anonimowego dostępu,
- TLS poza zaufaną, odseparowaną siecią lokalną,
- brak publikowania haseł, kluczy i danych konfiguracyjnych,
- jednoznaczny identyfikator instalacji przy wielu lokalizacjach,
- Last Will and Testament dla stanu dostępności rdzenia.

## 9. Implementacja warstwowa

Przewidywany komponent:

```text
MQTTPublisher
├── mapowanie modeli domenowych na kontrakt MQTT
├── kolejka publikacji
├── reconnect z backoff
├── retained state
├── heartbeat / availability
└── metryki diagnostyczne
```

Komponent implementuje port integracyjny, np. `IEventPublisher` lub `ITelemetryPublisher`. Domena nie zależy od biblioteki MQTT ani od konkretnego brokera.

Przy wyłączonej konfiguracji MQTT wykorzystywana jest implementacja `NullPublisher`, a cały system zachowuje pełną funkcjonalność lokalną.

## 10. Status decyzji

MQTT zostaje przewidziany w architekturze jako opcjonalny moduł integracyjny. Nie jest wymagany do uruchomienia pierwszej działającej wersji systemu, ale kontrakty domenowe i podział warstw muszą umożliwić jego późniejsze dodanie bez przebudowy rdzenia.