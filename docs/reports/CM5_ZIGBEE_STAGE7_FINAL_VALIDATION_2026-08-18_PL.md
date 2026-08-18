# CM5 Zigbee Stage 7 — końcowa walidacja gałęzi

Data walidacji: 2026-08-18
Gałąź: `agent/zigbee-stage1`
Tryb stanowiska: sam CM5 + infrastruktura Zigbee; część wykonawcza celowo offline

## Wynik

Stage 7 zakończony wynikiem PASS.

Potwierdzono pełny przepływ:

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

## Git i usługi

- gałąź: `agent/zigbee-stage1`
- HEAD testowany na CM5: `8b44b78dcda17cd2462d1de4052019a22fdf7743`
- working tree: clean
- `ventilation-core.service`: active
- `wvc-web-ui.service`: active
- `mosquitto.service`: active
- `zigbee2mqtt.service`: active

## Stan bezpieczny stanowiska

Część wykonawcza była podczas testu celowo odłączona.

Walidator pracował w trybie:

```bash
--allow-hardware-offline
```

Potwierdzono:

- programowe setpointy `0 V / 0 V`,
- oczekiwany stan `FAULT` wynikający z odłączonego DAC,
- brak traktowania odłączonych DFR0971/SEN55/AERO jako błędu testu Zigbee.

## Sieć Zigbee

- `permit_join=false`
- coordinator type: `ZStack3x0`
- coordinator IEEE: `0x00124b0038aaf159`
- Python `paho-mqtt`: `2.1.0`
- callback API: `CallbackAPIVersion.VERSION2`

## Pełna regresja repozytorium

Uruchomiono pełny zestaw:

```text
Ran 245 tests in 0.159s
OK
full unittest suite: PASS
```

Testy obejmowały także istniejące moduły AERO, DAC, SEN55, TACHO, alerty, Web V2, OTA, telemetrykę i serwisową warstwę sieciową.

## Live end-to-end

Potwierdzono:

```text
web API == web state.zigbee: PASS
settings route/assets: PASS
read-only GUI contract: PASS
direct core mapping: PASS
```

### Nawiew

- rola: `supply`
- friendly name: `temp_nawiew`
- IEEE: `0xa4c13810e66fffff`
- temperatura podczas testu: `29.6 °C`
- bateria: `100 %`
- linkquality: `112`
- messages: `12`
- parse_errors: `0`

### Wywiew

- rola: `extract`
- friendly name: `temp_wywiew`
- IEEE: `0xa4c13810bdedffff`
- temperatura podczas testu: `30.5 °C`
- bateria: `100 %`
- linkquality: `58`
- messages: `12`
- parse_errors: `0`

## Kontrola restartów

Przez cały Stage 7 nie restartowano usług:

```text
ventilation-core PID before/after: 12717 / 12717
wvc-web-ui PID before/after:       13124 / 13124
services untouched: PASS
```

## Zakres bezpieczeństwa

Podczas Stage 7:

- nie otwierano `permit_join`,
- nie publikowano komend MQTT,
- nie wykonywano operacji zapisu Zigbee,
- nie zmieniano alertów,
- nie zmieniano logiki sterowania wentylacją,
- nie restartowano usług,
- nie dotykano `main`.

## Decyzja

Gałąź `agent/zigbee-stage1` jest funkcjonalnie zakończona i zwalidowana na CM5.

Nie należy jej jeszcze scalać bezpośrednio do `main`. Zgodnie z przyjętym workflow następny krok to dokończenie osobnej gałęzi harmonogramów/historii/automatyki, a następnie utworzenie gałęzi integracyjnej i wspólna walidacja obu zakresów przed merge do `main`.
