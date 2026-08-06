# KAmod Service Wi-Fi — diagnostyka transportu heartbeat Stage 1

Data: 2026-08-06

Gałąź:

```text
agent/kamod-service-wifi-transport-diagnostics
```

Baza:

```text
agent/kamod-service-wifi-heartbeat-stage1
5e6c45804ec001090401c80faf89620c7d6004a3
```

## 1. Powód rozszerzenia

Podczas walidacji CM5 Service Agent wystąpiły dwa powtarzalne przejścia `sensor-node-2` do stanu heartbeat offline. W drugim incydencie agent wykrył wcześniej dwie pojedyncze luki sekwencji, a następnie ponad 35-sekundową przerwę bez zaakceptowanego heartbeat.

Dane CM5 potwierdziły jednocześnie:

- brak restartu ESP32,
- ciągły `boot_id` i uptime,
- utrzymaną asocjację stacji z AP,
- brak globalnej awarii AP i drugiego węzła,
- ciągłość produkcyjnego Modbus RTU.

Sama telemetria CM5 nie rozróżnia jednak dwóch przypadków:

1. `sendto()` na ESP32 zwraca błąd i sekwencja nie rośnie,
2. `sendto()` zwraca sukces, sekwencja rośnie, ale datagram nie dociera do CM5.

## 2. Zakres implementacji

Firmware `0.4.1-stage1` publikuje w uwierzytelnionym heartbeat dodatkowe pola:

```text
heartbeat_send_attempts
heartbeat_send_successes
heartbeat_send_failures
heartbeat_consecutive_send_failures
heartbeat_max_consecutive_send_failures
heartbeat_last_send_error
wifi_disconnect_events
wifi_got_ip_events
wifi_last_disconnect_reason
```

Liczniki są chronione osobnym lockiem krytycznym, ponieważ zdarzenia Wi-Fi są obsługiwane przez event loop, a wysyłanie heartbeat przez osobny task FreeRTOS.

## 3. Semantyka

- `heartbeat_send_attempts` rośnie przed każdym wywołaniem `send_heartbeat()`.
- `heartbeat_send_successes` rośnie po pełnym sukcesie utworzenia, podpisania i wysłania datagramu.
- `heartbeat_send_failures` rośnie dla każdego błędu przygotowania lub wysłania.
- liczniki consecutive/max pokazują serię kolejnych błędów lokalnych.
- `heartbeat_last_send_error` przechowuje ostatni `esp_err_t`; po sukcesie wraca do `ESP_OK`.
- `wifi_disconnect_events` rośnie przy `WIFI_EVENT_STA_DISCONNECTED`.
- `wifi_got_ip_events` rośnie przy `IP_EVENT_STA_GOT_IP`.
- `wifi_last_disconnect_reason` zachowuje reason code ostatniego rozłączenia.

Payload raportuje stan liczników z początku bieżącej próby wysłania. Dzięki temu pierwszy poprawnie dostarczony heartbeat po awarii zawiera wynik poprzednich prób.

## 4. Niezmienniki

Rozszerzenie:

- nie zmienia okresu heartbeat 10 s,
- nie dodaje retry,
- nie podnosi progu offline CM5,
- nie zmienia HMAC, replay protection ani schematu podstawowych pól,
- nie ingeruje w SEN55, Modbus RTU, mapę rejestrów ani watchdog,
- pozostawia packed firmware version `0x0004`, ponieważ rejestr Modbus koduje major/minor; pełny identyfikator tekstowy wynosi `0.4.1-stage1`.

## 5. Kryterium diagnostyczne kolejnego incydentu

Po następnym dropout:

- wzrost `heartbeat_send_failures` oznacza błąd lokalny po stronie ESP32,
- brak wzrostu `heartbeat_send_failures` przy luce `seq` oznacza utratę datagramu po zaakceptowaniu przez lokalny stos,
- wzrost `wifi_disconnect_events` lub `wifi_got_ip_events` wskazuje rozłączenie/reasocjację,
- brak zmian wszystkich powyższych przy braku prób wskazuje zatrzymanie lub opóźnienie taska heartbeat.

## 6. Status

```text
implementacja telemetrii firmware: GOTOWA
zmiana zachowania transportu:      NIE
flash dwóch węzłów:                DO WYKONANIA
kolejny soak:                      PO FLASHU I WALIDACJI
```

Nie wykonywać merge ani nie oznaczać PR jako Ready for Review bez wyraźnego polecenia użytkownika.
