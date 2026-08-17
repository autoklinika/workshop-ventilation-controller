# Zigbee — Stage 1

## Cel

Uruchomienie lokalnej warstwy Zigbee na CM5 bez naruszania stabilnej logiki sterowania wentylacją.

Docelowy przepływ:

```text
urządzenia Zigbee
    -> koordynator USB
    -> Zigbee2MQTT
    -> lokalny broker MQTT
    -> ventilation-core
    -> API
    -> GUI
```

GUI nie komunikuje się bezpośrednio z Zigbee2MQTT ani brokerem MQTT. `ventilation-core` pozostaje warstwą autorytatywną dla aplikacji.

## Zakres gałęzi `agent/zigbee-stage1`

W tej gałęzi implementujemy:

- wykrywanie i diagnostykę koordynatora,
- lokalny broker MQTT,
- Zigbee2MQTT,
- adapter MQTT/Zigbee w `ventilation-core`,
- model urządzeń i ich surowy stan,
- API do odczytu i zarządzania urządzeniami,
- zarządzanie Zigbee w `Ustawienia -> Zigbee`,
- dane diagnostyczne potrzebne później przez system alertów.

Nie implementujemy w tej gałęzi Alert System V2. Zigbee ma jedynie udostępniać fakty, np. `battery`, `linkquality`, `availability`, `last_seen`, stan brokera, Zigbee2MQTT i koordynatora.

## Potwierdzony sprzęt USB

Na CM5 wykryto:

```text
USB-UART: Silicon Labs CP2102N
VID:PID:  10c4:ea60
TTY:      /dev/ttyUSB0
```

Stała ścieżka używana przez konfigurację:

```text
/dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_Controller_822f54682ed0f01198f6423758f97c40-if00-port0
```

Nie używamy `/dev/ttyUSB0` w konfiguracji produkcyjnej, ponieważ numer TTY może zmienić się po restarcie lub dołożeniu kolejnych urządzeń USB.

CP2102N identyfikuje mostek USB-UART, a nie sam układ radiowy Zigbee. Typ adaptera Zigbee zostanie potwierdzony przez Zigbee2MQTT podczas pierwszego kontrolowanego uruchomienia; do tego momentu nie zakładamy `zstack`/`ember` na podstawie samego mostka USB.

## Etapy

1. Preflight CM5 i koordynatora — bez zmian w systemie.
2. Instalacja lokalnego brokera MQTT.
3. Instalacja Zigbee2MQTT i kontrolowany test koordynatora.
4. Potwierdzenie firmware/radia oraz utworzenie docelowej konfiguracji sieci Zigbee.
5. Integracja MQTT z `ventilation-core`.
6. Model urządzeń, API i operacje zarządzania.
7. GUI `Ustawienia -> Zigbee`.
8. Testy regresji istniejącego systemu i przygotowanie do integracji z pozostałymi gałęziami.

## Zasady bezpieczeństwa wdrożenia

- `main` pozostaje nietknięty podczas Stage 1.
- Brak automatycznego fallbacku wpływającego na istniejące sterowanie.
- Awaria MQTT/Zigbee nie może blokować pętli sterowania ani komunikacji z istniejącym hardware.
- Pierwsze uruchomienie Zigbee odbywa się bez sparowanych urządzeń i z kontrolą logów.
- `permit_join` ma być domyślnie wyłączone; otwieramy sieć tylko na żądanie z warstwy zarządzania.
- Broker MQTT jest elementem lokalnym CM5; zewnętrzny dostęp nie jest potrzebny do działania aplikacji.
- Aktywne alerty nie są tworzone w tej gałęzi.

## Pierwszy test

Po synchronizacji gałęzi uruchomić:

```bash
bash tools/zigbee_preflight.sh
```

Skrypt jest wyłącznie diagnostyczny i nie zmienia konfiguracji systemu.
