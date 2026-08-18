# CM5 Zigbee Stage 4 — walidacja integracji MQTT z ventilation-core

Data walidacji: 2026-08-18
Gałąź: `agent/zigbee-stage1`
Tryb: sam CM5, część wykonawcza celowo offline

## Wynik

Stage 4 zakończony wynikiem PASS.

Potwierdzono:

- `ventilation-core.service` aktywny,
- `mosquitto.service` aktywny,
- `zigbee2mqtt.service` aktywny,
- `wvc-web-ui.service` aktywny,
- `permit_join=false`,
- koordynator `ZStack3x0`, IEEE `0x00124b0038aaf159`,
- klient MQTT w `ventilation-core` połączony z brokerem,
- poprawne mapowanie obu czujników,
- brak błędów parsowania wiadomości,
- programowe setpointy wentylatorów pozostały `0 V / 0 V`.

## Zweryfikowane urządzenia

### Nawiew

- rola: `supply`
- friendly name: `temp_nawiew`
- IEEE: `0xa4c13810e66fffff`
- temperatura w teście: `28.6 °C`
- bateria: `100 %`
- linkquality: `76`
- licznik wiadomości w core: `2`
- błędy parsowania: `0`

### Wywiew

- rola: `extract`
- friendly name: `temp_wywiew`
- IEEE: `0xa4c13810bdedffff`
- temperatura w teście: `27.8 °C`
- bateria: `100 %`
- linkquality: `36`
- licznik wiadomości w core: `1`
- błędy parsowania: `0`

## Uwagi dotyczące stanowiska

Podczas tej walidacji fizycznie podłączony był wyłącznie moduł CM5 i infrastruktura Zigbee. DFR0971, SEN55 i AERO były celowo offline. Z tego powodu `ventilation-core` pozostawał w oczekiwanym stanie `FAULT` z `DAC_COMMUNICATION_LOST`; nie traktowano tego jako awarii testu Zigbee.

Instalator Stage 4 obsługuje ten przypadek wyłącznie po jawnym użyciu:

```bash
sudo bash tools/install_cm5_zigbee_core_stage4.sh --allow-hardware-offline
```

Tryb produkcyjny instalatora nadal wymaga potwierdzonego `STOP`, `hardware_ready=true` i `output_state_known=true`.

## Availability

W czasie odczytu z core pole `available` miało wartość `None`. Nie blokuje to Stage 4, ponieważ rzeczywiste wiadomości telemetryczne obu urządzeń zostały odebrane i poprawnie sparsowane. Stan dostępności pozostaje polem opcjonalnym i może być uzupełniony tylko wtedy, gdy Zigbee2MQTT publikuje odpowiednie komunikaty availability.

## Decyzja

Integrację:

```text
Zigbee2MQTT -> Mosquitto -> ventilation-core -> CoreState
```

uznaje się za zwalidowaną. Kolejny etap może budować dedykowany kontrakt Web API, a następnie GUI `Ustawienia -> Zigbee`, bez bezpośredniego dostępu GUI do MQTT.
