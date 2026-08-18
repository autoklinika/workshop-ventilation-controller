# Zigbee Stage 7 — końcowa walidacja regresyjna gałęzi

## Cel

Stage 7 nie dodaje żadnej funkcjonalności. Jego celem jest końcowe sprawdzenie gałęzi `agent/zigbee-stage1` po zakończeniu integracji koordynatora, dwóch czujników SNZB-02LD, klienta MQTT w `ventilation-core`, Web API oraz widoku `Ustawienia -> Zigbee`.

Walidacja obejmuje cały przepływ:

```text
SNZB-02LD
  -> GW90-POE-Ti / CC2652P
  -> Zigbee2MQTT
  -> Mosquitto 127.0.0.1:1883
  -> ventilation-core
  -> CoreState
  -> GET /api/v1/zigbee
  -> Web V2 / Ustawienia / Zigbee
```

## Zasady

Stage 7:

- nie restartuje `ventilation-core`,
- nie restartuje `wvc-web-ui`,
- nie otwiera `permit_join`,
- nie publikuje żadnych komend MQTT,
- nie zmienia konfiguracji Zigbee2MQTT,
- nie zmienia alertów,
- nie zmienia logiki sterowania wentylacją,
- nie dotyka `main`.

## Tryby sprzętowe

Domyślnie walidator oczekuje normalnego stanu produkcyjnego:

- `mode=STOP`,
- `hardware_ready=true`,
- `output_state_known=true`,
- setpointy `0 V / 0 V`.

Na obecnym stanowisku, gdzie część wykonawcza jest celowo odłączona, należy użyć:

```bash
sudo bash tools/validate_cm5_zigbee_stage7.sh --allow-hardware-offline
```

W tym trybie walidator wymaga:

- setpointów programowych `0 V / 0 V`,
- `mode=FAULT`,
- aktywnego `DAC_COMMUNICATION_LOST`,
- `hardware_ready=false`,
- `output_state_known=false`.

Brak DFR0971, SEN55 i AERO nie jest wtedy błędem walidacji Zigbee.

## Co jest sprawdzane

1. Gałąź Git i czyste drzewo robocze.
2. Aktywność czterech usług: core, Web V2, Mosquitto, Zigbee2MQTT.
3. Niezmienność PID `ventilation-core` i `wvc-web-ui` podczas całego testu.
4. Pełny zestaw testów `unittest` repozytorium.
5. `permit_join=false` i obecność koordynatora Zigbee.
6. Połączenie klienta MQTT w `ventilation-core`.
7. Dokładne mapowanie:
   - `supply -> temp_nawiew -> 0xa4c13810e66fffff`,
   - `extract -> temp_wywiew -> 0xa4c13810bdedffff`.
8. Realne temperatury, baterie, `linkquality`, `messages > 0` i `parse_errors=0`.
9. Zgodność `GET /api/v1/zigbee` z `GET /api/v1/state -> state.zigbee`.
10. Dostępność `/settings` oraz assetów widoku Zigbee.
11. Brak endpointów zapisu Zigbee w kontrakcie Web.

## Kryterium zakończenia

Po wyniku `Stage 7 PASS` gałąź Zigbee można uznać za funkcjonalnie zamkniętą i gotową do późniejszej integracji z pozostałymi gałęziami projektu. Nie oznacza to automatycznego merge do `main`.
