# Dwukanałowa komunikacja z węzłami pomiarowymi

## 1. Cel

Każdy węzeł pomiarowy SEN55 + KAmod ESP32 POW RS485 korzysta z dwóch niezależnych kanałów komunikacyjnych:

- RS-485 Modbus RTU jako kanału produkcyjnego,
- prywatnego Wi-Fi CM5 jako kanału serwisowego.

Rozdzielenie kanałów zwiększa odporność systemu na awarie i pozwala precyzyjniej diagnozować utratę komunikacji.

## 2. Kanał produkcyjny — RS-485

RS-485 jest jedynym kanałem wykorzystywanym do bieżącej pracy systemu. Przenosi:

- pomiary SEN55,
- status jakości i świeżości pomiaru,
- diagnostykę podstawową węzła,
- dane wymagane przez deterministyczną logikę `ventilation-core`.

Wi-Fi nie zastępuje Modbus RTU i nie jest używane do podstawowego sterowania ani przesyłania produkcyjnej telemetrii.

## 3. Kanał serwisowy — prywatne Wi-Fi CM5

Wi-Fi służy wyłącznie do:

- OTA firmware,
- provisioningu,
- heartbeatów,
- diagnostyki serwisowej,
- odczytu wersji firmware,
- pobierania lokalnego bufora zdarzeń,
- zdalnego restartu węzła w trybie serwisowym,
- odczytu parametrów takich jak uptime, RSSI i temperatura ESP32.

Kanał serwisowy nie może posiadać funkcji bezpośredniego sterowania wentylacją, zapisu DAC ani wykonywania poleceń Modbus wobec innych urządzeń.

## 4. Heartbeat węzła

Każdy KAmod cyklicznie przesyła do CM5 komunikat diagnostyczny zawierający co najmniej:

- `node_id`,
- wersję firmware,
- uptime,
- stan SEN55,
- czas od ostatniego poprawnego pomiaru,
- liczbę zapytań Modbus odebranych w ostatnim okresie,
- czas od ostatniego zapytania Modbus,
- RSSI Wi-Fi,
- przyczynę ostatniego restartu,
- stan OTA,
- liczniki błędów I²C i RS-485.

Przykład logiczny:

```json
{
  "node_id": "sensor-zone-1",
  "firmware": "1.2.0",
  "uptime_s": 483721,
  "sen55_status": "OK",
  "last_measurement_age_ms": 120,
  "modbus_requests_last_minute": 0,
  "last_modbus_request_age_s": 72,
  "wifi_rssi_dbm": -58,
  "ota_state": "READY"
}
```

Heartbeat jest informacją serwisową. Jego brak nie wpływa na podstawową pracę Modbus RTU.

## 5. Diagnostyka krzyżowa

CM5 interpretuje stan obu kanałów łącznie:

| RS-485 | Wi-Fi | Interpretacja |
|---|---|---|
| działa | działa | węzeł pracuje prawidłowo |
| nie działa | działa | prawdopodobny problem z RS-485, przewodem, terminacją lub interfejsem master |
| działa | nie działa | problem kanału serwisowego Wi-Fi; automatyka działa normalnie |
| nie działa | nie działa | możliwy brak zasilania, awaria KAmod albo całkowita utrata łączności |

Brak zapytań Modbus widziany przez KAmod nie jest samodzielnym dowodem uszkodzenia kabla. Dopiero korelacja:

- timeoutów Modbus po stronie CM5,
- działającego heartbeatu Wi-Fi,
- prawidłowego stanu SEN55,
- braku odebranych zapytań Modbus po stronie KAmod

pozwala oznaczyć awarię magistrali jako najbardziej prawdopodobną.

## 6. Lokalny bufor zdarzeń

KAmod przechowuje ograniczony, cykliczny bufor ostatnich zdarzeń, obejmujący między innymi:

- start i restart firmware,
- rozpoczęcie i zatrzymanie pomiarów SEN55,
- błędy I²C,
- utratę i odzyskanie Wi-Fi,
- rozpoczęcie, wynik i rollback OTA,
- długi brak zapytań Modbus,
- przepełnienie liczników błędów,
- aktywację watchdoga.

Po odzyskaniu Wi-Fi CM5 może pobrać bufor i dołączyć zdarzenia do centralnego dziennika diagnostycznego.

## 7. Reakcja systemu

Utrata RS-485 pozostaje zdarzeniem deterministycznym wykrywanym przez CM5. `ventilation-core` przechodzi wtedy do wcześniej zdefiniowanej strategii bezpiecznej dla braku świeżych danych.

Wi-Fi może jedynie wzbogacić diagnozę. Nie może zmieniać reakcji bezpieczeństwa ani dostarczać zastępczych pomiarów do logiki sterowania.

Utrata Wi-Fi powoduje wyłącznie niedostępność OTA i funkcji serwisowych. Odczyty Modbus RTU oraz automatyka pozostają aktywne.

## 8. Zasady bezpieczeństwa

- węzły nie mają dostępu do Internetu ani sieci warsztatowej,
- ruch Wi-Fi jest ograniczony zaporą CM5 do niezbędnych usług lokalnych,
- zdalny restart wymaga uwierzytelnienia i jest rejestrowany,
- OTA wykorzystuje obrazy A/B z walidacją i rollbackiem,
- Wi-Fi nie udostępnia operacji sterujących urządzeniami wykonawczymi,
- awaria jednego kanału nie może blokować działania drugiego.

## 9. Widok serwisowy

Panel serwisowy CM5 powinien prezentować dla każdego węzła co najmniej:

- stan RS-485,
- stan Wi-Fi,
- stan SEN55,
- czas ostatniego pomiaru,
- czas ostatniego zapytania Modbus,
- firmware i uptime,
- RSSI,
- przyczynę ostatniego restartu,
- status OTA,
- aktywną diagnozę krzyżową.

Dokument rozwija zasady opisane w `SYSTEM_ARCHITECTURE_PL.md` i decyzji D-043 w `DECISIONS_PL.md`.