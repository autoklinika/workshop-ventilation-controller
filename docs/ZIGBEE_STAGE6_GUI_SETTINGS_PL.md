# Zigbee Stage 6 — Web V2 `Ustawienia -> Zigbee`

## Cel

Stage 6 dodaje do Web V2 widok diagnostyczny `Ustawienia -> Zigbee` oparty wyłącznie na autorytatywnym API z Stage 5:

```text
GET /api/v1/zigbee
```

Przepływ danych pozostaje bez zmian:

```text
SNZB-02LD
  -> Zigbee2MQTT
  -> Mosquitto
  -> ventilation-core
  -> /api/v1/zigbee
  -> Web V2 / Ustawienia / Zigbee
```

GUI nie łączy się bezpośrednio z MQTT ani Zigbee2MQTT.

## Zakres widoku

Widok pokazuje:

- stan połączenia MQTT widziany przez `ventilation-core`,
- adres lokalnego brokera,
- liczbę urządzeń,
- sumę błędów parsowania,
- dla każdego czujnika:
  - rolę `NAWIEW` / `WYWIEW`,
  - `friendly_name`,
  - IEEE,
  - topic,
  - temperaturę,
  - baterię,
  - `linkquality`,
  - `availability`,
  - `last_seen`,
  - czas odebrania wiadomości przez core,
  - licznik wiadomości i błędów parsowania.

Jeżeli Zigbee2MQTT nie publikuje osobnego stanu `availability`, GUI nie nazywa urządzenia `OFFLINE`. Przy odebranej telemetrii pokazuje `TELEMETRIA AKTYWNA`, a surowe pole availability jako `niepublikowane`.

## Zasady bezpieczeństwa

Stage 6 jest tylko do odczytu. Nie dodaje:

- `permit_join`,
- parowania,
- usuwania urządzeń,
- zmiany nazw urządzeń,
- sterowania Zigbee,
- bezpośredniego dostępu do MQTT,
- zmian alertów,
- zmian sterowania wentylacją.

## Routing Web V2

Dodano trasę:

```text
/settings
```

Pozycja `USTAWIENIA` w lewym pasku Web V2 staje się aktywna i prowadzi do sekcji Zigbee. `SERWIS` pozostaje wyłączony.

## Walidacja CM5

Po synchronizacji gałęzi:

```bash
sudo bash tools/validate_cm5_zigbee_gui_stage6.sh
```

Walidator:

1. sprawdza aktywne usługi,
2. zapisuje PID `ventilation-core`,
3. uruchamia test kontraktu Stage 6,
4. restartuje tylko `wvc-web-ui.service`,
5. sprawdza `/settings`, `zigbee-settings.js` i `zigbee-settings.css`,
6. odczytuje realne dane z `/api/v1/zigbee`,
7. potwierdza mapowanie obu czujników i brak błędów parsowania,
8. sprawdza, że PID `ventilation-core` się nie zmienił.

## Następny etap

Po walidacji Stage 6 można zdecydować, czy w tej samej sekcji mają pojawić się później funkcje zarządzania urządzeniami. Nie są one częścią obecnego etapu i wymagają osobnego projektu kontraktu zapisu oraz zabezpieczeń.
