# Zigbee Stage 10 — retained telemetry, availability i poprawny wiek danych

## Problem

Po restarcie `ventilation-core` role systemowe Zigbee startowały z pustym stanem i czekały na kolejny raport urządzenia. Dodatkowo GUI pokazywało `Availability: niepublikowane`.

Przyczyny:

1. Zigbee2MQTT ma domyślnie `retain=false` dla wiadomości urządzeń.
2. Availability jest domyślnie wyłączone.
3. Aktualny Zigbee2MQTT publikuje availability jako retained JSON `{"state":"online"}` / `{"state":"offline"}`, podczas gdy poprzedni adapter core akceptował tylko tekst `online` / `offline`.
4. `ZIGBEE_DEVICE_DATA_STALE` liczył wiek od czasu odebrania MQTT przez core. Po odebraniu retained wiadomości po restarcie mogłoby to błędnie odmłodzić stary pomiar.

## Poprawka

### Retained telemetry

Dla ról systemowych:

- `temp_nawiew`,
- `temp_wywiew`,

ustawiamy przez oficjalny request Zigbee2MQTT:

```text
bridge/request/device/options
options.retain=true
```

Dzięki temu kolejny raport urządzenia jest zapisywany przez broker jako retained i po następnym restarcie core jest dostarczany natychmiast po subskrypcji.

### Availability

Włączamy:

```yaml
availability:
  enabled: true
```

przez `bridge/request/options`. Ta opcja wymaga restartu Zigbee2MQTT. Availability jest publikowane jako retained topic:

```text
zigbee2mqtt/<friendly_name>/availability
```

Core obsługuje bieżący JSON Zigbee2MQTT oraz zachowuje kompatybilność z dawnym tekstowym `online/offline`.

### Stale data

`ZIGBEE_DEVICE_DATA_STALE` używa teraz w pierwszej kolejności czasu pomiaru urządzenia:

```text
last_seen
```

a dopiero gdy `last_seen` jest niedostępne lub niepoprawne, używa:

```text
last_message_at
```

Oznacza to, że stary retained pomiar pozostaje widoczny po restarcie core, ale nie jest błędnie traktowany jako świeży.

## Wdrożenie na obecnym CM5

```bash
sudo bash tools/apply_cm5_zigbee_reliability_stage10.sh --allow-hardware-offline
```

Skrypt:

1. sprawdza bezpieczny stan `0 V / 0 V`,
2. uruchamia testy,
3. potwierdza `permit_join=false`,
4. ustawia `retain=true` dla obu czujników,
5. włącza availability,
6. restartuje tylko Zigbee2MQTT, aby zastosować availability,
7. weryfikuje retained availability,
8. prosi oba SNZB-02LD o aktualne `temperature` i `battery`,
9. restartuje core, aby sprawdzić odtworzenie retained state,
10. nie otwiera pairing i nie usuwa urządzeń.

Jeżeli śpiący czujnik nie odpowie na `/get`, skrypt może pokazać `WAITING_FOR_FIRST_RETAINED_REPORT`. Wtedy wystarczy raz wybudzić/ogrzać czujnik. Następny raport zostanie zapisany jako retained i kolejne restarty core nie będą już powodowały pustej karty.

## Źródła projektowe

Implementacja została zweryfikowana względem bieżącej dokumentacji Zigbee2MQTT: `Device Availability`, `Devices and Groups`, `MQTT Topics and Messages` oraz strony urządzenia `SONOFF SNZB-02LD`.
